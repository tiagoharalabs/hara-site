#!/usr/bin/env python3
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "apps/commander/scripts/commander_e2e_harness.py"
SOURCE = HARNESS.read_text(encoding="utf-8")

ast.parse(SOURCE)

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_E2E_HARNESS_{code}=FAIL")
    print(f"COMMANDER_E2E_HARNESS_{code}=PASS")

for tool in (
    "hara.health",
    "hara.functions.list",
    "hara.functions.describe",
    "hara.functions.invoke",
    "hara.receipts.get",
):
    need(repr(tool) in SOURCE or f'"{tool}"' in SOURCE, "TOOL_" + tool.upper().replace(".", "_"))

need("x-hara-mcp-product-token" in SOURCE, "PRODUCT_TOKEN_HEADER")
need("MCP_QUOTA_RESERVE_INVALID" in SOURCE, "QUOTA_RESERVE_GUARD")
need("MCP_QUOTA_RELEASE_STATE_INVALID" in SOURCE, "QUOTA_RELEASE_GUARD")
need("REQUEST_USAGE_TERMINAL" in SOURCE, "RELEASE_REPLAY_GUARD")
need("MCP_QUOTA_COMMIT_STATE_INVALID" in SOURCE, "QUOTA_COMMIT_GUARD")
need("DEVICE_RECEIPT_SHA256_MISSING" in SOURCE, "RECEIPT_GUARD")
need("finally:" in SOURCE and "release_quota(" in SOURCE, "FAILURE_RELEASE_PATH")
need("MCP_PRODUCT_TOKEN_VALUE" not in SOURCE, "SECRET_LITERAL_ABSENT")
need("print(token" not in SOURCE and "print(f\"{token" not in SOURCE, "SECRET_PRINT_ABSENT")
need("mode & 0o077" in SOURCE, "TOKEN_FILE_MODE_GUARD")
need("COMMANDER_E2E_SECRET_EXPOSED=FALSE" in SOURCE, "SECRET_EVIDENCE_MARKER")
need('"quota-roundtrip", "five-tool"' in SOURCE, "MODES")
need('parsed.netloc != "commander.haralabs.com.br"' in SOURCE, "CANONICAL_ORIGIN_HOST_GUARD")
need('origin != DEFAULT_ORIGIN' in SOURCE, "CANONICAL_ORIGIN_EXACT_GUARD")
need("NoRedirectHandler" in SOURCE and "NO_REDIRECT_OPENER.open" in SOURCE, "REDIRECT_FAIL_CLOSED")
need("COMMANDER_REDIRECT_DENIED" in SOURCE, "REDIRECT_DENIAL_MARKER")
need("reconcile_usage_state" in SOURCE, "QUOTA_RECONCILE_HELPER")
need("COMMANDER_E2E_QUOTA_COMMIT_RECONCILED=PASS" in SOURCE, "COMMIT_RECONCILE_MARKER")
need("COMMANDER_E2E_QUOTA_RELEASE_RECONCILED=PASS" in SOURCE, "RELEASE_RECONCILE_MARKER")
need("MCP_QUOTA_RECONCILE_RECEIPT_MISMATCH" in SOURCE, "RECONCILE_RECEIPT_GUARD")
need("DEVICE_CALL_SELECTED_DEVICE_CHANGED" in SOURCE, "SELECTED_DEVICE_STABILITY_GUARD")
need("DEVICE_CALL_STATUS_DEVICE_ID_MISMATCH" in SOURCE, "STATUS_DEVICE_CORRELATION_GUARD")
need("DEVICE_HEALTH_AGENT_VERSION_MISMATCH" in SOURCE, "AGENT_VERSION_GUARD")
need("RELEASE_MANIFEST" in SOURCE and "stable_agent_version" in SOURCE, "RELEASE_MANIFEST_VERSION_GUARD")
need("expected_receipt_request_id" in SOURCE, "RECEIPT_REQUEST_CORRELATION_GUARD")
need("result_stdout_sha256" in SOURCE, "RECEIPT_STDOUT_BINDING_GUARD")
need("defer_invoke_quota_commit=True" in SOURCE, "DEFERRED_INVOKE_COMMIT_GUARD")
five_tool_source = SOURCE.split("def five_tool(", 1)[1].split("def parser()", 1)[0]
need(
    five_tool_source.index('"hara.receipts.get"') < five_tool_source.index("committed = commit_quota("),
    "RECEIPT_PROOF_BEFORE_QUOTA_COMMIT",
)
need(
    "COMMANDER_E2E_RECEIPT_PROOF_FAILURE_RELEASE=PASS" in five_tool_source,
    "RECEIPT_PROOF_FAILURE_RELEASE_GUARD",
)

