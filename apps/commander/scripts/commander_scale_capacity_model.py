#!/usr/bin/env python3
"""Deterministic offline capacity model for H.A.R.A. Commander device transport.

This script performs arithmetic only. It never opens a network connection and
therefore is safe to run against PROD-adjacent source trees.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class PollV1Capacity:
    devices: int
    poll_seconds: float
    heartbeat_seconds: float
    idle_poll_rps: float
    heartbeat_rps: float
    baseline_http_rps: float
    idle_poll_requests_per_day: float
    heartbeat_requests_per_day: float
    baseline_http_requests_per_day: float


@dataclass(frozen=True)
class EventV2Capacity:
    devices: int
    persistent_connections: int
    idle_call_poll_rps: float
    idle_call_poll_requests_per_day: float
    note: str


def poll_v1(devices: int, poll_seconds: float = 2.0, heartbeat_seconds: float = 30.0) -> PollV1Capacity:
    if devices <= 0:
        raise ValueError("devices must be > 0")
    if poll_seconds <= 0 or heartbeat_seconds <= 0:
        raise ValueError("intervals must be > 0")

    idle_poll_rps = devices / poll_seconds
    heartbeat_rps = devices / heartbeat_seconds
    return PollV1Capacity(
        devices=devices,
        poll_seconds=poll_seconds,
        heartbeat_seconds=heartbeat_seconds,
        idle_poll_rps=idle_poll_rps,
        heartbeat_rps=heartbeat_rps,
        baseline_http_rps=idle_poll_rps + heartbeat_rps,
        idle_poll_requests_per_day=idle_poll_rps * SECONDS_PER_DAY,
        heartbeat_requests_per_day=heartbeat_rps * SECONDS_PER_DAY,
        baseline_http_requests_per_day=(idle_poll_rps + heartbeat_rps) * SECONDS_PER_DAY,
    )


def event_v2(devices: int) -> EventV2Capacity:
    if devices <= 0:
        raise ValueError("devices must be > 0")
    return EventV2Capacity(
        devices=devices,
        persistent_connections=devices,
        idle_call_poll_rps=0.0,
        idle_call_poll_requests_per_day=0.0,
        note=(
            "Target steady state: Durable Object WebSocket Hibernation keeps the "
            "device channel connected without periodic /calls/next HTTP polling. "
            "Reconnect, liveness and real-call traffic are measured separately."
        ),
    )


def self_check() -> None:
    baseline = poll_v1(20_000)
    assert baseline.idle_poll_rps == 10_000.0
    assert round(baseline.heartbeat_rps, 6) == round(20_000 / 30, 6)
    assert baseline.baseline_http_requests_per_day == 921_600_000.0

    target = event_v2(20_000)
    assert target.persistent_connections == 20_000
    assert target.idle_call_poll_rps == 0.0
    assert target.idle_call_poll_requests_per_day == 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--devices",
        type=int,
        nargs="*",
        default=[100, 1_000, 5_000, 20_000],
        help="Device populations to model.",
    )
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        self_check()

    rows = []
    for count in args.devices:
        rows.append(
            {
                "poll_v1": asdict(poll_v1(count, args.poll_seconds, args.heartbeat_seconds)),
                "event_v2_target": asdict(event_v2(count)),
            }
        )

    if args.json:
        print(json.dumps({"schema": "hara.commander-scale-capacity.v1", "rows": rows}, indent=2, sort_keys=True))
    else:
        print("devices | poll_rps | heartbeat_rps | baseline_http_rps | baseline_http_requests_day")
        for row in rows:
            v1 = row["poll_v1"]
            print(
                f'{v1["devices"]:>7} | '
                f'{v1["idle_poll_rps"]:>8.2f} | '
                f'{v1["heartbeat_rps"]:>13.2f} | '
                f'{v1["baseline_http_rps"]:>17.2f} | '
                f'{v1["baseline_http_requests_per_day"]:>26.0f}'
            )

    if args.check:
        print("COMMANDER_SCALE_CAPACITY_MODEL=PASS")
        print("COMMANDER_EVENT_V2_IDLE_HTTP_POLL_TARGET=ZERO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
