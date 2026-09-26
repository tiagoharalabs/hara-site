#!/usr/bin/env python3
"""Experimental stdlib-only WebSocket transport for H.A.R.A. Commander Event V2.

This module is intentionally not part of the public Agent release yet. It exists
so the Event V2 client protocol can be tested without adding a third-party
runtime dependency to customer machines.

Security posture:
- HTTPS/WSS only;
- system CA validation via ssl.create_default_context();
- no redirects;
- bearer credential only in the TLS-protected Upgrade request;
- no credential in exception text;
- server frames must be unmasked and bounded;
- fragmented data frames are denied in this first protocol version.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import urlsplit

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_HEADER_BYTES = 16 * 1024
MAX_EVENT_BYTES = 4 * 1024
KEEPALIVE_IDLE_SECONDS = 60.0
RECONNECT_BASE_SECONDS = 10.0
RECONNECT_MAX_SECONDS = 15.0
MAX_CONTROL_PAYLOAD_BYTES = 125
EVENT_SCHEMA = "hara.commander-device-event.v2"
DURABLE_LIVENESS_SECONDS = 6 * 60 * 60


class EventV2Error(RuntimeError):
    pass


def fail(code: str) -> EventV2Error:
    return EventV2Error(code)


def event_endpoint(base_url: str) -> tuple[str, int, str]:
    parsed = urlsplit(str(base_url or ""))
    if parsed.scheme.lower() != "https":
        raise fail("EVENT_V2_HTTPS_REQUIRED")
    if parsed.username or parsed.password or parsed.fragment:
        raise fail("EVENT_V2_ORIGIN_INVALID")
    if not parsed.hostname:
        raise fail("EVENT_V2_ORIGIN_INVALID")
    if parsed.query:
        raise fail("EVENT_V2_ORIGIN_INVALID")
    port = parsed.port or 443
    base_path = parsed.path.rstrip("/")
    path = (base_path + "/api/device/channel") if base_path else "/api/device/channel"
    return parsed.hostname, port, path


def websocket_key() -> str:
    return base64.b64encode(os.urandom(16)).decode("ascii")


def expected_accept(key: str) -> str:
    raw = (str(key) + WS_GUID).encode("ascii")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")


def build_handshake_request(host: str, port: int, path: str, token: str, key: str) -> bytes:
    if not token or "\r" in token or "\n" in token:
        raise fail("EVENT_V2_CREDENTIAL_INVALID")
    authority = host if port == 443 else f"{host}:{port}"
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {authority}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        f"Authorization: Bearer {token}",
        "User-Agent: HARA-Commander-Agent-EventV2/experimental",
        "",
        "",
    ]
    return "\r\n".join(lines).encode("ascii")


def parse_handshake_response(raw: bytes, key: str) -> None:
    if len(raw) > MAX_HEADER_BYTES:
        raise fail("EVENT_V2_HANDSHAKE_TOO_LARGE")
    try:
        text = raw.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise fail("EVENT_V2_HANDSHAKE_INVALID") from exc
    head = text.split("\r\n\r\n", 1)[0]
    lines = head.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/1.1 101 "):
        raise fail("EVENT_V2_UPGRADE_REJECTED")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise fail("EVENT_V2_HANDSHAKE_INVALID")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    if headers.get("upgrade", "").lower() != "websocket":
        raise fail("EVENT_V2_UPGRADE_REJECTED")
    if "upgrade" not in headers.get("connection", "").lower():
        raise fail("EVENT_V2_UPGRADE_REJECTED")
    if headers.get("sec-websocket-accept") != expected_accept(key):
        raise fail("EVENT_V2_ACCEPT_MISMATCH")


def _masked(payload: bytes, mask: bytes) -> bytes:
    return bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


def encode_client_frame(opcode: int, payload: bytes, mask_key: bytes | None = None) -> bytes:
    if opcode not in {0x1, 0x8, 0x9, 0xA}:
        raise fail("EVENT_V2_OPCODE_DENIED")
    payload = bytes(payload)
    if len(payload) > MAX_EVENT_BYTES:
        raise fail("EVENT_V2_MESSAGE_TOO_LARGE")
    mask = mask_key if mask_key is not None else os.urandom(4)
    if len(mask) != 4:
        raise fail("EVENT_V2_MASK_INVALID")
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes([first, 0x80 | length])
    elif length <= 0xFFFF:
        header = bytes([first, 0x80 | 126]) + struct.pack("!H", length)
    else:
        header = bytes([first, 0x80 | 127]) + struct.pack("!Q", length)
    return header + mask + _masked(payload, mask)


@dataclass(frozen=True)
class ServerFrame:
    opcode: int
    payload: bytes
    consumed: int


@dataclass(frozen=True)
class ReconnectPolicy:
    base_seconds: float = RECONNECT_BASE_SECONDS
    max_seconds: float = RECONNECT_MAX_SECONDS

    def delay(self, attempt: int, random_unit: float) -> float:
        if attempt < 0:
            raise fail("EVENT_V2_RECONNECT_ATTEMPT_INVALID")
        if not 0.0 <= random_unit < 1.0:
            raise fail("EVENT_V2_RECONNECT_RANDOM_INVALID")
        cap = min(self.max_seconds, self.base_seconds * (2 ** attempt))
        return random_unit * cap


def decode_server_frame(raw: bytes, max_bytes: int = MAX_EVENT_BYTES) -> ServerFrame:
    if len(raw) < 2:
        raise fail("EVENT_V2_FRAME_INCOMPLETE")
    first, second = raw[0], raw[1]
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    if not fin:
        raise fail("EVENT_V2_FRAGMENTATION_DENIED")
    if masked:
        raise fail("EVENT_V2_SERVER_MASK_DENIED")
    if opcode not in {0x1, 0x8, 0x9, 0xA}:
        raise fail("EVENT_V2_OPCODE_DENIED")

    offset = 2
    length = second & 0x7F
    if length == 126:
        if len(raw) < offset + 2:
            raise fail("EVENT_V2_FRAME_INCOMPLETE")
        length = struct.unpack("!H", raw[offset:offset + 2])[0]
        offset += 2
    elif length == 127:
        if len(raw) < offset + 8:
            raise fail("EVENT_V2_FRAME_INCOMPLETE")
        length = struct.unpack("!Q", raw[offset:offset + 8])[0]
        offset += 8

    if length > max_bytes:
        raise fail("EVENT_V2_MESSAGE_TOO_LARGE")
    if len(raw) < offset + length:
        raise fail("EVENT_V2_FRAME_INCOMPLETE")
    return ServerFrame(opcode=opcode, payload=raw[offset:offset + length], consumed=offset + length)


def read_exact(stream: BinaryIO, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        data = stream.read(count - len(chunks))
        if not data:
            raise fail("EVENT_V2_SOCKET_CLOSED")
        chunks.extend(data)
    return bytes(chunks)


def recv_server_frame(sock: socket.socket, max_bytes: int = MAX_EVENT_BYTES) -> ServerFrame:
    first_two = read_exact(sock, 2)
    first, second = first_two[0], first_two[1]
    if second & 0x80:
        raise fail("EVENT_V2_SERVER_MASK_DENIED")
    length_code = second & 0x7F
    extra = b""
    if length_code == 126:
        extra = read_exact(sock, 2)
        length = struct.unpack("!H", extra)[0]
    elif length_code == 127:
        extra = read_exact(sock, 8)
        length = struct.unpack("!Q", extra)[0]
    else:
        length = length_code
    if length > max_bytes:
        raise fail("EVENT_V2_MESSAGE_TOO_LARGE")
    payload = read_exact(sock, length)
    return decode_server_frame(first_two + extra + payload, max_bytes=max_bytes)


def open_event_socket(base_url: str, token: str, timeout: float = 25.0) -> ssl.SSLSocket:
    host, port, path = event_endpoint(base_url)
    key = websocket_key()
    raw_request = build_handshake_request(host, port, path, token, key)

    plain = socket.create_connection((host, port), timeout=timeout)
    try:
        context = ssl.create_default_context()
        tls = context.wrap_socket(plain, server_hostname=host)
    except Exception:
        plain.close()
        raise fail("EVENT_V2_TLS_FAILED")

    try:
        tls.settimeout(timeout)
        tls.sendall(raw_request)
        response = bytearray()
        while b"\r\n\r\n" not in response:
            if len(response) >= MAX_HEADER_BYTES:
                raise fail("EVENT_V2_HANDSHAKE_TOO_LARGE")
            chunk = tls.recv(2048)
            if not chunk:
                raise fail("EVENT_V2_SOCKET_CLOSED")
            response.extend(chunk)
        header, remainder = bytes(response).split(b"\r\n\r\n", 1)
        if remainder:
            # The first server event must be read through the frame reader so
            # transport state is never silently discarded.
            raise fail("EVENT_V2_EARLY_FRAME_UNSUPPORTED")
        parse_handshake_response(header + b"\r\n\r\n", key)
        return tls
    except Exception:
        tls.close()
        raise


def send_text(sock: socket.socket, text: str) -> None:
    payload = str(text).encode("utf-8")
    sock.sendall(encode_client_frame(0x1, payload))


def send_liveness(sock: socket.socket) -> None:
    send_text(sock, json.dumps(
        {"schema": EVENT_SCHEMA, "type": "LIVENESS"},
        separators=(",", ":"),
        sort_keys=True,
    ))


def parse_event_frame(frame: ServerFrame) -> dict:
    if frame.opcode != 0x1:
        raise fail("EVENT_V2_EVENT_FRAME_REQUIRED")
    try:
        raw = frame.payload.decode("utf-8")
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise fail("EVENT_V2_EVENT_INVALID") from exc
    if not isinstance(payload, dict) or payload.get("schema") != EVENT_SCHEMA:
        raise fail("EVENT_V2_EVENT_INVALID")
    if payload.get("type") != "CALL_AVAILABLE":
        raise fail("EVENT_V2_EVENT_TYPE_DENIED")
    if set(payload) != {"schema", "type", "call_id"}:
        raise fail("EVENT_V2_EVENT_FIELDS_DENIED")
    call_id = str(payload.get("call_id") or "")
    if (
        not call_id
        or len(call_id) > 180
        or any(not (ch.isalnum() or ch in "_.:-") for ch in call_id)
    ):
        raise fail("EVENT_V2_CALL_ID_INVALID")
    return {
        "schema": EVENT_SCHEMA,
        "type": "CALL_AVAILABLE",
        "call_id": call_id,
    }


def send_ping(sock: socket.socket, payload: bytes = b"") -> None:
    payload = bytes(payload)
    if len(payload) > MAX_CONTROL_PAYLOAD_BYTES:
        raise fail("EVENT_V2_CONTROL_PAYLOAD_TOO_LARGE")
    sock.sendall(encode_client_frame(0x9, payload))


def send_pong(sock: socket.socket, payload: bytes) -> None:
    payload = bytes(payload)
    if len(payload) > MAX_CONTROL_PAYLOAD_BYTES:
        raise fail("EVENT_V2_CONTROL_PAYLOAD_TOO_LARGE")
    sock.sendall(encode_client_frame(0xA, payload))


def recv_event_or_keepalive(
    sock: socket.socket,
    idle_seconds: float = KEEPALIVE_IDLE_SECONDS,
) -> ServerFrame | None:
    if idle_seconds <= 0:
        raise fail("EVENT_V2_KEEPALIVE_INTERVAL_INVALID")

    prior_timeout = sock.gettimeout()
    try:
        sock.settimeout(idle_seconds)
        try:
            frame = recv_server_frame(sock)
        except socket.timeout:
            # Protocol PING is transport keepalive only. Cloudflare's
            # hibernation runtime answers incoming protocol PING with PONG
            # without invoking the Durable Object message handler.
            send_ping(sock)
            return None

        if frame.opcode == 0x9:
            # Standards-compliant fallback for servers/proxies that send PING.
            send_pong(sock, frame.payload)
            return None
        if frame.opcode == 0xA:
            return None
        if frame.opcode == 0x8:
            raise fail("EVENT_V2_SERVER_CLOSED")
        return frame
    finally:
        sock.settimeout(prior_timeout)


def close_socket(sock: socket.socket, code: int = 1000) -> None:
    try:
        sock.sendall(encode_client_frame(0x8, struct.pack("!H", code)))
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass
