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

print("COMMANDER_E2E_HARNESS=PASS")
