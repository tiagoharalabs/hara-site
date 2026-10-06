#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
APP_JS = (APP / "public" / "app.js").read_text(encoding="utf-8")
HTML = (APP / "public" / "index.html").read_text(encoding="utf-8")
M26 = (APP / "migrations" / "0026_slo_incidents.sql").read_text(encoding="utf-8")
M27 = (APP / "migrations" / "0027_slo_incident_ack_escalation.sql").read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SLO_ACTIONS_{code}=FAIL")
    print(f"COMMANDER_SLO_ACTIONS_{code}=PASS")


for column in (
    "acknowledged_at_utc",
    "acknowledged_by_subject_id",
    "escalation_level",
    "escalated_at_utc",
):
    need(column in M27, "MIGRATION_" + column.upper())
need("idx_commander_slo_incidents_open_escalation" in M27, "MIGRATION_INDEX")

need("portalAcknowledgeSloIncident" in WORKER, "ACK_HANDLER")
need("portalEscalateSloIncident" in WORKER, "ESCALATE_HANDLER")
need('"/api/portal/slo/ack"' in WORKER, "ACK_ROUTE")
need('"/api/portal/slo/escalate"' in WORKER, "ESCALATE_ROUTE")
need("requirePortalMutationOrigin(request)" in WORKER, "ORIGIN_GUARD")
need("enforcePortalMutationRateLimit(env,session)" in WORKER, "RATE_LIMIT")
need("SLO_STATUS_ADMIN_REQUIRED" in WORKER, "ADMIN_GUARD")
need("COALESCE(acknowledged_at_utc,?)" in WORKER, "ACK_IDEMPOTENT")
need("escalation_level < ? THEN ? ELSE escalation_level END" in WORKER, "ESCALATION_MONOTONIC")

need("SLO_ALERT_ESCALATION_L1_SECONDS = 60 * 60" in WORKER, "AUTO_L1_1H")
need("SLO_ALERT_ESCALATION_L2_SECONDS = 4 * 60 * 60" in WORKER, "AUTO_L2_4H")
need("SLO_ALERT_ESCALATION_L3_SECONDS = 12 * 60 * 60" in WORKER, "AUTO_L3_12H")
need("targetLevel=ageSeconds >= SLO_ALERT_ESCALATION_L3_SECONDS" in WORKER, "AUTO_ESCALATION_WIRED")

need("data-slo-ack" in HTML and "data-slo-escalate" in HTML, "UI_ACTIONS")
need('mutateSloIncident("ack")' in APP_JS, "UI_ACK_WIRED")
need('mutateSloIncident("escalate",next)' in APP_JS, "UI_ESCALATE_WIRED")
need("acknowledged_at_utc" in APP_JS and "escalation_level" in APP_JS, "UI_STATE")
need("app.js?v=20261006-slosem1" in HTML, "CACHE_KEY")

with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
    db = sqlite3.connect(tmp.name)
    db.executescript(
        """
        PRAGMA foreign_keys=OFF;
        CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY);
        """
    )
    db.executescript(M26)
    db.executescript(M27)
    cols = {row[1] for row in db.execute("PRAGMA table_info(commander_slo_incidents)")}
    need(
        {
            "acknowledged_at_utc",
            "acknowledged_by_subject_id",
            "escalation_level",
            "escalated_at_utc",
        }.issubset(cols),
        "MIGRATION_SMOKE",
    )
    indexes = {row[1] for row in db.execute("PRAGMA index_list(commander_slo_incidents)")}
    need("idx_commander_slo_incidents_open_escalation" in indexes, "INDEX_SMOKE")

print("COMMANDER_SLO_INCIDENT_ACTIONS=PASS")
