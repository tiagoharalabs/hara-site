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


def enqueue_invoke(token: str, subject: str, device_id: str, request_id: str) -> dict:
    return post_json(
        "/api/internal/device/calls",
        token,
        {
            "issuer": DEV_ISSUER,
            "subject": subject,
            "tool_id": "hara.functions.invoke",
            "request_id": request_id,
            "device_id": device_id,
            "payload": {"function_id": FUNCTION_ID, "arguments": {"argv": []}},
        },
    )


def wait_call(token: str, subject: str, call_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = post_json(
            "/api/internal/device/calls/status",
            token,
            {"issuer": DEV_ISSUER, "subject": subject, "call_id": call_id},
        )
        state = str(status.get("state") or "")
        if state in {"COMPLETED", "FAILED", "EXPIRED", "CANCELLED"}:
            return status
        time.sleep(0.20)
    raise ProbeError("QUOTA_PROBE_CALL_TIMEOUT")


def require_reserved(obj: dict) -> dict:
    if obj.get("allowed") is not True or obj.get("code") != "ALLOW":
        raise ProbeError("QUOTA_RESERVE_DENIED")
    usage = obj.get("usage") or {}
    if usage.get("state") != "RESERVED":
        raise ProbeError("QUOTA_RESERVE_STATE_INVALID")
    return usage


def run(token: str, subject: str, device_id: str, timeout: float) -> dict:
    # Law 1: reserve -> release -> replay must be terminal and not consume quota.
    release_req = "HARA-EV2-QUOTA-REL-" + str(uuid.uuid4())
    reserve1 = require_reserved(authorize(token, subject, release_req))
    released = release(token, subject, release_req)
    released_usage = released.get("usage") or {}
    if released.get("transition") != "RELEASE" or released_usage.get("state") != "RELEASED":
        raise ProbeError("QUOTA_RELEASE_INVALID")
    if int(released_usage.get("consumed_units") or 0) > int(reserve1.get("consumed_units") or 0):
        raise ProbeError("QUOTA_RELEASE_CONSUMED_INCREASED")
    replay = authorize(token, subject, release_req)
    if replay.get("allowed") is not False or replay.get("code") != "REQUEST_USAGE_TERMINAL":
        raise ProbeError("QUOTA_RELEASE_REPLAY_NOT_TERMINAL")
    if (replay.get("usage") or {}).get("state") != "RELEASED":
        raise ProbeError("QUOTA_RELEASE_REPLAY_STATE_INVALID")

    # Law 2: reserve -> real Event V2 invoke -> receipt -> commit.
    commit_req = "HARA-EV2-QUOTA-COMMIT-" + str(uuid.uuid4())
    require_reserved(authorize(token, subject, commit_req))

    call = enqueue_invoke(token, subject, device_id, commit_req)
    call_id = str(call.get("call_id") or "")
    if not call_id.startswith("HARA-CALL-"):
        raise ProbeError("QUOTA_EVENT_CALL_ID_INVALID")
    status = wait_call(token, subject, call_id, timeout)
    if status.get("state") != "COMPLETED" or status.get("error_code"):
        raise ProbeError("QUOTA_EVENT_CALL_NOT_COMPLETED")

    result = status.get("result") or {}
    if result.get("state") != "PASS":
        raise ProbeError("QUOTA_EVENT_RESULT_NOT_PASS")
    if result.get("operational_authority") != "HARA_COMMANDER":
        raise ProbeError("QUOTA_EVENT_AUTHORITY_INVALID")
    receipt_sha256 = str(result.get("bridge_receipt_sha256") or "").lower()
    if len(receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in receipt_sha256):
        raise ProbeError("QUOTA_EVENT_RECEIPT_INVALID")

    committed = commit(token, subject, commit_req, receipt_sha256)
    usage = committed.get("usage") or {}
    if committed.get("transition") != "COMMIT" or usage.get("state") != "COMMITTED":
        raise ProbeError("QUOTA_COMMIT_INVALID")
    consumed_after_commit = int(usage.get("consumed_units") or 0)

    # Same commit must be idempotent and must not double-charge.
    committed_again = commit(token, subject, commit_req, receipt_sha256)
    usage_again = committed_again.get("usage") or {}
    if usage_again.get("state") != "COMMITTED" or usage_again.get("existing") is not True:
        raise ProbeError("QUOTA_COMMIT_IDEMPOTENCY_INVALID")
    if int(usage_again.get("consumed_units") or 0) != consumed_after_commit:
        raise ProbeError("QUOTA_DOUBLE_CHARGE_DETECTED")

    replay_committed = authorize(token, subject, commit_req)
    replay_usage = replay_committed.get("usage") or {}
    if replay_committed.get("allowed") is not True or replay_usage.get("state") != "COMMITTED":
        raise ProbeError("QUOTA_COMMIT_REPLAY_INVALID")
    if str(replay_usage.get("receipt_sha256") or "").lower() != receipt_sha256:
        raise ProbeError("QUOTA_COMMIT_RECEIPT_MISMATCH")

    release_after_commit = release(token, subject, commit_req)
    release_after_usage = release_after_commit.get("usage") or {}
    if release_after_usage.get("code") != "RESERVATION_NOT_ACTIVE":
        raise ProbeError("QUOTA_COMMITTED_RELEASE_NOT_DENIED")
    if release_after_usage.get("state") != "COMMITTED":
        raise ProbeError("QUOTA_COMMITTED_RELEASE_STATE_DRIFT")

    return {
        "release_terminal": True,
        "commit_state": "COMMITTED",
        "idempotent_commit": True,
        "double_charge": False,
        "event_v2_call": True,
        "receipt_bound": True,
        "authority": "HARA_COMMANDER",
    }


def self_check() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert DEV_ORIGIN.endswith(".workers.dev")
    forbidden_prod = "https://commander." + "haralabs.com.br"
    assert forbidden_prod not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                if any(isinstance(child, ast.Name) and child.id == "token" for child in ast.walk(arg)):
                    raise AssertionError("QUOTA_PROBE_SECRET_PRINT_SURFACE")
    print("COMMANDER_EVENT_V2_QUOTA_PROBE_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_QUOTA_PROBE_ORIGIN=DEV_ONLY")
    print("COMMANDER_EVENT_V2_QUOTA_PROBE_TOKEN_OUTPUT=ABSENT")


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
        raise ProbeError("QUOTA_PROBE_TIMEOUT_INVALID")

    token = load_token(Path(args.token_file))
    try:
        proof = run(token, args.subject.strip(), args.device_id.strip(), args.timeout)
    finally:
        token = ""

    print("COMMANDER_EVENT_V2_QUOTA_PARITY=PASS")
    print("COMMANDER_EVENT_V2_QUOTA_RELEASE_REPLAY=TERMINAL")
    print("COMMANDER_EVENT_V2_QUOTA_COMMIT=" + proof["commit_state"])
    print("COMMANDER_EVENT_V2_QUOTA_COMMIT_IDEMPOTENT=TRUE")
    print("COMMANDER_EVENT_V2_QUOTA_DOUBLE_CHARGE=FALSE")
    print("COMMANDER_EVENT_V2_QUOTA_RECEIPT_BOUND=TRUE")
    print("COMMANDER_EVENT_V2_QUOTA_AUTHORITY=" + proof["authority"])
    print("COMMANDER_EVENT_V2_QUOTA_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as exc:
        print("COMMANDER_EVENT_V2_QUOTA_PARITY=FAIL:" + str(exc))
        raise SystemExit(1)
