"""Offline heartbeat deadlines through the real .56 driver and wire reader.

Socket/clock boundaries are synthetic. No real socket, process, enrollment,
runtime status file, native service, or fallback HTTP endpoint is touched.
"""
import importlib.util
import json
from pathlib import Path
import socket
import struct
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch


AGENT_DIR = (Path(__file__).resolve().parents[1] /
             "release-candidates/commercial-0.3.56-source/agent")
DEV_ORIGIN = "https://hara-commander-r163-canary-20261024.tiago-sartori.workers.dev"
CONFIG = {
    "HARA_COMMANDER_URL": DEV_ORIGIN,
    "HARA_COMMANDER_ENVIRONMENT": "DEV",
    "HARA_COMMANDER_EVENT_V2_DEV_ENABLED": "true",
    "HARA_COMMANDER_TRANSPORT_MODE": "OUTBOUND_RELAY",
    "HARA_COMMANDER_APPROVAL_MODE": "PERSISTENT_TRUSTED",
    "HARA_DEVICE_ID": "synthetic-heartbeat-device",
    "HARA_TENANT_ID": "synthetic-heartbeat-tenant",
    "HARA_DEVICE_ARCH": "synthetic-test",
    "HARA_DEVICE_TOKEN": "synthetic-heartbeat-token-not-a-credential",
}


def server_frame(opcode, payload):
    payload = bytes(payload)
    if len(payload) >= 126:
        raise ValueError("fixture frame too large")
    return bytes([0x80 | opcode, len(payload)]) + payload


