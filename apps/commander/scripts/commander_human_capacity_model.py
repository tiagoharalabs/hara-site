#!/usr/bin/env python3
"""Offline human-plane capacity model for H.A.R.A. Commander.

Arithmetic only. No network calls and no production mutation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

SECONDS_PER_MINUTE = 60
MINUTES_PER_DAY = 1440
SESSION_TOUCH_MINUTES = 5


@dataclass(frozen=True)
class HumanCapacity:
    registered_users: int
    active_fraction: float
    active_users: int
    authenticated_requests_per_active_user_minute: float
    authenticated_requests_per_second: float
    session_selects_per_second: float
    session_touch_writes_per_second_upper_bound: float
    session_selects_per_day: float
    session_touch_writes_per_day_upper_bound: float


def human_capacity(
    registered_users: int,
    active_fraction: float,
    requests_per_active_user_minute: float,
) -> HumanCapacity:
    if registered_users <= 0:
        raise ValueError("registered_users must be > 0")
    if not 0 < active_fraction <= 1:
        raise ValueError("active_fraction must be in (0, 1]")
    if requests_per_active_user_minute < 0:
        raise ValueError("requests_per_active_user_minute must be >= 0")

    active_users = round(registered_users * active_fraction)
    request_rps = active_users * requests_per_active_user_minute / SECONDS_PER_MINUTE

    # Current resolvePortalSession() performs one PRODUCT_DB SELECT per
    # authenticated request. Each continuously active session may additionally
    # write last_seen_at_utc at most once per SESSION_TOUCH_MINUTES.
    touch_wps = active_users / (SESSION_TOUCH_MINUTES * SECONDS_PER_MINUTE)

    return HumanCapacity(
        registered_users=registered_users,
        active_fraction=active_fraction,
        active_users=active_users,
        authenticated_requests_per_active_user_minute=requests_per_active_user_minute,
        authenticated_requests_per_second=request_rps,
        session_selects_per_second=request_rps,
        session_touch_writes_per_second_upper_bound=touch_wps,
        session_selects_per_day=request_rps * 86400,
        session_touch_writes_per_day_upper_bound=touch_wps * 86400,
    )


def self_check() -> None:
    row = human_capacity(10_000, 1.0, 12.0)
    assert row.active_users == 10_000
    assert row.authenticated_requests_per_second == 2_000.0
    assert round(row.session_touch_writes_per_second_upper_bound, 6) == round(10_000 / 300, 6)

    realistic = human_capacity(10_000, 0.10, 6.0)
    assert realistic.active_users == 1_000
    assert realistic.authenticated_requests_per_second == 100.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, nargs="*", default=[1_000, 5_000, 10_000])
    parser.add_argument("--active-fraction", type=float, default=0.10)
    parser.add_argument("--requests-per-active-user-minute", type=float, default=6.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        self_check()

    rows = [
        asdict(human_capacity(count, args.active_fraction, args.requests_per_active_user_minute))
        for count in args.users
    ]

    if args.json:
        print(json.dumps({
            "schema": "hara.commander-human-capacity.v1",
            "assumptions": {
                "session_selects_per_authenticated_request": 1,
                "session_touch_minutes": SESSION_TOUCH_MINUTES,
                "note": "This models current database operation demand, not a claimed provider capacity limit.",
            },
            "rows": rows,
        }, indent=2, sort_keys=True))
    else:
        print("users | active | auth_rps | session_select_rps | touch_write_rps_upper")
        for row in rows:
            print(
                f'{row["registered_users"]:>5} | '
                f'{row["active_users"]:>6} | '
                f'{row["authenticated_requests_per_second"]:>8.2f} | '
                f'{row["session_selects_per_second"]:>18.2f} | '
                f'{row["session_touch_writes_per_second_upper_bound"]:>21.2f}'
            )

    if args.check:
        print("COMMANDER_HUMAN_CAPACITY_MODEL=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