namespace = {
    "__name__": "commander_e2e_harness_test",
    "__file__": str(HARNESS),
}
exec(compile(SOURCE, str(HARNESS), "exec"), namespace)
clean_origin = namespace["clean_origin"]
HarnessError = namespace["HarnessError"]

assert clean_origin("https://commander.haralabs.com.br") == "https://commander.haralabs.com.br"
assert clean_origin("https://commander.haralabs.com.br/") == "https://commander.haralabs.com.br"
for bad_origin in (
    "http://commander.haralabs.com.br",
    "https://commander.haralabs.com.br.evil.example",
    "https://commander.haralabs.com.br/path",
    "https://commander.haralabs.com.br?x=1",
    "https://commander.haralabs.com.br#fragment",
    "https://user@commander.haralabs.com.br",
):
    try:
        clean_origin(bad_origin)
    except HarnessError as exc:
        assert str(exc) == "COMMANDER_ORIGIN_NOT_CANONICAL"
    else:
        raise SystemExit("COMMANDER_E2E_HARNESS_NONCANONICAL_ORIGIN_ALLOWED=FAIL")


validate_tool_result = namespace["validate_tool_result"]
canonical_json_sha256 = namespace["canonical_json_sha256"]
stable_agent_version = namespace["stable_agent_version"]
EXPECTED_DEVICE = "device"
EXPECTED_VERSION = stable_agent_version()
need(bool(EXPECTED_VERSION), "STABLE_AGENT_VERSION")

def base_wrapper(inner: dict, *, bridge_receipt_sha256=None) -> dict:
    wrapper = {
        "state": "PASS",
        "operational_authority": "HARA_SERVICES",
        "runtime_authority_from_chatgpt": False,
        "mutation_performed": False,
        "result": inner,
        "blocker": None,
    }
    if bridge_receipt_sha256 is not None:
        wrapper["bridge_receipt_sha256"] = bridge_receipt_sha256
    return wrapper

health = base_wrapper({
    "services_bridge_state": "PASS",
    "hara_services_state": "PASS",
    "registered_function_count": 1,
    "executable_function_count": 1,
    "authority": "HARA_SERVICES",
    "device": {"device_id": EXPECTED_DEVICE, "agent_version": EXPECTED_VERSION},
})
validate_tool_result("hara.health", health, expected_device_id=EXPECTED_DEVICE, expected_agent_version=EXPECTED_VERSION)
need(True, "SEMANTIC_HEALTH")

listing = base_wrapper({
    "registered_function_count": 1,
    "executable_function_count": 1,
    "active_function_count": 1,
    "domains": ["DEVICE"],
    "functions": [{"function_id": "device.info", "state": "ACTIVE"}],
})
validate_tool_result("hara.functions.list", listing, expected_device_id=EXPECTED_DEVICE, expected_agent_version=EXPECTED_VERSION)
need(True, "SEMANTIC_FUNCTION_LIST")

description = base_wrapper({
    "function_id": "device.info",
    "state": "ACTIVE",
    "EXECUTION_SEMANTICS": {
        "risk_class": "READ_ONLY",
        "change_intent_required": False,
    },
    "AUTHORITY": {"fail_closed": True},
})
validate_tool_result("hara.functions.describe", description, expected_device_id=EXPECTED_DEVICE, expected_agent_version=EXPECTED_VERSION)
need(True, "SEMANTIC_FUNCTION_DESCRIBE")

INVOKE_STDOUT = json.dumps({"device_id": EXPECTED_DEVICE, "agent_version": EXPECTED_VERSION})
INVOKE_STDOUT_SHA256 = hashlib.sha256(INVOKE_STDOUT.encode("utf-8")).hexdigest()
invoked = base_wrapper({
    "function_id": "device.info",
    "risk_class": "READ_ONLY",
    "process_exit_code": 0,
    "stdout": INVOKE_STDOUT,
    "domain_success_inferred": False,
}, bridge_receipt_sha256="a" * 64)
validate_tool_result("hara.functions.invoke", invoked, expected_device_id=EXPECTED_DEVICE, expected_agent_version=EXPECTED_VERSION)
need(True, "SEMANTIC_FUNCTION_INVOKE")