def import_source(name, filename):
    spec = importlib.util.spec_from_file_location(name, AGENT_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.now = 1.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


class SocketBoundary:
    """A TLS stream boundary with independently stalled read/write directions."""
    def __init__(self, clock, data=b"", *, probe_send_delay=0,
                 probe_send_failure=False, blocked_close=False, max_chunk=None):
        self.clock = clock
        self.data = bytes(data)
        self.timeout = 20.0
        self.closed = False
        self.probe_send_delay = probe_send_delay
        self.probe_send_failure = probe_send_failure
        self.blocked_close = blocked_close
        self.max_chunk = max_chunk
        self.sent = []
        self.reads = 0

    def settimeout(self, value):
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def pending(self):
        return len(self.data)

    def read(self, count):
        self.reads += 1
        if not self.data:
            self.clock.advance(self.timeout or 0)
            raise socket.timeout("synthetic incomplete peer frame")
        size = min(count, len(self.data), self.max_chunk or count)
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk

    def sendall(self, data):
        opcode = data[0] & 0x0F
        self.sent.append(bytes(data))
        if opcode == 1:
            self.clock.advance(self.probe_send_delay)
            if self.probe_send_failure:
                raise socket.timeout("synthetic failed probe send")
        if opcode == 8 and self.blocked_close:
            self.clock.advance(self.timeout or 0)
            raise socket.timeout("synthetic blocked graceful close")

    def shutdown(self, _how):
        pass

    def close(self):
        self.closed = True


class Gate:
    def __init__(self):
        self.notifications = 0

    def notify(self):
        self.notifications += 1


class AdversarialHeartbeatTests(unittest.TestCase):
    def setUp(self):
        suffix = self.id().rsplit(".", 1)[-1]
        self.driver = import_source("r163_adversarial_driver_" + suffix, "event_v2_dev.py")
        self.wire = import_source("r163_adversarial_wire_" + suffix, "event_v2_wire.py")
        self.agent = import_source("r163_adversarial_agent_" + suffix, "linux.py")
        self.clock = Clock()
        self.gate = Gate()
        self.progress = []
        self.status = []
        self.callbacks = SimpleNamespace(
            _relay_progress=lambda kind, **fields: self.progress.append((self.clock.now, kind, fields)),
            try_write_runtime_status=lambda **fields: self.status.append(fields),
            utcnow=lambda: "2026-10-25T00:00:00Z",
        )

    def close_frame(self, code=4003):
        return server_frame(8, struct.pack("!H", code))

    def run_session(self, stream, *, handshake_delay=0):
        def open_socket(origin, token):
            self.assertEqual(origin, CONFIG["HARA_COMMANDER_URL"])
            self.assertEqual(token, CONFIG["HARA_DEVICE_TOKEN"])
            self.clock.advance(handshake_delay)
            return stream
        with patch.object(self.wire, "open_event_socket", side_effect=open_socket), \
             patch.object(self.wire.time, "monotonic", side_effect=self.clock.monotonic), \
             patch.object(self.driver.select, "select", return_value=([stream], [], [])):
            self.driver.run_session(self.callbacks, CONFIG, self.gate, self.wire,
                                    liveness_state={"at": 1.0}, monotonic=self.clock.monotonic)

    def test_handshake_plus_probe_send_does_not_exceed_guardian_silence_budget(self):
        stream = SocketBoundary(self.clock,
                                server_frame(1, self.driver.ACK.encode()) + self.close_frame(),
                                probe_send_delay=20)
        started = self.clock.now
        with self.assertRaisesRegex(RuntimeError, "EVENT_V2_AUTHORIZATION_ENDED"):
            self.run_session(stream, handshake_delay=25)
        attempts = [at for at, kind, _fields in self.progress if kind == "HEARTBEAT_ATTEMPT"]
        self.assertTrue(attempts)
        gaps = [later - earlier for earlier, later in zip([started, *attempts[:-1]], attempts)]
        self.assertLessEqual(max(gaps), self.agent.RELAY_WORKER_TIMEOUT_SECONDS,
                             "sequential bounded I/O consumed a guardian restart before reporting progress")
        self.assertEqual(sum(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress), 1)

    def test_partial_probe_frame_timeout_does_not_wait_again_for_graceful_close(self):
        partial = server_frame(1, self.driver.ACK.encode())[:5]
        stream = SocketBoundary(self.clock, partial, blocked_close=True)
        started = self.clock.now
        with self.assertRaises((socket.timeout, RuntimeError)):
            self.run_session(stream)
        self.assertTrue(stream.closed)
        self.assertLessEqual(self.clock.now - started, self.agent.RELAY_WORKER_TIMEOUT_SECONDS,
                             "probe timeout was followed by another full socket timeout during teardown")
        self.assertFalse(any(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress))
        self.assertEqual(self.gate.notifications, 0)

    def test_partial_ack_across_upgrade_remainder_is_confirmed_once_and_then_revoked(self):
        ack = server_frame(1, self.driver.ACK.encode())
        stream = SocketBoundary(self.clock, ack[3:] + self.close_frame(), max_chunk=2)
        self.wire._UPGRADE_REMAINDER[stream] = ack[:3]
        with self.assertRaisesRegex(RuntimeError, "EVENT_V2_AUTHORIZATION_ENDED"):
            self.run_session(stream)
        self.assertTrue(stream.closed)
        self.assertGreater(stream.reads, 3)
        self.assertEqual(sum(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress), 1)
        self.assertEqual(self.gate.notifications, 1)
        self.assertEqual(len(self.status), 1)

    def test_protocol_ping_and_pong_do_not_confirm_health_or_wake_executor(self):
        stream = SocketBoundary(self.clock, server_frame(9, b"synthetic") +
                                server_frame(10, b"synthetic") + self.close_frame())
        with self.assertRaisesRegex(RuntimeError, "EVENT_V2_AUTHORIZATION_ENDED"):
            self.run_session(stream)
        self.assertIn(10, [data[0] & 0x0F for data in stream.sent])
        self.assertFalse(any(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress))
        self.assertEqual(self.gate.notifications, 0)

    def test_duplicate_probe_ack_is_not_an_extra_health_confirmation(self):
        ack = server_frame(1, self.driver.ACK.encode())
        stream = SocketBoundary(self.clock, ack + ack)
        with self.assertRaisesRegex(RuntimeError, "EVENT_V2_UNSOLICITED_PROBE_ACK"):
            self.run_session(stream)
        self.assertTrue(stream.closed)
        self.assertEqual(sum(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress), 1)
        self.assertEqual(self.gate.notifications, 1)

    def test_failed_probe_send_closes_without_claiming_health_or_notifying(self):
        stream = SocketBoundary(self.clock, probe_send_failure=True)
        with self.assertRaises(socket.timeout):
            self.run_session(stream)
        self.assertTrue(stream.closed)
        self.assertFalse(any(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress))
        self.assertEqual(self.gate.notifications, 0)

    def test_real_0356_wrapper_keeps_module_identity_and_revokes_without_http_fallback(self):
        wake = json.dumps({"schema": self.wire.EVENT_SCHEMA, "type": "CALL_AVAILABLE",
                           "call_id": "synthetic-durable-call"}).encode()
        stream = SocketBoundary(self.clock, server_frame(1, self.driver.ACK.encode()) +
                                server_frame(1, wake) + self.close_frame())
        signal = threading.BoundedSemaphore(1)
        signal.acquire()
        config = {**CONFIG, "_event_v2_wake_signal": signal}
        real_session = self.driver.run_session

        def session(agent, cfg, gate, wire, **kwargs):
            self.assertIs(agent, self.agent)
            return real_session(agent, cfg, gate, wire, monotonic=self.clock.monotonic, **kwargs)

        with patch.object(self.agent, "event_v2_dev_module", return_value=self.driver), \
             patch.object(self.agent, "_relay_progress", self.callbacks._relay_progress), \
             patch.object(self.agent, "try_write_runtime_status", self.callbacks.try_write_runtime_status), \
             patch.object(self.agent, "post_json", side_effect=AssertionError("HTTP fallback was not admitted")) as http, \
             patch.object(self.driver, "load_wire", return_value=self.wire), \
             patch.object(self.driver, "progress_sleep"), \
             patch.object(self.driver, "run_session", side_effect=session), \
             patch.object(self.wire, "open_event_socket", return_value=stream), \
             patch.object(self.wire.time, "monotonic", side_effect=self.clock.monotonic), \
             patch.object(self.driver.select, "select", return_value=([stream], [], [])):
            self.agent._event_v2_heartbeat_worker(config, None)
        http.assert_not_called()
        self.assertTrue(stream.closed)
        self.assertEqual(sum(kind == "HEARTBEAT_CONFIRMED" for _at, kind, _fields in self.progress), 1)
        self.assertEqual([fields["code"] for _at, kind, fields in self.progress if kind == "REVOKED"],
                         ["EVENT_V2_AUTHORIZATION_ENDED"])
        self.assertTrue(signal.acquire(blocking=False))
        self.assertFalse(signal.acquire(blocking=False), "wake hints stopped being coalesced")


if __name__ == "__main__":
    unittest.main()
