#!/usr/bin/env python3
"""Polling V1 compatibility loop for the Commander customer release candidate.

This preserves the proven heartbeat/poll transport as rollback while using the
customer-plane execution adapter so receipts/health remain HARA_COMMANDER-owned.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDER = HERE.parent
AGENT_PATH = COMMANDER / "experimental" / "event_v2_customer_agent.py"

HEARTBEAT_SECONDS = 30.0
POLL_SECONDS = 2.0


def load_agent():
    spec = importlib.util.spec_from_file_location(
        "hara_commander_rc_customer_agent",
        AGENT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("COMMANDER_RC_CUSTOMER_AGENT_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_forever(agent, config, *, sleep=time.sleep, monotonic=time.monotonic) -> None:
    last_heartbeat = 0.0
    last_error_code = None
    last_error_write = 0.0

    while True:
        now = monotonic()
        try:
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                agent.post_json(
                    config["HARA_COMMANDER_URL"] + "/api/device/heartbeat",
                    config["HARA_DEVICE_TOKEN"],
                    {
                        "device_id": config["HARA_DEVICE_ID"],
                        "architecture": config["HARA_DEVICE_ARCH"],
                        "agent_version": agent.BASELINE.AGENT_VERSION,
                    },
                )
                last_heartbeat = now
                last_error_code = None
                agent.try_write_runtime_status(
                    heartbeat_at=agent.utcnow(),
                    error_code=None,
                    error_at=None,
                )

            call = agent.post_json(
                config["HARA_COMMANDER_URL"] + "/api/device/calls/next",
                config["HARA_DEVICE_TOKEN"],
                {},
            )
            if call:
                agent.execute_call(config, call)
        except Exception as exc:
            code = agent.safe_error_code(exc)
            if code != last_error_code or now - last_error_write >= 60:
                agent.try_write_runtime_status(
                    error_code=code,
                    error_at=agent.utcnow(),
                )
                last_error_code = code
                last_error_write = now
        sleep(POLL_SECONDS)


def self_test() -> None:
    agent = load_agent()
    assert HEARTBEAT_SECONDS == 30.0
    assert POLL_SECONDS == 2.0
    assert agent.OPERATIONAL_AUTHORITY == "HARA_COMMANDER"
    assert agent.TRANSPORT_MODE == "EVENT_V2"
    print("COMMANDER_AGENT_RC_POLL_V1_LOOP=PASS")
    print("COMMANDER_AGENT_RC_POLL_V1_AUTHORITY=HARA_COMMANDER")
    print("COMMANDER_AGENT_RC_POLL_V1_HEARTBEAT_SECONDS=30")
    print("COMMANDER_AGENT_RC_POLL_V1_POLL_SECONDS=2")


def main() -> int:
    agent = load_agent()
    if "--self-test" in sys.argv:
        self_test()
        return 0
    config = agent.load_config()
    run_forever(agent, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