receipt = {
    "schema": "hara.commander-device-receipt.v1",
    "request_id": "req",
    "device_id": EXPECTED_DEVICE,
    "tool_id": "hara.functions.invoke",
    "function_id_if_any": "device.info",
    "transport_mode": "OUTBOUND_RELAY",
    "operational_authority": "HARA_SERVICES",
    "execution_authority": "HARA_COMMANDER_AGENT",
    "mutation_class": "READ_ONLY_OR_NONE_V1",
    "state": "PASS",
    "payload_values_persisted": False,
    "result_binding": "STDOUT_SHA256_V1",
    "result_stdout_sha256": INVOKE_STDOUT_SHA256,
    "completed_at_utc": "2026-09-24T00:00:00Z",
}
receipt_sha = canonical_json_sha256(receipt)
validate_tool_result(
    "hara.receipts.get",
    base_wrapper(receipt),
    expected_device_id=EXPECTED_DEVICE,
    expected_agent_version=EXPECTED_VERSION,
    expected_receipt_sha256=receipt_sha,
    expected_receipt_request_id="req",
    expected_receipt_stdout_sha256=INVOKE_STDOUT_SHA256,
)
need(True, "SEMANTIC_RECEIPT_CORRELATION")

wrong_stdout_receipt = dict(receipt)
wrong_stdout_receipt["result_stdout_sha256"] = "0" * 64
try:
    validate_tool_result(
        "hara.receipts.get",
        base_wrapper(wrong_stdout_receipt),
        expected_device_id=EXPECTED_DEVICE,
        expected_agent_version=EXPECTED_VERSION,
        expected_receipt_sha256=canonical_json_sha256(wrong_stdout_receipt),
        expected_receipt_request_id="req",
        expected_receipt_stdout_sha256=INVOKE_STDOUT_SHA256,
    )
except HarnessError as exc:
    need(
        str(exc) == "DEVICE_RECEIPT_SEMANTICS_INVALID",
        "SEMANTIC_RECEIPT_STDOUT_MISMATCH_DENIED",
    )
else:
    raise SystemExit(
        "COMMANDER_E2E_HARNESS_SEMANTIC_RECEIPT_STDOUT_MISMATCH_DENIED=FAIL"
    )

wrong_request_receipt = dict(receipt)
wrong_request_receipt["request_id"] = "other-request"
try:
    validate_tool_result(
        "hara.receipts.get",
        base_wrapper(wrong_request_receipt),
        expected_device_id=EXPECTED_DEVICE,
        expected_agent_version=EXPECTED_VERSION,
        expected_receipt_sha256=canonical_json_sha256(wrong_request_receipt),
        expected_receipt_request_id="req",
        expected_receipt_stdout_sha256=INVOKE_STDOUT_SHA256,
    )
except HarnessError as exc:
    need(str(exc) == "DEVICE_RECEIPT_SEMANTICS_INVALID", "SEMANTIC_RECEIPT_REQUEST_MISMATCH_DENIED")
else:
    raise SystemExit("COMMANDER_E2E_HARNESS_SEMANTIC_RECEIPT_REQUEST_MISMATCH_DENIED=FAIL")

bad_receipt = dict(receipt)
bad_receipt["completed_at_utc"] = "2026-09-24T00:00:01Z"
try:
    validate_tool_result(
        "hara.receipts.get",
        base_wrapper(bad_receipt),
        expected_device_id=EXPECTED_DEVICE,
        expected_agent_version=EXPECTED_VERSION,
        expected_receipt_sha256=receipt_sha,
        expected_receipt_request_id="req",
        expected_receipt_stdout_sha256=INVOKE_STDOUT_SHA256,
    )
except HarnessError as exc:
    need(str(exc) == "DEVICE_RECEIPT_CORRELATION_INVALID", "SEMANTIC_RECEIPT_MISMATCH_DENIED")
else:
    raise SystemExit("COMMANDER_E2E_HARNESS_SEMANTIC_RECEIPT_MISMATCH_DENIED=FAIL")

bad_health = base_wrapper(dict(health["result"]))
bad_health["result"]["services_bridge_state"] = "FAIL"
try:
    validate_tool_result("hara.health", bad_health, expected_device_id=EXPECTED_DEVICE, expected_agent_version=EXPECTED_VERSION)
except HarnessError as exc:
    need(str(exc) == "DEVICE_HEALTH_SEMANTICS_INVALID", "SEMANTIC_BAD_HEALTH_DENIED")
else:
    raise SystemExit("COMMANDER_E2E_HARNESS_SEMANTIC_BAD_HEALTH_DENIED=FAIL")


