#!/usr/bin/env python3
"""Control-plane request reference model; one 24h Agent session per day."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")
AGENT=(APP/"public/agent/linux.py").read_text(encoding="utf-8")
MIGRATION=(APP/"migrations/0029_local_tunnel_authorization.sql").read_text(encoding="utf-8")
AGENT_MIGRATION=(APP/"migrations/0030_agent_lifecycle_telemetry.sql").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit(f"COMMANDER_LOCAL_TUNNEL_UNIT_ECONOMICS_{code}=FAIL")
    print(f"COMMANDER_LOCAL_TUNNEL_UNIT_ECONOMICS_{code}=PASS")

lease_hours=6
renewals_per_day=24//lease_hours
requests_per_renewal=2  # portal code + lease exchange (usage piggybacks)
authorization_requests_per_day=renewals_per_day*requests_per_renewal
metering_min_interval_hours=1
max_mcp_metering_syncs_per_day=24//metering_min_interval_hours
agent_heartbeat_requests_per_day=24
agent_start_stop_requests_per_day=2  # ONE 24h service session/day, NOT a restart worst case.
reference_requests_per_day=(authorization_requests_per_day+max_mcp_metering_syncs_per_day
    +agent_heartbeat_requests_per_day+agent_start_stop_requests_per_day)
reference_requests_30d=reference_requests_per_day*30
free_tools_month=10000
ratio=reference_requests_30d/free_tools_month
reduction=(1-ratio)*100

need('PRODUCT_LEASE_TTL_SECONDS = 6 * 60 * 60' in WORKER,"LEASE_6H")
need('/api/portal/devices/authorization-code' in WORKER,"PORTAL_CODE_REQUEST")
need('/api/device/product-lease' in WORKER,"DEVICE_LEASE_REQUEST")
need('"usage_report":local_usage_report(config)' in AGENT,"USAGE_PIGGYBACK")
need('if transport_mode(config)=="LOCAL_TUNNEL":' in AGENT,"LOCAL_TUNNEL_BRANCH")
branch=AGENT.split('if transport_mode(config)=="LOCAL_TUNNEL":',1)[1].split('last_heartbeat=0.0',1)[0]
need('/api/device/calls/next' not in branch,"IDLE_CALL_POLL_ZERO")
need('/api/device/heartbeat' not in branch,"LEGACY_DEVICE_HEARTBEAT_ZERO")
need('relay_calls_per_local_tool_call":0' in AGENT,"TOOL_RELAY_ZERO")
need('cloud_quota_consumed_by_local_tool_call":False' in AGENT,"TOOL_CLOUD_QUOTA_ZERO")
need('commander_device_usage_totals' in MIGRATION and 'commander_device_usage_daily' in MIGRATION,"AGGREGATE_SYNC_TABLES")
need('commander_device_agent_telemetry' in AGENT_MIGRATION,"HOURLY_EVENT_PERSISTENCE")
need(renewals_per_day==4,"MAX_RENEWALS_PER_DAY")
need('LOCAL_METERING_MIN_INTERVAL_SECONDS = 60 * 60' in AGENT,"MCP_METERING_MIN_INTERVAL_1H")
need('AGENT_TELEMETRY_INTERVAL_SECONDS = 60 * 60' in AGENT,"AGENT_HEARTBEAT_1H")
need('LOCAL_MCP_SESSION_START' in AGENT and 'LOCAL_MCP_SESSION_STOP' in AGENT,"MCP_SESSION_START_STOP")
need('AGENT_START' in AGENT and 'AGENT_HEARTBEAT' in AGENT and 'AGENT_STOP' in AGENT,"AGENT_LIFECYCLE_THREE_EVENTS")
need(max_mcp_metering_syncs_per_day==24,"MAX_MCP_METERING_SYNCS_PER_DAY")
need(authorization_requests_per_day==8,"AUTHORIZATION_REQUESTS_PER_DAY")
need(reference_requests_per_day==58,"ONE_SESSION_REFERENCE_REQUESTS_PER_DAY")
need(reference_requests_30d==1740,"ONE_SESSION_REFERENCE_REQUESTS_30D")
need(ratio<=0.174,"FREE_10K_CONTROL_PLANE_REFERENCE_RATIO")
need(reduction>=82.6,"FREE_10K_REQUEST_REDUCTION_REFERENCE")

print(f"COMMANDER_LOCAL_TUNNEL_MAX_RENEWALS_PER_DAY={renewals_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_AUTHORIZATION_REQUESTS_PER_DAY={authorization_requests_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_MAX_MCP_METERING_SYNCS_PER_DAY={max_mcp_metering_syncs_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_AGENT_HEARTBEATS_PER_DAY={agent_heartbeat_requests_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_AGENT_START_STOP_PER_DAY_REFERENCE={agent_start_stop_requests_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_CORE_REQUESTS_PER_DAY_ONE_SESSION_REFERENCE={reference_requests_per_day}")
print(f"COMMANDER_LOCAL_TUNNEL_CORE_REQUESTS_30D_ONE_SESSION_REFERENCE={reference_requests_30d}")
print(f"COMMANDER_LOCAL_TUNNEL_FREE_10K_CORE_REQUEST_RATIO_REFERENCE={ratio:.4f}")
print(f"COMMANDER_LOCAL_TUNNEL_FREE_10K_REQUEST_REDUCTION_PERCENT_REFERENCE={reduction:.1f}")
print("COMMANDER_LOCAL_TUNNEL_UNIT_ECONOMICS=PASS")
