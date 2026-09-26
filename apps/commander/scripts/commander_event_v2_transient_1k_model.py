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
DO_INCLUDED_REQUESTS_MONTH = 1_000_000
DO_EXCESS_USD_PER_MILLION_REQUESTS = 0.15
D1_INCLUDED_ROWS_READ_MONTH = 25_000_000_000
D1_EXCESS_USD_PER_MILLION_ROWS_READ = 0.001
D1_INCLUDED_ROWS_WRITTEN_MONTH = 50_000_000
D1_EXCESS_USD_PER_MILLION_ROWS_WRITTEN = 1.00
D1_ROWS_READ_PER_TRANSIENT_HTTP = 13
D1_ROWS_WRITTEN_PER_TRANSIENT_HTTP = 0
MEASURED_LINUX_INVOKE_P95_SECONDS = 0.942058
FIRST_1K_CONSERVATIVE_CALL_SECONDS = 1.0
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
    reconnect_request_day: int
    do_request_equivalents_day: int
    do_request_equivalents_month: int
    do_excess_request_usd_month: float
    do_duration_gb_seconds_month: float
    do_excess_duration_usd_month: float
    d1_rows_read_day: int
    d1_rows_read_month: int
    d1_excess_rows_read_usd_month: float
    d1_call_rows_written_day: int
    d1_control_rows_written_day: int
    d1_rows_written_day: int
    d1_rows_written_month: int
    d1_excess_rows_written_usd_month: float