bad_version = base_wrapper(json.loads(json.dumps(health["result"])))
bad_version["result"]["device"]["agent_version"] = "0.0.0-stale"
try:
    validate_tool_result(
        "hara.health",
        bad_version,
        expected_device_id=EXPECTED_DEVICE,
        expected_agent_version=EXPECTED_VERSION,
    )
except HarnessError as exc:
    need(str(exc) == "DEVICE_HEALTH_AGENT_VERSION_MISMATCH", "SEMANTIC_STALE_AGENT_DENIED")
else:
    raise SystemExit("COMMANDER_E2E_HARNESS_SEMANTIC_STALE_AGENT_DENIED=FAIL")

bad_device = base_wrapper(json.loads(json.dumps(health["result"])))
bad_device["result"]["device"]["device_id"] = "other-device"
try:
    validate_tool_result(
        "hara.health",
        bad_device,
        expected_device_id=EXPECTED_DEVICE,
        expected_agent_version=EXPECTED_VERSION,
    )
except HarnessError as exc:
    need(str(exc) == "DEVICE_HEALTH_DEVICE_ID_MISMATCH", "SEMANTIC_WRONG_DEVICE_DENIED")
else:
    raise SystemExit("COMMANDER_E2E_HARNESS_SEMANTIC_WRONG_DEVICE_DENIED=FAIL")

five_tool = namespace["five_tool"]
five_globals = five_tool.__globals__
original_execute_remote_tool = five_globals["execute_remote_tool"]
original_commit_quota = five_globals["commit_quota"]
original_release_quota = five_globals["release_quota"]
original_reconcile_usage_state = five_globals["reconcile_usage_state"]

success_events = []
def success_execute(_origin, _token, _issuer, _subject, tool_id, **kwargs):
    success_events.append(tool_id)
    if tool_id == "hara.health":
        return {"device_id": EXPECTED_DEVICE}
    if tool_id == "hara.functions.invoke":
        assert kwargs.get("defer_invoke_quota_commit") is True
        return {
            "device_id": EXPECTED_DEVICE,
            "request_id": "invoke-request",
            "receipt_sha256": "a" * 64,
            "result_stdout_sha256": INVOKE_STDOUT_SHA256,
            "quota_reserved_for_caller": True,
        }
    if tool_id == "hara.receipts.get":
        assert kwargs.get("expected_receipt_stdout_sha256") == INVOKE_STDOUT_SHA256
        success_events.append("RECEIPT_PROVEN")
    return {"device_id": EXPECTED_DEVICE}

def success_commit(_origin, _token, _issuer, _subject, request_id, receipt_sha256):
    assert "RECEIPT_PROVEN" in success_events
    assert request_id == "invoke-request"
    assert receipt_sha256 == "a" * 64
    success_events.append("QUOTA_COMMITTED")
    return {"usage": {"state": "COMMITTED"}}

five_globals["execute_remote_tool"] = success_execute
five_globals["commit_quota"] = success_commit
five_globals["release_quota"] = lambda *_a, **_k: (_ for _ in ()).throw(
    AssertionError("UNEXPECTED_RELEASE_ON_SUCCESS")
)
five_globals["reconcile_usage_state"] = lambda *_a, **_k: (_ for _ in ()).throw(
    AssertionError("UNEXPECTED_RECONCILE_ON_SUCCESS")
)
try:
    five_tool("https://commander.haralabs.com.br", "token", "issuer", "subject", 10, EXPECTED_VERSION)
finally:
    five_globals["execute_remote_tool"] = original_execute_remote_tool
    five_globals["commit_quota"] = original_commit_quota
    five_globals["release_quota"] = original_release_quota
    five_globals["reconcile_usage_state"] = original_reconcile_usage_state

need(
    success_events.index("RECEIPT_PROVEN") < success_events.index("QUOTA_COMMITTED"),
    "DYNAMIC_RECEIPT_PROOF_BEFORE_COMMIT",
)

failure_events = []
def failure_execute(_origin, _token, _issuer, _subject, tool_id, **kwargs):
    failure_events.append(tool_id)
    if tool_id == "hara.health":
        return {"device_id": EXPECTED_DEVICE}
    if tool_id == "hara.functions.invoke":
        return {
            "device_id": EXPECTED_DEVICE,
            "request_id": "invoke-request-fail",
            "receipt_sha256": "b" * 64,
            "result_stdout_sha256": INVOKE_STDOUT_SHA256,
            "quota_reserved_for_caller": True,
        }
    if tool_id == "hara.receipts.get":
        raise HarnessError("DEVICE_RECEIPT_SEMANTICS_INVALID")
    return {"device_id": EXPECTED_DEVICE}

