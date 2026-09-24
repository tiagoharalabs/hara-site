#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

APP = Path(__file__).resolve().parents[1]
RELEASE_MANIFEST = APP / "public/release/agent-manifest.json"
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

class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "REDIRECT_DENIED", headers, fp)

NO_REDIRECT_OPENER = build_opener(NoRedirectHandler)

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

def stable_agent_version() -> str:
    if not RELEASE_MANIFEST.is_file():
        raise HarnessError("AGENT_RELEASE_MANIFEST_MISSING")
    try:
        manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError("AGENT_RELEASE_MANIFEST_INVALID") from exc
    version = str(manifest.get("agent_version") or "").strip()
    if not version:
        raise HarnessError("AGENT_RELEASE_VERSION_MISSING")
    return version

def clean_origin(value: str) -> str:
    origin = value.rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "commander.haralabs.com.br"
        or parsed.path
        or parsed.query
        or parsed.fragment
        or origin != DEFAULT_ORIGIN
    ):
        raise HarnessError("COMMANDER_ORIGIN_NOT_CANONICAL")
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
        with NO_REDIRECT_OPENER.open(req, timeout=20) as response:
            raw = response.read().decode()
            if not raw:
                return {}
            return json.loads(raw)
    except HTTPError as exc:
        if 300 <= int(exc.code) < 400:
            raise HarnessError("COMMANDER_REDIRECT_DENIED") from exc
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

