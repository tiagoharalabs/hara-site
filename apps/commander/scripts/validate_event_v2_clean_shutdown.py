#!/usr/bin/env python3
"""Prove Event V2 shutdown publishes connected=false on unwind."""

from __future__ import annotations

import importlib.util
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOOP = ROOT / "apps/commander/experimental/event_v2_agent_loop.py"
INSTALLER = ROOT / "apps/commander/candidate/install_linux_rc.sh"


def load_loop():
    spec = importlib.util.spec_from_file_location("hara_event_v2_shutdown_validation", LOOP)
    if spec is None or spec.loader is None:
        raise AssertionError("EVENT_V2_LOOP_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    DURABLE_LIVENESS_SECONDS = 21600

    def __init__(self):
        self.closed = 0

    def open_event_socket(self, _url, _token):
        return object()

    def recv_event_or_keepalive(self, _sock):
        raise KeyboardInterrupt()

    def close_socket(self, _sock):
        self.closed += 1


class FakeAgent:
    def __init__(self):
        self.status = []
        self.calls = 0

    def utcnow(self):
        self.calls += 1
        return f"2026-09-26T02:00:0{self.calls}+00:00"

    def try_write_event_v2_status(self, **kwargs):
        self.status.append(dict(kwargs))
        return True

    def post_json(self, _url, _token, _payload):
        return None

    def execute_call(self, _config, _call):
        raise AssertionError("NO_CALL_EXPECTED")


def main() -> int:
    loop = load_loop()

    try:
        loop._shutdown_signal(signal.SIGTERM, None)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("SIGTERM_HANDLER_DID_NOT_UNWIND")

    transport = FakeTransport()
    agent = FakeAgent()
    config = {
        "HARA_COMMANDER_URL": "https://dev.invalid",
        "HARA_DEVICE_TOKEN": "test",
    }

    try:
        loop.run_connected_session(
            transport,
            agent,
            config,
            max_steps=None,
            monotonic=lambda: 1.0,
        )
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("SESSION_INTERRUPT_NOT_PROPAGATED")

    assert transport.closed == 1
    assert len(agent.status) == 2
    assert agent.status[0]["connected"] is True
    assert agent.status[1]["connected"] is False
    assert agent.status[1]["disconnected_at_utc"]

    low = loop.durable_liveness_interval("device-a", 21600)
    high = loop.durable_liveness_interval("device-b", 21600)
    assert 20700 <= low <= 22500
    assert 20700 <= high <= 22500
    assert low != high

    source = LOOP.read_text(encoding="utf-8")
    assert "signal.signal(signal.SIGTERM, _shutdown_signal)" in source
    assert "install_shutdown_handlers()" in source
    assert "except KeyboardInterrupt:" in source
    assert "termination is a normal exit" in source

    installer = INSTALLER.read_text(encoding="utf-8")
    assert 'event_connected=STALE' in installer
    assert '[ "$rc" != "ACTIVE" ]' in installer

    print("COMMANDER_EVENT_V2_SIGTERM_SHUTDOWN=PASS")
    print("COMMANDER_EVENT_V2_SIGTERM_STATUS_FALSE=PASS")
    print("COMMANDER_EVENT_V2_SOCKET_CLOSE_ON_SHUTDOWN=PASS")
    print("COMMANDER_EVENT_V2_TOPLEVEL_SHUTDOWN_TRACEBACK=ABSENT_BY_CONTRACT")
    print("COMMANDER_AGENT_RC_STALE_CONNECTED_STATUS=DENY")
    print("COMMANDER_EVENT_V2_LINUX_LIVENESS_JITTER=DETERMINISTIC_+/-15M")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
