#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import runpy
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
LINUX_PATH = APP / "public" / "agent" / "linux.py"
LINUX = LINUX_PATH.read_text(encoding="utf-8")
WINDOWS = (APP / "public" / "agent" / "windows.ps1").read_text(encoding="utf-8")
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
PORTAL = (APP / "public" / "app.js").read_text(encoding="utf-8")
PROBE = (APP / "scripts" / "commander_operational_slo.py").read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SLO_FAILURE_SEMANTICS_{code}=FAIL")
    print(f"COMMANDER_SLO_FAILURE_SEMANTICS_{code}=PASS")


for source, label in ((LINUX, "LINUX"), (WINDOWS, "WINDOWS")):
    need("CLIENT_ACTION" in source and "POLICY" in source and "SERVICE" in source, label + "_CLASSES")
    need("HTTP_400" in source and "FILENOTFOUNDERROR" in source, label + "_CLIENT_CODES")
    need("LOCAL_OPERATOR_APPROVAL_DENIED" in source and "APPROVAL_TIMEOUT" in source, label + "_POLICY_CODES")
    need("availability_success_rate_percent" in source, label + "_AVAILABILITY_RATE")
    need("service_failed" in source and "client_failed" in source and "policy_failed" in source, label + "_COUNTERS")

need("summary.service_failed == null ? summary.failed : summary.service_failed" in WORKER, "LEGACY_FAIL_CLOSED")
need("weighted_availability_success_rate_percent" in WORKER, "TENANT_AVAILABILITY_RATE")
need("weighted_outcome_success_rate_percent" in WORKER, "TENANT_OUTCOME_RATE")
need("% disponibilidade" in PORTAL, "PORTAL_LABEL")
need("weighted_availability_success_rate_percent" in PROBE, "PROBE_AVAILABILITY")
need("weighted_outcome_success_rate_percent" in PROBE, "PROBE_OUTCOME")
need('"success_metric":"availability_success_rate_percent"' in LINUX, "LINUX_METRIC_DECLARED")
need('success_metric="availability_success_rate_percent"' in WINDOWS, "WINDOWS_METRIC_DECLARED")
need('success_metric:"availability_success_rate_percent"' in WORKER, "WORKER_METRIC_DECLARED")

ns = runpy.run_path(str(LINUX_PATH))
with tempfile.TemporaryDirectory(prefix="hara-slo-semantics-") as td:
    root = Path(td)
    globals_map = ns["local_activity_snapshot"].__globals__
    globals_map["DATA_DIR"] = root
    globals_map["OPERATIONS_DB_FILE"] = root / "operations.sqlite3"
    globals_map["CONSOLE_EVENTS_FILE"] = root / "console-events.jsonl"
    globals_map["STATUS_FILE"] = root / "runtime-status.json"
    globals_map["SESSION_FILE"] = root / "operator-session.json"
    globals_map["RECEIPT_DIR"] = root / "receipts"

    now = datetime.now(timezone.utc).isoformat()

    def insert(event: str, state: str, idx: int, duration: int | None, error: str | None) -> None:
        with ns["_ops_connect"]() as db:
            db.execute(
                """INSERT INTO activity_events
                   (at_utc,event,state,tool_id,function_id,request_id,error_code,
                    receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    now, event, state, "hara.ping", "device.ping", f"REQ-{idx}", error,
                    hashlib.sha256(f"receipt-{idx}".encode()).hexdigest(),
                    None, None, duration, "LOCAL_STDIO",
                ),
            )
            db.commit()

    for i in range(25):
        insert("PASS", "COMPLETED", i, 500, None)

    expected_client = (
        "HTTP_400",
        "FILENOTFOUNDERROR",
        "EDIT_MATCH_AMBIGUOUS",
        "PROCESS_SESSION_EXITED",
    )
    for offset, code in enumerate(expected_client, start=100):
        insert("DENIED", "FAILED", offset, 100, code)
    insert("DENIED", "FAILED", 200, 100, "LOCAL_OPERATOR_APPROVAL_DENIED")

    snap = ns["local_activity_snapshot"]("24h", limit=10, include_events=False)
    summary = snap["summary"]
    slo = snap["slo"]

    need(summary["completed"] == 25, "DYNAMIC_COMPLETED")
    need(summary["failed"] == 5, "DYNAMIC_RAW_FAILED")
    need(summary["client_failed"] == 4, "DYNAMIC_CLIENT_FAILED")
    need(summary["policy_failed"] == 1, "DYNAMIC_POLICY_FAILED")
    need(summary["service_failed"] == 0, "DYNAMIC_SERVICE_ZERO")
    need(summary["success_rate_percent"] == 83.3, "DYNAMIC_RAW_OUTCOME")
    need(summary["availability_success_rate_percent"] == 100.0, "DYNAMIC_AVAILABILITY")
    need(slo["status"] == "PASS", "DYNAMIC_EXPECTED_ERRORS_DO_NOT_BREACH")

    insert("DENIED", "FAILED", 300, 100, "RUNTIME_ERROR")
    snap2 = ns["local_activity_snapshot"]("24h", limit=10, include_events=False)
    summary2 = snap2["summary"]
    need(summary2["service_failed"] == 1, "DYNAMIC_UNKNOWN_COUNTS_SERVICE")
    need(summary2["availability_success_rate_percent"] == 96.2, "DYNAMIC_SERVICE_AVAILABILITY_DROP")
    need(snap2["slo"]["status"] == "DEGRADED", "DYNAMIC_SERVICE_FAILURE_BREACH")

print("COMMANDER_SLO_FAILURE_SEMANTICS=PASS")
