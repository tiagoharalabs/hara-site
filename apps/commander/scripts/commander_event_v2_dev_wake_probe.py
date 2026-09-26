#!/usr/bin/env python3
"""Secret-safe live DEV wake probe for Commander Event V2.

The probe exercises the normal internal Commander device-call API against the
exact DEV origin and never prints the MCP product token or call result payload.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DEV_ISSUER = "https://auth.haralabs.com.br/"
DEFAULT_TOOL = "hara.health"


class ProbeError(RuntimeError):
    pass


def load_token(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ProbeError("WAKE_PROBE_TOKEN_FILE_UNSAFE") from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProbeError("WAKE_PROBE_TOKEN_FILE_UNSAFE")
        if os.name != "nt":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ProbeError("WAKE_PROBE_TOKEN_FILE_OWNER")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ProbeError("WAKE_PROBE_TOKEN_FILE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as handle:
            fd = -1
            token = handle.read().strip()
    finally:
        if fd >= 0:
            os.close(fd)

    if len(token) < 48:
        raise ProbeError("WAKE_PROBE_TOKEN_INVALID")
    return token


def post_json(path: str, token: str, body: dict) -> dict:
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    request = Request(
        DEV_ORIGIN + path,
        data=payload,
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-hara-mcp-product-token": token,
            "user-agent": "HARA-Commander-EventV2-DEV-Wake-Probe/1",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            obj = json.loads(raw or "{}")
        except json.JSONDecodeError:
            obj = {}
        raise ProbeError(str(obj.get("code") or f"HTTP_{exc.code}")) from None
    except (URLError, TimeoutError) as exc:
        raise ProbeError("WAKE_PROBE_NETWORK_ERROR") from exc

    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError("WAKE_PROBE_RESPONSE_INVALID") from exc


def run_probe(token: str, subject: str, device_id: str, timeout: float) -> dict:
    request_id = "HARA-EV2-WAKE-" + str(uuid.uuid4())
    started = time.monotonic()

    call = post_json(
        "/api/internal/device/calls",
        token,
        {
            "issuer": DEV_ISSUER,
            "subject": subject,
            "tool_id": DEFAULT_TOOL,
            "request_id": request_id,
            "device_id": device_id,
            "payload": {},
        },
    )
    if call.get("schema") != "hara.commander-device-call.v1":
        raise ProbeError("WAKE_PROBE_ENQUEUE_INVALID")

    call_id = str(call.get("call_id") or "")
    if not call_id:
        raise ProbeError("WAKE_PROBE_CALL_ID_MISSING")

    deadline = started + timeout
    terminal = None
    while time.monotonic() < deadline:
        status = post_json(
            "/api/internal/device/calls/status",
            token,
            {
                "issuer": DEV_ISSUER,
                "subject": subject,
                "call_id": call_id,
            },
        )
        if status.get("schema") != "hara.commander-device-call-status.v1":
            raise ProbeError("WAKE_PROBE_STATUS_INVALID")
        state = str(status.get("state") or "")
        if state in {"COMPLETED", "FAILED", "EXPIRED", "CANCELLED"}:
            terminal = status
            break
        time.sleep(0.20)

    if terminal is None:
        raise ProbeError("WAKE_PROBE_TIMEOUT")
    if terminal.get("state") != "COMPLETED" or terminal.get("error_code"):
        raise ProbeError(
            "WAKE_PROBE_TERMINAL_" + str(terminal.get("state") or "UNKNOWN")
        )

    result = terminal.get("result") or {}
    if result.get("state") != "PASS":
        raise ProbeError("WAKE_PROBE_RESULT_NOT_PASS")
    if result.get("operational_authority") != "HARA_COMMANDER":
        raise ProbeError("WAKE_PROBE_AUTHORITY_INVALID")
    nested = result.get("result") or {}
    if nested.get("device_channel_state") != "PASS":
        raise ProbeError("WAKE_PROBE_DEVICE_CHANNEL_NOT_PASS")

    return {
        "latency_ms": int((time.monotonic() - started) * 1000),
        "state": "COMPLETED",
        "authority": "HARA_COMMANDER",
        "device_channel_state": "PASS",
    }


def self_check() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert DEV_ORIGIN == "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
    assert "/api/internal/device/calls" in source
    assert "/api/internal/device/calls/status" in source
    assert "x-hara-mcp-product-token" in source
    assert "print(token" not in source
    assert "repr(token" not in source
    assert "result_json" not in source
    assert "commander.haralabs.com.br/api/internal" not in source
    print("COMMANDER_EVENT_V2_DEV_WAKE_PROBE_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_DEV_WAKE_PROBE_ORIGIN=DEV_ONLY")
    print("COMMANDER_EVENT_V2_DEV_WAKE_PROBE_TOKEN_OUTPUT=ABSENT")
    print("COMMANDER_EVENT_V2_DEV_WAKE_PROBE_RESULT_PAYLOAD_OUTPUT=ABSENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--subject")
    parser.add_argument("--device-id")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")
    if not args.token_file or not args.subject or not args.device_id:
        parser.error("--token-file, --subject and --device-id are required")
    if args.timeout < 2 or args.timeout > 30:
        raise ProbeError("WAKE_PROBE_TIMEOUT_INVALID")

    token = load_token(Path(args.token_file))
    try:
        result = run_probe(token, args.subject.strip(), args.device_id.strip(), args.timeout)
    finally:
        token = ""

    print("COMMANDER_EVENT_V2_DEV_WAKE=PASS")
    print("COMMANDER_EVENT_V2_DEV_WAKE_STATE=" + result["state"])
    print("COMMANDER_EVENT_V2_DEV_WAKE_AUTHORITY=" + result["authority"])
    print("COMMANDER_EVENT_V2_DEV_WAKE_DEVICE_CHANNEL=" + result["device_channel_state"])
    print("COMMANDER_EVENT_V2_DEV_WAKE_LATENCY_MS=" + str(result["latency_ms"]))
    print("COMMANDER_EVENT_V2_DEV_WAKE_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as exc:
        print("COMMANDER_EVENT_V2_DEV_WAKE=FAIL:" + str(exc))
        raise SystemExit(1)
