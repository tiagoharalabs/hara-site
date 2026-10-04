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
      "x-request-id": `test-http-${id}`,
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
assert.equal(tools.length, 35);
const mutationTools = new Set([
  "hara.files.create_directory",
  "hara.files.write",
  "hara.files.edit",
  "hara.files.move",
  "hara.files.copy",
  "hara.files.delete",
  "hara.files.rollback",
  "hara.process.start",
  "hara.process.interact",
  "hara.process.kill",
]);
for (const tool of tools) {
  assert.equal(tool.annotations?.readOnlyHint, !mutationTools.has(tool.name));
  assert.equal(tool.annotations?.destructiveHint, ["hara.files.write","hara.files.delete","hara.files.rollback","hara.process.interact","hara.process.kill"].includes(tool.name));
  assert.deepEqual(tool._meta?.securitySchemes, [
    { type: "oauth2", scopes: ["openid"] },
  ]);
}

const openWorldTools = new Set([
  "hara.functions.invoke",
  "hara.process.start",
  "hara.process.interact",
]);
for (const name of CUSTOMER_MCP_TOOLS) {
  assert.equal(
    tools.find((tool) => tool.name === name)?.annotations?.openWorldHint,
    openWorldTools.has(name),
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
assert.equal(calls[0].transport_request_id, "test-http-3");
assert.equal(calls[0].arguments.function_id, "device.info");

const purposeCall = await rpc(4, "tools/call", {
  name: "hara.processes.list",
  arguments: { computer: "nucleo-a", limit: 7 },
});
assert.equal(purposeCall.result?.isError, undefined);
assert.equal(calls.length, 2);
assert.equal(calls[1].tool_id, "hara.processes.list");
assert.equal(calls[1].arguments.computer, "nucleo-a");
assert.equal(calls[1].arguments.limit, 7);

const resourceCall = await rpc(41, "tools/call", {
  name: "hara.system.resources",
  arguments: { computer: "nucleo-a" },
});
assert.equal(resourceCall.result?.isError, undefined);
assert.equal(calls.at(-1).tool_id, "hara.system.resources");

const workspaceCall = await rpc(42, "tools/call", {
  name: "hara.workspace.inspect",
  arguments: { computer: "nucleo-a", path: "/srv/project", max_entries: 40 },
});
assert.equal(workspaceCall.result?.isError, undefined);
assert.equal(calls.at(-1).tool_id, "hara.workspace.inspect");
assert.equal(calls.at(-1).arguments.max_entries, 40);

const deniedUnknown = await rpc(5, "tools/call", {
  name: "shell.run",
  arguments: {},
});
assert.ok(deniedUnknown.error);
assert.equal(calls.length, 4);

const badHost = await handleCustomerMcpRequest(
  new Request("https://evil.example/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 6,
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
console.log("COMMANDER_CUSTOMER_MCP_PURPOSE_SPECIFIC_TOOLS=PASS");
console.log("COMMANDER_CUSTOMER_MCP_TOOL_ANNOTATIONS=PASS");
console.log("COMMANDER_CUSTOMER_MCP_SECURITY_SCHEMES=PASS");
console.log("COMMANDER_CUSTOMER_MCP_REQUEST_ID_BINDING=PASS");
console.log("COMMANDER_CUSTOMER_MCP_ARBITRARY_SHELL=DENIED");
console.log("COMMANDER_CUSTOMER_MCP_HOST_GUARD=PASS");
