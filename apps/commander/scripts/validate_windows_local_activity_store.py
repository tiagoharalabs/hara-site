#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
WINDOWS=(APP/"public/agent/windows.ps1").read_text(encoding="utf-8")
MANIFEST=(APP/"public/release/agent-manifest.json").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit("COMMANDER_WINDOWS_LOCAL_ACTIVITY_"+code+"=FAIL")
    print("COMMANDER_WINDOWS_LOCAL_ACTIVITY_"+code+"=PASS")

need('$AgentVersion = "0.3.41"' in WINDOWS,"AGENT_VERSION")
need('$OperationsDb = Join-Path $Root "operations.sqlite3"' in WINDOWS,"DB_PATH")
need('DllImport("winsqlite3.dll"' in WINDOWS,"NATIVE_WINSQLITE")
need("sqlite3_open16" in WINDOWS and "sqlite3_prepare16_v2" in WINDOWS,"PARAMETERIZED_SQLITE_API")
need("sqlite3_bind_text16" in WINDOWS and "sqlite3_bind_int64" in WINDOWS,"PARAMETER_BINDINGS")
need("CREATE TABLE IF NOT EXISTS activity_events" in WINDOWS,"ACTIVITY_TABLE")
need("payload_json" not in WINDOWS[WINDOWS.index("CREATE TABLE IF NOT EXISTS activity_events"):WINDOWS.index("function Write-LocalActivityEvent")],"RAW_PAYLOAD_COLUMN_ABSENT")
need("result_json" not in WINDOWS[WINDOWS.index("CREATE TABLE IF NOT EXISTS activity_events"):WINDOWS.index("function Write-LocalActivityEvent")],"RAW_RESULT_COLUMN_ABSENT")
need("console_events_jsonl_v1" in WINDOWS,"JSONL_MIGRATION_MARKER")
need("Get-LocalActivityWindow" in WINDOWS and 'source="LOCAL_SQLITE"' in WINDOWS,"LOCAL_SNAPSHOT_SOURCE")
need("Get-LocalActivityHeartbeatSnapshot" in WINDOWS,"HEARTBEAT_SNAPSHOT_BUILDER")
heartbeat=WINDOWS.split('Send-Json "$($Cfg.base_url)/api/device/heartbeat"',1)[1].split("20 | Out-Null",1)[0]
need("activity_snapshots" not in heartbeat,"HEARTBEAT_DOES_NOT_UPLOAD_ACTIVITY")
need("customer_content_synced=$false" in WINDOWS,"CLOUD_CONTENT_FALSE")
need("action_summary_local_only=$true" in WINDOWS,"ACTION_SUMMARY_LOCAL_ONLY")
need("Protect-LocalCommandPreview" in WINDOWS and "<redacted>" in WINDOWS,"COMMAND_REDACTION")
need("COMMANDER_WINDOWS_LOCAL_ACTIVITY_SQLITE=PASS" in WINDOWS,"SELFTEST_SQLITE")
need("COMMANDER_WINDOWS_LOCAL_ACTIVITY_RAW_CONTENT=ABSENT" in WINDOWS,"SELFTEST_RAW_CONTENT")
need("COMMANDER_WINDOWS_LOCAL_ACTIVITY_SNAPSHOT_PRIVACY=PASS" in WINDOWS,"SELFTEST_SNAPSHOT_PRIVACY")
need('"agent_version": "0.3.41"' in MANIFEST,"MANIFEST_VERSION")
print("COMMANDER_WINDOWS_LOCAL_ACTIVITY_STORE=PASS")
