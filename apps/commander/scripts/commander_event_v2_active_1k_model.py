#!/usr/bin/env python3
"""Deterministic active-workload budget for the first 1k Event V2 target.

Arithmetic only: no network, no Cloudflare mutation, no customer data.

The default status-poll rate comes from the canonical 30-call DEV baseline:
26/30 terminal responses returned directly from enqueue and 4 total status polls.
It is evidence for budgeting, not a latency SLA.
"""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CAPACITY_MODEL = ROOT / "commander_scale_capacity_model.py"

OBSERVED_CALLS = 30
OBSERVED_STATUS_POLLS = 4
OBSERVED_TERMINAL_FROM_ENQUEUE = 26
OBSERVED_STATUS_POLLS_PER_CALL = OBSERVED_STATUS_POLLS / OBSERVED_CALLS

# One notify request is sent to the per-device DeviceChannel per durable call.
DO_NOTIFY_REQUESTS_PER_CALL = 1.0

# The current agent drain loop claims one call then performs one final empty
# reconciliation read for an isolated wake. A fully packed 8-call drain uses
# eight successful claims plus one empty reconciliation read.
CLAIM_NEXT_HTTP_PER_CALL_ISOLATED = 2.0
CLAIM_NEXT_HTTP_PER_CALL_PACKED_8 = 9.0 / 8.0

ENQUEUE_HTTP_PER_CALL = 1.0
COMPLETE_HTTP_PER_CALL = 1.0


@dataclass(frozen=True)
class ActiveBudget:
    devices: int
    calls_per_device_per_day: float
    calls_per_day: float
    observed_status_polls_per_call: float
    status_poll_http_per_day: float
    enqueue_http_per_day: float
    complete_http_per_day: float
    claim_next_http_per_day_isolated: float
    claim_next_http_per_day_packed_8: float
    worker_http_per_day_isolated: float
    worker_http_per_day_packed_8: float
    do_notify_requests_per_day: float
    do_liveness_billed_request_equivalents_per_day: float
    do_request_equivalents_per_day: float
    v1_idle_http_requests_per_day: float
    active_http_vs_v1_idle_fraction_isolated: float
    note: str


def load_capacity_model() -> dict:
    return runpy.run_path(str(CAPACITY_MODEL))


def active_budget(
    devices: int,
    calls_per_device_per_day: float,
    status_polls_per_call: float = OBSERVED_STATUS_POLLS_PER_CALL,
) -> ActiveBudget:
    if devices <= 0:
        raise ValueError("devices must be > 0")
    if calls_per_device_per_day < 0:
        raise ValueError("calls_per_device_per_day must be >= 0")
    if status_polls_per_call < 0:
        raise ValueError("status_polls_per_call must be >= 0")

    capacity = load_capacity_model()
    v1 = capacity["poll_v1"](devices)
    idle = capacity["event_v2"](devices)

    calls = devices * calls_per_device_per_day
    status = calls * status_polls_per_call
    enqueue = calls * ENQUEUE_HTTP_PER_CALL
    complete = calls * COMPLETE_HTTP_PER_CALL
    claim_isolated = calls * CLAIM_NEXT_HTTP_PER_CALL_ISOLATED
    claim_packed = calls * CLAIM_NEXT_HTTP_PER_CALL_PACKED_8
    worker_isolated = enqueue + complete + status + claim_isolated
    worker_packed = enqueue + complete + status + claim_packed
    notify = calls * DO_NOTIFY_REQUESTS_PER_CALL
    liveness = idle.durable_liveness_billed_do_requests_per_day
    do_total = notify + liveness

    return ActiveBudget(
        devices=devices,
        calls_per_device_per_day=calls_per_device_per_day,
        calls_per_day=calls,
        observed_status_polls_per_call=status_polls_per_call,
        status_poll_http_per_day=status,
        enqueue_http_per_day=enqueue,
        complete_http_per_day=complete,
        claim_next_http_per_day_isolated=claim_isolated,
        claim_next_http_per_day_packed_8=claim_packed,
        worker_http_per_day_isolated=worker_isolated,
        worker_http_per_day_packed_8=worker_packed,
        do_notify_requests_per_day=notify,
        do_liveness_billed_request_equivalents_per_day=liveness,
        do_request_equivalents_per_day=do_total,
        v1_idle_http_requests_per_day=v1.baseline_http_requests_per_day,
        active_http_vs_v1_idle_fraction_isolated=(
            worker_isolated / v1.baseline_http_requests_per_day
            if v1.baseline_http_requests_per_day
            else 0.0
        ),
        note=(
            "Budget uses the canonical 30-call DEV status-poll baseline. "
            "Isolated claim-next is a conservative steady-call shape; packed-8 "
            "shows the current bounded drain advantage. Reconnect, quota, identity, "
            "D1 rows-read/written and connection establishment remain separately "
            "measured dimensions."
        ),
    )


