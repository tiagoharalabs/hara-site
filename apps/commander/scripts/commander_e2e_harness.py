#!/usr/bin/env python3
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

DEFAULT_ORIGIN = "https://commander.haralabs.com.br"
FUNCTION_ID = "device.info"
TOOLS = (
    "hara.health",
    "hara.functions.list",
    "hara.functions.describe",
    "hara.functions.invoke",
    "hara.receipts.get",
)

class HarnessError(RuntimeError):
    pass

def load_token(path: Path) -> str:
    if not path.is_file():
        raise HarnessError("MCP_PRODUCT_TOKEN_FILE_MISSING")
    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise HarnessError("MCP_PRODUCT_TOKEN_FILE_PERMISSIONS")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 48:
        raise HarnessError("MCP_PRODUCT_TOKEN_INVALID")
    return token

def clean_origin(value: str) -> str:
    origin = value.rstrip("/")
    if not origin.startswith("https://"):
        raise HarnessError("COMMANDER_ORIGIN_MUST_BE_HTTPS")
    return origin

def post_json(origin: str, path: str, token: str, body: dict) -> dict:
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    req = Request(
        origin + path,
        data=payload,
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-hara-mcp-product-token": token,
            "user-agent": "HARA-Commander-E2E-Harness/1",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode()
            if not raw:
                return {}
            return json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode()
        try:
            obj = json.loads(raw or "{}")
        except json.JSONDecodeError:
            obj = {}
        code = str(obj.get("code") or f"HTTP_{exc.code}")
        raise HarnessError(code) from exc
    except URLError as exc:
        raise HarnessError("COMMANDER_NETWORK_ERROR") from exc

def request_id(prefix: str) -> str:
    return f"HARA-E2E-{prefix}-{uuid.uuid4()}"

def authorize(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    tool_id: str,
    req_id: str,
    *,
    function_id: str | None = None,
) -> dict:
    body = {
        "issuer": issuer,
        "subject": subject,
        "tool_id": tool_id,
        "request_id": req_id,
    }
    if function_id:
        body["function_id"] = function_id
    decision = post_json(origin, "/api/internal/mcp/authorize", token, body)
    if decision.get("allowed") is not True or decision.get("code") != "ALLOW":
        raise HarnessError(str(decision.get("code") or "MCP_AUTHORIZE_DENIED"))
    return decision

def release_quota(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    req_id: str,
) -> dict:
    obj = post_json(
        origin,
        "/api/internal/mcp/release",
        token,
        {"issuer": issuer, "subject": subject, "request_id": req_id},
    )
    if obj.get("transition") != "RELEASE":
        raise HarnessError("MCP_QUOTA_RELEASE_INVALID")
    return obj

def commit_quota(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    req_id: str,
    receipt_sha256: str,
) -> dict:
    if len(receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in receipt_sha256):
        raise HarnessError("MCP_RECEIPT_SHA256_INVALID")
    obj = post_json(
        origin,
        "/api/internal/mcp/commit",
        token,
        {
            "issuer": issuer,
            "subject": subject,
            "request_id": req_id,
            "receipt_sha256": receipt_sha256,
        },
    )
    if obj.get("transition") != "COMMIT":
        raise HarnessError("MCP_QUOTA_COMMIT_INVALID")
    return obj

def enqueue_call(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    tool_id: str,
    req_id: str,
    payload: dict,
) -> dict:
    obj = post_json(
        origin,
        "/api/internal/device/calls",
        token,
        {
            "issuer": issuer,
            "subject": subject,
            "tool_id": tool_id,
            "request_id": req_id,
            "payload": payload,
        },
    )
    if obj.get("schema") != "hara.commander-device-call.v1":
        raise HarnessError("DEVICE_CALL_ENQUEUE_INVALID")
    if obj.get("state") not in {"PENDING", "EXECUTING", "COMPLETED", "FAILED"}:
        raise HarnessError("DEVICE_CALL_STATE_INVALID")
    return obj

def call_status(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    call_id: str,
) -> dict:
    obj = post_json(
        origin,
        "/api/internal/device/calls/status",
        token,
        {"issuer": issuer, "subject": subject, "call_id": call_id},
    )
    if obj.get("schema") != "hara.commander-device-call-status.v1":
        raise HarnessError("DEVICE_CALL_STATUS_INVALID")
    return obj

def wait_terminal(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    call_id: str,
    timeout: float,
) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = call_status(origin, token, issuer, subject, call_id)
        state = str(last.get("state") or "")
        if state in {"COMPLETED", "FAILED", "EXPIRED", "CANCELLED"}:
            return last
        time.sleep(1.0)
    raise HarnessError(f"DEVICE_CALL_TIMEOUT_{str((last or {}).get('state') or 'UNKNOWN')}")

def quota_roundtrip(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
) -> None:
    req_id = request_id("QUOTA")
    reserved = False
    try:
        decision = authorize(
            origin,
            token,
            issuer,
            subject,
            "hara.functions.invoke",
            req_id,
            function_id=FUNCTION_ID,
        )
        usage = decision.get("usage") or {}
        if usage.get("ok") is not True:
            raise HarnessError("MCP_QUOTA_RESERVE_INVALID")
        if usage.get("state") not in {"RESERVED", "COMMITTED"}:
            raise HarnessError("MCP_QUOTA_RESERVE_STATE_INVALID")
        if usage.get("state") == "COMMITTED":
            raise HarnessError("MCP_QUOTA_REQUEST_ID_COLLISION")
        reserved = True
        released = release_quota(origin, token, issuer, subject, req_id)
        released_usage = released.get("usage") or {}
        if released_usage.get("state") != "RELEASED":
            raise HarnessError("MCP_QUOTA_RELEASE_STATE_INVALID")
        reserved = False

        replay = post_json(
            origin,
            "/api/internal/mcp/authorize",
            token,
            {
                "issuer": issuer,
                "subject": subject,
                "tool_id": "hara.functions.invoke",
                "request_id": req_id,
                "function_id": FUNCTION_ID,
            },
        )
        if replay.get("allowed") is not False or replay.get("code") != "REQUEST_USAGE_TERMINAL":
            raise HarnessError("MCP_QUOTA_RELEASE_REPLAY_GUARD_INVALID")

        print("COMMANDER_E2E_QUOTA_RESERVE=PASS")
        print("COMMANDER_E2E_QUOTA_RELEASE=PASS")
        print("COMMANDER_E2E_QUOTA_RELEASE_REPLAY=DENIED")
        print("COMMANDER_E2E_QUOTA_NET_USAGE=ZERO")
    finally:
        if reserved:
            try:
                release_quota(origin, token, issuer, subject, req_id)
                print("COMMANDER_E2E_QUOTA_CLEANUP=PASS")
            except Exception:
                print("COMMANDER_E2E_QUOTA_CLEANUP=PENDING")

def tool_payload(tool_id: str, receipt_sha256: str | None = None) -> dict:
    if tool_id in {"hara.health", "hara.functions.list"}:
        return {}
    if tool_id == "hara.functions.describe":
        return {"function_id": FUNCTION_ID}
    if tool_id == "hara.functions.invoke":
        return {"function_id": FUNCTION_ID, "arguments": {"argv": []}}
    if tool_id == "hara.receipts.get":
        if not receipt_sha256:
            raise HarnessError("RECEIPT_REQUIRED")
        return {"receipt_id_or_sha256": receipt_sha256}
    raise HarnessError("TOOL_ID_INVALID")

def execute_remote_tool(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    tool_id: str,
    *,
    receipt_sha256: str | None = None,
    timeout: float = 45.0,
) -> dict:
    req_id = request_id(tool_id.split(".")[-1].upper())
    reserved = False
    try:
        function_id = FUNCTION_ID if tool_id == "hara.functions.invoke" else None
        decision = authorize(
            origin,
            token,
            issuer,
            subject,
            tool_id,
            req_id,
            function_id=function_id,
        )
        if tool_id == "hara.functions.invoke":
            usage = decision.get("usage") or {}
            if usage.get("ok") is not True or usage.get("state") != "RESERVED":
                raise HarnessError("MCP_QUOTA_RESERVE_INVALID")
            reserved = True

        call = enqueue_call(
            origin,
            token,
            issuer,
            subject,
            tool_id,
            req_id,
            tool_payload(tool_id, receipt_sha256),
        )
        call_id = str(call.get("call_id") or "")
        if not call_id:
            raise HarnessError("DEVICE_CALL_ID_MISSING")
        terminal = wait_terminal(
            origin, token, issuer, subject, call_id, timeout
        )
        state = str(terminal.get("state") or "")
        if state != "COMPLETED":
            code = str(terminal.get("error_code") or state or "DEVICE_CALL_FAILED")
            raise HarnessError(code)

        result = terminal.get("result") or {}
        bridge_receipt = str(result.get("bridge_receipt_sha256") or "")
        if tool_id == "hara.functions.invoke":
            if len(bridge_receipt) != 64:
                raise HarnessError("DEVICE_RECEIPT_SHA256_MISSING")
            committed = commit_quota(
                origin,
                token,
                issuer,
                subject,
                req_id,
                bridge_receipt,
            )
            usage = committed.get("usage") or {}
            if usage.get("state") != "COMMITTED":
                raise HarnessError("MCP_QUOTA_COMMIT_STATE_INVALID")
            reserved = False

        print(f"COMMANDER_E2E_TOOL_{tool_id.upper().replace('.', '_')}=PASS")
        return {
            "tool_id": tool_id,
            "call_id": call_id,
            "receipt_sha256": bridge_receipt or None,
            "state": state,
        }
    finally:
        if reserved:
            try:
                release_quota(origin, token, issuer, subject, req_id)
                print("COMMANDER_E2E_INVOKE_QUOTA_CLEANUP=PASS")
            except Exception:
                print("COMMANDER_E2E_INVOKE_QUOTA_CLEANUP=PENDING")

def five_tool(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    timeout: float,
) -> None:
    execute_remote_tool(origin, token, issuer, subject, "hara.health", timeout=timeout)
    execute_remote_tool(origin, token, issuer, subject, "hara.functions.list", timeout=timeout)
    execute_remote_tool(origin, token, issuer, subject, "hara.functions.describe", timeout=timeout)
    invoked = execute_remote_tool(
        origin, token, issuer, subject, "hara.functions.invoke", timeout=timeout
    )
    execute_remote_tool(
        origin,
        token,
        issuer,
        subject,
        "hara.receipts.get",
        receipt_sha256=str(invoked["receipt_sha256"]),
        timeout=timeout,
    )
    print("COMMANDER_E2E_FIVE_TOOL=PASS")
    print("COMMANDER_E2E_QUOTA_COMMIT=PASS")

def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Run sanitized HARA Commander production E2E proofs."
    )
    ap.add_argument(
        "mode",
        choices=("quota-roundtrip", "five-tool"),
        help="reversible quota proof or full real-device five-tool proof",
    )
    ap.add_argument(
        "--origin",
        default=os.environ.get("HARA_COMMANDER_URL", DEFAULT_ORIGIN),
    )
    ap.add_argument(
        "--token-file",
        default=os.environ.get(
            "HARA_COMMANDER_MCP_TOKEN_FILE",
            str(Path(__file__).resolve().parents[1] / ".generated" / "mcp-product-prod-token"),
        ),
    )
    ap.add_argument(
        "--issuer",
        default=os.environ.get("HARA_E2E_ISSUER", ""),
    )
    ap.add_argument(
        "--subject",
        default=os.environ.get("HARA_E2E_SUBJECT", ""),
    )
    ap.add_argument("--timeout", type=float, default=45.0)
    return ap

def main() -> int:
    args = parser().parse_args()
    origin = clean_origin(args.origin)
    issuer = args.issuer.strip()
    subject = args.subject.strip()
    if not issuer or not subject:
        raise HarnessError("E2E_IDENTITY_REQUIRED")
    if args.timeout < 5 or args.timeout > 55:
        raise HarnessError("E2E_TIMEOUT_INVALID")

    token_path = Path(args.token_file).expanduser().resolve()
    token = load_token(token_path)
    try:
        if args.mode == "quota-roundtrip":
            quota_roundtrip(origin, token, issuer, subject)
        else:
            five_tool(origin, token, issuer, subject, args.timeout)
    finally:
        token = ""
    print("COMMANDER_E2E_SECRET_EXPOSED=FALSE")
    print(f"COMMANDER_E2E_MODE_{args.mode.upper().replace('-', '_')}=PASS")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as exc:
        print(f"COMMANDER_E2E=FAIL:{exc}")
        print("COMMANDER_E2E_SECRET_EXPOSED=FALSE")
        raise SystemExit(1)
