#!/usr/bin/env python3
from pathlib import Path
import ast

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
