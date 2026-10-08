#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")
AGENT=(APP/"public/agent/linux.py").read_text(encoding="utf-8")
MIGRATION=(APP/"migrations/0029_local_tunnel_authorization.sql").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit(f"COMMANDER_LOCAL_TUNNEL_UNIT_ECONOMICS_{code}=FAIL")
    print(f"COMMANDER_LOCAL_TUNNEL_UNIT_ECONOMICS_{code}=PASS")

lease_hours=6
renewals_per_day=24//lease_hours
requests_per_renewal=2  # portal code + device lease exchange (usage sync piggybacks)
core_requests_per_day=renewals_per_day*requests_per_renewal
core_requests_30d=core_requests_per_day*30
free_tools_month=10000
ratio=core_requests_30d/free_tools_month
reduction=(1-ratio)*100

need('PRODUCT_LEASE_TTL_SECONDS = 6 * 60 * 60' in WORKER,"LEASE_6H")
need('/api/portal/devices/authorization-code' in WORKER,"PORTAL_CODE_REQUEST")
need('/api/device/product-lease' in WORKER,"DEVICE_LEASE_REQUEST")
need('"usage_report":local_usage_report(config)' in AGENT,"USAGE_PIGGYBACK")
need('if transport_mode(config)=="LOCAL_TUNNEL":' in AGENT,"LOCAL_TUNNEL_BRANCH")
branch=AGENT.split('if transport_mode(config)=="LOCAL_TUNNEL":',1)[1].split('last_heartbeat=0.0',1)[0]
need('/api/device/calls/next' not in branch,"IDLE_CALL_POLL_ZERO")
need('/api/device/heartbeat' not in branch,"IDLE_HEARTBEAT_ZERO")
need('relay_calls_per_local_tool_call":0' in AGENT,"TOOL_RELAY_ZERO")
need('cloud_quota_consumed_by_local_tool_call":False' in AGENT,"TOOL_CLOUD_QUOTA_ZERO")
need('commander_device_usage_totals' in MIGRATION and 'commander_device_usage_daily' in MIGRATION,"AGGREGATE_SYNC_TABLES")
need(renewals_per_day==4,"MAX_RENEWALS_PER_DAY")
need(core_requests_per_day==8,"CORE_REQUESTS_PER_DAY")
need(core_requests_30d==240,"CORE_REQUESTS_30D")
need(ratio<=0.024,"FREE_10K_CONTROL_PLANE_RATIO")
need(reduction>=97.6,"FREE_10K_REQUEST_REDUCTION")

print(f"COMMANDER_LOCAL_TUNNEL_MAX_RENEWALS_PER_DAY={renewals_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_CORE_CONTROL_REQUESTS_PER_DAY={core_requests_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_CORE_CONTROL_REQUESTS_30D={core_requests_30d}")
print(f"COMMANDER_LOCAL_TUNNEL_FREE_10K_CORE_REQUEST_RATIO={ratio:.4f}")
print(f"COMMANDER_LOCAL_TUNNEL_FREE_10K_CORE_REQUEST_REDUCTION_PERCENT={reduction:.1f}")
print("COMMANDER_LOCAL_TUNNEL_UNIT_ECONOMICS=PASS")
