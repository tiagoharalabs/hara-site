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
need('id="internalBetaDiagnostics"' in HTML and "DIAGNÓSTICO LOCAL · BETA" in HTML,"BETA_DIAGNOSTICS_MARKED")
need("removido da versão final" in HTML,"GA_REMOVAL_COPY")
need('LOCAL_ACTIVITY_ORIGIN + "/v1/activity' in JS,"LOCAL_DIAGNOSTICS_SOURCE")
need('diagnosticsPanel.hidden=!localOnly' in JS,"LOCAL_ONLY_RENDER")
need('AGENT_VERSION = "0.3.40"' in LINUX,"LINUX_SIGNED_AGENT_UNCHANGED")
need('$AgentVersion = "0.3.40"' in WINDOWS,"WINDOWS_SIGNED_AGENT_UNCHANGED")
print("COMMANDER_PUBLIC_RUNTIME_BOUNDARY=PASS")
