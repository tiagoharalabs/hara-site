#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
MIG = (APP / "migrations" / "0026_slo_incidents.sql").read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SLO_INCIDENT_{code}=FAIL")
    print(f"COMMANDER_SLO_INCIDENT_{code}=PASS")


need("CREATE TABLE commander_slo_state" in MIG, "STATE_TABLE")
need("CREATE TABLE commander_slo_incidents" in MIG, "INCIDENT_TABLE")
need("idx_commander_slo_incidents_tenant_state" in MIG, "TENANT_INDEX")
need("idx_commander_slo_incidents_resolved" in MIG, "RETENTION_INDEX")
need("CHECK (state IN ('PASS','DEGRADED','INSUFFICIENT_DATA'))" in MIG, "STATE_CONSTRAINT")
need("CHECK (state IN ('OPEN','RESOLVED'))" in MIG, "INCIDENT_CONSTRAINT")

need('SLO_ALERT_PROFILE = "INTERNAL_BETA_V1"' in WORKER, "PROFILE")
need("SLO_ALERT_BREACH_STREAK = 2" in WORKER, "BREACH_HYSTERESIS")
need("SLO_ALERT_RECOVERY_STREAK = 2" in WORKER, "RECOVERY_HYSTERESIS")
need("SLO_ALERT_INCIDENT_RETENTION_SECONDS = 90 * 24 * 60 * 60" in WORKER, "RETENTION_90D")
need("evaluateTenantSloRows" in WORKER, "EVALUATOR")
need("missing || stale || degraded" in WORKER, "DATA_GAP_DEGRADED")
need('breach >= SLO_ALERT_BREACH_STREAK' in WORKER, "OPEN_AFTER_STREAK")
need('recovery >= SLO_ALERT_RECOVERY_STREAK' in WORKER, "RESOLVE_AFTER_STREAK")
need("runSloAlertMaintenance(env)" in WORKER, "MAINTENANCE")
need('ctx.waitUntil(runSloAlertMaintenance(env));' in WORKER, "CRON_WIRED")
need('url.pathname === "/api/portal/slo"' in WORKER, "PORTAL_ROUTE")
need('SLO_STATUS_ADMIN_REQUIRED' in WORKER, "PORTAL_ADMIN_GATE")
need('url.pathname === "/api/dev/slo-maintenance"' in WORKER, "DEV_CANARY_ROUTE")
need("await requireMcpProductToken(request, env);" in WORKER, "DEV_CANARY_AUTH")
need("payload_json" not in MIG.lower() and "result_json" not in MIG.lower(), "NO_CUSTOMER_CONTENT_SCHEMA")

# Migration smoke test.
db = sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE tenants (
  tenant_id TEXT PRIMARY KEY,
  display_name TEXT,
  state TEXT,
  environment TEXT,
  created_at_utc TEXT
);
""")
db.executescript(MIG)
db.execute("INSERT INTO tenants VALUES ('T1','Tenant','ACTIVE','DEV','2026-10-05T00:00:00Z')")
db.execute(
    """INSERT INTO commander_slo_state
       (tenant_id,profile,state,breach_streak,recovery_streak,current_incident_id,
        last_evaluated_at_utc,last_snapshot_at_utc,summary_json,updated_at_utc)
       VALUES ('T1','INTERNAL_BETA_V1','PASS',0,0,NULL,
               '2026-10-05T00:00:00Z','2026-10-05T00:00:00Z','{}','2026-10-05T00:00:00Z')"""
)
db.execute(
    """INSERT INTO commander_slo_incidents
       (incident_id,tenant_id,profile,state,opened_at_utc,resolved_at_utc,
        first_breach_at_utc,last_breach_at_utc,last_seen_at_utc,summary_json,
        resolution_json,updated_at_utc)
       VALUES ('I1','T1','INTERNAL_BETA_V1','OPEN','2026-10-05T00:00:00Z',NULL,
               '2026-10-05T00:00:00Z','2026-10-05T00:00:00Z',
               '2026-10-05T00:00:00Z','{}',NULL,'2026-10-05T00:00:00Z')"""
)
need(db.execute("SELECT state FROM commander_slo_state WHERE tenant_id='T1'").fetchone() == ("PASS",), "MIGRATION_STATE_READ")
need(db.execute("SELECT state FROM commander_slo_incidents WHERE incident_id='I1'").fetchone() == ("OPEN",), "MIGRATION_INCIDENT_READ")
indexes = {row[1] for row in db.execute("PRAGMA index_list('commander_slo_incidents')")}
need("idx_commander_slo_incidents_tenant_state" in indexes, "MIGRATION_INDEX_READ")

# Deterministic policy model.
def transition(prev_state, breach, recovery, incident_open, observed):
    if observed == "DEGRADED":
        breach = breach + 1 if prev_state == "DEGRADED" else 1
        recovery = 0
        if not incident_open and breach >= 2:
            incident_open = True
    elif observed == "PASS":
        breach = 0
        recovery = recovery + 1 if incident_open else 0
        if incident_open and recovery >= 2:
            incident_open = False
            recovery = 0
    else:
        breach = 0
        recovery = 0
    return observed, breach, recovery, incident_open

state, b, r, opened = "PASS", 0, 0, False
state, b, r, opened = transition(state, b, r, opened, "DEGRADED")
need((b, opened) == (1, False), "FIRST_BREACH_NO_INCIDENT")
state, b, r, opened = transition(state, b, r, opened, "DEGRADED")
need((b, opened) == (2, True), "SECOND_BREACH_OPENS")
state, b, r, opened = transition(state, b, r, opened, "PASS")
need((r, opened) == (1, True), "FIRST_RECOVERY_KEEPS_OPEN")
state, b, r, opened = transition(state, b, r, opened, "PASS")
need((r, opened) == (0, False), "SECOND_RECOVERY_RESOLVES")

print("COMMANDER_SLO_INCIDENT_STATE=PASS")
