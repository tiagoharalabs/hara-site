#!/usr/bin/env python3
"""Deterministic reconnect-storm model for Commander Event V2.

The model uses the exact ReconnectPolicy from the experimental client and a
stable SHA-256-derived entropy stream so CI can detect regressions toward
synchronized reconnects.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
TRANSPORT = APP / "experimental" / "event_v2_websocket.py"


def load_transport():
    spec = importlib.util.spec_from_file_location("hara_event_v2_transport_reconnect_model", TRANSPORT)
    if spec is None or spec.loader is None:
        raise RuntimeError("RECONNECT_MODEL_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entropy(device_index: int, attempt: int) -> float:
    digest = hashlib.sha256(f"{device_index}:{attempt}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


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


def self_check() -> None:
    transport = load_transport()
    policy = transport.ReconnectPolicy()

    assert policy.base_seconds == 10.0
    assert policy.max_seconds == 15.0

    expected = {
        (100, 0): 14,
        (1_000, 0): 117,
        (5_000, 0): 532,
        (20_000, 0): 2052,
        (20_000, 1): 1384,
    }
    for key, max_bucket in expected.items():
        devices, attempt = key
        profile = attempt_profile(policy, devices, attempt)
        assert profile["max_attempts_in_1s_bucket"] == max_bucket

    thousand = attempt_profile(policy, 1_000, 0)
    twenty_k = attempt_profile(policy, 20_000, 0)

    # Practical 1k target: first reconnect wave stays near ~100/s rather than
    # concentrating all 1,000 devices into one second.
    assert thousand["max_attempts_in_1s_bucket"] <= 150

    # 20k is architecture headroom, not a current SLA. The first wave must at
    # least be distributed by an order of magnitude compared with the old 1s
    # reconnect window. D1 presence-write pressure is tracked separately.
    assert twenty_k["max_attempts_in_1s_bucket"] <= 2_200
    assert twenty_k["max_bucket_fraction"] <= 0.11


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", type=int, nargs="*", default=[100, 1_000, 5_000, 20_000])
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

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
            "schema": "hara.commander-event-v2-reconnect-storm.v1",
            "policy": {
                "base_seconds": policy.base_seconds,
                "max_seconds": policy.max_seconds,
                "full_jitter": True,
            },
            "rows": rows,
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

    if args.check:
        print("COMMANDER_EVENT_V2_RECONNECT_STORM_MODEL=PASS")
        print("COMMANDER_EVENT_V2_RECONNECT_BASE_SECONDS=10")
        print("COMMANDER_EVENT_V2_RECONNECT_MAX_SECONDS=15")
        print("COMMANDER_EVENT_V2_1K_FIRST_WAVE_MAX_PER_SECOND=117")
        print("COMMANDER_EVENT_V2_20K_FIRST_WAVE_MAX_PER_SECOND=2052")
        print("COMMANDER_EVENT_V2_RECONNECT_D1_PRESSURE_20K=REQUIRES_SEPARATE_GUARD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
