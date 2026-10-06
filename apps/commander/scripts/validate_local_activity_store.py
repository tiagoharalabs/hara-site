#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import runpy
import sqlite3
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
AGENT = APP / "public" / "agent" / "linux.py"
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
MIGRATION = (APP / "migrations" / "0022_device_local_activity_snapshot.sql").read_text(encoding="utf-8")
PORTAL = (APP / "public" / "app.js").read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit("COMMANDER_LOCAL_ACTIVITY_" + code + "=FAIL")
    print("COMMANDER_LOCAL_ACTIVITY_" + code + "=PASS")


# Legacy cloud columns may still exist until the explicit purge runs, but the
# public product must not ingest, render, or schedule activity/SLO diagnostics.
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE commander_devices (device_id TEXT PRIMARY KEY)")
db.executescript(MIGRATION)
columns = {row[1] for row in db.execute("PRAGMA table_info(commander_devices)")}
need({"activity_summary_json", "activity_summary_at_utc"}.issubset(columns), "LEGACY_CLOUD_COLUMNS_KNOWN")
need("payload_json" not in MIGRATION and "result_json" not in MIGRATION, "CLOUD_RAW_CONTENT_ABSENT")
heartbeat = WORKER.split("async function heartbeatDevice",1)[1].split("async function markDeviceOffline",1)[0]
need("cleanAgentActivitySnapshots" not in WORKER, "NO_HEARTBEAT_SANITIZER_NEEDED")
need("activity_summary_json" not in heartbeat and "activity_summary_at_utc" not in heartbeat, "NO_CLOUD_ACTIVITY_WRITE")
need("customer_activity_detail_persisted: false" in heartbeat, "CLOUD_DETAIL_FALSE")
need('INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT' in WORKER, "PUBLIC_DIAGNOSTIC_ROUTES_DISABLED")
need('id="activityTotal"' not in (APP / "public" / "index.html").read_text(encoding="utf-8"), "PUBLIC_ACTIVITY_UI_ABSENT")

# Exercise Linux local SQLite store in an isolated XDG-like root.
ns = runpy.run_path(str(AGENT))
agent_globals = ns["append_console_event"].__globals__
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    agent_globals["DATA_DIR"] = root
    agent_globals["OPERATIONS_DB_FILE"] = root / "operations.sqlite3"
    agent_globals["CONSOLE_EVENTS_FILE"] = root / "console-events.jsonl"

    legacy = {
        "schema": "hara.commander-console-event.v1",
        "at_utc": "2099-01-01T00:00:00+00:00",
        "event": "PASS",
        "state": "COMPLETED",
        "tool_id": "hara.ping",
        "function_id": "device.ping",
        "request_id": "legacy-local",
        "error_code": None,
        "receipt_sha256": None,
        "approval_id": None,
        "action_summary": None,
        "duration_ms": 5,
        "transport_mode": "LOCAL_MCP",
    }
    agent_globals["CONSOLE_EVENTS_FILE"].write_text(
        json.dumps(legacy, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    call = {
        "call_id": "local-call",
        "request_id": "local-request",
        "tool_id": "hara.process.run",
        "payload": {"command": "printf local-first", "timeout_ms": 3000},
        "_transport": "LOCAL_MCP",
    }
    ns["append_console_event"](
        "PASS",
        call,
        state="COMPLETED",
        duration_ms=17,
        receipt_sha256="a" * 64,
    )

    snap = ns["local_activity_snapshot"]("7d", limit=20, include_events=True)
    need(snap["source"] == "LOCAL_SQLITE", "SQLITE_SOURCE")
    need(snap["privacy"]["local_authoritative"] is True, "LOCAL_AUTHORITY")
    need(snap["privacy"]["cloud_history_persisted"] is False, "CLOUD_HISTORY_FALSE")
    need(snap["summary"]["total_calls"] >= 1, "SUMMARY_COUNT")
    need(any(x.get("tool_id") == "hara.process.run" for x in snap["events"]), "TOOL_ID_SHAPE")
    need(any("process.run" in str(x.get("action_summary") or "") for x in snap["events"]), "LOCAL_ACTION_SUMMARY")

    with sqlite3.connect(agent_globals["OPERATIONS_DB_FILE"]) as local_db:
        cols = {row[1] for row in local_db.execute("PRAGMA table_info(activity_events)")}
        need("payload_json" not in cols and "result_json" not in cols, "LOCAL_RAW_PAYLOAD_COLUMNS_ABSENT")
        migrated = local_db.execute(
            "SELECT COUNT(*) FROM activity_events WHERE request_id='legacy-local'"
        ).fetchone()[0]
        need(migrated == 1, "JSONL_MIGRATION_ONCE")

    mode = stat.S_IMODE(agent_globals["OPERATIONS_DB_FILE"].stat().st_mode)
    need(mode == 0o600, "SQLITE_MODE_0600")

    recent = ns["_local_recent_events"](20, tool="hara.process.run", window="7d")
    need(recent["source"] == "LOCAL_SQLITE", "LOCAL_MCP_ACTIVITY_SOURCE")
    need(recent["detail_location"] == "LOCAL_DEVICE", "LOCAL_MCP_DETAIL_LOCATION")
    need(recent["cloud_history_persisted"] is False, "LOCAL_MCP_ZERO_CLOUD_HISTORY")

print("COMMANDER_LOCAL_ACTIVITY_STORE=PASS")
