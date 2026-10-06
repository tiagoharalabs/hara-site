#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
HTML=(APP/"public/index.html").read_text(encoding="utf-8")
JS=(APP/"public/app.js").read_text(encoding="utf-8")
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")
LINUX=(APP/"public/agent/linux.py").read_text(encoding="utf-8")
WINDOWS=(APP/"public/agent/windows.ps1").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit(f"COMMANDER_PRODUCT_BOUNDARY_{code}=FAIL")
    print(f"COMMANDER_PRODUCT_BOUNDARY_{code}=PASS")

for forbidden in [
    "internalBetaDiagnostics",
    "SLO interno",
    "Taxa de sucesso local",
    "Duração média local",
    "Transporte local",
    "Detalhes avançados",
    "activityTopTools",
    "activityTopErrors",
    "usageLedger",
]:
    need(forbidden not in HTML,"UI_NO_"+re.sub(r"[^A-Z0-9]+","_",forbidden.upper()).strip("_"))

need('if (next === "usage") loadUsageActivity();' not in JS,"UI_NO_ACTIVITY_FETCH")
need('O Commander na nuvem mantém apenas o mínimo necessário' in HTML,"UI_PRIVACY_COPY")

for route in [
    "/api/portal/activity",
    "/api/portal/slo",
    "/api/portal/slo/ack",
    "/api/portal/slo/escalate",
]:
    marker=f'url.pathname === "{route}"'
    pos=WORKER.find(marker)
    need(pos>=0,"ROUTE_PRESENT_"+route.replace("/","_").upper())
    excerpt=WORKER[pos:pos+240]
    need("INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT" in excerpt and ",404" in excerpt,
         "ROUTE_DISABLED_"+route.replace("/","_").upper())

scheduled=WORKER[WORKER.find("async scheduled("):]
need("runSloAlertMaintenance(env)" not in scheduled,"NO_PRODUCT_SLO_CRON")
need("cleanAgentActivitySnapshots" not in WORKER,"NO_CLOUD_ACTIVITY_INGEST")
need("activitySnapshotNumber" not in WORKER,"NO_CLOUD_ACTIVITY_SANITIZER")
need("activity_summary_json = CASE" not in WORKER,"NO_HEARTBEAT_ACTIVITY_WRITE")
need("DEVICE_HEARTBEAT_PERSIST_SECONDS = 120" in WORKER,"HEARTBEAT_PERSIST_120S")
need("DEVICE_ONLINE_GRACE_SECONDS = 240" in WORKER,"ONLINE_GRACE_240S")
need("customer_activity_detail_persisted: false" in WORKER,"HEARTBEAT_DETAIL_FALSE")

hb=WORKER[WORKER.find("async function heartbeatDevice"):WORKER.find("async function markDeviceOffline")]
need("body.activity_snapshots" not in hb and "cleanAgentActivitySnapshots(" not in hb,"HEARTBEAT_IGNORES_ACTIVITY_SNAPSHOTS")
need("persistCutoff" in hb and "metadataChanged" in hb,"HEARTBEAT_COALESCED_WRITE")

linux_hb=LINUX[LINUX.find('/api/device/heartbeat')-300:LINUX.find('/api/device/heartbeat')+700]
windows_hb=WINDOWS[WINDOWS.find('/api/device/heartbeat')-300:WINDOWS.find('/api/device/heartbeat')+700]
linux_minimal="activity_snapshots" not in linux_hb
windows_minimal="activity_snapshots" not in windows_hb
print("COMMANDER_PRODUCT_BOUNDARY_LINUX_HEARTBEAT_MINIMAL="+("PASS" if linux_minimal else "PENDING_SIGNED_AGENT_ROLLOUT"))
print("COMMANDER_PRODUCT_BOUNDARY_WINDOWS_HEARTBEAT_MINIMAL="+("PASS" if windows_minimal else "PENDING_SIGNED_AGENT_ROLLOUT"))
need("body.activity_snapshots" not in hb and "cleanAgentActivitySnapshots(" not in hb,"LEGACY_AGENT_DETAIL_REJECTED_BY_CLOUD")

need("def local_activity_snapshot" in LINUX and "OPERATIONS_DB_FILE" in LINUX,"LINUX_DETAIL_LOCAL")
need("Get-LocalActivityWindow" in WINDOWS and "LocalActivity" in WINDOWS,"WINDOWS_DETAIL_LOCAL")
need('"customer_content_included":False' in LINUX,"LINUX_SUPPORT_NO_CUSTOMER_CONTENT")
need('"command_content_included":False' in LINUX,"LINUX_SUPPORT_NO_COMMAND_CONTENT")
need('"result_content_included":False' in LINUX,"LINUX_SUPPORT_NO_RESULT_CONTENT")

print("COMMANDER_PRODUCT_BOUNDARY=PASS")
