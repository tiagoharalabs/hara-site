#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math

FREE_MONTHLY_CALL_LIMIT = 10_000
LOCAL_BUDGET_BLOCK_UNITS = 100
PRODUCT_LEASE_REFRESH_HOURS = 4
DAYS_PER_MONTH = 30
OLD_QUOTA_RPCS_PER_GOVERNED_CALL = 2  # reserve + commit/release
TARGET_USER_RUNGS = (100, 1_000)


def free_user(calls: int) -> dict:
    calls = max(0, min(FREE_MONTHLY_CALL_LIMIT, int(calls)))
    old_quota_rpcs = calls * OLD_QUOTA_RPCS_PER_GOVERNED_CALL
    blocks = math.ceil(calls / LOCAL_BUDGET_BLOCK_UNITS) if calls else 0
    scheduled_lease_refreshes = math.ceil(DAYS_PER_MONTH * 24 / PRODUCT_LEASE_REFRESH_HOURS)
    # Rollover may force a lease refresh before the next scheduled refresh.
    product_lease_http_upper_bound = scheduled_lease_refreshes + blocks
    reduction = (
        100 * (1 - blocks / old_quota_rpcs)
        if old_quota_rpcs
        else 100.0
    )
    return {
        "calls_per_month": calls,
        "old_cloud_quota_rpcs": old_quota_rpcs,
        "local_budget_blocks_max": blocks,
        "cloud_budget_allocations_max": blocks,
        "quota_plane_rpc_reduction_percent": round(reduction, 3),
        "signed_lease_scheduled_refreshes_max": scheduled_lease_refreshes,
        "signed_lease_http_upper_bound_with_forced_rollover": product_lease_http_upper_bound,
        "local_sqlite_debit_transitions": calls * 2,
        "incremental_http_requests_for_budget_report": 0,
        "activity_detail_cloud_history_required": False,
        "tenant_quota_status_complexity": "O1_FALLBACK",
    }


def rung(users: int) -> dict:
    per = free_user(FREE_MONTHLY_CALL_LIMIT)
    calls = users * per["calls_per_month"]
    old_rpcs = users * per["old_cloud_quota_rpcs"]
    blocks = users * per["cloud_budget_allocations_max"]
    return {
        "free_users": users,
        "calls_per_month_at_full_free_allowance": calls,
        "legacy_quota_rpcs_per_month": old_rpcs,
        "local_budget_allocations_per_month_max": blocks,
        "quota_rpcs_avoided_per_month": old_rpcs - blocks,
        "quota_plane_rpc_reduction_percent": per["quota_plane_rpc_reduction_percent"],
        "signed_lease_scheduled_refreshes_per_month_max": users * per["signed_lease_scheduled_refreshes_max"],
        "note": "Lease refresh is an authorization/cache request, not a TenantQuota per-call decision.",
    }


def build() -> dict:
    return {
        "schema": "hara.commander-local-first-unit-economics.v1",
        "pricing": "NOT_MODELED_REQUIRES_LIVE_ANALYTICS",
        "architecture": {
            "free_monthly_calls": FREE_MONTHLY_CALL_LIMIT,
            "local_budget_block_units": LOCAL_BUDGET_BLOCK_UNITS,
            "product_lease_refresh_hours": PRODUCT_LEASE_REFRESH_HOURS,
            "unlimited_plan_quota_read_path": "BYPASS",
            "free_call_debit_authority": "LOCAL_SQLITE_WITH_CLOUD_ISSUED_BLOCK",
            "cloud_monthly_ceiling_authority": "HARA_COMMANDER_CLOUD",
            "activity_detail_authority": "LOCAL_DEVICE",
            "activity_cloud_sync": "BOUNDED_AGGREGATE_HEARTBEAT",
            "tenant_quota_fallback_status": "O1_PERIOD_USAGE",
        },
        "free_user_scenarios": {
            str(calls): free_user(calls)
            for calls in (100, 1_000, 10_000)
        },
        "scale_rungs_all_free_full_allowance": {
            str(users): rung(users) for users in TARGET_USER_RUNGS
        },
        "measurement_needed_for_usd": [
            "worker_cpu_ms",
            "durable_object_requests",
            "durable_object_duration_gb_seconds",
            "d1_rows_read",
            "d1_rows_written",
            "egress_bytes",
        ],
    }


def validate(model: dict) -> None:
    full = model["free_user_scenarios"]["10000"]
    assert full["old_cloud_quota_rpcs"] == 20_000
    assert full["local_budget_blocks_max"] == 100
    assert full["quota_plane_rpc_reduction_percent"] == 99.5
    assert full["signed_lease_scheduled_refreshes_max"] == 180
    assert full["incremental_http_requests_for_budget_report"] == 0
    assert full["activity_detail_cloud_history_required"] is False
    hundred = model["scale_rungs_all_free_full_allowance"]["100"]
    assert hundred["calls_per_month_at_full_free_allowance"] == 1_000_000
    assert hundred["legacy_quota_rpcs_per_month"] == 2_000_000
    assert hundred["local_budget_allocations_per_month_max"] == 10_000
    thousand = model["scale_rungs_all_free_full_allowance"]["1000"]
    assert thousand["calls_per_month_at_full_free_allowance"] == 10_000_000
    assert thousand["legacy_quota_rpcs_per_month"] == 20_000_000
    assert thousand["local_budget_allocations_per_month_max"] == 100_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    model = build()
    validate(model)
    if args.check:
        print("COMMANDER_LOCAL_FIRST_UNIT_ECONOMICS=PASS")
        print("COMMANDER_FREE_10K_LEGACY_QUOTA_RPCS=20000")
        print("COMMANDER_FREE_10K_LOCAL_BUDGET_BLOCKS_MAX=100")
        print("COMMANDER_FREE_10K_QUOTA_RPC_REDUCTION_PERCENT=99.5")
        print("COMMANDER_COST_USD=REQUIRES_LIVE_ANALYTICS")
        return 0
    print(json.dumps(model, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
