#!/usr/bin/env python3
"""DEV-only quota parity proof over the real Commander Event V2 path.

The probe uses the existing isolated DEV canary MCP token file, never prints
secret material or customer content, and proves both release and commit
semantics without touching PROD.
"""

from __future__ import annotations

import argparse
import ast
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
FUNCTION_ID = "device.info"
WORKER = Path(__file__).resolve().parent.parent / "src" / "worker.js"


class ProbeError(RuntimeError):
    pass


def load_token(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ProbeError("QUOTA_PROBE_TOKEN_FILE_UNSAFE") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProbeError("QUOTA_PROBE_TOKEN_FILE_UNSAFE")
        if os.name != "nt":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ProbeError("QUOTA_PROBE_TOKEN_FILE_OWNER")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ProbeError("QUOTA_PROBE_TOKEN_FILE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as handle:
            fd = -1
            token = handle.read().strip()
    finally:
        if fd >= 0:
            os.close(fd)
    if len(token) < 48:
        raise ProbeError("QUOTA_PROBE_TOKEN_INVALID")
    return token


def post_json(path: str, token: str, body: dict) -> dict:
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    req = Request(
        DEV_ORIGIN + path,
        data=payload,
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-hara-mcp-product-token": token,
            "user-agent": "HARA-Commander-EventV2-Quota-Probe/1",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            obj = json.loads(raw or "{}")
        except json.JSONDecodeError:
            obj = {}
        raise ProbeError(str(obj.get("code") or f"HTTP_{exc.code}")) from None
    except (URLError, TimeoutError) as exc:
        raise ProbeError("QUOTA_PROBE_NETWORK_ERROR") from exc
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError("QUOTA_PROBE_RESPONSE_INVALID") from exc


def authorize(token: str, subject: str, request_id: str) -> dict:
    return post_json(
        "/api/internal/mcp/authorize",
        token,
        {
            "issuer": DEV_ISSUER,
            "subject": subject,
            "tool_id": "hara.functions.invoke",
            "request_id": request_id,
            "function_id": FUNCTION_ID,
        },
    )


def release(token: str, subject: str, request_id: str) -> dict:
    return post_json(
        "/api/internal/mcp/release",
        token,
        {"issuer": DEV_ISSUER, "subject": subject, "request_id": request_id},
    )


def commit(token: str, subject: str, request_id: str, receipt_sha256: str) -> dict:
    return post_json(
        "/api/internal/mcp/commit",
        token,
        {
            "issuer": DEV_ISSUER,
            "subject": subject,
            "request_id": request_id,
            "receipt_sha256": receipt_sha256,
        },
    )


def transient_call(token: str, subject: str, request_id: str, tool_id: str, payload: dict) -> dict:
    return post_json(
        "/api/internal/device/transient-call",
        token,
        {
            "issuer": DEV_ISSUER,
            "subject": subject,
            "tool_id": tool_id,
            "request_id": request_id,
            "payload": payload,
        },
    )


def require_transient_common(obj: dict) -> None:
    if obj.get("schema") != "hara.commander-device-transient-call.v1":
        raise ProbeError("TRANSIENT_SCHEMA_INVALID")
    if obj.get("transport_mode") != "EVENT_V2_TRANSIENT_RPC":
        raise ProbeError("TRANSIENT_MODE_INVALID")
    if obj.get("persisted_customer_payload") is not False:
        raise ProbeError("TRANSIENT_PAYLOAD_PERSISTENCE_INVALID")
    if obj.get("persisted_customer_result") is not False:
        raise ProbeError("TRANSIENT_RESULT_PERSISTENCE_INVALID")
    signal = obj.get("learning_signal") or {}
    if signal.get("schema") != "hara.commander-learning-signal.v1":
        raise ProbeError("TRANSIENT_LEARNING_SCHEMA_INVALID")
    if signal.get("customer_content_collected") is not False:
        raise ProbeError("TRANSIENT_LEARNING_CONTENT_INVALID")


def run(token: str, subject: str, device_id: str, timeout: float) -> dict:
    del timeout
    cycle_started = time.perf_counter()
    health_req = "TRANSIENT-HEALTH-" + uuid.uuid4().hex
    health_started = time.perf_counter()
    try:
        health = transient_call(token, subject, health_req, "hara.health", {})
    except ProbeError as exc:
        raise ProbeError("STAGE_HEALTH__" + str(exc)) from exc
    health_ms = (time.perf_counter() - health_started) * 1000.0
    require_transient_common(health)
    if health.get("state") != "COMPLETED":
        raise ProbeError("TRANSIENT_HEALTH_NOT_COMPLETED")
    if str(health.get("device_id") or "") != device_id:
        raise ProbeError("TRANSIENT_SELECTED_DEVICE_MISMATCH")

    invoke_req = "TRANSIENT-INVOKE-" + uuid.uuid4().hex
    invoke_payload = {"function_id": FUNCTION_ID, "arguments": {"argv": []}}
    invoke_started = time.perf_counter()
    try:
        first = transient_call(
            token, subject, invoke_req, "hara.functions.invoke", invoke_payload
        )
    except ProbeError as exc:
        raise ProbeError("STAGE_INVOKE_FIRST__" + str(exc)) from exc
    invoke_ms = (time.perf_counter() - invoke_started) * 1000.0
    require_transient_common(first)
    if first.get("state") != "COMPLETED":
        raise ProbeError("TRANSIENT_INVOKE_NOT_COMPLETED")
    if str(first.get("device_id") or "") != device_id:
        raise ProbeError("TRANSIENT_SELECTED_DEVICE_MISMATCH")
    if first.get("execution_mode") != "EXECUTE_OR_REPLAY":
        raise ProbeError("TRANSIENT_EXECUTION_MODE_INVALID")
    usage = first.get("usage") or {}
    if usage.get("state") != "COMMITTED":
        raise ProbeError("TRANSIENT_QUOTA_NOT_COMMITTED")
    receipt_sha256 = str(first.get("receipt_sha256") or "").lower()
    if len(receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in receipt_sha256):
        raise ProbeError("TRANSIENT_RECEIPT_INVALID")

    replay_started = time.perf_counter()
    try:
        replay = transient_call(
            token, subject, invoke_req, "hara.functions.invoke", invoke_payload
        )
    except ProbeError as exc:
        raise ProbeError("STAGE_INVOKE_REPLAY__" + str(exc)) from exc
    replay_ms = (time.perf_counter() - replay_started) * 1000.0
    require_transient_common(replay)
    if replay.get("state") != "COMPLETED":
        raise ProbeError("TRANSIENT_REPLAY_NOT_COMPLETED")
    if replay.get("execution_mode") != "REPLAY_ONLY":
        raise ProbeError("TRANSIENT_REPLAY_MODE_INVALID")
    replay_usage = replay.get("usage") or {}
    if replay_usage.get("state") != "COMMITTED":
        raise ProbeError("TRANSIENT_REPLAY_QUOTA_INVALID")
    if str(replay.get("receipt_sha256") or "").lower() != receipt_sha256:
        raise ProbeError("TRANSIENT_REPLAY_RECEIPT_MISMATCH")
    if (replay.get("learning_signal") or {}).get("outcome") != "REPLAYED":
        raise ProbeError("TRANSIENT_REPLAY_SIGNAL_INVALID")

    return {
        "health": True,
        "invoke": True,
        "request_id": invoke_req,
        "receipt_sha256": receipt_sha256,
        "commit_state": "COMMITTED",
        "replay_mode": "REPLAY_ONLY",
        "replay_outcome": "REPLAYED",
        "payload_persisted": False,
        "result_persisted": False,
        "learning_content": False,
        "health_ms": health_ms,
        "invoke_ms": invoke_ms,
        "replay_ms": replay_ms,
        "cycle_ms": (time.perf_counter() - cycle_started) * 1000.0,
    }


def self_check() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert DEV_ORIGIN.endswith(".workers.dev")
    assert "/api/internal/device/transient-call" in source
    assert "EXECUTE_OR_REPLAY" in source
    assert "REPLAY_ONLY" in source
    assert "customer_content_collected" in source
    forbidden_prod = "https://commander." + "haralabs.com.br"
    assert forbidden_prod not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                if any(isinstance(child, ast.Name) and child.id == "token" for child in ast.walk(arg)):
                    raise AssertionError("TRANSIENT_PROBE_SECRET_PRINT_SURFACE")
    print("COMMANDER_EVENT_V2_TRANSIENT_LIVE_PROBE_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_TRANSIENT_LIVE_PROBE_ORIGIN=DEV_ONLY")
    print("COMMANDER_EVENT_V2_TRANSIENT_LIVE_PROBE_TOKEN_OUTPUT=ABSENT")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--subject")
    parser.add_argument("--device-id")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")
    if not args.token_file or not args.subject or not args.device_id:
        parser.error("--token-file, --subject and --device-id are required")
    if args.timeout < 5 or args.timeout > 40:
        raise ProbeError("TRANSIENT_PROBE_TIMEOUT_INVALID")

    token = load_token(Path(args.token_file))
    try:
        proof = run(token, args.subject.strip(), args.device_id.strip(), args.timeout)
    finally:
        token = ""

    print("COMMANDER_EVENT_V2_TRANSIENT_LIVE=PASS")
    print("COMMANDER_EVENT_V2_TRANSIENT_HEALTH=PASS")
    print("COMMANDER_EVENT_V2_TRANSIENT_INVOKE=PASS")
    print("COMMANDER_EVENT_V2_TRANSIENT_QUOTA_COMMIT=" + proof["commit_state"])
    print("COMMANDER_EVENT_V2_TRANSIENT_REPLAY_MODE=" + proof["replay_mode"])
    print("COMMANDER_EVENT_V2_TRANSIENT_REPLAY_OUTCOME=" + proof["replay_outcome"])
    print("COMMANDER_EVENT_V2_TRANSIENT_PAYLOAD_PERSISTED=FALSE")
    print("COMMANDER_EVENT_V2_TRANSIENT_RESULT_PERSISTED=FALSE")
    print("COMMANDER_EVENT_V2_TRANSIENT_LEARNING_CONTENT=FALSE")
    print("COMMANDER_EVENT_V2_TRANSIENT_REQUEST_ID=" + proof["request_id"])
    print("COMMANDER_EVENT_V2_TRANSIENT_HEALTH_MS=" + f"{proof['health_ms']:.3f}")
    print("COMMANDER_EVENT_V2_TRANSIENT_INVOKE_MS=" + f"{proof['invoke_ms']:.3f}")
    print("COMMANDER_EVENT_V2_TRANSIENT_REPLAY_MS=" + f"{proof['replay_ms']:.3f}")
    print("COMMANDER_EVENT_V2_TRANSIENT_CYCLE_MS=" + f"{proof['cycle_ms']:.3f}")
    print("COMMANDER_EVENT_V2_TRANSIENT_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as exc:
        print("COMMANDER_EVENT_V2_TRANSIENT_LIVE=FAIL:" + str(exc))
        raise SystemExit(1)
