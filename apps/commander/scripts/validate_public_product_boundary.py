#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src"/"worker.js").read_text(encoding="utf-8")
SIMPLE=(APP/"src"/"customer-mcp-simple.mjs").read_text(encoding="utf-8")
HTML=(APP/"public"/"index.html").read_text(encoding="utf-8")
JS=(APP/"public"/"app.js").read_text(encoding="utf-8")
LINUX=(APP/"public"/"agent"/"linux.py").read_text(encoding="utf-8")
WINDOWS=(APP/"public"/"agent"/"windows.ps1").read_text(encoding="utf-8")
CONTRACT=(APP/"src"/"device-tool-contract.mjs").read_text(encoding="utf-8")

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_PUBLIC_BOUNDARY_{code}=FAIL")
    print(f"COMMANDER_PUBLIC_BOUNDARY_{code}=PASS")

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--ga",action="store_true")
    args=ap.parse_args()

    need('"/api/portal/activity?limit=50' not in JS,"NO_CLOUD_ACTIVITY_UI_FETCH")
    need('fetch("/api/portal/slo"' not in JS,"NO_CLOUD_SLO_UI_FETCH")
    need('data-slo-ack' not in HTML and 'data-slo-escalate' not in HTML,"NO_PUBLIC_SLO_ACTIONS")
    need('INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT' in WORKER,"CLOUD_DIAGNOSTIC_ROUTES_DISABLED")
    scheduled=WORKER.split("async scheduled(",1)[1].split("};",1)[0]
    need("runSloAlertMaintenance(env)" not in scheduled,"NO_PUBLIC_SLO_CRON")

    heartbeat=WORKER.split("async function heartbeatDevice",1)[1].split("async function markDeviceOffline",1)[0]
    need("activity_summary_json" not in heartbeat and "activity_summary_at_utc" not in heartbeat,"NO_ACTIVITY_SNAPSHOT_PERSIST")
    need("customer_activity_detail_persisted: false" in heartbeat,"HEARTBEAT_PRIVACY_ATTESTATION")
    need("DEVICE_HEARTBEAT_PERSIST_SECONDS = 120" in WORKER,"HEARTBEAT_WRITE_THROTTLE")
    need("DEVICE_ONLINE_GRACE_SECONDS = 240" in WORKER,"ONLINE_GRACE_MATCHES_THROTTLE")

    linux_heartbeat=LINUX.split('if now-last_heartbeat>=30:',1)[1].split('if now-last_product_lease',1)[0]
    windows_heartbeat=WINDOWS.split('if (((Get-Date)-$LastHeartbeat).TotalSeconds -ge 30)',1)[1].split('try {',1)[0]
    need("activity_snapshots" not in linux_heartbeat,"LINUX_NO_ACTIVITY_UPLOAD")
    need("activity_snapshots" not in windows_heartbeat,"WINDOWS_NO_ACTIVITY_UPLOAD")

    need('"hara.activity.local"' in SIMPLE and '"hara.calls.recent.local"' in SIMPLE,"SIMPLE_HISTORY_LOCAL_ROUTING")
    need("DEVICE_LOCAL_ACTIVITY_TOOLS" in CONTRACT,"LOCAL_ACTIVITY_DEVICE_CONTRACT")
    need('if (toolId === "hara.activity") toolId = "hara.activity.local";' in WORKER,"LEGACY_ACTIVITY_LOCAL_TRANSLATION")
    need('if (toolId === "hara.calls.recent") toolId = "hara.calls.recent.local";' in WORKER,"LEGACY_RECENT_LOCAL_TRANSLATION")

    need('id="internalBetaDiagnostics"' in HTML and "DIAGNÓSTICO LOCAL · BETA" in HTML,"BETA_LOCAL_DIAGNOSTICS_MARKED")
    need("Somente para desenvolvimento" in HTML and "removido da versão final" in HTML,"GA_REMOVAL_COPY")
    need('LOCAL_ACTIVITY_ORIGIN + "/v1/activity' in JS,"LOCALHOST_ACTIVITY_SOURCE")
    need('diagnosticsPanel.hidden=!localOnly' in JS,"LOCAL_ONLY_DIAGNOSTIC_RENDER")

    # Relay content is transport-only: payload is redacted at claim and result
    # is redacted after status retrieval.
    claim=WORKER.split("async function claimNextDeviceCall",1)[1].split("async function completeDeviceCall",1)[0]
    status=WORKER.split("async function deviceCallStatus",1)[1].split("async function dispatchTransientDeviceCall",1)[0]
    need("SET payload_json = ?" in claim and "redactedDeviceCallContent" in claim,"RELAY_PAYLOAD_HOT_REDACTION")
    need("SET result_json = ?" in status and "redactedDeviceCallContent" in status,"RELAY_RESULT_HOT_REDACTION")

    beta_present='id="internalBetaDiagnostics"' in HTML
    if args.ga and beta_present:
        raise SystemExit("COMMANDER_PUBLIC_BOUNDARY_GA_BETA_DIAGNOSTICS_REMOVAL=FAIL")
    print("COMMANDER_PUBLIC_BOUNDARY_GA_BETA_DIAGNOSTICS_REMOVAL="+("PENDING" if beta_present else "PASS"))
    print("COMMANDER_PUBLIC_PRODUCT_BOUNDARY=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
