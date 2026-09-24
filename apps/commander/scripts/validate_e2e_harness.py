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

print("COMMANDER_E2E_HARNESS_CANONICAL_ORIGIN=PASS")
print("COMMANDER_E2E_HARNESS_REDIRECT_FAIL_CLOSED=PASS")
print("COMMANDER_E2E_HARNESS=PASS")
