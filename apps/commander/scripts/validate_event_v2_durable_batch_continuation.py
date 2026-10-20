#!/usr/bin/env python3
"""Exercise reconnect reconciliation without a second wake notification."""
from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "experimental/event_v2_agent_loop.py"
TRANSPORT = Path(__file__).resolve().parents[1] / "experimental/event_v2_websocket.py"
spec = importlib.util.spec_from_file_location("hara_event_v2_batch_regression", LOOP)
assert spec and spec.loader
loop = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = loop
spec.loader.exec_module(loop)

CONFIG = {
    "HARA_COMMANDER_URL": "https://fixture.invalid",
    "HARA_DEVICE_TOKEN": "fixture-token",
    "HARA_DEVICE_ID": "fixture-device",
}


class Agent:
    def __init__(self, count, revoke_after=None):
        self.pending = [{"call_id": str(i)} for i in range(count)]
        self.executed = []
        self.reads = 0
        self.status = []
        self.revoke_after = revoke_after

    def utcnow(self):
        return "2026-10-20T00:00:00Z"

    def try_write_event_v2_status(self, **state):
        self.status.append(state)
        return True

    def post_json(self, url, token, payload):
        assert url.endswith("/api/device/calls/next")
        assert token == CONFIG["HARA_DEVICE_TOKEN"] and payload == {}
        self.reads += 1
        if self.revoke_after is not None and len(self.executed) >= self.revoke_after:
            raise RuntimeError("DEVICE_REVOKED")
        return self.pending.pop(0) if self.pending else None

    def execute_call(self, config, call):
        assert config is CONFIG
        self.executed.append(call["call_id"])


class Transport:
    DURABLE_LIVENESS_SECONDS = 21600

    def __init__(self):
        self.recv_intervals = []
        self.closed = 0

    def open_event_socket(self, url, token):
        assert url == CONFIG["HARA_COMMANDER_URL"]
        assert token == CONFIG["HARA_DEVICE_TOKEN"]
        return object()

    def recv_event_or_keepalive(self, sock):
        self.recv_intervals.append(None)
        return None

    def recv_event_if_ready(self, sock, timeout):
        self.recv_intervals.append(timeout)
        return None

    def close_socket(self, sock):
        self.closed += 1


for count in (0, 1, 8, 9, 12, 16):
    agent, transport = Agent(count), Transport()
    result = loop.run_connected_session(transport, agent, CONFIG, max_steps=4)
    assert agent.executed == [str(i) for i in range(count)], (count, agent.executed)
    assert agent.pending == [], count
    assert result["drained_calls"] == count
    assert transport.closed == 1 and agent.status[-1]["connected"] is False
    assert agent.reads == count + 1, (count, agent.reads)
    assert transport.recv_intervals[-1] is None, count
    if count >= loop.MAX_DRAIN_CALLS:
        assert 0 < transport.recv_intervals[0] <= 1, (count, transport.recv_intervals)
    else:
        assert all(interval is None for interval in transport.recv_intervals)
print("COMMANDER_EVENT_V2_RECONNECT_BATCH_COUNTS_0_1_8_9_12_16=PASS")

agent, transport = Agent(12, revoke_after=8), Transport()
try:
    loop.run_connected_session(transport, agent, CONFIG, max_steps=4)
except RuntimeError as exc:
    assert str(exc) == "DEVICE_REVOKED"
else:
    raise AssertionError("REVOCATION_NOT_HONORED_BETWEEN_BATCHES")
assert agent.executed == [str(i) for i in range(8)]
assert len(agent.pending) == 4
assert len(set(agent.executed)) == 8
assert transport.closed == 1 and agent.status[-1]["connected"] is False
print("COMMANDER_EVENT_V2_REVOKE_BETWEEN_BATCHES_NO_REPLAY=PASS")

# A short backlog probe must not impose its timeout on a partially delivered
# frame. The remaining bytes arrive after the probe interval.
transport_spec = importlib.util.spec_from_file_location("hara_event_v2_batch_transport", TRANSPORT)
assert transport_spec and transport_spec.loader
wire = importlib.util.module_from_spec(transport_spec)
sys.modules[transport_spec.name] = wire
transport_spec.loader.exec_module(wire)
class ReadSocket:
    def __init__(self, sock):
        self.sock = sock

    def read(self, count):
        return self.sock.recv(count)

    def pending(self):
        return 0

    def fileno(self):
        return self.sock.fileno()

    def gettimeout(self):
        return self.sock.gettimeout()

    def settimeout(self, timeout):
        self.sock.settimeout(timeout)


left, right = socket.socketpair()
reader = ReadSocket(left)
try:
    assert wire.recv_event_if_ready(reader, 0.001) is None
    frame = b'\x81\x02{}'
    right.sendall(frame[:1])
    sender = threading.Thread(target=lambda: (time.sleep(0.06), right.sendall(frame[1:])))
    sender.start()
    received = wire.recv_event_if_ready(reader, 0.001)
    sender.join(timeout=1)
    assert not sender.is_alive()
    assert received and received.payload == b"{}"
finally:
    left.close()
    right.close()
print("COMMANDER_EVENT_V2_BACKLOG_PROBE_PRESERVES_PARTIAL_FRAME=PASS")

class PendingResultAgent(Agent):
    def __init__(self):
        super().__init__(1)
        self.flushed = 0

    def flush_completion_outbox(self, config):
        self.flushed += 1
        return 0

    def completion_outbox_pending(self):
        return 1


pending = PendingResultAgent()
try:
    loop.drain_durable_calls(pending, CONFIG)
except RuntimeError as exc:
    assert str(exc) == "EVENT_V2_RESULT_DELIVERY_PENDING"
else:
    raise AssertionError("NEW_CALL_CLAIMED_WITH_UNDELIVERED_RESULT")
assert pending.flushed == 1 and pending.reads == 0 and pending.executed == []
print("COMMANDER_EVENT_V2_PENDING_RESULT_BLOCKS_NEW_CLAIM=PASS")
