#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src/worker.js").read_text()
FULL=(APP/"src/customer-mcp.mjs").read_text()
SIMPLE=(APP/"src/customer-mcp-simple.mjs").read_text()

def need(ok, code):
    if not ok:
        raise SystemExit(f"COMMANDER_MCP_PROD_RUNTIME_{code}=FAIL")
    print(f"COMMANDER_MCP_PROD_RUNTIME_{code}=PASS")

history=WORKER.split("async function productTransactionHistory",1)[1].split("async function dashboardForSubject",1)[0]
recent=WORKER.split("async function recentCustomerCalls",1)[1].split("function portalActivitySource",1)[0]

need('detail_level: "AGGREGATE_ONLY"' in history, "AGGREGATE_HISTORY")
need('tool_id' not in history and 'payload_json' not in history and 'result_json' not in history, "AGGREGATE_HISTORY_NO_DIAGNOSTICS")
need('if (toolId === "hara.activity")' in WORKER and 'const activity=await portalActivity(' in WORKER, "ACTIVITY_ADMITTED")
need('if (toolId === "hara.calls.recent")' in WORKER and 'const calls = await recentCustomerCalls(env, context, args);' in WORKER, "RECENT_CALLS_ADMITTED")
need('payload_json' not in recent and 'result_json' not in recent and 'command_json' not in recent and 'argv' not in recent, "RECENT_CALLS_METADATA_ONLY")
need('if (code === "DEVICE_OFFLINE")' in FULL and 'state: "UNAVAILABLE"' in FULL, "FULL_OFFLINE_OPERATIONAL")
need('if (code === "DEVICE_OFFLINE")' in SIMPLE and 'state: "UNAVAILABLE"' in SIMPLE, "SIMPLE_OFFLINE_OPERATIONAL")
need('category: "DEVICE_AVAILABILITY"' in FULL and 'category: "DEVICE_AVAILABILITY"' in SIMPLE, "OFFLINE_CATEGORY")
need('retryable: true' in FULL and 'retryable: true' in SIMPLE, "OFFLINE_RETRYABLE")
need('"get_activity"' in SIMPLE and '"get_recent_tool_calls"' in SIMPLE, "SIMPLE_24_SURFACE_PRESERVED")
print("COMMANDER_MCP_PROD_RUNTIME_CONTRACT=PASS")
