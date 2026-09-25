#!/usr/bin/env python3
import argparse
import json
from decimal import Decimal, ROUND_HALF_UP

PRICING_SNAPSHOT_DATE = "2026-09-25"
REGISTERED_HUMANS = 10_000
PEAK_ACTIVE_HUMANS = 2_000
ACTIVE_HOURS_PER_DAY = 8
DAYS_PER_MONTH = 30

PASSIVE_PRODUCT_REFRESHES_PER_MINUTE = Decimal("2")
PASSIVE_DEVICE_REFRESHES_PER_MINUTE = Decimal("4")
INVOKES_PER_ACTIVE_HUMAN_PER_MINUTE = Decimal("1")

WORKERS_INCLUDED_REQUESTS = 10_000_000
WORKERS_REQUEST_OVERAGE_PER_MILLION_USD = Decimal("0.30")
WORKERS_BASE_USD = Decimal("5.00")

D1_INCLUDED_ROWS_READ = 25_000_000_000
D1_INCLUDED_ROWS_WRITTEN = 50_000_000
SESSION_LOGICAL_ROWS_PER_RESOLUTION = 3
LOGIN_D1_WRITES_PER_LOGIN_HEADROOM = 6
SESSION_TOUCH_SECONDS = 30 * 60

DO_INCLUDED_REQUESTS = 1_000_000
DO_REQUEST_OVERAGE_PER_MILLION_USD = Decimal("0.15")
DO_SOFT_LIMIT_RPS = Decimal("1000")
DO_COMPLEX_PLANNING_FLOOR_RPS = Decimal("200")

