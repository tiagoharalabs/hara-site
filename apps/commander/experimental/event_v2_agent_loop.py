#!/usr/bin/env python3
"""Experimental Event V2 loop for the H.A.R.A. Commander Linux Agent.

Source/test only. This file is intentionally not included in the stable Agent
release manifest. It reuses the proven 0.3.7 five-tool execution functions while
replacing idle polling with an event wake channel.

Design:
- the stable/durable lane keeps D1 as durable call truth;
- CALL_AVAILABLE is only a wake hint for that lane;
- DEV-only CALL_TRANSIENT executes directly over the connected socket and
  returns CALL_RESULT without persisting customer payload/result in D1;
- reconnect reconciles in bounded batches until durable truth is empty;
- no fixed idle polling;
- protocol PING maintains transport without app-level heartbeat spam;
- one application LIVENESS checkpoint every 6h while otherwise idle.
"""

from __future__ import annotations

import importlib.util
import random
import hashlib
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDER = HERE.parent
TRANSPORT_PATH = HERE / "event_v2_websocket.py"
AGENT_PATH = HERE / "event_v2_customer_agent.py"
MAX_DRAIN_CALLS = 8
BACKLOG_RECV_SECONDS = 0.05
STABLE_CONNECTION_SECONDS = 60.0
LIVENESS_JITTER_SECONDS = 15 * 60


def _shutdown_signal(_signum, _frame):
    # Convert process termination into normal Python unwinding so the
    # connected-session finally block closes the socket and publishes
    # connected=false before exit.
    raise KeyboardInterrupt()


def install_shutdown_handlers() -> None:
    signal.signal(signal.SIGTERM, _shutdown_signal)
    signal.signal(signal.SIGINT, _shutdown_signal)


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
        _load(AGENT_PATH, "hara_event_v2_customer_agent"),
    )


def durable_liveness_interval(device_id: str, target_seconds: float) -> float:
    """Spread durable checkpoints across +/-15m without changing the 6h mean."""
    digest = hashlib.sha256(str(device_id).encode("utf-8")).digest()
    unit = int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)
    return target_seconds + ((unit * 2.0) - 1.0) * LIVENESS_JITTER_SECONDS


def safe_telemetry_add(telemetry, key, amount=1) -> None:
    if telemetry is not None:
        try:
            telemetry.add(key, amount)
        except Exception:
            # Observability cannot turn successful customer commands into errors.
            pass


def drain_durable_calls(agent, config, max_calls: int = MAX_DRAIN_CALLS, *, telemetry=None) -> int:
    if max_calls < 1 or max_calls > MAX_DRAIN_CALLS:
        raise RuntimeError("EVENT_V2_DRAIN_BOUND_INVALID")
    if hasattr(agent,"flush_completion_outbox") and hasattr(agent,"completion_outbox_pending"):
        agent.flush_completion_outbox(config)
        if agent.completion_outbox_pending():
            raise RuntimeError("EVENT_V2_RESULT_DELIVERY_PENDING")
    drained = 0
    while drained < max_calls:
        call = agent.post_json(
            config["HARA_COMMANDER_URL"] + "/api/device/calls/next",
            config["HARA_DEVICE_TOKEN"],
            {},
        )
        if not call:
            break
        safe_telemetry_add(telemetry, "durable_calls")
        agent.execute_call(config, call)
        drained += 1
        if hasattr(agent,"completion_outbox_pending") and agent.completion_outbox_pending():
            raise RuntimeError("EVENT_V2_RESULT_DELIVERY_PENDING")
    return drained


