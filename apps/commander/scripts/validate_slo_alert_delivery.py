#!/usr/bin/env python3
from __future__ import annotations
import sqlite3, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src"/"worker.js").read_text()
M26=(APP/"migrations"/"0026_slo_incidents.sql").read_text()
M27=(APP/"migrations"/"0027_slo_incident_ack_escalation.sql").read_text()
M29=(APP/"migrations"/"0029_slo_alert_deliveries.sql").read_text()

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SLO_ALERT_DELIVERY_{code}=FAIL")
    print(f"COMMANDER_SLO_ALERT_DELIVERY_{code}=PASS")

for token in [
    "commander_slo_alert_deliveries","delivery_key","event_type","attempt_count",
    "next_attempt_at_utc","last_error_code","idx_commander_slo_alert_delivery_pending"
]:
    need(token in M29, "MIGRATION_"+token.upper())

for token in [
    "queueSloAlertDelivery","deliverPendingSloAlerts","SLO_ALERT_WEBHOOK_URL",
    "SLO_ALERT_WEBHOOK_SECRET","x-hara-signature","HMAC","OPENED","ESCALATED","RESOLVED",
    "state='RETRY'","state='DELIVERED'","https:"
]:
    need(token in WORKER, "WORKER_"+token.upper().replace("-","_").replace("'",""))

need("command_content_included:false" in WORKER, "PRIVACY_COMMAND")
need("payload_content_included:false" in WORKER, "PRIVACY_PAYLOAD")
need("result_content_included:false" in WORKER, "PRIVACY_RESULT")
need("customer_content_included:false" in WORKER, "PRIVACY_CUSTOMER")
need("await deliverPendingSloAlerts(env);" in WORKER, "CRON_ORDER")
need("INSERT OR IGNORE INTO commander_slo_alert_deliveries" in WORKER, "IDEMPOTENT_OUTBOX")

with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
    db=sqlite3.connect(tmp.name)
    db.executescript("""
      PRAGMA foreign_keys=OFF;
      CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY);
      CREATE TABLE users (subject_id TEXT PRIMARY KEY);
      CREATE TABLE commander_devices (device_id TEXT PRIMARY KEY);
    """)
    db.executescript(M26)
    db.executescript(M27)
    db.executescript(M29)
    cols={r[1] for r in db.execute("PRAGMA table_info(commander_slo_alert_deliveries)")}
    need({"delivery_key","payload_json","state","attempt_count","delivered_at_utc"}.issubset(cols),"MIGRATION_SMOKE")

print("COMMANDER_SLO_ALERT_DELIVERY=PASS")
