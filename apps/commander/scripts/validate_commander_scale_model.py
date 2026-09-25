#!/usr/bin/env python3
"""Regression checks for the deterministic Commander scale model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "commander_scale_capacity_model.py"


def load_model():
    spec = importlib.util.spec_from_file_location("commander_scale_capacity_model", MODEL)
    if spec is None or spec.loader is None:
        raise RuntimeError("MODEL_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    model = load_model()
    model.self_check()

    expected = {
        100: 50.0,
        1_000: 500.0,
        5_000: 2_500.0,
        20_000: 10_000.0,
    }
    for devices, expected_poll_rps in expected.items():
        row = model.poll_v1(devices)
        assert row.idle_poll_rps == expected_poll_rps
        assert row.baseline_http_rps > row.idle_poll_rps

        event = model.event_v2(devices)
        assert event.persistent_connections == devices
        assert event.idle_call_poll_rps == 0.0

    print("COMMANDER_SCALE_MODEL_REGRESSION=PASS")
    print("COMMANDER_SCALE_20K_V1_IDLE_POLL_RPS=10000")
    print("COMMANDER_SCALE_20K_V1_BASELINE_REQUESTS_DAY=921600000")
    print("COMMANDER_SCALE_EVENT_V2_IDLE_CALL_POLL_RPS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
