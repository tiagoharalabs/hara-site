#!/usr/bin/env python3
"""#163 P0-1 source regressions. Fake TLS/clock only; no network or credentials.

Tests load this staging area's experimental transport and actual reconnect loop.
Reconnect values below are client policy, not Cloudflare capacity or admission.
All checks use unittest and remain active under python -O.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1]
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, APP / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("P01_TEST_SOURCE_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(float(seconds))
        self.now += seconds


class PlainSocket:
    def __init__(self, timeout=25.0):
        self.timeout = timeout
        self.closed = False

    def settimeout(self, timeout):
        self.timeout = timeout

    def gettimeout(self):
        return self.timeout

    def close(self):
        self.closed = True


def server_event(call_id):
    payload = json.dumps({"schema": "hara.commander-device-event.v2",
                          "type": "CALL_AVAILABLE", "call_id": call_id},
                         separators=(",", ":")).encode()
    if len(payload) >= 126:
        raise RuntimeError("P01_TEST_FRAME_TOO_LONG")
    return bytes([0x81, len(payload)]) + payload


class FakeTLS(PlainSocket):
    """Generate Upgrade from the random key in the real outgoing request.

    Read delays obey a per-recv socket timeout. Fragmented headers can therefore
    reveal a missing total monotonic deadline without any real sleeping.
    """
    def __init__(self, clock, frames=(), *, split_first=None, header_chunk=None,
                 read_seconds=0.0, accept_valid=True):
        super().__init__()
        self.clock = clock
        self.frames = tuple(frames)
        self.split_first = split_first
        self.header_chunk = header_chunk
        self.read_seconds = read_seconds
        self.accept_valid = accept_valid
        self.parts = []
        self.request_key = None
        self.sent = []
        self.recv_calls = 0
        self.timeout_history = []

    def settimeout(self, timeout):
        self.timeout_history.append(timeout)
        super().settimeout(timeout)

    def sendall(self, raw):
        self.sent.append(bytes(raw))
        if not raw.startswith(b"GET "):
            return
        import base64
        request = raw.decode("ascii")
        lines = dict(line.split(": ", 1) for line in request.split("\r\n")[1:] if ": " in line)
        self.request_key = lines["Sec-WebSocket-Key"]
        accept = base64.b64encode(hashlib.sha1((self.request_key + GUID).encode()).digest()).decode()
        if not self.accept_valid:
            accept = "invalid-test-accept"
        header = ("HTTP/1.1 101 Switching Protocols\r\n"
                  "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                  "Sec-WebSocket-Accept: " + accept + "\r\n\r\n").encode("ascii")
        frames = b"".join(self.frames)
        if self.header_chunk:
            self.parts = [header[i:i + self.header_chunk] for i in range(0, len(header), self.header_chunk)]
            if frames:
                self.parts.append(frames)
        elif self.split_first is not None:
            self.parts = [header + frames[:self.split_first], frames[self.split_first:]]
        else:
            self.parts = [header + frames]

    def recv(self, count):
        self.recv_calls += 1
        if not self.parts:
            return b""
        if self.timeout is not None and self.read_seconds > self.timeout:
            self.clock.now += self.timeout
            raise socket.timeout("P01_SYNTHETIC_READ_TIMEOUT")
        self.clock.now += self.read_seconds
        chunk = self.parts[0][:count]
        self.parts[0] = self.parts[0][count:]
        if not self.parts[0]:
            self.parts.pop(0)
        return chunk

    def read(self, count):
        return self.recv(count)


class Agent:
    @staticmethod
    def utcnow():
        return "2026-10-24T12:00:00Z"

    @staticmethod
    def safe_error_code(_error):
        return "SYNTHETIC_CONNECTION_FAILED"

    @staticmethod
    def try_write_runtime_status(**_values):
        return True

    @staticmethod
    def try_write_event_v2_status(**_values):
        return True


class ReconnectRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.transport = load("p01_transport_" + self.id().split(".")[-1],
                              "experimental/event_v2_websocket.py")
        self.loop = load("p01_loop_" + self.id().split(".")[-1],
                         "experimental/event_v2_agent_loop.py")

    def fake_open(self, tls, *, timeout=25.0, connect_seconds=0.0, tls_seconds=0.0):
        plain = PlainSocket(timeout)
        self.addCleanup(plain.close)

        def connect(_address, timeout):
            if connect_seconds > timeout:
                tls.clock.now += timeout
                raise socket.timeout("P01_SYNTHETIC_CONNECT_TIMEOUT")
            tls.clock.now += connect_seconds
            plain.timeout = timeout
            return plain

        def wrap(_plain, server_hostname, **_kwargs):
            self.assertEqual(server_hostname, "synthetic.invalid")
            if tls_seconds > plain.timeout:
                tls.clock.now += plain.timeout
                raise socket.timeout("P01_SYNTHETIC_TLS_TIMEOUT")
            tls.clock.now += tls_seconds
            return tls

        context = SimpleNamespace(wrap_socket=wrap)
        with patch.object(self.transport.socket, "create_connection", side_effect=connect), \
             patch.object(self.transport.ssl, "create_default_context", return_value=context), \
             patch.object(self.transport.time, "monotonic", side_effect=tls.clock.monotonic):
            return self.transport.open_event_socket("https://synthetic.invalid",
                                                    "synthetic-test-only-not-a-device-token",
                                                    timeout=timeout)

    def test_101_coalesced_with_one_frame_preserves_exactly_one_event(self):
        clock = Clock()
        tls = FakeTLS(clock, [server_event("CALL-COALESCED-1")])
        sock = self.fake_open(tls)
        self.addCleanup(sock.close)
        self.assertIsNotNone(tls.request_key, "test must bind the real outgoing random Upgrade key")
        frame = self.transport.recv_server_frame(sock)
        self.assertEqual(self.transport.parse_event_frame(frame), {
            "schema": self.transport.EVENT_SCHEMA, "type": "CALL_AVAILABLE", "call_id": "CALL-COALESCED-1"})
        with self.assertRaisesRegex(self.transport.EventV2Error, "SOCKET_CLOSED|FRAME_INCOMPLETE"):
            self.transport.recv_server_frame(sock)

    def test_101_coalesced_with_two_frames_preserves_order_without_duplicate(self):
        tls = FakeTLS(Clock(), [server_event("CALL-FIRST"), server_event("CALL-SECOND")])
        sock = self.fake_open(tls)
        self.addCleanup(sock.close)
        ids = [self.transport.parse_event_frame(self.transport.recv_server_frame(sock))["call_id"]
               for _ in range(2)]
        self.assertEqual(ids, ["CALL-FIRST", "CALL-SECOND"])
        with self.assertRaises(self.transport.EventV2Error):
            self.transport.recv_server_frame(sock)

    def test_coalesced_frame_prefix_is_completed_from_later_tls_bytes(self):
        tls = FakeTLS(Clock(), [server_event("CALL-PARTIAL")], split_first=5)
        sock = self.fake_open(tls)
        self.addCleanup(sock.close)
        self.assertEqual(self.transport.parse_event_frame(self.transport.recv_server_frame(sock))["call_id"],
                         "CALL-PARTIAL")
        self.assertFalse(tls.parts)

    def test_header_only_upgrade_remains_valid(self):
        tls = FakeTLS(Clock())
        sock = self.fake_open(tls)
        self.addCleanup(sock.close)
        self.assertFalse(tls.closed)

    def test_invalid_accept_still_closes_tls(self):
        tls = FakeTLS(Clock(), accept_valid=False)
        with self.assertRaisesRegex(self.transport.EventV2Error, "ACCEPT_MISMATCH"):
            self.fake_open(tls)
        self.assertTrue(tls.closed)

    def test_fragmented_upgrade_cannot_renew_total_25_second_deadline(self):
        clock = Clock()
        tls = FakeTLS(clock, header_chunk=2, read_seconds=1.0)
        with self.assertRaises((self.transport.EventV2Error, TimeoutError)):
            self.fake_open(tls, timeout=25.0)
        self.assertLessEqual(clock.now, 25.000001, "header fragments renewed the total handshake timeout")
        self.assertTrue(tls.closed)

    def test_connect_tls_and_header_share_one_total_handshake_budget(self):
        clock = Clock()
        tls = FakeTLS(clock, read_seconds=10.0)
        with self.assertRaises((self.transport.EventV2Error, TimeoutError)):
            self.fake_open(tls, timeout=25.0, connect_seconds=8.0, tls_seconds=12.0)
        self.assertLessEqual(clock.now, 25.000001)
        self.assertTrue(tls.closed)

    def test_policy_defaults_are_explicit_client_policy(self):
        policy = self.transport.ReconnectPolicy()
        self.assertEqual(policy.base_seconds, 60.0)
        self.assertEqual(policy.max_seconds, 120.0)
        self.assertEqual(policy.minimum_seconds, 1.0)
        self.assertEqual(policy.startup_seconds, 120.0)

    def test_policy_delay_uses_first_attempt_zero_floor_and_capped_exponential(self):
        policy = self.transport.ReconnectPolicy()
        for attempt, entropy, expected in [(0, 0.0, 1.0), (0, 0.5, 30.5),
                                           (1, 0.5, 60.5), (2, 0.5, 60.5), (31, 0.5, 60.5)]:
            with self.subTest(attempt=attempt, entropy=entropy):
                self.assertAlmostEqual(policy.delay(attempt, entropy), expected)

    def test_startup_spread_is_separate_and_within_120_seconds(self):
        policy = self.transport.ReconnectPolicy()
        for entropy in [0.0, 0.25, 0.5, math.nextafter(1.0, 0.0)]:
            with self.subTest(entropy=entropy):
                self.assertAlmostEqual(policy.startup_delay(entropy), entropy * 120.0)
                self.assertGreaterEqual(policy.startup_delay(entropy), 0.0)
                self.assertLess(policy.startup_delay(entropy), 120.0)

    def test_policy_rejects_bool_non_integer_and_negative_attempts(self):
        policy = self.transport.ReconnectPolicy()
        for attempt in [False, True, -1, 0.0, 1.5, float("nan"), float("inf"), None, "0"]:
            with self.subTest(attempt=repr(attempt)):
                with self.assertRaises((ValueError, self.transport.EventV2Error)):
                    policy.delay(attempt, 0.5)

    def test_policy_rejects_non_finite_out_of_range_or_bool_entropy(self):
        policy = self.transport.ReconnectPolicy()
        for entropy in [float("nan"), float("inf"), -float("inf"), -0.001, 1.0, True, False]:
            with self.subTest(entropy=repr(entropy)):
                with self.assertRaises((ValueError, self.transport.EventV2Error)):
                    policy.delay(0, entropy)
                with self.assertRaises((ValueError, self.transport.EventV2Error)):
                    policy.startup_delay(entropy)

    def test_policy_rejects_invalid_finite_ranges_at_construction(self):
        for field in ["base_seconds", "max_seconds", "minimum_seconds", "startup_seconds"]:
            for value in [float("nan"), float("inf"), -float("inf"), -1.0, True, "60"]:
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaises((ValueError, self.transport.EventV2Error)):
                        self.transport.ReconnectPolicy(**{field: value})
        for fields in [{"base_seconds": 0.0}, {"max_seconds": 0.0},
                       {"minimum_seconds": 0.0}, {"max_seconds": 30.0},
                       {"minimum_seconds": 61.0}]:
            with self.subTest(fields=fields):
                with self.assertRaises((ValueError, self.transport.EventV2Error)):
                    self.transport.ReconnectPolicy(**fields)

    def run_scripted_loop(self, durations):
        clock = Clock()
        events = []
        attempts = []
        startup_calls = []
        sessions = iter(durations)

        class Policy:
            @staticmethod
            def startup_delay(entropy):
                startup_calls.append(entropy)
                return 120.0 * entropy

            @staticmethod
            def delay(attempt, entropy):
                attempts.append(attempt)
                return 1.0 + entropy * (min(120.0, 60.0 * 2 ** attempt) - 1.0)

        def sleep(seconds):
            events.append(("sleep", seconds))
            clock.sleep(seconds)

        def session(_transport, _agent, _config, **kwargs):
            events.append(("connect", clock.now))
            self.assertEqual(kwargs["monotonic"](), clock.now)
            try:
                duration = next(sessions)
            except StopIteration:
                raise KeyboardInterrupt()
            clock.now += duration
            raise RuntimeError("SYNTHETIC_CONNECTION_FAILED")

        with patch.object(self.loop, "run_connected_session", side_effect=session):
            with self.assertRaises(KeyboardInterrupt):
                self.loop.run_forever(SimpleNamespace(ReconnectPolicy=Policy), Agent(), {},
                                      sleep=sleep, monotonic=clock.monotonic, random_unit=lambda: 0.5)
        return SimpleNamespace(clock=clock, events=events, attempts=attempts, startup_calls=startup_calls)

    def test_loop_spreads_initial_connection_once_before_attempting_upgrade(self):
        run = self.run_scripted_loop([])
        self.assertEqual(run.startup_calls, [0.5])
        self.assertEqual(run.events, [("sleep", 60.0), ("connect", 60.0)])

    def test_first_retry_uses_attempt_zero_then_increments_after_calculation(self):
        run = self.run_scripted_loop([0.0, 0.0, 0.0])
        self.assertEqual(run.attempts, [0, 1, 2])
        self.assertEqual(run.clock.sleeps, [60.0, 30.5, 60.5, 60.5])
        self.assertEqual(run.startup_calls, [0.5], "reconnect must not repeat startup spreading")

    def test_stable_session_resets_retry_attempt_to_zero(self):
        run = self.run_scripted_loop([0.0, 0.0, 60.0])
        self.assertEqual(run.attempts, [0, 1, 0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