def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def build():
    seconds = ACTIVE_HOURS_PER_DAY * 3600 * DAYS_PER_MONTH
    product_rps = Decimal(PEAK_ACTIVE_HUMANS) * PASSIVE_PRODUCT_REFRESHES_PER_MINUTE / Decimal(60)
    device_rps = Decimal(PEAK_ACTIVE_HUMANS) * PASSIVE_DEVICE_REFRESHES_PER_MINUTE / Decimal(60)
    worker_rps = product_rps + device_rps
    worker_requests = int(worker_rps * seconds)

    worker_overage = max(worker_requests - WORKERS_INCLUDED_REQUESTS, 0)
    worker_request_cost = Decimal(worker_overage) / Decimal(1_000_000) * WORKERS_REQUEST_OVERAGE_PER_MILLION_USD

    logical_session_rows = worker_requests * SESSION_LOGICAL_ROWS_PER_RESOLUTION
    logical_session_rows_10x = logical_session_rows * 10

    touches_per_active_per_day = ACTIVE_HOURS_PER_DAY * 3600 // SESSION_TOUCH_SECONDS
    session_touch_writes = PEAK_ACTIVE_HUMANS * touches_per_active_per_day * DAYS_PER_MONTH
    daily_login_writes = REGISTERED_HUMANS * LOGIN_D1_WRITES_PER_LOGIN_HEADROOM
    monthly_login_writes = daily_login_writes * DAYS_PER_MONTH
    modeled_d1_writes = session_touch_writes + monthly_login_writes

    quota_status_requests = int(product_rps * seconds)
    quota_status_overage = max(quota_status_requests - DO_INCLUDED_REQUESTS, 0)
    quota_status_request_cost = Decimal(quota_status_overage) / Decimal(1_000_000) * DO_REQUEST_OVERAGE_PER_MILLION_USD

    invoke_rps = Decimal(PEAK_ACTIVE_HUMANS) * INVOKES_PER_ACTIVE_HUMAN_PER_MINUTE / Decimal(60)
    # reserve + one terminal transition (commit or release)
    invoke_quota_rps = invoke_rps * 2
    single_hot_tenant_quota_rps = product_rps + invoke_quota_rps

    return {
        "schema": "hara.commander-human-10k-cost-envelope.v1",
        "pricing_snapshot_date": PRICING_SNAPSHOT_DATE,
        "target": {
            "registered_humans": REGISTERED_HUMANS,
            "peak_active_humans": PEAK_ACTIVE_HUMANS,
            "active_hours_per_day": ACTIVE_HOURS_PER_DAY,
            "days_per_month": DAYS_PER_MONTH,
        },
        "workers": {
            "stress_requests_per_second": float(worker_rps),
            "stress_requests_per_month": worker_requests,
            "included_requests_per_month": WORKERS_INCLUDED_REQUESTS,
            "request_overage_usd": money(worker_request_cost),
            "base_subscription_usd": money(WORKERS_BASE_USD),
            "request_plus_base_usd_excluding_cpu": money(WORKERS_BASE_USD + worker_request_cost),
        },
        "d1": {
            "logical_session_rows_per_month": logical_session_rows,
            "logical_session_rows_percent_of_included": round(100 * logical_session_rows / D1_INCLUDED_ROWS_READ, 3),
            "logical_session_rows_10x_percent_of_included": round(100 * logical_session_rows_10x / D1_INCLUDED_ROWS_READ, 3),
            "modeled_writes_per_month": modeled_d1_writes,
            "modeled_writes_percent_of_included": round(100 * modeled_d1_writes / D1_INCLUDED_ROWS_WRITTEN, 3),
            "included_rows_read_per_month": D1_INCLUDED_ROWS_READ,
            "included_rows_written_per_month": D1_INCLUDED_ROWS_WRITTEN,
            "note": "logical estimate; validate production rows_read/rows_written from D1 analytics",
        },
        "tenant_quota": {
            "status_requests_per_month_at_product_ttl_cap": quota_status_requests,
            "status_request_overage_usd_excluding_duration_storage": money(quota_status_request_cost),
            "single_tenant_stress_rps": float(single_hot_tenant_quota_rps),
            "cloudflare_single_do_soft_limit_rps": float(DO_SOFT_LIMIT_RPS),
            "complex_operation_planning_floor_rps": float(DO_COMPLEX_PLANNING_FLOOR_RPS),
            "percent_of_soft_limit": float(round(100 * single_hot_tenant_quota_rps / DO_SOFT_LIMIT_RPS, 2)),
            "percent_of_complex_planning_floor": float(round(100 * single_hot_tenant_quota_rps / DO_COMPLEX_PLANNING_FLOOR_RPS, 2)),
        },
        "pricing_sources": {
            "workers": "https://developers.cloudflare.com/workers/platform/pricing/",
            "d1": "https://developers.cloudflare.com/d1/platform/pricing/",
            "durable_objects": "https://developers.cloudflare.com/durable-objects/platform/pricing/",
            "durable_object_limits": "https://developers.cloudflare.com/durable-objects/reference/faq/",
        },
    }

def validate(model):
    assert model["workers"]["stress_requests_per_second"] == 200.0
    assert model["workers"]["stress_requests_per_month"] == 172_800_000
    assert model["workers"]["request_overage_usd"] == "48.84"
    assert model["workers"]["request_plus_base_usd_excluding_cpu"] == "53.84"
    assert model["d1"]["logical_session_rows_per_month"] == 518_400_000
    assert model["d1"]["logical_session_rows_10x_percent_of_included"] < 21
    assert model["d1"]["modeled_writes_per_month"] == 2_760_000
    assert model["d1"]["modeled_writes_percent_of_included"] < 6
    assert model["tenant_quota"]["single_tenant_stress_rps"] < 134
    assert model["tenant_quota"]["percent_of_complex_planning_floor"] < 67
    assert model["tenant_quota"]["percent_of_soft_limit"] < 14

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    model = build()
    validate(model)
    if args.check:
        print("COMMANDER_HUMAN_10K_COST_ENVELOPE=PASS")
        print("COMMANDER_HUMAN_10K_PRICING_SNAPSHOT=" + PRICING_SNAPSHOT_DATE)
        return
    print(json.dumps(model, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
