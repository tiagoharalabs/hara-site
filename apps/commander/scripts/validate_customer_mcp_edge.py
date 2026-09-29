#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMMANDER = ROOT / "apps" / "commander"
MODULE = COMMANDER / "src" / "customer-mcp.mjs"
WORKER = COMMANDER / "src" / "worker.js"
PACKAGE = ROOT / "package.json"
TEST = COMMANDER / "scripts" / "test_customer_mcp_edge.mjs"

TOOLS = (
    "hara.health",
    "hara.functions.list",
    "hara.functions.describe",
    "hara.functions.invoke",
    "hara.receipts.get",
)


def main() -> int:
    module = MODULE.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))

    dependencies = package.get("dependencies") or {}
    assert dependencies.get("@modelcontextprotocol/server") == "2.2.0"
    assert dependencies.get("zod") == "4.6.5"

    assert "createMcpHandler" in module
    assert 'legacy: "stateless"' in module
    assert 'responseMode: "json"' in module
    assert "maxRequestBodySize: 256 * 1024" in module

    for tool in TOOLS:
        assert module.count(f'"{tool}"') >= 2, tool

    assert "readOnlyHint: true" in module
    assert "destructiveHint: false" in module
    assert "idempotentHint: true" in module
    assert "openWorldHint: true" in module
    assert 'securitySchemes: SECURITY_SCHEMES' in module
    assert '{ type: "oauth2", scopes: ["openid"] }' in module

    for forbidden in (
        "shell.run",
        "/bin/sh",
        "/bin/bash",
        "child_process",
        "/srv/hara",
        "services.haralabs",
    ):
        assert forbidden not in module, forbidden

    assert 'url.pathname === "/api/dev/mcp/proof"' in worker
    assert 'handleCustomerMcpRequest(request' in worker
    assert "executeCustomerMcpTool(" in worker
    assert "customer_services_relay: false" in worker
    assert "enqueueDeviceCall(env" in worker
    assert "deviceCallStatus(env" in worker
    assert 'execution_authority: "HARA_COMMANDER_AGENT"' in worker
    health_projection = worker.split('if (toolId === "hara.health") {', 1)[1].split(
        '} else if (toolId === "hara.functions.list") {',
        1,
    )[0]
    for forbidden in ("services_bridge_state", "hara_services_state", '"authority"'):
        assert forbidden not in health_projection, forbidden
    for required in (
        '"device_id"',
        '"hostname"',
        '"platform"',
        '"agent_version"',
        '"tunnel_mode"',
    ):
        assert required in health_projection, required
    receipt_projection = worker.split('} else if (toolId === "hara.receipts.get") {', 1)[1].split(
        "\n  }\n\n  const projected =",
        1,
    )[0]
    assert '"execution_authority"' in receipt_projection
    assert ".reserve(" in worker
    assert ".commit(" in worker
    assert ".release(" in worker

    customer_executor = worker.split(
        "async function executeCustomerMcpTool(", 1
    )[1].split(
        "async function claimNextDeviceCall(", 1
    )[0]
    assert 'reservation.state === "COMMITTED"' in customer_executor
    assert "CUSTOMER_MCP_COMMITTED_RECEIPT_INVALID" in customer_executor
    assert "CUSTOMER_MCP_QUOTA_STATE_INVALID" in customer_executor
    assert "replayed: true" in customer_executor
    assert "bridge_receipt_sha256: committedReceiptSha" in customer_executor
    assert customer_executor.index(
        'reservation.state === "COMMITTED"'
    ) < customer_executor.index("enqueueDeviceCall(env")
    committed_replay = customer_executor.split(
        'if (reservation.state === "COMMITTED") {', 1
    )[1].split(
        'if (reservation.state !== "RESERVED") {', 1
    )[0]
    assert "enqueueDeviceCall" not in committed_replay
    assert ".commit(" not in committed_replay
    assert ".release(" not in committed_replay

    assert 'allowedHosts: ["hara-commander-dev-v2.tiago-sartori.workers.dev"]' in worker

    subprocess.run(
        ["node", str(TEST)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        ["npm", "audit", "--omit=dev"],
        cwd=ROOT,
        check=True,
    )

    print("COMMANDER_CUSTOMER_MCP_SDK_PIN=PASS")
    print("COMMANDER_CUSTOMER_MCP_EXACT_FIVE_TOOLS=PASS")
    print("COMMANDER_CUSTOMER_MCP_OAUTH_SCHEME=PASS")
    print("COMMANDER_CUSTOMER_MCP_DURABLE_DEVICE_PATH=PASS")
    print("COMMANDER_CUSTOMER_MCP_QUOTA_LIFECYCLE=PASS")
    print("COMMANDER_CUSTOMER_MCP_COMMITTED_REPLAY=PASS")
    print("COMMANDER_CUSTOMER_MCP_CUSTOMER_SERVICES_RELAY=FALSE")
    print("COMMANDER_CUSTOMER_MCP_EXECUTION_AUTHORITY=HARA_COMMANDER_AGENT")
    print("COMMANDER_CUSTOMER_MCP_HEALTH_DEVICE_PROJECTION=PASS")
    print("COMMANDER_CUSTOMER_MCP_RUNTIME_VULNERABILITIES=0")
    print("COMMANDER_CUSTOMER_MCP_EDGE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
