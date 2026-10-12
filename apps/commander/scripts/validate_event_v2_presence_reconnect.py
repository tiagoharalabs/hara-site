#!/usr/bin/env python3
"""Offline regression for Event V2 presence deadlines across socket reconnects.

Exercises the actual Agent loop and transport reconnect policy with an injected
monotonic clock and scripted sockets. No real network, device, database, sleep,
or customer command is used. Idle durable reads stay bounded to one per socket.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOOP = ROOT / "apps/commander/experimental/event_v2_agent_loop.py"
TRANSPORT = ROOT / "apps/commander/experimental/event_v2_websocket.py"
CONFIG = {
    "HARA_COMMANDER_URL": "https://test.invalid",
    "HARA_DEVICE_TOKEN": "offline-fixture",
    "HARA_DEVICE_ID": "HARA-DEVICE-presence-reconnect-fixture",
}
checks = 0


def check(condition, label):
    global checks
    assert condition, label
    checks += 1


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError("PRESENCE_FIXTURE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self, initial=0.0):
        self.now = float(initial)
        self.sleeps = []

    def monotonic(self):
        return self.now

    def advance_to(self, target):
        target = target(self.now) if callable(target) else float(target)
        assert target >= self.now, "FAKE_CLOCK_REVERSED"
        self.now = target

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.now += delay


class Agent:
    def __init__(self):
        self.requests = []
        self.status = []
        self.errors = []

    def utcnow(self):
        return "2026-10-12T00:00:00Z"

    def try_write_event_v2_status(self, **kwargs):
        self.status.append(kwargs)
        return True

    def try_write_runtime_status(self, **kwargs):
        self.errors.append(kwargs)
        return True

    def safe_error_code(self, error):
        return str(error)

    def post_json(self, url, _token, payload):
        self.requests.append((url, payload))
        assert url.endswith("/api/device/calls/next"), "IDLE_EXTRA_HTTP_REQUEST"
        assert payload == {}, "IDLE_UNEXPECTED_REQUEST_PAYLOAD"
        return None

    def execute_call(self, _config, _call):
        raise AssertionError("UNEXPECTED_CUSTOMER_COMMAND")


class ScriptedTransport:
    DURABLE_LIVENESS_SECONDS = 21600

    def __init__(self, real_transport, clock, sessions, failed_sends=0):
        self.ReconnectPolicy = real_transport.ReconnectPolicy
        self.clock = clock
        self.sessions = sessions
        self.opened = 0
        self.closed = []
        self.frames = 0
        self.attempts = []
        self.successes = []
        self.failed_sends = failed_sends

    def open_event_socket(self, _url, _token):
        assert self.opened < len(self.sessions), "UNBOUNDED_RECONNECT_LOOP"
        sock = self.opened
        self.opened += 1
        return sock

    def recv_event_or_keepalive(self, sock):
        assert self.sessions[sock], "UNBOUNDED_SESSION_LOOP"
        action, at = self.sessions[sock].pop(0)
        self.clock.advance_to(at)
        self.frames += 1
        if action == "disconnect":
            raise RuntimeError("EVENT_V2_SERVER_CLOSED")
        if action == "stop":
            raise KeyboardInterrupt()
        assert action == "idle", "FIXTURE_EVENT_UNSUPPORTED"
        return None

    def send_liveness(self, sock, *_telemetry):
        self.attempts.append((sock, self.clock.now))
        if self.failed_sends:
            self.failed_sends -= 1
            raise RuntimeError("EVENT_V2_SEND_FAILED")
        self.successes.append((sock, self.clock.now))

    def close_socket(self, sock):
        self.closed.append(sock)


def run(sessions, *, failed_sends=0, initial=0):
    loop = load(LOOP, "hara_presence_loop_" + str(checks))
    real_transport = load(TRANSPORT, "hara_presence_transport_" + str(checks))
    clock = Clock(initial)
    agent = Agent()
    transport = ScriptedTransport(real_transport, clock, sessions, failed_sends)
    try:
        loop.run_forever(
            transport,
            agent,
            CONFIG,
            sleep=clock.sleep,
            random_unit=lambda: 0.5,
            monotonic=clock.monotonic,
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("FIXTURE_STOP_NOT_PROPAGATED")
    check(len(transport.closed) == transport.opened, "RECONNECT_SOCKET_LEAK")
    check(len(agent.requests) == transport.opened, "IDLE_RECONCILIATION_REQUEST_INFLATION")
    check(all(0 < delay <= 15 for delay in clock.sleeps), "RECONNECT_BUSY_LOOP_OR_BACKOFF_OVERSHOOT")
    return loop, real_transport, clock, agent, transport


def main():
    loop = load(LOOP, "hara_presence_loop_interval")
    interval = loop.durable_liveness_interval(CONFIG["HARA_DEVICE_ID"], 21600)
    check(20700 <= interval <= 22500, "EXISTING_6H_JITTER_CONTRACT_CHANGED")

    # Reconnect before the server's five-hour connect refresh threshold. The
    # last durable presence may still be the initial one: seven-hour TTL must
    # survive reconnect at 1h54 rather than moving this deadline to 7h54+.
    _, _, _, _, transport = run([
        [("disconnect", 6840)],
        [("idle", interval - 1), ("idle", interval),
         ("idle", interval + 60), ("stop", interval + 120)],
    ])
    check(transport.successes == [(1, interval)], "RECONNECT_RESET_DURABLE_DEADLINE")
    check(transport.successes[0][1] < 7 * 3600, "CONNECTED_DEVICE_WOULD_EXCEED_PRESENCE_TTL")
    print("COMMANDER_EVENT_V2_RECONNECT_PRESERVES_ORIGINAL_DEADLINE=PASS")

    # A later reconnect must retain the most recent successful checkpoint,
    # rather than either socket-connect time or process-start time.
    _, _, _, _, transport = run([
        [("idle", interval), ("disconnect", interval + 7200)],
        [("idle", 2 * interval - 1), ("idle", 2 * interval),
         ("idle", 2 * interval + 60), ("stop", 2 * interval + 120)],
    ])
    check(transport.successes == [(0, interval), (1, 2 * interval)],
          "RECONNECT_LOST_SUCCESSFUL_LIVENESS_CHECKPOINT")
    check(len(transport.attempts) == 2, "EARLY_OR_DUPLICATE_IDLE_LIVENESS")
    print("COMMANDER_EVENT_V2_RECONNECT_PRESERVES_SUCCESSFUL_CHECKPOINT=PASS")

    # Failed send must not consume the deadline: the replacement socket sends
    # at its next received keepalive, without waiting another six hours.
    _, _, clock, agent, transport = run([
        [("idle", interval)],
        [("idle", lambda now: now + 60), ("stop", lambda now: now + 60)],
    ], failed_sends=1)
    check(len(transport.attempts) == 2, "FAILED_SEND_ADVANCED_LIVENESS_DEADLINE")
    check(transport.attempts[0] == (0, interval), "FIRST_SEND_DEADLINE_CHANGED")
    check(len(transport.successes) == 1 and transport.successes[0][0] == 1,
          "FAILED_SEND_NOT_RETRIED_AFTER_RECONNECT")
    check(0 < transport.successes[0][1] - interval <= 75,
          "FAILED_SEND_RETRY_DELAY_EXCEEDS_TRANSPORT_AND_BACKOFF_BOUND")
    check(len(agent.errors) == 1 and clock.sleeps, "FAILED_SEND_DID_NOT_USE_RECONNECT_PATH")
    print("COMMANDER_EVENT_V2_FAILED_SEND_RETAINS_DEADLINE=PASS")

    # Repeated send failures remain due, but always leave the socket and use
    # the existing reconnect backoff. No tight application retry loop occurs.
    sessions = [[("idle", interval)]]
    sessions.extend([[("idle", lambda now: now)] for _ in range(5)])
    sessions.append([("idle", lambda now: now), ("stop", lambda now: now)])
    _, real_transport, clock, _, transport = run(sessions, failed_sends=6)
    expected_delays = [real_transport.ReconnectPolicy().delay(attempt, 0.5)
                       for attempt in [0, 1, 2, 3, 4, 5]]
    check(clock.sleeps == expected_delays, "FAILED_SEND_BYPASSED_EXISTING_BACKOFF")
    check(len(transport.attempts) == 7 and len(transport.successes) == 1,
          "REPEATED_FAILED_SEND_CHECKPOINT_LOST_OR_DUPLICATED")
    check(transport.successes[0][1] == interval + sum(expected_delays),
          "REPEATED_FAILED_SEND_RETRY_NOT_AT_NEXT_SESSION")
    print("COMMANDER_EVENT_V2_FAILED_SEND_RECONNECT_BACKOFF=PASS")

    # Many idle keepalives use transport frames only: no fixed HTTP polling
    # or extra durable liveness before the existing interval.
    idle = [("idle", i * 60) for i in range(1, 301)]
    idle.append(("stop", 18060))
    _, _, clock, agent, transport = run([idle])
    check(not transport.attempts, "IDLE_LIVENESS_REQUEST_INFLATION")
    check(len(agent.requests) == 1, "IDLE_FIXED_HTTP_POLLING")
    check(not clock.sleeps, "IDLE_SESSION_RECONNECTING_WITHOUT_FAILURE")
    print("COMMANDER_EVENT_V2_IDLE_KEEPALIVE_NO_EXTRA_HTTP=PASS")

    # Standalone bounded-session callers retain their own initial baseline.
    clock = Clock(123.0)
    real_transport = load(TRANSPORT, "hara_presence_transport_standalone")
    transport = ScriptedTransport(real_transport, clock, [[
        ("idle", 123 + interval - 1), ("idle", 123 + interval),
    ]])
    agent = Agent()
    result = loop.run_connected_session(
        transport, agent, CONFIG, max_steps=2, monotonic=clock.monotonic,
    )
    check(result["steps"] == 2, "STANDALONE_BOUNDED_API_CHANGED")
    check(transport.successes == [(0, 123 + interval)],
          "STANDALONE_BASELINE_OR_JITTER_CHANGED")
    check(transport.closed == [0], "STANDALONE_SOCKET_LEAK")
    print("COMMANDER_EVENT_V2_STANDALONE_SESSION_COMPATIBILITY=PASS")
    print(f"COMMANDER_EVENT_V2_PRESENCE_RECONNECT_REGRESSION={checks}/{checks}_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