five_globals["execute_remote_tool"] = failure_execute
five_globals["commit_quota"] = lambda *_a, **_k: failure_events.append("UNEXPECTED_COMMIT")
def failure_release(_origin, _token, _issuer, _subject, request_id):
    assert request_id == "invoke-request-fail"
    failure_events.append("QUOTA_RELEASED")
    return {"usage": {"state": "RELEASED"}}
five_globals["release_quota"] = failure_release
five_globals["reconcile_usage_state"] = original_reconcile_usage_state
try:
    try:
        five_tool("https://commander.haralabs.com.br", "token", "issuer", "subject", 10, EXPECTED_VERSION)
    except HarnessError as exc:
        assert str(exc) == "DEVICE_RECEIPT_SEMANTICS_INVALID"
    else:
        raise AssertionError("RECEIPT_FAILURE_NOT_PROPAGATED")
finally:
    five_globals["execute_remote_tool"] = original_execute_remote_tool
    five_globals["commit_quota"] = original_commit_quota
    five_globals["release_quota"] = original_release_quota
    five_globals["reconcile_usage_state"] = original_reconcile_usage_state

need("UNEXPECTED_COMMIT" not in failure_events, "DYNAMIC_BAD_RECEIPT_NOT_COMMITTED")
need(failure_events.count("QUOTA_RELEASED") == 1, "DYNAMIC_BAD_RECEIPT_RELEASED")

reconcile = namespace["reconcile_usage_state"]
globals_ = reconcile.__globals__
original_post_json = globals_["post_json"]
original_sleep = globals_["time"].sleep
globals_["time"].sleep = lambda _seconds: None

try:
    globals_["post_json"] = lambda *_args, **_kwargs: {
        "allowed": False,
        "code": "REQUEST_USAGE_TERMINAL",
        "usage": {"state": "RELEASED"},
    }
    released = reconcile("https://commander.haralabs.com.br", "token", "issuer", "subject", "req", "RELEASED")
    need(released.get("state") == "RELEASED", "RECONCILE_RELEASED")

    receipt = "a" * 64
    globals_["post_json"] = lambda *_args, **_kwargs: {
        "allowed": True,
        "code": "ALLOW",
        "usage": {"state": "COMMITTED", "receipt_sha256": receipt},
    }
    committed = reconcile(
        "https://commander.haralabs.com.br",
        "token",
        "issuer",
        "subject",
        "req",
        "COMMITTED",
        receipt_sha256=receipt,
    )
    need(committed.get("state") == "COMMITTED", "RECONCILE_COMMITTED")

    transient = iter((
        HarnessError("COMMANDER_NETWORK_ERROR"),
        {
            "allowed": True,
            "code": "ALLOW",
            "usage": {"state": "COMMITTED", "receipt_sha256": receipt},
        },
    ))
    def transient_post(*_args, **_kwargs):
        value = next(transient)
        if isinstance(value, Exception):
            raise value
        return value
    globals_["post_json"] = transient_post
    recovered = reconcile(
        "https://commander.haralabs.com.br",
        "token",
        "issuer",
        "subject",
        "req",
        "COMMITTED",
        receipt_sha256=receipt,
    )
    need(recovered.get("state") == "COMMITTED", "RECONCILE_TRANSIENT_NETWORK")

    globals_["post_json"] = lambda *_args, **_kwargs: {
        "allowed": True,
        "code": "ALLOW",
        "usage": {"state": "COMMITTED", "receipt_sha256": "b" * 64},
    }
    try:
        reconcile(
            "https://commander.haralabs.com.br",
            "token",
            "issuer",
            "subject",
            "req",
            "COMMITTED",
            receipt_sha256=receipt,
            attempts=1,
        )
    except HarnessError as exc:
        need(str(exc) == "MCP_QUOTA_RECONCILE_RECEIPT_MISMATCH", "RECONCILE_RECEIPT_MISMATCH_DENIED")
    else:
        raise SystemExit("COMMANDER_E2E_HARNESS_RECONCILE_RECEIPT_MISMATCH_DENIED=FAIL")
finally:
    globals_["post_json"] = original_post_json
    globals_["time"].sleep = original_sleep

print("COMMANDER_E2E_HARNESS_CANONICAL_ORIGIN=PASS")
print("COMMANDER_E2E_HARNESS_REDIRECT_FAIL_CLOSED=PASS")
print("COMMANDER_E2E_HARNESS=PASS")
