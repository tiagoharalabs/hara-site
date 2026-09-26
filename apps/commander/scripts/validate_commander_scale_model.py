#!/usr/bin/env python3
"""Regression checks for the deterministic Commander scale model."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "commander_scale_capacity_model.py"
ACTIVE_MODEL = ROOT / "commander_event_v2_active_1k_model.py"
TRANSIENT_MODEL = ROOT / "commander_event_v2_transient_1k_model.py"


def load_model():
    return runpy.run_path(str(MODEL))


def load_active_model():
    return runpy.run_path(str(ACTIVE_MODEL))


def main() -> int:
    model = load_model()
    model["self_check"]()
    active = load_active_model()
    active["self_check"]()
    transient = runpy.run_path(str(TRANSIENT_MODEL))
    transient["self_check"]()

    expected = {
        100: 50.0,
        1_000: 500.0,
        5_000: 2_500.0,
        20_000: 10_000.0,
    }
    for devices, expected_poll_rps in expected.items():
        row = model["poll_v1"](devices)
        assert row.idle_poll_rps == expected_poll_rps
        assert row.baseline_http_rps > row.idle_poll_rps

        event = model["event_v2"](devices)
        assert event.persistent_connections == devices
        assert event.idle_call_poll_rps == 0.0

    print("COMMANDER_SCALE_MODEL_REGRESSION=PASS")
    print("COMMANDER_SCALE_20K_V1_IDLE_POLL_RPS=10000")
    print("COMMANDER_SCALE_20K_V1_BASELINE_REQUESTS_DAY=921600000")
    ten = active["active_budget"](1_000, 10)
    hundred = active["active_budget"](1_000, 100)
    assert round(ten.worker_http_per_day_isolated) == 41_333
    assert round(hundred.worker_http_per_day_isolated) == 413_333
    assert ten.do_request_equivalents_per_day == 10_200
    transient_ten = transient["transient_budget"](1_000, 10, 0.5)
    assert transient_ten.worker_http_day == 10_000
    assert transient_ten.do_request_equivalents_day == 10_700
    assert transient_ten.do_duration_gb_seconds_month == 18_750

    print("COMMANDER_SCALE_EVENT_V2_IDLE_CALL_POLL_RPS=0")
    print("COMMANDER_SCALE_EVENT_V2_ACTIVE_1K_MODEL=PASS")
    print("COMMANDER_SCALE_EVENT_V2_1K_10_CALLS_DEVICE_DAY_HTTP=41333")
    print("COMMANDER_SCALE_EVENT_V2_1K_100_CALLS_DEVICE_DAY_HTTP=413333")
    print("COMMANDER_SCALE_EVENT_V2_TRANSIENT_1K_10_CALLS_DEVICE_DAY_HTTP=10000")
    print("COMMANDER_SCALE_EVENT_V2_TRANSIENT_1K_10_CALLS_DEVICE_DAY_DO_REQ_EQ=10700")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
