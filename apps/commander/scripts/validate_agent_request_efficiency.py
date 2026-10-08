#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
LINUX = (APP / "public/agent/linux.py").read_text(encoding="utf-8")
WINDOWS = (APP / "public/agent/windows.ps1").read_text(encoding="utf-8")

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_AGENT_REQUEST_EFFICIENCY_{code}=FAIL")
    print(f"COMMANDER_AGENT_REQUEST_EFFICIENCY_{code}=PASS")

def py_int(name: str) -> int:
    pattern = "^" + re.escape(name) + r"\s*=\s*(\d+)\s*$"
    m = re.search(pattern, LINUX, re.M)
    if not m:
        raise SystemExit(f"COMMANDER_AGENT_REQUEST_EFFICIENCY_{name}=MISSING")
    return int(m.group(1))

def ps_int(name: str) -> int:
    pattern = r"^\$" + re.escape(name) + r"\s*=\s*(\d+)\s*$"
    m = re.search(pattern, WINDOWS, re.M)
    if not m:
        raise SystemExit(f"COMMANDER_AGENT_REQUEST_EFFICIENCY_{name}=MISSING")
    return int(m.group(1))

need('AGENT_VERSION = "0.3.43"' in LINUX, "LINUX_VERSION")
need('$AgentVersion = "0.3.43"' in WINDOWS, "WINDOWS_VERSION")

hb = py_int("HEARTBEAT_SECONDS")
hot = py_int("CALL_POLL_HOT_SECONDS")
idle = py_int("CALL_POLL_IDLE_SECONDS")
window = py_int("CALL_POLL_HOT_WINDOW_SECONDS")
startup = py_int("CALL_POLL_STARTUP_HOT_SECONDS")

need(hb == ps_int("HeartbeatSeconds"), "HEARTBEAT_PARITY")
need(hot == ps_int("CallPollHotSeconds"), "HOT_POLL_PARITY")
need(idle == ps_int("CallPollIdleSeconds"), "IDLE_POLL_PARITY")
need(window == ps_int("CallPollHotWindowSeconds"), "HOT_WINDOW_PARITY")
need(startup == ps_int("CallPollStartupHotSeconds"), "STARTUP_WINDOW_PARITY")

need(hb == 60, "HEARTBEAT_60S")
need(hot == 2, "HOT_POLL_2S")
need(idle == 10, "IDLE_POLL_10S")
need(window >= 60, "HOT_WINDOW_BOUNDED")
need(startup >= hot and startup <= window, "STARTUP_HOT_BOUNDED")

backoff_initial = py_int("RATE_LIMIT_BACKOFF_INITIAL_SECONDS")
backoff_max = py_int("RATE_LIMIT_BACKOFF_MAX_SECONDS")
need(backoff_initial == ps_int("RateLimitBackoffInitialSeconds"), "RATE_LIMIT_BACKOFF_INITIAL_PARITY")
need(backoff_max == ps_int("RateLimitBackoffMaxSeconds"), "RATE_LIMIT_BACKOFF_MAX_PARITY")
need(backoff_initial == 30, "RATE_LIMIT_BACKOFF_INITIAL_30S")
need(backoff_max == 300, "RATE_LIMIT_BACKOFF_MAX_300S")
need(backoff_initial < backoff_max, "RATE_LIMIT_BACKOFF_RANGE")
need('if code == "HTTP_429":' in LINUX, "LINUX_429_BACKOFF")
need('rate_limit_backoff_seconds * 2' in LINUX, "LINUX_429_EXPONENTIAL")
need('if ($code -eq "HTTP_429")' in WINDOWS, "WINDOWS_429_BACKOFF")
need('$RateLimitBackoffSeconds*2' in WINDOWS, "WINDOWS_429_EXPONENTIAL")
need('TRANSPORT_BACKOFF' in LINUX and 'TRANSPORT_BACKOFF' in WINDOWS, "BACKOFF_OBSERVABILITY")

need('"OPERATIONAL" if operational else "DENIED"' in LINUX, "LINUX_OPERATIONAL_EVENT")
need('state="EXPECTED" if operational else "FAILED"' in LINUX, "LINUX_OPERATIONAL_STATE")
need('function Test-OperationalErrorCode' in WINDOWS, "WINDOWS_OPERATIONAL_CLASSIFIER")
need('"OPERATIONAL"}else{"DENIED"}' in WINDOWS, "WINDOWS_OPERATIONAL_EVENT")
need('"EXPECTED"}else{"FAILED"}' in WINDOWS, "WINDOWS_OPERATIONAL_STATE")
need("event IN ('PASS','DENIED','OPERATIONAL')" in LINUX, "LINUX_ACTIVITY_OPERATIONAL_INCLUDED")
need("event IN ('PASS','DENIED','OPERATIONAL')" in WINDOWS, "WINDOWS_ACTIVITY_OPERATIONAL_INCLUDED")
need("state='EXPECTED'" in LINUX and 'AS operational' in LINUX, "LINUX_OPERATIONAL_SUMMARY")
need("state='EXPECTED'" in WINDOWS and 'AS operational' in WINDOWS, "WINDOWS_OPERATIONAL_SUMMARY")

need('if now-last_heartbeat>=HEARTBEAT_SECONDS:' in LINUX, "LINUX_HEARTBEAT_CONSTANT")
need('poll_hot_until=time.monotonic()+CALL_POLL_HOT_WINDOW_SECONDS' in LINUX, "LINUX_HOT_ON_CALL")
need('sleep_seconds=CALL_POLL_HOT_SECONDS if time.monotonic()<poll_hot_until else CALL_POLL_IDLE_SECONDS' in LINUX, "LINUX_ADAPTIVE_SLEEP")

need('TotalSeconds -ge $HeartbeatSeconds' in WINDOWS, "WINDOWS_HEARTBEAT_CONSTANT")
need('$PollHotUntil=(Get-Date).AddSeconds($CallPollHotWindowSeconds)' in WINDOWS, "WINDOWS_HOT_ON_CALL")
need('$PollSleep=if ((Get-Date) -lt $PollHotUntil) {$CallPollHotSeconds} else {$CallPollIdleSeconds}' in WINDOWS, "WINDOWS_ADAPTIVE_SLEEP")
need('function New-DirectResult([string]$FunctionId,[string]$RiskClass,$Data,[object]$ExitCode=0)' in WINDOWS, "WINDOWS_NULLABLE_EXIT_ENVELOPE")
need('$exit=if ($null -ne $run.exit_code) {[int]$run.exit_code} else {$null}' in WINDOWS, "WINDOWS_TIMEOUT_EXIT_NULL")

lease_seconds = 4 * 60 * 60
idle_requests_per_day = (86400 // idle) + (86400 // hb) + (86400 // lease_seconds)
seven_idle_requests_per_day = idle_requests_per_day * 7

need(idle_requests_per_day <= 11000, "ONE_IDLE_AGENT_BUDGET")
need(seven_idle_requests_per_day <= 75000, "SEVEN_IDLE_AGENT_BUDGET")

print(f"COMMANDER_AGENT_IDLE_REQUESTS_PER_DAY={idle_requests_per_day}")
print(f"COMMANDER_AGENT_SEVEN_IDLE_REQUESTS_PER_DAY={seven_idle_requests_per_day}")
print("COMMANDER_AGENT_REQUEST_EFFICIENCY=PASS")
