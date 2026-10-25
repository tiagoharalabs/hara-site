#!/usr/bin/env python3
"""Deterministic reconnect-storm model for Commander Event V2.

Uses the experimental client's actual startup/retry order and deterministic
entropy. Model checks never admit a provider rate or a commercial Agent.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
TRANSPORT = APP / "experimental" / "event_v2_websocket.py"


def load_transport():
    spec = importlib.util.spec_from_file_location("hara_event_v2_transport_reconnect_model", TRANSPORT)
    if spec is None or spec.loader is None:
        raise RuntimeError("RECONNECT_MODEL_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def entropy(device_index: int, attempt: int) -> float:
    digest = hashlib.sha256(f"{device_index}:{attempt}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def fnv1a32(value: str) -> int:
    result = 2166136261
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 16777619) & 0xFFFFFFFF
    return result


def offline_profile(devices: int) -> dict:
    buckets = Counter(
        30 + (fnv1a32(f"HARA-DEVICE-{index}") % 30)
        for index in range(devices)
    )
    maximum = max(buckets.values())
    return {
        "devices": devices,
        "offline_grace_min_seconds": 30,
        "offline_grace_max_seconds": 60,
        "max_offline_writes_in_1s_bucket": maximum,
        "max_bucket_fraction": maximum / devices,
        "nonempty_buckets": len(buckets),
    }


def liveness_profile(devices: int) -> dict:
    # Same deterministic FNV distribution used by the Windows RC, across a
    # 30-minute window centered on the six-hour durable-liveness target.
    buckets = Counter(
        fnv1a32(f"HARA-DEVICE-{index}") % 1801
        for index in range(devices)
    )
    maximum = max(buckets.values())
    return {
        "devices": devices,
        "spread_seconds": 1800,
        "max_liveness_messages_in_1s_bucket": maximum,
        "max_bucket_fraction": maximum / devices,
        "nonempty_buckets": len(buckets),
    }


def attempt_profile(policy, devices: int, attempt: int) -> dict:
    delays = [policy.delay(attempt, entropy(i, attempt)) for i in range(devices)]
    buckets = Counter(int(delay) for delay in delays)
    maximum = max(buckets.values())
    cap = min(policy.max_seconds, policy.base_seconds * (2 ** attempt))
    return {
        "devices": devices,
        "attempt": attempt,
        "cap_seconds": cap,
        "max_attempts_in_1s_bucket": maximum,
        "max_bucket_fraction": maximum / devices,
        "nonempty_buckets": len(buckets),
    }


def planned_attempt_times(policy, device: int, failures: int, handshake_seconds: float) -> list[float]:
    """Same order as run_forever: initial spread, then retry0, retry1, ... ."""
    now=policy.startup_delay(entropy(device,-1));times=[now]
    for attempt in range(failures):
        now+=handshake_seconds
        now+=policy.delay(attempt,entropy(device,attempt))
        times.append(now)
    return times


def timeline_profile(policy, devices: int, failures: int, handshake_seconds: float, *, session_drop=False) -> dict:
    def attempts(device):
        if not session_drop:return planned_attempt_times(policy,device,failures,handshake_seconds)
        # A live session lost simultaneously does not repeat startup spreading.
        now=0.0;times=[]
        for attempt in range(failures):
            now+=policy.delay(attempt,entropy(device,attempt));times.append(now)
            now+=handshake_seconds
        return times
    times=sorted(t for device in range(devices) for t in attempts(device))
    buckets=Counter(int(value) for value in times)
    return {'devices':devices,'attempts':len(times),'failed_rounds':failures,
            'scenario':'existing_session_drop' if session_drop else 'process_restart',
            'handshake_seconds_assumed':handshake_seconds,
            'max_attempts_in_1s_bucket':max(buckets.values()),
            'scheduled_connect_p95_s':times[int((len(times)-1)*.95)],
            'scheduled_connect_p99_s':times[int((len(times)-1)*.99)],
            'active_connections_measured':None,'http_latency_measured':False,
            'hosted_gate':'HOSTED_20K_HOLD'}


def self_check() -> None:
    transport = load_transport()
    policy = transport.ReconnectPolicy()

    def require(condition,code):
        if not condition:raise RuntimeError(code)
    require((policy.base_seconds,policy.max_seconds,policy.minimum_seconds,policy.startup_seconds)==
            (60.0,120.0,1.0,120.0),'RECONNECT_RUNTIME_POLICY_DRIFT')
    require(planned_attempt_times(policy,7,3,0)==planned_attempt_times(policy,7,3,0),'MODEL_NONDETERMINISTIC')
    for attempt in [0,1,31]:
        require(1<=policy.delay(attempt,0)<policy.delay(attempt,.999)<121,'MODEL_BACKOFF_INVALID')
    # Regression against the old model's 10-second independent first wave.
    # Neither number is a provider ceiling. Actual client loops are fixture-tested.
    legacy=max(Counter(int(entropy(i,0)*10) for i in range(20000)).values())
    require(legacy==2052,'LEGACY_MODEL_REFERENCE_CHANGED')
    for duration in [0,25]:
        trace=timeline_profile(policy,20000,3,duration)
        require(trace['max_attempts_in_1s_bucket']<legacy,'RECONNECT_SPREAD_REGRESSION')
    require(offline_profile(20000)['max_offline_writes_in_1s_bucket']==722,'OFFLINE_PROFILE_DRIFT')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", type=int, nargs="*", default=[100, 1_000, 5_000, 20_000])
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.devices or any(n<1 or n>20000 for n in args.devices) or len(args.devices)>8 or not 1<=args.attempts<=32:
        parser.error('devices must be 1..20000 (at most 8 sizes), attempts 1..32')

    transport = load_transport()
    policy = transport.ReconnectPolicy()

    if args.check:
        self_check()

    rows = []
    for devices in args.devices:
        for attempt in range(args.attempts):
            rows.append(attempt_profile(policy, devices, attempt))

    if args.json:
        print(json.dumps({
            "schema": "hara.commander-event-v2-reconnect-storm.v2",
            "model_check": "MODEL_PASS" if args.check else "NOT_CHECKED",
            "hosted_gate": "HOSTED_20K_HOLD",
            "commercial_agent_event_v2_parity": False,
            "scope": "EXPERIMENTAL_CLIENT_SOURCE_ONLY",
            "policy": {
                "base_seconds": policy.base_seconds,
                "max_seconds": policy.max_seconds,
                "minimum_seconds": policy.minimum_seconds,
                "startup_seconds": policy.startup_seconds,
                "full_jitter": False,
                "jitter": "UNIFORM_WITH_RETRY_FLOOR",
            },
            "rows": rows,
            "timelines": [timeline_profile(policy,count,args.attempts,seconds,session_drop=drop)
                          for count in args.devices for seconds in [0,25] for drop in [False,True]],
            "offline_disconnect_profiles": [
                offline_profile(count) for count in args.devices
            ],
            "durable_liveness_profiles": [
                liveness_profile(count) for count in args.devices
            ],
        }, indent=2, sort_keys=True))
    else:
        print("devices | attempt | cap_s | max_1s_bucket | max_bucket_fraction")
        for row in rows:
            print(
                f'{row["devices"]:>7} | {row["attempt"]:>7} | '
                f'{row["cap_seconds"]:>5.1f} | '
                f'{row["max_attempts_in_1s_bucket"]:>13} | '
                f'{row["max_bucket_fraction"]:>19.4f}'
            )

    if args.check and not args.json:
        print("COMMANDER_EVENT_V2_RECONNECT_STORM_MODEL=MODEL_PASS")
        print("COMMANDER_EVENT_V2_HOSTED_GATE=HOSTED_20K_HOLD")
        print("COMMANDER_EVENT_V2_PROVIDER_THROUGHPUT_LIMIT=UNBOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
