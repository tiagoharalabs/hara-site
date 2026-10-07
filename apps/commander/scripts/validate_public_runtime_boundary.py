#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src"/"worker.js").read_text(encoding="utf-8")
HTML=(APP/"public"/"index.html").read_text(encoding="utf-8")
JS=(APP/"public"/"app.js").read_text(encoding="utf-8")
LINUX=(APP/"public/agent/linux.py").read_text(encoding="utf-8")
WINDOWS=(APP/"public/agent/windows.ps1").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit(f"COMMANDER_PUBLIC_RUNTIME_{code}=FAIL")
    print(f"COMMANDER_PUBLIC_RUNTIME_{code}=PASS")

need('"/api/portal/activity?limit=50' not in JS,"NO_CLOUD_ACTIVITY_FETCH")
need('fetch("/api/portal/slo"' not in JS,"NO_CLOUD_SLO_FETCH")
need('data-slo-ack' not in HTML and 'data-slo-escalate' not in HTML,"NO_PUBLIC_SLO_ACTIONS")
need('INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT' in WORKER,"DIAGNOSTIC_ROUTES_DISABLED")
scheduled=WORKER.split("async scheduled(",1)[1].split("};",1)[0]
need("runSloAlertMaintenance(env)" not in scheduled,"NO_PUBLIC_SLO_CRON")
heartbeat=WORKER.split("async function heartbeatDevice",1)[1].split("async function markDeviceOffline",1)[0]
need("activity_summary_json" not in heartbeat and "activity_summary_at_utc" not in heartbeat,"NO_ACTIVITY_SNAPSHOT_PERSIST")
need("DEVICE_HEARTBEAT_PERSIST_SECONDS = 120" in WORKER,"HEARTBEAT_WRITE_THROTTLE")
need("DEVICE_ONLINE_GRACE_SECONDS = 240" in WORKER,"ONLINE_GRACE")
need("customer_activity_detail_persisted: false" in heartbeat,"PRIVACY_ATTESTATION")
recent_calls=WORKER.split("async function recentCustomerCalls",1)[1].split("function portalActivitySource",1)[0]
need(
    'payload_json' not in recent_calls
    and 'result_json' not in recent_calls
    and 'command_json' not in recent_calls
    and 'argv' not in recent_calls
    and 'if (toolId === "hara.calls.recent")' in WORKER,
    "REMOTE_HISTORY_METADATA_ONLY",
)
need('id="internalBetaDiagnostics"' not in HTML and "DIAGNÓSTICO LOCAL · BETA" not in HTML,"NO_PUBLIC_BETA_DIAGNOSTICS")
need("removido da versão final" not in HTML,"NO_PUBLIC_INTERNAL_REMOVAL_COPY")
need('if (next === "usage") loadUsageActivity();' not in JS,"NO_PUBLIC_USAGE_ACTIVITY_LOAD")
need('O Commander na nuvem mantém apenas o mínimo necessário' in HTML,"PUBLIC_PRIVACY_COPY")
need('AGENT_VERSION = "0.3.40"' in LINUX,"LINUX_SIGNED_AGENT_UNCHANGED")
need('$AgentVersion = "0.3.40"' in WINDOWS,"WINDOWS_SIGNED_AGENT_UNCHANGED")
print("COMMANDER_PUBLIC_RUNTIME_BOUNDARY=PASS")
