#!/usr/bin/env python3
"""Offline telemetry-cost budget model for H.A.R.A. Commander.

Arithmetic only. No network calls and no production mutation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

SECONDS_PER_DAY = 86_400
REQUESTS_PER_ACTIVE_USER_PER_MINUTE = 6.0
ACTIVE_FRACTION = 0.20
CUSTOM_SUCCESS_SAMPLE_RATE = 0.0025
CUSTOM_DAILY_BUDGET = 100_000


@dataclass(frozen=True)
class TelemetryBudget:
    registered_users: int
    active_users: int
    portal_request_rps: float
    portal_requests_per_day: float
    success_sample_rate: float
    sampled_success_events_per_day: float
    custom_daily_budget: int
    budget_fraction: float


def scenario(registered_users: int) -> TelemetryBudget:
    if registered_users <= 0:
        raise ValueError("registered_users must be > 0")

    active_users = round(registered_users * ACTIVE_FRACTION)
    rps = active_users * REQUESTS_PER_ACTIVE_USER_PER_MINUTE / 60.0
    requests_day = rps * SECONDS_PER_DAY
    sampled = requests_day * CUSTOM_SUCCESS_SAMPLE_RATE

    return TelemetryBudget(
        registered_users=registered_users,
        active_users=active_users,
        portal_request_rps=rps,
        portal_requests_per_day=requests_day,
        success_sample_rate=CUSTOM_SUCCESS_SAMPLE_RATE,
        sampled_success_events_per_day=sampled,
        custom_daily_budget=CUSTOM_DAILY_BUDGET,
        budget_fraction=sampled / CUSTOM_DAILY_BUDGET,
    )


def validate(rows: list[TelemetryBudget]) -> None:
    tenk = next(row for row in rows if row.registered_users == 10_000)
    assert tenk.active_users == 2_000
    assert tenk.portal_request_rps == 200.0
    assert tenk.portal_requests_per_day == 17_280_000.0
    assert tenk.sampled_success_events_per_day == 43_200.0
    assert tenk.budget_fraction == 0.432
    assert tenk.sampled_success_events_per_day < CUSTOM_DAILY_BUDGET


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, nargs="*", default=[100, 1_000, 10_000])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = [scenario(n) for n in args.users]
    validate(rows)

    payload = {
        "schema": "hara.commander-telemetry-budget.v1",
        "assumptions": {
            "active_fraction": ACTIVE_FRACTION,
            "requests_per_active_user_per_minute": REQUESTS_PER_ACTIVE_USER_PER_MINUTE,
            "custom_success_sample_rate": CUSTOM_SUCCESS_SAMPLE_RATE,
            "custom_daily_budget": CUSTOM_DAILY_BUDGET,
            "note": (
                "Built-in platform metrics remain the 100% source for request/error volume. "
                "This budget applies only to optional privacy-safe custom application telemetry."
            ),
        },
        "scenarios": [asdict(row) for row in rows],
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("users | active | portal_rps | requests_day | sampled_custom_day | budget_fraction")
        for row in rows:
            print(
                f"{row.registered_users:>5} | "
                f"{row.active_users:>6} | "
                f"{row.portal_request_rps:>10.2f} | "
                f"{row.portal_requests_per_day:>12.0f} | "
                f"{row.sampled_success_events_per_day:>18.0f} | "
                f"{row.budget_fraction:>15.3f}"
            )

    if args.check:
        print("COMMANDER_TELEMETRY_BUDGET=PASS")
        print("COMMANDER_TELEMETRY_10K_CUSTOM_EVENTS_UNDER_BUDGET=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
