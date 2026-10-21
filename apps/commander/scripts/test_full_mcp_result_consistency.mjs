import assert from "node:assert/strict";
import { handleCustomerMcpRequest } from "../src/customer-mcp.mjs";

// Exercise the real full-profile MCP handler with a synthetic executor only.
const endpoint = "https://commander.example.invalid/api/mcp";
let nextId = 0;
const results = [];

async function check(name, run) {
  try {
    await run();
    results.push({ name, state: "PASS" });
  } catch (error) {
    results.push({ name, state: "FAIL", error: error.code || error.name });
  }
}

async function call(executor) {
  let executions = 0;
  const request = new Request(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
    body: JSON.stringify({
      jsonrpc: "2.0", id: ++nextId, method: "tools/call",
      params: { name: "hara.ping", arguments: { computer: "fixture" } },
    }),
  });
  const response = await handleCustomerMcpRequest(request, {
    executeTool: async input => { executions++; return executor(input); },
    authInfo: { token: "synthetic", clientId: "FULL_RESULT_TEST", scopes: ["openid"] },
    allowedHosts: ["commander.example.invalid"],
  });
  assert.equal(response.status, 200);
  let payload;
  if ((response.headers.get("content-type") || "").includes("application/json")) {
    payload = await response.json();
  } else {
    const line = (await response.text()).split(/\r?\n/).find(text => text.startsWith("data: "));
    assert.ok(line);
    payload = JSON.parse(line.slice(6));
  }
  assert.ok(payload.result);
  assert.equal(executions, 1);
  return payload.result;
}

const nativeDenied = code => ({
  state: "DENIED", mutation_performed: false,
  operational_authority: "LOCAL_OPERATOR_SESSION",
  bridge_receipt_sha256: "ab".repeat(32),
  blocker: { code }, result: {},
});

await check("classifies_known_native_operational_failure", async () => {
  const response = await call(() => nativeDenied("FILENOTFOUNDERROR"));
  const value = response.structuredContent;
  assert.equal(response.isError, true);
  assert.equal(value.state, "NOT_FOUND");
  assert.equal(value.source_state, "DENIED");
  assert.equal(value.blocker.code, "FILENOTFOUNDERROR");
  assert.equal(value.operational_authority, "LOCAL_OPERATOR_SESSION");
  assert.equal(value.bridge_receipt_sha256, "ab".repeat(32));
  assert.deepEqual(JSON.parse(response.content[0].text), value);
});
await check("keeps_real_denial", async () => {
  const value = nativeDenied("PERMISSIONERROR");
  const response = await call(() => value);
  assert.equal(response.isError, true);
  assert.deepEqual(response.structuredContent, value);
});
await check("keeps_uncertain_mutation", async () => {
  const value = { ...nativeDenied("FILENOTFOUNDERROR"), mutation_performed: null };
  const response = await call(() => value);
  assert.equal(response.isError, true);
  assert.deepEqual(response.structuredContent, value);
});
await check("flags_projected_direct_path_failure", async () => {
  const response = await call(() => nativeDenied("DEVICE_LOCAL_TUNNEL_DIRECT_PATH_REQUIRED"));
  assert.equal(response.isError, true);
  assert.equal(response.structuredContent.state, "DIRECT_PATH_REQUIRED");
  assert.equal(response.structuredContent.source_state, "DENIED");
});
for (const [name, executor] of [
  ["returned_timeout", () => nativeDenied("DEVICE_CALL_TIMEOUT")],
  ["thrown_timeout", () => { throw new Error("DEVICE_CALL_TIMEOUT"); }],
]) {
  await check(name, async () => {
    const response = await call(executor);
    const value = response.structuredContent;
    assert.equal(response.isError, true);
    assert.equal(value.state, "TIMEOUT");
    assert.equal(value.mutation_performed, null);
    assert.equal(value.blocker.retryable, false);
    assert.equal(value.blocker.requires_reconciliation, true);
    assert.equal(value.result.execution_outcome, "UNKNOWN");
    assert.equal(value.result.automatic_retry_allowed, false);
    assert.equal(value.result.next_action, "RECONCILE_EXISTING_CALL");
  });
}
await check("hides_arbitrary_exception_detail", async () => {
  const response = await call(() => { throw new Error("Bearer synthetic-fixture-secret at /private/fixture"); });
  assert.equal(response.isError, true);
  const text = response.content[0].text;
  assert.equal(JSON.parse(text).code, "COMMANDER_MCP_TOOL_FAILED");
  assert.ok(!text.includes("synthetic-fixture-secret"));
  assert.ok(!text.includes("private"));
});
for (const [code, category] of [
  ["AGENT_UPGRADE_REQUIRED", "AGENT_CAPABILITY"],
  ["LIST_OFFSET_UNSUPPORTED", "PAGINATION_CAPABILITY"],
]) {
  await check(`classifies_${code}`, async () => {
    const response = await call(() => { throw new Error(code); });
    assert.equal(response.isError, true);
    assert.equal(response.structuredContent.state, "UNAVAILABLE");
    assert.equal(response.structuredContent.blocker.code, code);
    assert.equal(response.structuredContent.blocker.category, category);
    assert.equal(response.structuredContent.blocker.retryable, false);
    assert.equal(response.structuredContent.result.recommended_tool, "hara.capabilities");
  });
}
await check("flags_native_failed_state", async () => {
  const value = { state: "FAILED", mutation_performed: false, result: {} };
  const response = await call(() => value);
  assert.equal(response.isError, true);
  assert.deepEqual(response.structuredContent, value);
});
await check("preserves_confirmed_success", async () => {
  const value = { state: "PASS", mutation_performed: true, result: { process_exit_code: 0 } };
  const response = await call(() => value);
  assert.notEqual(response.isError, true);
  assert.deepEqual(response.structuredContent, value);
});

console.log(JSON.stringify({
  schema: "hara.commander-full-mcp-result-consistency.v1",
  scope: "IN_PROCESS_FULL_MCP_HANDLER_SYNTHETIC_EXECUTOR_NO_NETWORK",
  checked: results.length,
  passed: results.filter(result => result.state === "PASS").length,
  results,
}, null, 2));
process.exitCode = results.some(result => result.state !== "PASS") ? 1 : 0;
