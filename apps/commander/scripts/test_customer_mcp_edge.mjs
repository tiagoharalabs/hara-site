import assert from "node:assert/strict";

import {
  CUSTOMER_MCP_TOOLS,
  handleCustomerMcpRequest,
} from "../src/customer-mcp.mjs";

const endpoint = "https://mcp.haralabs.com.br/mcp";
const calls = [];

async function executeTool(request) {
  calls.push(request);
  return {
    state: "PASS",
    operational_authority: "HARA_COMMANDER",
    runtime_authority_from_chatgpt: false,
    mutation_performed: false,
    tool_id: request.tool_id,
    result: { ok: true, echo: request.arguments },
  };
}

async function rpc(id, method, params = undefined) {
  const body = { jsonrpc: "2.0", id, method };
  if (params !== undefined) body.params = params;
  const request = new Request(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
    },
    body: JSON.stringify(body),
  });
  const response = await handleCustomerMcpRequest(request, {
    executeTool,
    authInfo: {
      token: "redacted",
      clientId: "HARA-TEST-CLIENT",
      scopes: ["openid"],
    },
    allowedHosts: ["mcp.haralabs.com.br"],
  });
  assert.equal(response.status, 200);
  const contentType = String(response.headers.get("content-type") || "");
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  const dataLine = text
    .split(/\r?\n/)
    .find((line) => line.startsWith("data: "));
  assert.ok(dataLine, "SSE response must contain a data frame");
  return JSON.parse(dataLine.slice(6));
}

const initialize = await rpc(1, "initialize", {
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "hara-test", version: "1" },
});
assert.equal(initialize.jsonrpc, "2.0");
assert.equal(initialize.id, 1);
assert.ok(initialize.result?.serverInfo);

const listed = await rpc(2, "tools/list", {});
const tools = listed.result?.tools || [];
assert.deepEqual(
  tools.map((tool) => tool.name),
  CUSTOMER_MCP_TOOLS,
);
assert.equal(tools.length, 5);
for (const tool of tools) {
  assert.equal(tool.annotations?.readOnlyHint, true);
  assert.equal(tool.annotations?.destructiveHint, false);
  assert.equal(tool.annotations?.idempotentHint, true);
  assert.deepEqual(tool._meta?.securitySchemes, [
    { type: "oauth2", scopes: ["openid"] },
  ]);
}
assert.equal(
  tools.find((tool) => tool.name === "hara.functions.invoke")
    ?.annotations?.openWorldHint,
  true,
);
for (const name of CUSTOMER_MCP_TOOLS.filter(
  (value) => value !== "hara.functions.invoke",
)) {
  assert.equal(
    tools.find((tool) => tool.name === name)?.annotations?.openWorldHint,
    false,
  );
}

const called = await rpc(3, "tools/call", {
  name: "hara.functions.describe",
  arguments: { function_id: "device.info" },
});
assert.equal(called.result?.isError, undefined);
assert.equal(called.result?.structuredContent?.state, "PASS");
assert.equal(calls.length, 1);
assert.equal(calls[0].tool_id, "hara.functions.describe");
assert.equal(calls[0].mcp_request_id, 3);
assert.equal(calls[0].arguments.function_id, "device.info");

const deniedUnknown = await rpc(4, "tools/call", {
  name: "shell.run",
  arguments: {},
});
assert.ok(deniedUnknown.error);
assert.equal(calls.length, 1);

const badHost = await handleCustomerMcpRequest(
  new Request("https://evil.example/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 5,
      method: "tools/list",
      params: {},
    }),
  }),
  {
    executeTool,
    allowedHosts: ["mcp.haralabs.com.br"],
  },
);
assert.equal(badHost.status, 421);

console.log("COMMANDER_CUSTOMER_MCP_PROTOCOL=PASS");
console.log("COMMANDER_CUSTOMER_MCP_EXACT_FIVE_TOOLS=PASS");
console.log("COMMANDER_CUSTOMER_MCP_TOOL_ANNOTATIONS=PASS");
console.log("COMMANDER_CUSTOMER_MCP_SECURITY_SCHEMES=PASS");
console.log("COMMANDER_CUSTOMER_MCP_REQUEST_ID_BINDING=PASS");
console.log("COMMANDER_CUSTOMER_MCP_ARBITRARY_SHELL=DENIED");
console.log("COMMANDER_CUSTOMER_MCP_HOST_GUARD=PASS");
