#!/usr/bin/env python3
"""Offline tests for the experimental Commander Event V2 WebSocket client."""

from __future__ import annotations

import importlib.util
import socket
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "experimental" / "event_v2_websocket.py"


def load_client():
    spec = importlib.util.spec_from_file_location("event_v2_websocket", CLIENT)
    if spec is None or spec.loader is None:
        raise RuntimeError("EVENT_V2_CLIENT_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expect_code(fn, code):
    try:
        fn()
    except Exception as exc:
        assert str(exc) == code, (str(exc), code)
        return
    raise AssertionError("expected error " + code)


class IdleSocket:
    def __init__(self):
        self.timeout = None
        self.sent = []

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value

    def read(self, _count):
        raise socket.timeout()

    def sendall(self, data):
        self.sent.append(bytes(data))


def main() -> int:
    client = load_client()

    # RFC 6455 handshake example.
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    expected = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    assert client.expected_accept(key) == expected
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {expected}\r\n\r\n"
    ).encode("ascii")
    client.parse_handshake_response(response, key)

    host, port, path = client.event_endpoint("https://commander.example.test")
    assert (host, port, path) == (
        "commander.example.test",
        443,
        "/api/device/channel",
    )
    expect_code(
        lambda: client.event_endpoint("http://commander.example.test"),
        "EVENT_V2_HTTPS_REQUIRED",
    )
    expect_code(
        lambda: client.event_endpoint("https://user:pw@commander.example.test"),
        "EVENT_V2_ORIGIN_INVALID",
    )

    # Client frames are masked; decoding the masked bytes with the known mask
    # must recover the exact payload.
    payload = b'{"schema":"hara.commander-device-event.v2","type":"PING"}'
    mask = b"\x01\x02\x03\x04"
    frame = client.encode_client_frame(0x1, payload, mask_key=mask)
    assert frame[1] & 0x80
    assert frame[2:6] == mask
    encoded = frame[6:]
    recovered = bytes(byte ^ mask[i % 4] for i, byte in enumerate(encoded))
    assert recovered == payload

    # Bounded unmasked server text frame.
    server_payload = b'{"schema":"hara.commander-device-event.v2","type":"CALL_AVAILABLE","call_id":"C1"}'
    server_frame = bytes([0x81, len(server_payload)]) + server_payload
    decoded = client.decode_server_frame(server_frame)
    assert decoded.opcode == 0x1
    assert decoded.payload == server_payload

    # Server masking and fragmentation are fail-closed.
    expect_code(
        lambda: client.decode_server_frame(bytes([0x81, 0x80])),
        "EVENT_V2_SERVER_MASK_DENIED",
    )
    expect_code(
        lambda: client.decode_server_frame(bytes([0x01, 0x00])),
        "EVENT_V2_FRAGMENTATION_DENIED",
    )

    # 126-length framing is handled deterministically.
    p126 = b"x" * 126
    raw126 = bytes([0x81, 126]) + struct.pack("!H", len(p126)) + p126
    d126 = client.decode_server_frame(raw126)
    assert d126.payload == p126

    # Full-jitter reconnect policy is deterministic under injected entropy.
    policy = client.ReconnectPolicy()
    assert policy.delay(0, 0.0) == 0.0
    assert policy.delay(0, 0.5) == 0.5
    assert policy.delay(1, 0.5) == 1.0
    assert policy.delay(5, 0.5) == 16.0
    assert policy.delay(6, 0.5) == 30.0
    assert 59.0 < policy.delay(20, 0.999) < 60.0
    expect_code(
        lambda: policy.delay(-1, 0.5),
        "EVENT_V2_RECONNECT_ATTEMPT_INVALID",
    )
    expect_code(
        lambda: policy.delay(0, 1.0),
        "EVENT_V2_RECONNECT_RANDOM_INVALID",
    )

    # Idle receive emits one RFC6455 protocol PING, not an application JSON
    # heartbeat, and restores the caller's socket timeout.
    idle = IdleSocket()
    assert client.KEEPALIVE_IDLE_SECONDS == 60.0
    assert client.recv_event_or_keepalive(idle) is None
    assert idle.timeout is None
    assert len(idle.sent) == 1
    ping = idle.sent[0]
    assert ping[0] == 0x89  # FIN + protocol PING opcode
    assert ping[1] & 0x80   # client control frames remain masked
    expect_code(
        lambda: client.send_ping(idle, b"x" * 126),
        "EVENT_V2_CONTROL_PAYLOAD_TOO_LARGE",
    )

    # Credential validation must not echo the supplied value.
    secret = "DO_NOT_ECHO_THIS_SECRET"
    try:
        client.build_handshake_request("example.test", 443, "/", secret + "\n", key)
    except Exception as exc:
        assert secret not in str(exc)
        assert str(exc) == "EVENT_V2_CREDENTIAL_INVALID"
    else:
        raise AssertionError("credential newline must fail")

    print("COMMANDER_EVENT_V2_LINUX_CLIENT_OFFLINE_TEST=PASS")
    print("COMMANDER_EVENT_V2_TLS_REQUIRED=PASS")
    print("COMMANDER_EVENT_V2_HANDSHAKE_RFC6455=PASS")
    print("COMMANDER_EVENT_V2_CLIENT_MASKING=PASS")
    print("COMMANDER_EVENT_V2_SERVER_FRAME_BOUNDS=PASS")
    print("COMMANDER_EVENT_V2_CLIENT_SECRET_ECHO=ABSENT")
    print("COMMANDER_EVENT_V2_RECONNECT_FULL_JITTER=PASS")
    print("COMMANDER_EVENT_V2_RECONNECT_MAX_SECONDS=60")
    print("COMMANDER_EVENT_V2_PROTOCOL_KEEPALIVE_IDLE_SECONDS=60")
    print("COMMANDER_EVENT_V2_APPLICATION_HEARTBEAT_ON_IDLE=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
