#!/usr/bin/env python3
"""Deterministic first-1k cost envelope for Event V2 transient RPC.

This model intentionally separates transport economics from live D1 row billing.
Source snapshot: Cloudflare Durable Objects pricing published 2026-08-25.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

DAYS_PER_MONTH = 30
DO_MEMORY_GB = 0.125
DO_INCLUDED_GB_SECONDS_MONTH = 400_000
DO_EXCESS_USD_PER_MILLION_GB_SECONDS = 12.50
DO_RESULT_MESSAGE_BILLING_RATIO = 20
DURABLE_LIVENESS_MESSAGES_PER_DEVICE_DAY = 4


@dataclass(frozen=True)
class TransientBudget:
    devices: int
    calls_per_device_day: float
    average_call_seconds: float
    calls_day: int
    worker_http_day: int
    quota_rpc_day: int
    do_request_equivalents_day: int
    do_duration_gb_seconds_month: float
    do_excess_duration_usd_month: float


def transient_budget(
    devices: int,
    calls_per_device_day: float,
    average_call_seconds: float,
    invoke_fraction: float = 1.0,
) -> TransientBudget:
    if not 0.0 <= invoke_fraction <= 1.0:
        raise ValueError("invoke_fraction must be between 0 and 1")
    calls_day = round(devices * calls_per_device_day)
    liveness_messages_day = devices * DURABLE_LIVENESS_MESSAGES_PER_DEVICE_DAY
    invoke_calls_day = round(calls_day * invoke_fraction)

    # One Worker dispatch request per logical call. The DeviceChannel sees one
    # dispatch request plus one inbound CALL_RESULT message (20:1 billing ratio).
    # Each successful hara.functions.invoke also performs one TenantQuota
    # reserve RPC and one commit RPC. Cloudflare bills each DO RPC method call
    # as one request. Failed invokes replace commit with release, preserving the
    # same two-quota-RPC planning envelope.
    worker_http_day = calls_day
    quota_rpc_day = invoke_calls_day * 2
    do_request_equivalents_day = math.ceil(
        calls_day
        + quota_rpc_day
        + (calls_day / DO_RESULT_MESSAGE_BILLING_RATIO)
        + (liveness_messages_day / DO_RESULT_MESSAGE_BILLING_RATIO)
    )

    active_seconds_month = (
        calls_day * average_call_seconds * DAYS_PER_MONTH
    )
    gb_seconds_month = active_seconds_month * DO_MEMORY_GB
    excess = max(0.0, gb_seconds_month - DO_INCLUDED_GB_SECONDS_MONTH)
    rounded_millions = math.ceil(excess / 1_000_000) if excess else 0
    duration_cost = (
        rounded_millions * DO_EXCESS_USD_PER_MILLION_GB_SECONDS
    )

    return TransientBudget(
        devices=devices,
        calls_per_device_day=calls_per_device_day,
        average_call_seconds=average_call_seconds,
        calls_day=calls_day,
        worker_http_day=worker_http_day,
        quota_rpc_day=quota_rpc_day,
        do_request_equivalents_day=do_request_equivalents_day,
        do_duration_gb_seconds_month=gb_seconds_month,
        do_excess_duration_usd_month=duration_cost,
    )


def self_check() -> None:
    ten = transient_budget(1_000, 10, 0.5)
    assert ten.calls_day == 10_000
    assert ten.worker_http_day == 10_000
    assert ten.quota_rpc_day == 20_000
    assert ten.do_request_equivalents_day == 30_700
    assert ten.do_duration_gb_seconds_month == 18_750
    assert ten.do_excess_duration_usd_month == 0

    heavy = transient_budget(1_000, 100, 10.0)
    assert heavy.calls_day == 100_000
    assert heavy.do_duration_gb_seconds_month == 3_750_000
    assert heavy.do_excess_duration_usd_month == 50.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    self_check()
    if args.check:
        print("COMMANDER_TRANSIENT_1K_MODEL=PASS")
        print("COMMANDER_TRANSIENT_CALL_TABLE_PAYLOAD_WRITES_PER_CALL=0")
        print("COMMANDER_TRANSIENT_CALL_TABLE_RESULT_WRITES_PER_CALL=0")
        print("COMMANDER_TRANSIENT_1K_10_CALLS_DEVICE_DAY_QUOTA_RPC=20000")
        print("COMMANDER_TRANSIENT_1K_10_CALLS_DEVICE_DAY_DO_REQ_EQ=30700")
        return 0

    print(
        "devices | calls/dev/day | avg_s | calls/day | worker_http/day | "
        "quota_rpc/day | do_req_eq/day | do_gb_s/month | do_excess_usd/month"
    )
    for calls_per_device in (1, 10, 100):
        for avg_seconds in (0.5, 2.0, 10.0):
            row = transient_budget(1_000, calls_per_device, avg_seconds)
            print(
                f"{row.devices:7d} | {row.calls_per_device_day:13.1f} | "
                f"{row.average_call_seconds:5.1f} | {row.calls_day:9d} | "
                f"{row.worker_http_day:15d} | "
                f"{row.quota_rpc_day:13d} | "
                f"{row.do_request_equivalents_day:13d} | "
                f"{row.do_duration_gb_seconds_month:14.0f} | "
                f"{row.do_excess_duration_usd_month:19.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
