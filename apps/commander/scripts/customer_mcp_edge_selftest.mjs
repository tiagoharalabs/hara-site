import assert from "node:assert/strict";

import {
  CUSTOMER_MCP_PROTOCOL_VERSION,
  customerMcpToolDefinitions,
  handleCustomerMcpProtocol,
  normalizeCustomerToolPayload,
} from "../src/mcp-customer-edge.mjs";
import {
  customerMcpEnabled,
  customerMcpProtectedResourceMetadata,
  customerMcpUnauthorized,
} from "../src/mcp-hara-identity.mjs";
import {
  projectCustomerToolResponse,
} from "../src/mcp-customer-projection.mjs";

function rpc(method, params = {}, id = 1) {
  return new Request("https://commander.haralabs.com.br/api/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });
}

const tools = customerMcpToolDefinitions();
assert.equal(tools.length, 5);
assert.deepEqual(
  tools.map((tool) => tool.name),
  [
    "hara.health",
    "hara.functions.list",
    "hara.functions.describe",
    "hara.functions.invoke",
    "hara.receipts.get",
  ],
);
for (const tool of tools) {
  assert.equal(tool.annotations.readOnlyHint, true);
  assert.equal(tool.annotations.destructiveHint, false);
  assert.equal(tool.annotations.idempotentHint, true);
}
assert.equal(tools.find((x) => x.name === "hara.functions.invoke").annotations.openWorldHint, true);
assert.equal(tools.filter((x) => x.name !== "hara.functions.invoke").every((x) => x.annotations.openWorldHint === false), true);

const initialize = await handleCustomerMcpProtocol(rpc("initialize", {
  protocolVersion: CUSTOMER_MCP_PROTOCOL_VERSION,
  capabilities: {},
  clientInfo: { name: "selftest", version: "1" },
}), { callTool: async () => ({}) });
assert.equal(initialize.status, 200);
const initializeBody = await initialize.json();
assert.equal(initializeBody.result.protocolVersion, CUSTOMER_MCP_PROTOCOL_VERSION);
assert.equal(initializeBody.result.serverInfo.name, "H.A.R.A. Commander");
assert.equal(initializeBody.result.capabilities.tools.listChanged, false);

const listResponse = await handleCustomerMcpProtocol(rpc("tools/list"), {
  callTool: async () => ({ raise: "not-called" }),
});
const listBody = await listResponse.json();
assert.equal(listBody.result.tools.length, 5);

let observed = null;
const callResponse = await handleCustomerMcpProtocol(rpc("tools/call", {
  name: "hara.functions.invoke",
  arguments: { function_id: "device.info", argv: [] },
}, "call-1"), {
  callTool: async (name, payload, ctx) => {
    observed = { name, payload, ctx };
    return {
      state: "PASS",
      operational_authority: "HARA_COMMANDER_AGENT",
      runtime_authority_from_chatgpt: false,
      mutation_performed: false,
      result: { function_id: "device.info", risk_class: "READ_ONLY", stdout: "{}" },
    };
  },
});
const callBody = await callResponse.json();
assert.equal(callBody.result.isError, false);
assert.equal(observed.name, "hara.functions.invoke");
assert.deepEqual(observed.payload, {
  function_id: "device.info",
  arguments: { argv: [] },
});
assert.equal(observed.ctx.rpc_id, "call-1");

const unknown = await handleCustomerMcpProtocol(rpc("tools/call", {
  name: "shell.run",
  arguments: {},
}), { callTool: async () => ({}) });
const unknownBody = await unknown.json();
assert.equal(unknownBody.result.isError, true);
assert.equal(unknownBody.result.structuredContent.code, "MCP_TOOL_NOT_FOUND");

assert.deepEqual(
  normalizeCustomerToolPayload("hara.receipts.get", {
    receipt_id_or_sha256: "A".repeat(64),
  }),
  { receipt_id_or_sha256: "a".repeat(64) },
);

const projection = projectCustomerToolResponse("hara.functions.invoke", {
  state: "PASS",
  operational_authority: "HARA_COMMANDER_AGENT",
  runtime_authority_from_chatgpt: false,
  mutation_performed: false,
  bridge_receipt_sha256: "a".repeat(64),
  result: {
    function_id: "device.info",
    risk_class: "READ_ONLY",
    stdout: "public",
    stderr: "",
    secret: "must-not-project",
    tenant_id: "must-not-project",
  },
  internal_trace: "must-not-project",
});
assert.equal(projection.result.stdout, "public");
assert.equal("secret" in projection.result, false);
assert.equal("tenant_id" in projection.result, false);
assert.equal("internal_trace" in projection, false);

const prodEnv = {
  ENVIRONMENT: "PROD",
  CUSTOMER_MCP_EDGE_ENABLED: "true",
  CUSTOMER_MCP_RESOURCE: "https://commander.haralabs.com.br/api/mcp",
  AUTH_ISSUER: "https://auth.haralabs.com.br/",
};
assert.equal(customerMcpEnabled(prodEnv), true);
const metadata = customerMcpProtectedResourceMetadata(
  new Request("https://commander.haralabs.com.br/.well-known/oauth-protected-resource"),
  prodEnv,
);
assert.equal(metadata.resource, "https://commander.haralabs.com.br/api/mcp");
assert.deepEqual(metadata.authorization_servers, ["https://auth.haralabs.com.br"]);
assert.deepEqual(metadata.scopes_supported, ["openid", "email"]);

const unauthorized = customerMcpUnauthorized(
  new Request("https://commander.haralabs.com.br/api/mcp"),
);
assert.equal(unauthorized.status, 401);
assert.match(
  unauthorized.headers.get("www-authenticate") || "",
  /resource_metadata="https:\/\/commander\.haralabs\.com\.br\/\.well-known\/oauth-protected-resource"/,
);

console.log("COMMANDER_CUSTOMER_MCP_PROTOCOL=PASS");
console.log("COMMANDER_CUSTOMER_MCP_EXACT_FIVE_TOOLS=PASS");
console.log("COMMANDER_CUSTOMER_MCP_TOOL_ANNOTATIONS=PASS");
console.log("COMMANDER_CUSTOMER_MCP_PUBLIC_PROJECTION=PASS");
console.log("COMMANDER_CUSTOMER_MCP_HARA_IDENTITY_METADATA=PASS");
console.log("COMMANDER_CUSTOMER_MCP_ARBITRARY_SHELL=FALSE");
console.log("COMMANDER_CUSTOMER_MCP_SERVICES_RELAY=FALSE");
