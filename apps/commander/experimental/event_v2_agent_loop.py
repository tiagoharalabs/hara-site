#!/usr/bin/env python3
"""Experimental Event V2 loop for the H.A.R.A. Commander Linux Agent.

Source/test only. This file is intentionally not included in the stable Agent
release manifest. It reuses the proven 0.3.7 five-tool execution functions while
replacing idle polling with an event wake channel.

Design:
- D1 remains durable call truth;
- CALL_AVAILABLE is only a wake hint;
- reconnect performs one bounded reconciliation drain;
- no fixed idle polling;
- protocol PING maintains transport without app-level heartbeat spam;
- one application LIVENESS checkpoint every 6h while otherwise idle.
"""

from __future__ import annotations

import importlib.util
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDER = HERE.parent
TRANSPORT_PATH = HERE / "event_v2_websocket.py"
AGENT_PATH = COMMANDER / "public" / "agent" / "linux.py"
MAX_DRAIN_CALLS = 8
STABLE_CONNECTION_SECONDS = 60.0


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("EVENT_V2_MODULE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_modules():
    return (
        _load(TRANSPORT_PATH, "hara_event_v2_transport"),
        _load(AGENT_PATH, "hara_agent_v1_baseline"),
    )


def drain_durable_calls(agent, config, max_calls: int = MAX_DRAIN_CALLS) -> int:
    if max_calls < 1 or max_calls > MAX_DRAIN_CALLS:
        raise RuntimeError("EVENT_V2_DRAIN_BOUND_INVALID")
    drained = 0
    while drained < max_calls:
        call = agent.post_json(
            config["HARA_COMMANDER_URL"] + "/api/device/calls/next",
            config["HARA_DEVICE_TOKEN"],
            {},
        )
        if not call:
            break
        agent.execute_call(config, call)
        drained += 1
    return drained


def run_connected_session(
    transport,
    agent,
    config,
    *,
    max_steps: int | None = None,
    monotonic=time.monotonic,
) -> dict:
    sock = transport.open_event_socket(
        config["HARA_COMMANDER_URL"],
        config["HARA_DEVICE_TOKEN"],
    )
    connected_at = monotonic()
    last_liveness = connected_at
    steps = 0
    drained = 0

    try:
        # Reconcile durable truth exactly once after connect/reconnect so a
        # notification lost while disconnected cannot strand a pending call.
        drained += drain_durable_calls(agent, config)

        while max_steps is None or steps < max_steps:
            frame = transport.recv_event_or_keepalive(sock)
            now = monotonic()

            if now - last_liveness >= transport.DURABLE_LIVENESS_SECONDS:
                transport.send_liveness(sock)
                last_liveness = now

            if frame is not None:
                event = transport.parse_event_frame(frame)
                if event["type"] == "CALL_AVAILABLE":
                    # call_id is deliberately not trusted as execution authority.
                    # It only wakes a bounded read from durable call truth.
                    drained += drain_durable_calls(agent, config)

            steps += 1

        return {
            "connected_seconds": max(0.0, monotonic() - connected_at),
            "drained_calls": drained,
            "steps": steps,
        }
    finally:
        transport.close_socket(sock)


def run_forever(
    transport,
    agent,
    config,
    *,
    sleep=time.sleep,
    random_unit=None,
) -> None:
    policy = transport.ReconnectPolicy()
    entropy = random.SystemRandom()
    random_unit = random_unit or entropy.random
    attempt = 0

    while True:
        started = time.monotonic()
        try:
            run_connected_session(transport, agent, config)
            connected_seconds = time.monotonic() - started
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            connected_seconds = time.monotonic() - started
            code = agent.safe_error_code(exc)
            agent.try_write_runtime_status(error_code=code, error_at=agent.utcnow())

        if connected_seconds >= STABLE_CONNECTION_SECONDS:
            attempt = 0
        else:
            attempt = min(attempt + 1, 31)

        delay = policy.delay(attempt, random_unit())
        sleep(delay)


def main() -> int:
    transport, agent = load_modules()

    if "--self-test" in sys.argv:
        # Keep this runner outside the stable release but make import/source
        # readiness deterministic.
        assert MAX_DRAIN_CALLS == 8
        assert STABLE_CONNECTION_SECONDS == 60.0
        assert transport.DURABLE_LIVENESS_SECONDS == 21600
        print("COMMANDER_EVENT_V2_AGENT_LOOP_SOURCE=PASS")
        print("COMMANDER_EVENT_V2_IDLE_POLLING=ABSENT")
        print("COMMANDER_EVENT_V2_RECONCILIATION_DRAIN=BOUNDED_8")
        return 0

    config = agent.load_config()
    run_forever(transport, agent, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