def transient_budget(
    devices: int,
    calls_per_device_day: float,
    average_call_seconds: float,
    invoke_fraction: float = 1.0,
    reconnects_per_device_day: float = 0.0,
) -> TransientBudget:
    if not 0.0 <= invoke_fraction <= 1.0:
        raise ValueError("invoke_fraction must be between 0 and 1")
    if reconnects_per_device_day < 0:
        raise ValueError("reconnects_per_device_day must be non-negative")
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
    reconnect_request_day = round(devices * reconnects_per_device_day)
    do_request_equivalents_day = math.ceil(
        calls_day
        + quota_rpc_day
        + reconnect_request_day
        + (calls_day / DO_RESULT_MESSAGE_BILLING_RATIO)
        + (liveness_messages_day / DO_RESULT_MESSAGE_BILLING_RATIO)
    )
    do_requests_month = do_request_equivalents_day * DAYS_PER_MONTH
    do_request_excess = max(0, do_requests_month - DO_INCLUDED_REQUESTS_MONTH)
    do_request_rounded_millions = (
        math.ceil(do_request_excess / 1_000_000) if do_request_excess else 0
    )
    do_request_cost = (
        do_request_rounded_millions * DO_EXCESS_USD_PER_MILLION_REQUESTS
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

    d1_rows_read_day = calls_day * D1_ROWS_READ_PER_TRANSIENT_HTTP
    d1_rows_read_month = d1_rows_read_day * DAYS_PER_MONTH
    d1_read_excess = max(0, d1_rows_read_month - D1_INCLUDED_ROWS_READ_MONTH)
    d1_read_rounded_millions = (
        math.ceil(d1_read_excess / 1_000_000) if d1_read_excess else 0
    )
    d1_read_cost = (
        d1_read_rounded_millions * D1_EXCESS_USD_PER_MILLION_ROWS_READ
    )
    d1_call_rows_written_day = calls_day * D1_ROWS_WRITTEN_PER_TRANSIENT_HTTP
    d1_control_rows_written_day = liveness_messages_day + reconnect_request_day
    d1_rows_written_day = d1_call_rows_written_day + d1_control_rows_written_day
    d1_rows_written_month = d1_rows_written_day * DAYS_PER_MONTH
    d1_write_excess = max(
        0, d1_rows_written_month - D1_INCLUDED_ROWS_WRITTEN_MONTH
    )
    d1_write_rounded_millions = (
        math.ceil(d1_write_excess / 1_000_000) if d1_write_excess else 0
    )
    d1_write_cost = (
        d1_write_rounded_millions * D1_EXCESS_USD_PER_MILLION_ROWS_WRITTEN
    )

    return TransientBudget(
        devices=devices,
        calls_per_device_day=calls_per_device_day,
        average_call_seconds=average_call_seconds,
        calls_day=calls_day,
        worker_http_day=worker_http_day,
        quota_rpc_day=quota_rpc_day,
        reconnect_request_day=reconnect_request_day,
        do_request_equivalents_day=do_request_equivalents_day,
        do_request_equivalents_month=do_requests_month,
        do_excess_request_usd_month=do_request_cost,
        do_duration_gb_seconds_month=gb_seconds_month,
        do_excess_duration_usd_month=duration_cost,
        d1_rows_read_day=d1_rows_read_day,
        d1_rows_read_month=d1_rows_read_month,
        d1_excess_rows_read_usd_month=d1_read_cost,
        d1_call_rows_written_day=d1_call_rows_written_day,
        d1_control_rows_written_day=d1_control_rows_written_day,
        d1_rows_written_day=d1_rows_written_day,
        d1_rows_written_month=d1_rows_written_month,
        d1_excess_rows_written_usd_month=d1_write_cost,
    )


def self_check() -> None:
    ten = transient_budget(1_000, 10, 0.5)
    assert ten.calls_day == 10_000
    assert ten.worker_http_day == 10_000
    assert ten.quota_rpc_day == 20_000
    assert ten.do_request_equivalents_day == 30_700
    assert ten.do_duration_gb_seconds_month == 18_750
    assert ten.do_excess_duration_usd_month == 0
    assert ten.d1_rows_read_day == 130_000
    assert ten.d1_rows_read_month == 3_900_000
    assert ten.d1_excess_rows_read_usd_month == 0

    measured = transient_budget(
        1_000,
        10,
        FIRST_1K_CONSERVATIVE_CALL_SECONDS,
        reconnects_per_device_day=1.0,
    )
    assert measured.reconnect_request_day == 1_000
    assert measured.do_request_equivalents_day == 31_700
    assert measured.do_request_equivalents_month == 951_000
    assert measured.do_excess_request_usd_month == 0
    assert measured.do_duration_gb_seconds_month == 37_500
    assert measured.d1_rows_read_month == 3_900_000
    assert measured.d1_call_rows_written_day == 0
    assert measured.d1_control_rows_written_day == 5_000
    assert measured.d1_rows_written_month == 150_000
    assert measured.d1_excess_rows_written_usd_month == 0

    heavy_measured = transient_budget(
        1_000,
        100,
        FIRST_1K_CONSERVATIVE_CALL_SECONDS,
        reconnects_per_device_day=1.0,
    )
    assert heavy_measured.do_request_equivalents_day == 306_200
    assert heavy_measured.do_request_equivalents_month == 9_186_000
    assert math.isclose(heavy_measured.do_excess_request_usd_month, 1.35, rel_tol=0, abs_tol=1e-12)
    assert heavy_measured.do_duration_gb_seconds_month == 375_000
    assert heavy_measured.d1_rows_read_month == 39_000_000

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
        print("COMMANDER_TRANSIENT_D1_ROWS_READ_PER_HTTP=13")
        print("COMMANDER_TRANSIENT_D1_ROWS_WRITTEN_PER_HTTP=0")
        print("COMMANDER_TRANSIENT_LINUX_INVOKE_P95_SECONDS=0.942058")
        print("COMMANDER_TRANSIENT_FIRST_1K_CONSERVATIVE_CALL_SECONDS=1.0")
        print("COMMANDER_TRANSIENT_1K_10_CALLS_DAILY_RECONNECT_DO_REQ_MONTH=951000")
        print("COMMANDER_TRANSIENT_1K_10_CALLS_D1_ROWS_READ_MONTH=3900000")
        print("COMMANDER_TRANSIENT_1K_10_CALLS_D1_CONTROL_ROWS_WRITTEN_MONTH=150000")
        print("COMMANDER_TRANSIENT_1K_10_CALLS_DO_GB_SECONDS_MONTH=37500")
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
