import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { handleSimpleCustomerMcpRequest } from '../src/customer-mcp-simple.mjs';

// In-process MCP messages only: no cloud, device commands or network calls.
const source = fs.readFileSync(new URL('../src/customer-mcp-simple.mjs', import.meta.url), 'utf8');
const endpoint = 'https://commander.example.invalid/mcp';
const tests = [];
let requestId = 0;
async function test(name, fn) {
  try { await fn(); tests.push({ name, state: 'PASS' }); }
  catch (error) { tests.push({ name, state: 'FAIL', error: error.code || error.name }); }
}
async function rpc(executor, name = 'ping', args = { computer: 'fixture' }) {
  let executions = 0;
  const request = new Request(endpoint, {
    method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream' },
    body: JSON.stringify({ jsonrpc: '2.0', id: ++requestId, method: 'tools/call', params: { name, arguments: args } }),
  });
  const response = await handleSimpleCustomerMcpRequest(request, {
    executeTool: async input => { executions++; return executor(input); },
    authInfo: { token: 'synthetic-not-a-credential', clientId: 'RESULT_CONSISTENCY_TEST', scopes: ['openid'] },
    allowedHosts: ['commander.example.invalid'],
  });
  assert.equal(response.status, 200);
  let payload;
  if ((response.headers.get('content-type') || '').includes('application/json')) payload = await response.json();
  else {
    const line = (await response.text()).split(/\r?\n/).find(x => x.startsWith('data: '));
    assert.ok(line); payload = JSON.parse(line.slice(6));
  }
  assert.ok(payload.result, 'MCP_TOOL_RESULT_REQUIRED');
  return { result: payload.result, executions };
}
const throwing = code => () => { throw new Error(code); };
for (const code of ['DEVICE_OFFLINE', 'DEVICE_EVENT_UNDELIVERED', 'DEVICE_BUSY', 'CHANNEL_TRANSIENT_BUSY', 'FILENOTFOUNDERROR',
  'PROCESS_SESSION_NOT_FOUND', 'PROCESS_SESSION_EXITED', 'FILE_PRECONDITION_FAILED', 'DESTINATION_EXISTS',
  'EDIT_MATCH_AMBIGUOUS', 'PATH_NOT_DIRECTORY', 'BINARY_FILE_DENIED', 'WRITE_TOO_LARGE', 'DEVICE_LOCAL_TUNNEL_DIRECT_PATH_REQUIRED']) {
  await test('operational_error_is_flagged_' + code, async () => {
    const { result, executions } = await rpc(throwing(code));
    assert.equal(result.isError, true); assert.equal(executions, 1);
    assert.equal(result.structuredContent.blocker.code, code);
    assert.deepEqual(JSON.parse(result.content[0].text), result.structuredContent);
  });
}
for (const code of ['DEVICE_CALL_TIMEOUT', 'CHANNEL_TRANSIENT_TIMEOUT']) {
  for (const [name, args] of [
    ['start_process', { computer: 'fixture', command: 'synthetic-unused-command', timeout_ms: 1000 }],
    ['write_file', { computer: 'fixture', path: '/tmp/fixture-only', content: 'synthetic-private-content' }],
    ['ping', { computer: 'fixture' }],
  ]) {
    await test('timeout_requires_reconciliation_' + code + '_' + name, async () => {
      const { result, executions } = await rpc(throwing(code), name, args);
      const value = result.structuredContent;
      assert.equal(result.isError, true); assert.equal(executions, 1);
      assert.equal(value.state, 'TIMEOUT'); assert.equal(value.blocker.retryable, false);
      assert.equal(value.blocker.requires_reconciliation, true);
      assert.equal(value.mutation_performed, null); assert.equal(value.result.completed, null);
      assert.equal(value.result.execution_outcome, 'UNKNOWN');
      assert.equal(value.result.automatic_retry_allowed, false);
      assert.equal(value.result.next_action, 'RECONCILE_EXISTING_CALL');
      assert.deepEqual(value.result.recommended_tools, ['get_recent_tool_calls', 'get_receipt']);
      assert.ok(!JSON.stringify(result).includes('synthetic-private-content'));
      assert.ok(!JSON.stringify(result).includes('synthetic-unused-command'));
      assert.deepEqual(JSON.parse(result.content[0].text), value);
    });
  }
}
for (const state of ['DENIED', 'FAILED', 'TIMEOUT', 'UNAVAILABLE', 'CONFLICT', 'CANCELLED']) {
  await test('returned_failure_not_disguised_as_success_' + state, async () => {
    const value = { state, mutation_performed: null, blocker: { code: 'SYNTHETIC' }, result: {} };
    const { result } = await rpc(() => value);
    assert.equal(result.isError, true); assert.deepEqual(result.structuredContent, value);
  });
}
for (const message of [
  'Connection failed at /private/fixture/path',
  'Header Authorization: Bearer synthetic-fixture-secret',
  '{"private":"synthetic-fixture"}',
  'Device returned\ninternal stack detail',
  'x'.repeat(500),
  'DEVICE_CALL_TIMEOUT with extra private details',
]) {
  await test('arbitrary_exception_details_are_not_published_' + tests.length, async () => {
    const { result } = await rpc(throwing(message));
    assert.equal(result.isError, true);
    const body = JSON.parse(result.content[0].text);
    assert.equal(body.code, 'COMMANDER_MCP_TOOL_FAILED');
    assert.ok(!result.content[0].text.includes('synthetic-fixture'));
    assert.ok(!result.content[0].text.includes('private'));
  });
}
await test('symbolic_policy_error_preserved', async () => {
  const { result } = await rpc(throwing('POLICY_DENIED'));
  assert.equal(result.isError, true); assert.equal(JSON.parse(result.content[0].text).code, 'POLICY_DENIED');
});
await test('edit_match_absent_does_not_claim_file_absent', async () => {
  const { result } = await rpc(throwing('EDIT_MATCH_NOT_FOUND'));
  assert.equal(result.isError, true); assert.equal(result.structuredContent.blocker.category, 'EDIT_MATCH');
  assert.equal(result.structuredContent.result.match_found, false);
  assert.equal(Object.hasOwn(result.structuredContent.result, 'exists'), false);
  assert.equal(result.structuredContent.result.recommended_tool, 'hara.files.read');
});
await test('confirmed_success_is_unchanged', async () => {
  const value = { state: 'PASS', mutation_performed: true, result: { process_exit_code: 0 } };
  const { result, executions } = await rpc(() => value);
  assert.notEqual(result.isError, true); assert.equal(executions, 1);
  assert.deepEqual(result.structuredContent, value); assert.deepEqual(JSON.parse(result.content[0].text), value);
});
await test('running_session_is_not_a_tool_failure', async () => {
  const value = { state: 'RUNNING', result: { session_id: 'synthetic-session' } };
  const { result } = await rpc(() => value); assert.notEqual(result.isError, true);
});
await test('process_exit_code_is_not_automatically_domain_failure', async () => {
  const value = { state: 'PASS', result: { process_exit_code: 1, domain_success_inferred: false } };
  const { result } = await rpc(() => value); assert.notEqual(result.isError, true);
  assert.deepEqual(result.structuredContent, value);
});
await test('failed_read_can_still_express_transient_availability', async () => {
  const { result } = await rpc(throwing('DEVICE_OFFLINE'));
  assert.equal(result.structuredContent.blocker.retryable, true);
  assert.equal(result.structuredContent.state, 'UNAVAILABLE');
});
await test('undelivered_notification_does_not_claim_device_offline_or_execution', async () => {
  const { result } = await rpc(throwing('DEVICE_EVENT_UNDELIVERED'));
  const value = result.structuredContent;
  assert.equal(value.state, 'UNAVAILABLE');
  assert.equal(value.blocker.category, 'DEVICE_DELIVERY');
  assert.equal(value.blocker.retryable, true);
  assert.equal(value.result.device_state, 'NOT_PROVEN_OFFLINE');
  assert.equal(value.result.execution_started, false);
  assert.equal(value.result.new_request_required, true);
});
await test('explicit_ok_false_is_a_tool_error', async () => {
  const { result } = await rpc(() => ({ ok: false, code: 'SYNTHETIC' }));
  assert.equal(result.isError, true);
});
console.log(JSON.stringify({ schema: 'hara.commander-mcp-result-consistency.v1',
  source_sha256: createHash('sha256').update(source).digest('hex'), node_version: process.version,
  scope: 'IN_PROCESS_REAL_MCP_HANDLER_SYNTHETIC_EXECUTOR_NO_NETWORK',
  checked: tests.length, passed: tests.filter(x => x.state === 'PASS').length,
  failed: tests.filter(x => x.state === 'FAIL').length, tests }, null, 2));
process.exitCode = tests.some(x => x.state !== 'PASS') ? 1 : 0;