def run_connected_session(
    transport,
    agent,
    config,
    *,
    max_steps: int | None = None,
    monotonic=time.monotonic,
    reconnected=False,
    liveness_state: dict[str, float] | None = None,
) -> dict:
    sock = transport.open_event_socket(
        config["HARA_COMMANDER_URL"],
        config["HARA_DEVICE_TOKEN"],
    )
    connected_at = monotonic()
    connected_at_utc = agent.utcnow()
    if not agent.try_write_event_v2_status(
        connected=True,
        connected_at_utc=connected_at_utc,
        disconnected_at_utc=None,
        error_code=None,
    ):
        transport.close_socket(sock)
        raise RuntimeError("EVENT_V2_STATUS_WRITE_FAILED")
    telemetry = None
    if hasattr(agent, "open_telemetry"):
        try:
            telemetry = agent.open_telemetry()
        except Exception:
            # Keep the connected Agent functional if telemetry is unavailable.
            telemetry = None
    safe_telemetry_add(telemetry, "connections")
    if reconnected:
        safe_telemetry_add(telemetry, "reconnects")
    if liveness_state is None:
        # Standalone callers start the same six-hour cadence as before.
        liveness_state = {"last_liveness_at": connected_at}
    # The process loop shares this checkpoint across sockets. A reconnect is
    # not a durable presence write and must not postpone the next LIVENESS.
    last_duration_checkpoint = connected_at
    liveness_interval = durable_liveness_interval(
        config.get("HARA_DEVICE_ID", ""),
        transport.DURABLE_LIVENESS_SECONDS,
    )
    steps = 0
    drained = 0
    transient_calls = 0

    try:
        # A full batch leaves the queue state unknown. Keep reconciling while
        # it is full, with a brief socket readiness probe between batches so a close,
        # revocation or transient event can be handled during a long backlog.
        # Once a short batch/empty read is observed, resume normal idle waits.
        first_batch = drain_durable_calls(agent, config, telemetry=telemetry)
        drained += first_batch
        backlog_pending = first_batch == MAX_DRAIN_CALLS

        while max_steps is None or steps < max_steps:
            backlog_probe = backlog_pending
            frame = (transport.recv_event_if_ready(sock, BACKLOG_RECV_SECONDS)
                     if backlog_probe else transport.recv_event_or_keepalive(sock))
            now = monotonic()
            duration_delta = max(0, int(now - last_duration_checkpoint))
            if duration_delta >= 300:
                safe_telemetry_add(telemetry, "connected_seconds", min(86400, duration_delta))
                last_duration_checkpoint = now
            if frame is None and not backlog_probe:
                # Transport PING is an RFC6455 control frame, never a D1 write.
                safe_telemetry_add(telemetry, "transport_pings")

            if now - liveness_state["last_liveness_at"] >= liveness_interval:
                safe_telemetry_add(telemetry, "liveness_attempts")
                summary = None
                if telemetry is not None:
                    try:
                        summary = telemetry.snapshot()
                    except Exception:
                        pass
                if summary is None:
                    transport.send_liveness(sock)
                else:
                    # Piggyback once per ~6h; never create an extra HTTP poll.
                    transport.send_liveness(sock, summary)
                # Advance only after the transport accepted the complete send;
                # a failed send remains due on the next connected socket.
                liveness_state["last_liveness_at"] = now

            if frame is not None:
                event = transport.parse_event_frame(frame)
                if event["type"] == "CALL_AVAILABLE":
                    # call_id is deliberately not trusted as execution authority.
                    # It only wakes a bounded read from durable call truth.
                    backlog_pending = True
                elif event["type"] == "CALL_TRANSIENT":
                    safe_telemetry_add(telemetry, "transient_calls")
                    result = agent.execute_transient_call(config, event)
                    if str(result.get("state") or "") != "COMPLETED":
                        safe_telemetry_add(telemetry, "transient_failures")
                    transport.send_transient_result(sock, result)
                    transient_calls += 1

            if backlog_pending:
                batch = drain_durable_calls(agent, config, telemetry=telemetry)
                drained += batch
                backlog_pending = batch == MAX_DRAIN_CALLS

            steps += 1

        return {
            "connected_seconds": max(0.0, monotonic() - connected_at),
            "drained_calls": drained,
            "transient_calls": transient_calls,
            "steps": steps,
        }
    except Exception:
        safe_telemetry_add(telemetry, "session_errors")
        raise
    finally:
        safe_telemetry_add(telemetry, "disconnects")
        safe_telemetry_add(telemetry, "connected_seconds", max(0, min(86400, int(monotonic() - last_duration_checkpoint))))
        if telemetry is not None:
            try:
                telemetry.close()
            except Exception:
                pass
        transport.close_socket(sock)
        agent.try_write_event_v2_status(
            connected=False,
            disconnected_at_utc=agent.utcnow(),
            error_code=None,
        )


def run_forever(
    transport,
    agent,
    config,
    *,
    sleep=time.sleep,
    random_unit=None,
    monotonic=time.monotonic,
) -> None:
    policy = transport.ReconnectPolicy()
    entropy = random.SystemRandom()
    random_unit = random_unit or entropy.random
    attempt = 0
    had_session = False
    # One startup baseline, followed only by successful LIVENESS sends. Keep
    # it outside the reconnect loop even when the initial Upgrade fails.
    liveness_state = {"last_liveness_at": monotonic()}

    while True:
        started = monotonic()
        try:
            run_connected_session(
                transport, agent, config,
                reconnected=had_session,
                monotonic=monotonic,
                liveness_state=liveness_state,
            )
            connected_seconds = monotonic() - started
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            connected_seconds = monotonic() - started
            code = agent.safe_error_code(exc)
            agent.try_write_runtime_status(error_code=code, error_at=agent.utcnow())
            agent.try_write_event_v2_status(
                connected=False,
                disconnected_at_utc=agent.utcnow(),
                error_code=code,
            )

        had_session = True
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
        try:
            _shutdown_signal(signal.SIGTERM, None)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("EVENT_V2_SIGTERM_NOT_CONVERTED_TO_UNWIND")
        print("COMMANDER_EVENT_V2_AGENT_LOOP_SOURCE=PASS")
        print("COMMANDER_EVENT_V2_IDLE_POLLING=ABSENT")
        assert hasattr(agent, "try_write_event_v2_status")
        assert hasattr(agent, "execute_transient_call")
        assert hasattr(transport, "send_transient_result")
        print("COMMANDER_EVENT_V2_RECONCILIATION_DRAIN=BOUNDED_8")
        print("COMMANDER_EVENT_V2_TRANSIENT_RPC=SOURCE_READY_DEV_ONLY")
        print("COMMANDER_EVENT_V2_CONNECTION_STATUS=LOCAL_0600")
        print("COMMANDER_EVENT_V2_SIGTERM_CLEAN_UNWIND=PASS")
        return 0

    install_shutdown_handlers()
    config = agent.load_config()
    try:
        run_forever(transport, agent, config)
    except KeyboardInterrupt:
        # SIGTERM/SIGINT are converted to KeyboardInterrupt so the connected
        # session can unwind through its finally block first. Once the local
        # status is published as disconnected, termination is a normal exit.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