def usage_replay(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    req_id: str,
) -> dict:
    return post_json(
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

def reconcile_usage_state(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    req_id: str,
    expected_state: str,
    *,
    receipt_sha256: str | None = None,
    attempts: int = 3,
) -> dict:
    if expected_state not in {"RELEASED", "COMMITTED"}:
        raise HarnessError("MCP_QUOTA_RECONCILE_EXPECTATION_INVALID")
    last_error = None
    for attempt in range(attempts):
        try:
            replay = usage_replay(origin, token, issuer, subject, req_id)
            usage = replay.get("usage") or {}
            state = str(usage.get("state") or "")
            if expected_state == "RELEASED":
                if (
                    replay.get("allowed") is False
                    and replay.get("code") == "REQUEST_USAGE_TERMINAL"
                    and state == "RELEASED"
                ):
                    return usage
            elif (
                replay.get("allowed") is True
                and replay.get("code") == "ALLOW"
                and state == "COMMITTED"
            ):
                observed_receipt = str(usage.get("receipt_sha256") or "").lower()
                if receipt_sha256 is None or observed_receipt == receipt_sha256.lower():
                    return usage
                last_error = "MCP_QUOTA_RECONCILE_RECEIPT_MISMATCH"
        except HarnessError as exc:
            last_error = str(exc)
        if attempt + 1 < attempts:
            time.sleep(0.35)
    raise HarnessError(last_error or "MCP_QUOTA_RECONCILE_INVALID")

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
        try:
            released = release_quota(origin, token, issuer, subject, req_id)
            released_usage = released.get("usage") or {}
            if released_usage.get("state") != "RELEASED":
                raise HarnessError("MCP_QUOTA_RELEASE_STATE_INVALID")
        except HarnessError:
            reconcile_usage_state(
                origin, token, issuer, subject, req_id, "RELEASED"
            )
            print("COMMANDER_E2E_QUOTA_RELEASE_RECONCILED=PASS")
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
                try:
                    reconcile_usage_state(
                        origin, token, issuer, subject, req_id, "RELEASED"
                    )
                    print("COMMANDER_E2E_QUOTA_CLEANUP_RECONCILED=PASS")
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


def canonical_json_sha256(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def validate_tool_result(
    tool_id: str,
    wrapper: dict,
    *,
    expected_device_id: str,
    expected_agent_version: str,
    expected_receipt_sha256: str | None = None,
    expected_receipt_request_id: str | None = None,
) -> None:
    if wrapper.get("state") != "PASS":
        raise HarnessError("DEVICE_TOOL_RESULT_STATE_INVALID")
    if wrapper.get("operational_authority") != "HARA_SERVICES":
        raise HarnessError("DEVICE_TOOL_AUTHORITY_INVALID")
    if wrapper.get("runtime_authority_from_chatgpt") is not False:
        raise HarnessError("DEVICE_TOOL_RUNTIME_AUTHORITY_INVALID")
    if wrapper.get("mutation_performed") is not False:
        raise HarnessError("DEVICE_TOOL_MUTATION_FLAG_INVALID")
    if wrapper.get("blocker") is not None:
        raise HarnessError("DEVICE_TOOL_BLOCKER_PRESENT")
    inner = wrapper.get("result")
    if not isinstance(inner, dict):
        raise HarnessError("DEVICE_TOOL_RESULT_INVALID")

    if tool_id == "hara.health":
        if (
            inner.get("services_bridge_state") != "PASS"
            or inner.get("hara_services_state") != "PASS"
            or inner.get("authority") != "HARA_SERVICES"
        ):
            raise HarnessError("DEVICE_HEALTH_SEMANTICS_INVALID")
        device = inner.get("device") or {}
        if not isinstance(device, dict):
            raise HarnessError("DEVICE_HEALTH_DEVICE_INVALID")
        if str(device.get("device_id") or "") != expected_device_id:
            raise HarnessError("DEVICE_HEALTH_DEVICE_ID_MISMATCH")
        if str(device.get("agent_version") or "") != expected_agent_version:
            raise HarnessError("DEVICE_HEALTH_AGENT_VERSION_MISMATCH")
    elif tool_id == "hara.functions.list":
        functions = inner.get("functions")
        if not isinstance(functions, list):
            raise HarnessError("DEVICE_FUNCTION_LIST_INVALID")
        matches = [
            item for item in functions
            if isinstance(item, dict)
            and item.get("function_id") == FUNCTION_ID
            and item.get("state") == "ACTIVE"
        ]
        if (
            len(matches) != 1
            or inner.get("registered_function_count") != 1
            or inner.get("executable_function_count") != 1
            or inner.get("active_function_count") != 1
            or inner.get("domains") != ["DEVICE"]
        ):
            raise HarnessError("DEVICE_FUNCTION_LIST_SEMANTICS_INVALID")
    elif tool_id == "hara.functions.describe":
        semantics = inner.get("EXECUTION_SEMANTICS") or {}
        authority = inner.get("AUTHORITY") or {}
        if (
            inner.get("function_id") != FUNCTION_ID
            or inner.get("state") != "ACTIVE"
            or semantics.get("risk_class") != "READ_ONLY"
            or semantics.get("change_intent_required") is not False
            or authority.get("fail_closed") is not True
        ):
            raise HarnessError("DEVICE_FUNCTION_DESCRIBE_SEMANTICS_INVALID")
    elif tool_id == "hara.functions.invoke":
        if (
            inner.get("function_id") != FUNCTION_ID
            or inner.get("risk_class") != "READ_ONLY"
            or inner.get("process_exit_code") != 0
            or inner.get("domain_success_inferred") is not False
        ):
            raise HarnessError("DEVICE_FUNCTION_INVOKE_SEMANTICS_INVALID")
        try:
            stdout = json.loads(str(inner.get("stdout") or ""))
        except json.JSONDecodeError as exc:
            raise HarnessError("DEVICE_FUNCTION_INVOKE_STDOUT_INVALID") from exc
        if not isinstance(stdout, dict):
            raise HarnessError("DEVICE_FUNCTION_INVOKE_DEVICE_INVALID")
        if str(stdout.get("device_id") or "") != expected_device_id:
            raise HarnessError("DEVICE_FUNCTION_INVOKE_DEVICE_ID_MISMATCH")
        if str(stdout.get("agent_version") or "") != expected_agent_version:
            raise HarnessError("DEVICE_FUNCTION_INVOKE_AGENT_VERSION_MISMATCH")
    elif tool_id == "hara.receipts.get":
        if not expected_receipt_sha256 or not expected_receipt_request_id:
            raise HarnessError("RECEIPT_REQUIRED")
        if (
            inner.get("schema") != "hara.commander-device-receipt.v1"
            or inner.get("request_id") != expected_receipt_request_id
            or inner.get("device_id") != expected_device_id
            or inner.get("tool_id") != "hara.functions.invoke"
            or inner.get("function_id_if_any") != FUNCTION_ID
            or inner.get("transport_mode") != "OUTBOUND_RELAY"
            or inner.get("operational_authority") != "HARA_SERVICES"
            or inner.get("execution_authority") != "HARA_COMMANDER_AGENT"
            or inner.get("mutation_class") != "READ_ONLY_OR_NONE_V1"
            or inner.get("state") != "PASS"
            or inner.get("payload_values_persisted") is not False
        ):
            raise HarnessError("DEVICE_RECEIPT_SEMANTICS_INVALID")
        if canonical_json_sha256(inner) != expected_receipt_sha256.lower():
            raise HarnessError("DEVICE_RECEIPT_CORRELATION_INVALID")
    else:
        raise HarnessError("TOOL_ID_INVALID")

def execute_remote_tool(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    tool_id: str,
    *,
    expected_agent_version: str,
    expected_device_id: str | None = None,
    receipt_sha256: str | None = None,
    expected_receipt_request_id: str | None = None,
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
        call_device_id = str(call.get("device_id") or "")
        if not call_id:
            raise HarnessError("DEVICE_CALL_ID_MISSING")
        if not call_device_id:
            raise HarnessError("DEVICE_CALL_DEVICE_ID_MISSING")
        if expected_device_id and call_device_id != expected_device_id:
            raise HarnessError("DEVICE_CALL_SELECTED_DEVICE_CHANGED")
        terminal = wait_terminal(
            origin, token, issuer, subject, call_id, timeout
        )
        if str(terminal.get("call_id") or "") != call_id:
            raise HarnessError("DEVICE_CALL_STATUS_ID_MISMATCH")
        if str(terminal.get("request_id") or "") != req_id:
            raise HarnessError("DEVICE_CALL_STATUS_REQUEST_ID_MISMATCH")
        if str(terminal.get("device_id") or "") != call_device_id:
            raise HarnessError("DEVICE_CALL_STATUS_DEVICE_ID_MISMATCH")
        if str(terminal.get("tool_id") or "") != tool_id:
            raise HarnessError("DEVICE_CALL_STATUS_TOOL_ID_MISMATCH")
        state = str(terminal.get("state") or "")
        if state != "COMPLETED":
            code = str(terminal.get("error_code") or state or "DEVICE_CALL_FAILED")
            raise HarnessError(code)

        result = terminal.get("result") or {}
        validate_tool_result(
            tool_id,
            result,
            expected_device_id=call_device_id,
            expected_agent_version=expected_agent_version,
            expected_receipt_sha256=receipt_sha256,
            expected_receipt_request_id=expected_receipt_request_id,
        )
        bridge_receipt = str(result.get("bridge_receipt_sha256") or "").lower()
        if tool_id == "hara.functions.invoke":
            if (
                len(bridge_receipt) != 64
                or any(c not in "0123456789abcdef" for c in bridge_receipt)
            ):
                raise HarnessError("DEVICE_RECEIPT_SHA256_MISSING")
            try:
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
            except HarnessError:
                reconcile_usage_state(
                    origin,
                    token,
                    issuer,
                    subject,
                    req_id,
                    "COMMITTED",
                    receipt_sha256=bridge_receipt,
                )
                print("COMMANDER_E2E_QUOTA_COMMIT_RECONCILED=PASS")
            reserved = False

        print(f"COMMANDER_E2E_TOOL_{tool_id.upper().replace('.', '_')}=PASS")
        return {
            "tool_id": tool_id,
            "call_id": call_id,
            "request_id": req_id,
            "device_id": call_device_id,
            "receipt_sha256": bridge_receipt or None,
            "state": state,
        }
    finally:
        if reserved:
            try:
                release_quota(origin, token, issuer, subject, req_id)
                print("COMMANDER_E2E_INVOKE_QUOTA_CLEANUP=PASS")
            except Exception:
                try:
                    reconcile_usage_state(
                        origin, token, issuer, subject, req_id, "RELEASED"
                    )
                    print("COMMANDER_E2E_INVOKE_QUOTA_CLEANUP_RECONCILED=PASS")
                except Exception:
                    print("COMMANDER_E2E_INVOKE_QUOTA_CLEANUP=PENDING")

def five_tool(
    origin: str,
    token: str,
    issuer: str,
    subject: str,
    timeout: float,
    expected_agent_version: str,
) -> None:
    health = execute_remote_tool(
        origin,
        token,
        issuer,
        subject,
        "hara.health",
        expected_agent_version=expected_agent_version,
        timeout=timeout,
    )
    device_id = str(health["device_id"])
    for tool_id in ("hara.functions.list", "hara.functions.describe"):
        execute_remote_tool(
            origin,
            token,
            issuer,
            subject,
            tool_id,
            expected_agent_version=expected_agent_version,
            expected_device_id=device_id,
            timeout=timeout,
        )
    invoked = execute_remote_tool(
        origin,
        token,
        issuer,
        subject,
        "hara.functions.invoke",
        expected_agent_version=expected_agent_version,
        expected_device_id=device_id,
        timeout=timeout,
    )
    execute_remote_tool(
        origin,
        token,
        issuer,
        subject,
        "hara.receipts.get",
        expected_agent_version=expected_agent_version,
        expected_device_id=device_id,
        receipt_sha256=str(invoked["receipt_sha256"]),
        expected_receipt_request_id=str(invoked["request_id"]),
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
            five_tool(
                origin,
                token,
                issuer,
                subject,
                args.timeout,
                stable_agent_version(),
            )
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
