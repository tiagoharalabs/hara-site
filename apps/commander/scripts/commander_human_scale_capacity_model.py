#!/usr/bin/env python3
import argparse
import json
from dataclasses import asdict, dataclass

REGISTERED_USERS = (1_000, 10_000)
PEAK_ACTIVE_USERS = {1_000: 250, 10_000: 2_000}
PORTAL_REQUESTS_PER_ACTIVE_USER_PER_MINUTE = 6
LOGIN_BURST_PER_SECOND = {1_000: 25, 10_000: 100}
OLD_SESSION_TOUCH_SECONDS = 5 * 60
NEW_SESSION_TOUCH_SECONDS = 30 * 60
OLD_LOGIN_RETENTION_OPS = 2
NEW_LOGIN_RETENTION_OPS = 0
OIDC_PUBLIC_CACHE_TTL_SECONDS = 5 * 60
DASHBOARD_INITIAL_SESSION_READS_BEFORE = 3
DASHBOARD_INITIAL_SESSION_READS_AFTER = 1


@dataclass(frozen=True)
class Scenario:
    registered_users: int
    peak_active_users: int
    portal_requests_per_second: float
    current_session_reads_per_second: float
    old_session_touch_writes_per_second: float
    new_session_touch_writes_per_second: float
    session_touch_write_reduction_percent: float
    login_burst_per_second: int
    old_login_retention_ops_per_second: int
    new_login_retention_ops_per_second: int
    oidc_origin_fetch_pattern: str
    dashboard_initial_session_reads_before: int
    dashboard_initial_session_reads_after: int
    dashboard_initial_session_read_reduction_percent: float


def scenario(registered_users: int) -> Scenario:
    active = PEAK_ACTIVE_USERS[registered_users]
    portal_rps = active * PORTAL_REQUESTS_PER_ACTIVE_USER_PER_MINUTE / 60
    old_writes = active / OLD_SESSION_TOUCH_SECONDS
    new_writes = active / NEW_SESSION_TOUCH_SECONDS
    reduction = 100 * (1 - new_writes / old_writes)
    login_burst = LOGIN_BURST_PER_SECOND[registered_users]
    return Scenario(
        registered_users=registered_users,
        peak_active_users=active,
        portal_requests_per_second=portal_rps,
        current_session_reads_per_second=portal_rps,
        old_session_touch_writes_per_second=old_writes,
        new_session_touch_writes_per_second=new_writes,
        session_touch_write_reduction_percent=reduction,
        login_burst_per_second=login_burst,
        old_login_retention_ops_per_second=login_burst * OLD_LOGIN_RETENTION_OPS,
        new_login_retention_ops_per_second=login_burst * NEW_LOGIN_RETENTION_OPS,
        oidc_origin_fetch_pattern="cache-miss-bounded-not-login-linear",
        dashboard_initial_session_reads_before=DASHBOARD_INITIAL_SESSION_READS_BEFORE,
        dashboard_initial_session_reads_after=DASHBOARD_INITIAL_SESSION_READS_AFTER,
        dashboard_initial_session_read_reduction_percent=100 * (
            1 - DASHBOARD_INITIAL_SESSION_READS_AFTER / DASHBOARD_INITIAL_SESSION_READS_BEFORE
        ),
    )


def validate(rows):
    tenk = next(row for row in rows if row.registered_users == 10_000)
    assert tenk.peak_active_users == 2_000
    assert tenk.portal_requests_per_second == 200
    assert round(tenk.old_session_touch_writes_per_second, 3) == 6.667
    assert round(tenk.new_session_touch_writes_per_second, 3) == 1.111
    assert round(tenk.session_touch_write_reduction_percent, 1) == 83.3
    assert tenk.old_login_retention_ops_per_second == 200
    assert tenk.new_login_retention_ops_per_second == 0
    assert OIDC_PUBLIC_CACHE_TTL_SECONDS == 300
    assert tenk.dashboard_initial_session_reads_before == 3
    assert tenk.dashboard_initial_session_reads_after == 1
    assert round(tenk.dashboard_initial_session_read_reduction_percent, 1) == 66.7


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rows = [scenario(n) for n in REGISTERED_USERS]
    validate(rows)
    if args.check:
        print("COMMANDER_HUMAN_SCALE_10K=PASS")
        return
    print(json.dumps({
        "schema": "hara.commander-human-scale-capacity.v1",
        "assumptions": {
            "portal_requests_per_active_user_per_minute": PORTAL_REQUESTS_PER_ACTIVE_USER_PER_MINUTE,
            "oidc_public_cache_ttl_seconds": OIDC_PUBLIC_CACHE_TTL_SECONDS,
            "device_scale_owner": "#163",
            "human_scale_owner": "#167",
        },
        "scenarios": [asdict(row) for row in rows],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
