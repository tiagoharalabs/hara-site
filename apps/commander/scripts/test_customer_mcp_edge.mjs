import assert from "node:assert/strict";

import {
  CUSTOMER_MCP_TOOLS,
  handleCustomerMcpRequest,
} from "../src/customer-mcp.mjs";

const endpoint = "https://mcp.haralabs.com.br/mcp";
const calls = [];

async function executeTool(request) {
  calls.push(request);
  if (request.arguments?.computer === "__offline__") throw new Error("DEVICE_OFFLINE");
  if (request.arguments?.computer === "__missing__") throw new Error("FILENOTFOUNDERROR");
  if (request.arguments?.computer === "__parent_missing__") throw new Error("PARENT_DIRECTORY_NOT_FOUND");
  if (request.arguments?.computer === "__winparent__") throw new Error("FILESYSTEM_PARENT_NOT_FOUND");
  if (request.arguments?.computer === "__winexists__") throw new Error("FILESYSTEM_PATH_EXISTS");
  if (request.arguments?.computer === "__windir__") throw new Error("FILESYSTEM_NOT_DIRECTORY");
  if (request.arguments?.computer === "__session_missing__") throw new Error("PROCESS_SESSION_NOT_FOUND");
  if (request.arguments?.computer === "__busy__") throw new Error("DEVICE_BUSY");
  if (request.arguments?.computer === "__timeout__") throw new Error("DEVICE_CALL_TIMEOUT");
  if (request.arguments?.computer === "__exists__") throw new Error("DESTINATION_EXISTS");
  if (request.arguments?.computer === "__ambiguous__") throw new Error("COMPUTER_NAME_AMBIGUOUS");
  if (request.arguments?.computer === "__denied__") throw new Error("POLICY_DENIED");
  if (request.arguments?.computer === "__local_tunnel__") throw new Error("DEVICE_LOCAL_TUNNEL_DIRECT_PATH_REQUIRED");
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
assert.equal(tools.length, 37);
const mutationTools = new Set([
  "hara.files.create_directory",
  "hara.files.write",
  "hara.files.edit",
  "hara.files.move",
  "hara.files.copy",
  "hara.files.delete",
  "hara.files.rollback",
  "hara.process.run",
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
  "hara.process.run",
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

const runCall = await rpc(43, "tools/call", {
  name: "hara.process.run",
  arguments: { computer: "nucleo-a", command: "printf hi", timeout_ms: 500, max_lines: 20 },
});
assert.equal(runCall.result?.isError, undefined);
assert.equal(calls.at(-1).tool_id, "hara.process.run");
assert.equal(calls.at(-1).arguments.timeout_ms, 500);

const longRunCall = await rpc(431, "tools/call", {
  name: "hara.process.run",
  arguments: { computer: "nucleo-a", command: "sleep 12", timeout_ms: 20000, max_lines: 20 },
});
assert.equal(longRunCall.result?.isError, undefined);
assert.equal(longRunCall.result?.structuredContent?.state, "REQUIRES_MANAGED_SESSION");
assert.equal(longRunCall.result?.structuredContent?.blocker?.code, "PROCESS_RUN_TIMEOUT_EXCEEDS_ONESHOT_LIMIT");
assert.equal(longRunCall.result?.structuredContent?.blocker?.retryable, true);
assert.equal(longRunCall.result?.structuredContent?.result?.one_shot_max_timeout_ms, 10000);
assert.equal(longRunCall.result?.structuredContent?.result?.recommended_tool, "hara.process.start");
assert.equal(longRunCall.result?.structuredContent?.result?.follow_up_tool, "hara.process.output");
assert.equal(calls.at(-1).arguments.timeout_ms, 500);

const activityCall = await rpc(44, "tools/call", {
  name: "hara.activity",
  arguments: { window: "7d", limit: 25 },
});
assert.equal(activityCall.result?.isError, undefined);
assert.equal(calls.at(-1).tool_id, "hara.activity");
assert.equal(calls.at(-1).arguments.window, "7d");
assert.equal(calls.at(-1).arguments.limit, 25);

const offlineHealth = await rpc(44, "tools/call", {
  name: "hara.health",
  arguments: { computer: "__offline__" },
});
assert.equal(offlineHealth.result?.isError, undefined);
assert.equal(offlineHealth.result?.structuredContent?.state, "UNAVAILABLE");
assert.equal(offlineHealth.result?.structuredContent?.blocker?.code, "DEVICE_OFFLINE");
assert.equal(offlineHealth.result?.structuredContent?.blocker?.retryable, true);
assert.equal(offlineHealth.result?.structuredContent?.computer, "__offline__");

const deniedUnknown = await rpc(5, "tools/call", {
  name: "shell.run",
  arguments: {},
});
assert.ok(deniedUnknown.error);
assert.equal(calls.length, 7);

const missingInfo = await rpc(81, "tools/call", { name: "hara.files.info", arguments: { computer: "__missing__", path: "/tmp/missing" } });
assert.equal(missingInfo.result?.isError, undefined);
assert.equal(missingInfo.result?.structuredContent?.state, "NOT_FOUND");

const parentMissing = await rpc(82, "tools/call", { name: "hara.files.write", arguments: { computer: "__parent_missing__", path: "/tmp/no-parent/file", content: "x", mode: "rewrite" } });
assert.equal(parentMissing.result?.structuredContent?.state, "NOT_FOUND");
assert.equal(parentMissing.result?.structuredContent?.result?.recommended_tool, "hara.files.create_directory");

const sessionMissing = await rpc(83, "tools/call", { name: "hara.process.output", arguments: { computer: "__session_missing__", session_id: "missing", length: 20 } });
assert.equal(sessionMissing.result?.structuredContent?.state, "NOT_FOUND");
assert.equal(sessionMissing.result?.structuredContent?.result?.recommended_tool, "hara.process.sessions");

const busy = await rpc(84, "tools/call", { name: "hara.ping", arguments: { computer: "__busy__" } });
assert.equal(busy.result?.structuredContent?.state, "BUSY");
assert.equal(busy.result?.structuredContent?.blocker?.retryable, true);

const timeout = await rpc(85, "tools/call", { name: "hara.process.run", arguments: { computer: "__timeout__", command: "sleep 1", timeout_ms: 500, max_lines: 20 } });
assert.equal(timeout.result?.structuredContent?.state, "TIMEOUT");
assert.equal(timeout.result?.structuredContent?.blocker?.retryable, true);

const conflict = await rpc(86, "tools/call", { name: "hara.files.copy", arguments: { computer: "__exists__", source: "/tmp/a", destination: "/tmp/b" } });
assert.equal(conflict.result?.structuredContent?.state, "CONFLICT");

const ambiguous = await rpc(87, "tools/call", { name: "hara.ping", arguments: { computer: "__ambiguous__" } });
assert.equal(ambiguous.result?.structuredContent?.state, "NEEDS_INPUT");
assert.equal(ambiguous.result?.structuredContent?.result?.selection_required, true);

const localTunnel = await rpc(89, "tools/call", { name: "hara.ping", arguments: { computer: "__local_tunnel__" } });
assert.equal(localTunnel.result?.isError, undefined);
assert.equal(localTunnel.result?.structuredContent?.state, "DIRECT_PATH_REQUIRED");
assert.equal(localTunnel.result?.structuredContent?.blocker?.retryable, false);
assert.equal(localTunnel.result?.structuredContent?.result?.recommended_transport, "LOCAL_TUNNEL");
assert.equal(localTunnel.result?.structuredContent?.result?.remote_relay_required, false);

const denied = await rpc(88, "tools/call", { name: "hara.ping", arguments: { computer: "__denied__" } });
assert.equal(denied.result?.isError, true);
assert.match(denied.result?.content?.[0]?.text || "", /POLICY_DENIED/);

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
