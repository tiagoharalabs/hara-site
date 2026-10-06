#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
MIG = (APP / "migrations" / "0028_support_reports.sql").read_text(encoding="utf-8")
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SUPPORT_PLANE_{code}=FAIL")
    print(f"COMMANDER_SUPPORT_PLANE_{code}=PASS")


need("CREATE TABLE IF NOT EXISTS commander_support_reports" in MIG, "TABLE")
need("idx_commander_support_reports_tenant_time" in MIG, "TENANT_INDEX")
need("idx_commander_support_reports_device_time" in MIG, "DEVICE_INDEX")
need("idx_commander_support_reports_expiry" in MIG, "EXPIRY_INDEX")
need("report_json TEXT NOT NULL" in MIG, "SANITIZED_JSON_COLUMN")
need("payload_json" not in MIG and "result_json" not in MIG and "command_text" not in MIG, "NO_RAW_COLUMNS")

need("SUPPORT_REPORT_RETENTION_SECONDS = 30 * 24 * 60 * 60" in WORKER, "RETENTION_30D")
need("SUPPORT_REPORT_RETENTION_BATCH = 500" in WORKER, "RETENTION_BATCH")
need("SUPPORT_REPORT_MAX_BYTES = 16 * 1024" in WORKER, "MAX_16K")
need("function cleanSupportReportV2" in WORKER, "SANITIZER")
need('privacy[key] !== false' in WORKER, "PRIVACY_FAIL_CLOSED")
need("recent_receipt_sha256:receipts" in WORKER and ".slice(0,10)" in WORKER, "RECEIPT_BOUND")
need("SUPPORT_REPORT_DEVICE_NOT_FOUND" in WORKER, "DEVICE_TENANT_BINDING")
need("WHERE device_id=? AND tenant_id=? AND state='ACTIVE'" in WORKER, "DEVICE_SCOPE")
need("WHERE tenant_id=? AND device_id=?" in WORKER, "LIST_SCOPE_DEVICE")
need("WHERE support_report_id=? AND tenant_id=?" in WORKER, "DELETE_SCOPE")
need('url.pathname === "/api/portal/support-reports"' in WORKER, "PORTAL_ROUTE")
need('url.pathname === "/api/portal/support-reports/delete"' in WORKER, "DELETE_ROUTE")
need("requirePortalMutationOrigin(request)" in WORKER, "MUTATION_ORIGIN")
need("SUPPORT_REPORT_ADMIN_REQUIRED" in WORKER, "ADMIN_GATE")
need("cleanupExpiredSupportReports(env)" in WORKER, "RETENTION_CRON")
need("ORDER BY expires_at_utc LIMIT ?" in WORKER, "BOUNDED_PURGE")

db = sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys=ON")
db.executescript(
    """
    CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY);
    CREATE TABLE users (subject_id TEXT PRIMARY KEY);
    CREATE TABLE commander_devices (device_id TEXT PRIMARY KEY);
    """
)
db.executescript(MIG)
cols = {row[1] for row in db.execute("PRAGMA table_info(commander_support_reports)")}
need(
    {
        "support_report_id", "tenant_id", "subject_id", "device_id", "report_json",
        "submitted_at_utc", "expires_at_utc", "slo_status"
    }.issubset(cols),
    "DYNAMIC_SCHEMA",
)
indexes = {row[1] for row in db.execute("PRAGMA index_list(commander_support_reports)")}
need("idx_commander_support_reports_expiry" in indexes, "DYNAMIC_EXPIRY_INDEX")

print("COMMANDER_SUPPORT_PLANE=PASS")
