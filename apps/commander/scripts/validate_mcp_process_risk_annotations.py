#!/usr/bin/env python3
"""Fail-closed source contract: arbitrary process execution is destructive-risk.

MCP clients must not be told that arbitrary shell commands are non-destructive,
regardless of whether a particular invocation is read-only.
"""
from pathlib import Path

APP = Path(__file__).resolve().parents[1]


def tool(source: str, name: str) -> str:
    marker = '  server.registerTool(\n    "' + name + '",'
    assert marker in source, "MCP_PROCESS_RISK_TOOL_MISSING:" + name
    block = source.split(marker, 1)[1].split('  server.registerTool(', 1)[0]
    assert "readOnlyHint: false" in block, "MCP_PROCESS_READONLY_ANNOTATION_UNSAFE:" + name
    assert "destructiveHint: true" in block, "MCP_PROCESS_DESTRUCTIVE_ANNOTATION_MISSING:" + name
    assert "idempotentHint: false" in block, "MCP_PROCESS_IDEMPOTENCY_UNSAFE:" + name
    return block


full = (APP / "src/customer-mcp.mjs").read_text(encoding="utf-8")
simple = (APP / "src/customer-mcp-simple.mjs").read_text(encoding="utf-8")
for name in ("hara.process.run", "hara.process.start"):
    tool(full, name)
tool(simple, "start_process")
assert "ASK_EVERY_ACTION" in (APP / "public/install/linux.sh").read_text(encoding="utf-8")
assert "ASK_EVERY_ACTION" in (APP / "public/install/windows.ps1").read_text(encoding="utf-8")
print("MCP_PROCESS_FULL_PROFILE_DESTRUCTIVE_RISK=PASS")
print("MCP_PROCESS_SIMPLE_PROFILE_DESTRUCTIVE_RISK=PASS")
print("MCP_PROCESS_MISLEADING_NON_DESTRUCTIVE_HINT=ABSENT")
print("MCP_PROCESS_UNSIGNED_SOURCE_ONLY=TRUE")