def self_check() -> None:
    assert OBSERVED_TERMINAL_FROM_ENQUEUE == 26
    assert abs(OBSERVED_STATUS_POLLS_PER_CALL - (4.0 / 30.0)) < 1e-12

    ten = active_budget(1_000, 10)
    assert ten.calls_per_day == 10_000
    assert abs(ten.status_poll_http_per_day - (10_000 * 4 / 30)) < 1e-9
    assert ten.claim_next_http_per_day_isolated == 20_000
    assert ten.claim_next_http_per_day_packed_8 == 11_250
    assert abs(ten.worker_http_per_day_isolated - (10_000 + 10_000 + 20_000 + 10_000 * 4 / 30)) < 1e-9
    assert abs(ten.worker_http_per_day_packed_8 - (10_000 + 10_000 + 11_250 + 10_000 * 4 / 30)) < 1e-9
    assert ten.do_notify_requests_per_day == 10_000
    assert ten.do_liveness_billed_request_equivalents_per_day == 200
    assert ten.do_request_equivalents_per_day == 10_200
    assert ten.v1_idle_http_requests_per_day == 46_080_000
    assert ten.active_http_vs_v1_idle_fraction_isolated < 0.001

    hundred = active_budget(1_000, 100)
    assert hundred.calls_per_day == 100_000
    assert hundred.do_request_equivalents_per_day == 100_200
    assert hundred.active_http_vs_v1_idle_fraction_isolated < 0.01


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", type=int, default=1_000)
    parser.add_argument(
        "--calls-per-device-day",
        type=float,
        nargs="*",
        default=[1.0, 10.0, 100.0],
    )
    parser.add_argument(
        "--status-polls-per-call",
        type=float,
        default=OBSERVED_STATUS_POLLS_PER_CALL,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        self_check()

    rows = [
        active_budget(args.devices, calls, args.status_polls_per_call)
        for calls in args.calls_per_device_day
    ]

    if args.json:
        print(json.dumps(
            {
                "schema": "hara.commander-event-v2-active-1k-budget.v1",
                "observed_baseline": {
                    "calls": OBSERVED_CALLS,
                    "terminal_from_enqueue": OBSERVED_TERMINAL_FROM_ENQUEUE,
                    "status_polls": OBSERVED_STATUS_POLLS,
                    "status_polls_per_call": OBSERVED_STATUS_POLLS_PER_CALL,
                },
                "rows": [asdict(row) for row in rows],
            },
            indent=2,
            sort_keys=True,
        ))
    else:
        print(
            "devices | calls/dev/day | calls/day | status_polls/day | "
            "worker_http/day isolated | worker_http/day packed8 | do_req_eq/day"
        )
        for row in rows:
            print(
                f"{row.devices:>7} | "
                f"{row.calls_per_device_per_day:>13.1f} | "
                f"{row.calls_per_day:>9.0f} | "
                f"{row.status_poll_http_per_day:>16.0f} | "
                f"{row.worker_http_per_day_isolated:>24.0f} | "
                f"{row.worker_http_per_day_packed_8:>23.0f} | "
                f"{row.do_request_equivalents_per_day:>13.0f}"
            )

    if args.check:
        ten = active_budget(1_000, 10)
        hundred = active_budget(1_000, 100)
        print("COMMANDER_EVENT_V2_ACTIVE_1K_MODEL=PASS")
        print("COMMANDER_EVENT_V2_ACTIVE_BASELINE_TERMINAL_FROM_ENQUEUE=26/30")
        print("COMMANDER_EVENT_V2_ACTIVE_BASELINE_STATUS_POLLS=4/30")
        print("COMMANDER_EVENT_V2_1K_10_CALLS_DEVICE_DAY_TOTAL_CALLS=10000")
        print("COMMANDER_EVENT_V2_1K_10_CALLS_DEVICE_DAY_DO_REQ_EQ=10200")
        print(
            "COMMANDER_EVENT_V2_1K_10_CALLS_DEVICE_DAY_WORKER_HTTP_ISOLATED="
            + str(round(ten.worker_http_per_day_isolated))
        )
        print(
            "COMMANDER_EVENT_V2_1K_100_CALLS_DEVICE_DAY_WORKER_HTTP_ISOLATED="
            + str(round(hundred.worker_http_per_day_isolated))
        )
        print("COMMANDER_EVENT_V2_ACTIVE_D1_ROW_COST=MEASURE_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
