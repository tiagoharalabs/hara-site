// Source-only QA routing boundaries. Device rows, control credentials and native
// socket handles are explicit fixtures; no Services, provider, socket or load.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const NOW = Date.now();
const MEMBER = Object.freeze({ tenant_id: 'fixture-tenant', device_id: 'fixture-device' });
const NONCE = 'a'.repeat(32);
const BODY = Object.freeze({ ...MEMBER, nonce: NONCE });
const COMMON = Object.freeze({ source_head: 'b'.repeat(40), resource_sha256: 'c'.repeat(64),
  worker_version: '10000000-0000-4000-8000-000000000001' });

async function helpers() {
  const module = await import('../src/wss-live-witness-r163.mjs');
  assert.equal(typeof module.captureQaWssStatus, 'function', 'The gated DO capture helper must exist');
  assert.equal(typeof module.readQaWssStatus, 'function', 'The bounded QA read helper must exist');
  return module;
}

function status(changes = {}) {
  return { schema: 'hara.commander.r163.wss-status.v1', ...COMMON, ...MEMBER,
    nonce: NONCE, captured_ms: NOW,
    connections: [{ connection_id: '20000000-0000-4000-8000-000000000001',
      connected_at_ms: NOW - 1000, last_probe_ms: NOW - 100 }],
    native_acceptance: false, ...changes };
}

function internalRequest(headers = {}) {
  return new Request('https://device-channel/status', { headers: {
    'x-hara-channel-authenticated': '1', 'x-hara-tenant-id': MEMBER.tenant_id,
    'x-hara-device-id': MEMBER.device_id, 'x-hara-wss-witness-nonce': NONCE, ...headers,
  } });
}

function controlRequest({ method = 'POST', body = JSON.stringify(BODY), headers = {} } = {}) {
  return new Request('https://fixture.invalid/__qa/wss-status', { method,
    headers: { 'content-type': 'application/json', ...headers },
    ...(method === 'GET' ? {} : { body }),
  });
}

function fixture({ device = {}, reply = () => Response.json(status()) } = {}) {
  const log = [];
  const row = { ...MEMBER, state: 'ACTIVE', revoked_at_utc: null, tunnel_mode: 'EVENT_V2', ...device };
  const socket = { readyState: 1, deserializeAttachment: () => ({ ...MEMBER,
    connection_id: '20000000-0000-4000-8000-000000000001', connected_at_ms: NOW - 1000,
    superseded: false, event_v2_contract: 'commercial-0.3.56-durable-dev.v1' }) };
  const ctx = {
    getWebSockets: () => { log.push({ kind: 'sample' }); return [socket]; },
    getWebSocketAutoResponseTimestamp: () => { log.push({ kind: 'probe' }); return new Date(NOW - 100); },
  };
  const readDevice = async binding => { log.push({ kind: 'device', binding }); return row; };
  const env = {
    ENVIRONMENT: 'DEV', R163_QA_ISOLATED: 'true', R163_QA_WSS_WITNESS_ENABLED: 'true',
    R163_QA_BUDGET_V2_ENABLED: 'true', R163_QA_SOURCE_HEAD: COMMON.source_head,
    R163_QA_RESOURCE_SHA256: COMMON.resource_sha256, CF_VERSION_METADATA: { id: COMMON.worker_version },
    DEVICE_CHANNEL: { getByName: name => {
      log.push({ kind: 'namespace', name });
      return { fetch: async request => { log.push({ kind: 'fetch', request }); return reply(request); } };
    } },
  };
  return { env, ctx, readDevice, log, row };
}

test('all DEV isolation, budget, witness and immutable pin gates fail before any I/O', async () => {
  const { captureQaWssStatus, readQaWssStatus } = await helpers();
  for (const change of [
    { ENVIRONMENT: 'PROD' }, { R163_QA_ISOLATED: undefined }, { R163_QA_ISOLATED: true },
    { R163_QA_WSS_WITNESS_ENABLED: undefined }, { R163_QA_WSS_WITNESS_ENABLED: true },
    { R163_QA_BUDGET_V2_ENABLED: undefined }, { R163_QA_BUDGET_V2_ENABLED: true },
    { R163_QA_SOURCE_HEAD: undefined }, { R163_QA_SOURCE_HEAD: 'bad-head' },
    { R163_QA_RESOURCE_SHA256: undefined }, { R163_QA_RESOURCE_SHA256: 'bad-sha' },
    { CF_VERSION_METADATA: undefined }, { CF_VERSION_METADATA: { id: '' } },
  ]) {
    const f = fixture();
    Object.assign(f.env, change);
    await assert.rejects(() => captureQaWssStatus(internalRequest(), f.env, f.ctx, f.readDevice,
      { now: () => NOW }), /HOLD/);
    await assert.rejects(() => readQaWssStatus(controlRequest(), f.env), /HOLD/);
    assert.deepEqual(f.log, [], 'Denied configuration must not query D1, sockets or a DO');
  }
});

test('DO capture requires authenticated internal identity and a valid nonce before reading devices', async () => {
  const { captureQaWssStatus } = await helpers();
  for (const headers of [
    { 'x-hara-channel-authenticated': '' }, { 'x-hara-channel-authenticated': 'true' },
    { 'x-hara-tenant-id': '' }, { 'x-hara-device-id': '' },
    { 'x-hara-wss-witness-nonce': '' }, { 'x-hara-wss-witness-nonce': 'bad-nonce' },
  ]) {
    const f = fixture();
    await assert.rejects(() => captureQaWssStatus(internalRequest(headers), f.env, f.ctx,
      f.readDevice, { now: () => NOW }), /HOLD/);
    assert.deepEqual(f.log, []);
  }
});

test('live lifecycle and exact tenant/device must be verified before sampling native handles', async () => {
  const { captureQaWssStatus } = await helpers();
  for (const change of [
    { state: 'REVOKED' }, { revoked_at_utc: '2026-10-25T00:00:00Z' },
    { revoked_at_utc: undefined }, { tunnel_mode: 'EVENT_V2_OFFLINE' },
    { tunnel_mode: 'OUTBOUND_RELAY_OFFLINE' }, { tenant_id: 'other-tenant' },
    { device_id: 'other-device' },
  ]) {
    const f = fixture({ device: change });
    await assert.rejects(() => captureQaWssStatus(internalRequest(), f.env, f.ctx,
      f.readDevice, { now: () => NOW }), /HOLD/);
    assert.deepEqual(f.log.map(item => item.kind), ['device']);
  }
});

test('authorized live DO capture binds native observations to the configured source pins', async () => {
  const { captureQaWssStatus } = await helpers();
  const f = fixture();
  const result = await captureQaWssStatus(internalRequest(), f.env, f.ctx, f.readDevice, { now: () => NOW });
  assert.deepEqual(result, status());
  assert.equal(f.log[0].kind, 'device');
  assert.equal(f.log[0].binding.tenant_id, MEMBER.tenant_id);
  assert.equal(f.log[0].binding.device_id, MEMBER.device_id);
  assert.deepEqual(f.log.slice(1).map(item => item.kind), ['sample', 'probe']);
  assert.equal(result.native_acceptance, false);
});

test('one bounded POST queries only the exact scoped DO and builds fresh internal headers', async () => {
  const { readQaWssStatus } = await helpers();
  const f = fixture();
  const result = await readQaWssStatus(controlRequest({ headers: {
    authorization: 'Bearer SYNTHETIC_CONTROL_TEST_NOT_A_CREDENTIAL',
    'x-hara-tenant-id': 'untrusted-request-header',
  } }), f.env);
  assert.deepEqual(result, status());
  assert.deepEqual(f.log.map(item => item.kind), ['namespace', 'fetch']);
  assert.equal(f.log[0].name, MEMBER.tenant_id + ':' + MEMBER.device_id);
  const request = f.log[1].request;
  assert.ok(request instanceof Request);
  assert.equal(request.url, 'https://device-channel/status');
  assert.equal(request.method, 'GET');
  assert.equal(request.headers.get('x-hara-channel-authenticated'), '1');
  assert.equal(request.headers.get('x-hara-tenant-id'), MEMBER.tenant_id);
  assert.equal(request.headers.get('x-hara-device-id'), MEMBER.device_id);
  assert.equal(request.headers.get('x-hara-wss-witness-nonce'), NONCE);
  assert.equal(request.headers.get('authorization'), null);
  assert.equal(result.native_acceptance, false);
});

test('wrong methods, JSON keys and oversized declared or actual bytes fail before DO I/O', async () => {
  const { readQaWssStatus } = await helpers();
  for (const request of [
    { method: 'GET' }, { body: 'not-json' },
    { body: JSON.stringify({ ...MEMBER }) },
    { body: JSON.stringify({ ...BODY, extra: true }) },
    { body: JSON.stringify({ ...BODY, nonce: 'wrong' }) },
    { headers: { 'content-length': '4097' } },
    { body: ' '.repeat(4097) + JSON.stringify(BODY), headers: { 'content-length': '1' } },
  ]) {
    const f = fixture();
    await assert.rejects(() => readQaWssStatus(controlRequest(request), f.env), /HOLD/);
    assert.deepEqual(f.log, []);
  }
});

test('DO errors and mismatched identity, nonce, version, source or resources are HOLD', async () => {
  const { readQaWssStatus } = await helpers();
  for (const change of [
    { tenant_id: 'other-tenant' }, { device_id: 'other-device' }, { nonce: 'd'.repeat(32) },
    { source_head: 'e'.repeat(40) }, { worker_version: 'other-version' },
    { resource_sha256: 'f'.repeat(64) }, { native_acceptance: true }, { approved: true },
  ]) {
    const f = fixture({ reply: () => Response.json(status(change)) });
    await assert.rejects(() => readQaWssStatus(controlRequest(), f.env), /HOLD/);
    assert.deepEqual(f.log.map(item => item.kind), ['namespace', 'fetch']);
  }
  for (const reply of [
    () => Response.json(status(), { status: 503 }), () => new Response('not-json'),
  ]) {
    const f = fixture({ reply });
    await assert.rejects(() => readQaWssStatus(controlRequest(), f.env), /HOLD/);
  }
});

test('real QA control authenticates before dispatch and Core status uses authenticated lifecycle capture', async () => {
  const controlSource = await readFile(new URL('./recovery_queue_qa_worker_r163.mjs', import.meta.url), 'utf8');
  const coreSource = await readFile(new URL('../src/device-channel.mjs', import.meta.url), 'utf8');
  let called = 0;
  const sandbox = {
    Response, Request, URL, TextEncoder, crypto: globalThis.crypto,
    readQaWssStatus: async () => { called++; return status(); },
  };
  const runnable = controlSource
    .replace(/^import[^\n]*\n/gm, '')
    .replace(/^export class DeviceChannel[^\n]*\n/gm, '')
    .replace(/^export default[^\n]*\n?/gm, '');
  vm.runInNewContext(runnable + '\nglobalThis.qaUnderTest=legacyQaWorker;', sandbox);
  const f = fixture();
  const syntheticControl = 'SYNTHETIC_FIXTURE_CONTROL_NOT_A_CREDENTIAL';
  f.env.R163_QA_CONTROL_SHA256 = createHash('sha256').update(syntheticControl).digest('hex');
  const denied = await sandbox.qaUnderTest.fetch(controlRequest(), f.env, {});
  assert.equal(denied.status, 401);
  assert.equal(called, 0, 'An unauthenticated caller cannot trigger a witness read');
  const accepted = await sandbox.qaUnderTest.fetch(controlRequest({ headers: {
    authorization: 'Bearer ' + syntheticControl,
  } }), f.env, {});
  assert.equal(accepted.status, 200);
  assert.equal(called, 1);
  assert.equal((await accepted.json()).native_acceptance, false);

  const statusStart = coreSource.search(/if\s*\(url\.pathname\s*===\s*["']\/status["']/);
  const statusEnd = coreSource.indexOf('CHANNEL_ROUTE_NOT_FOUND', statusStart);
  assert.ok(statusStart >= 0 && statusEnd > statusStart);
  const branch = coreSource.slice(statusStart, statusEnd);
  assert.match(branch, /captureQaWssStatus\s*\(/);
  assert.match(branch, /this\.commercialDevice\s*\(/);
  assert.ok(coreSource.indexOf('requireAuthenticatedInternalRequest(request)') < statusStart,
    'Core internal authentication remains before the witness status branch');
});

test('real Core connect gates UUID attachments and status rechecks SQLite enrollment before counting', async t => {
  const { captureQaWssStatus } = await helpers();
  const { DatabaseSync } = await import('node:sqlite');
  const coreSource = await readFile(new URL('../src/device-channel.mjs', import.meta.url), 'utf8');

  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [NOW])); }
    static now() { return NOW; }
  }
  class RuntimeSocket {
    readyState = 1;
    attachment = null;
    serializeAttachment(value) { this.attachment = value; }
    deserializeAttachment() { return this.attachment; }
    close() { this.readyState = 3; }
  }
  class RuntimePair {
    constructor() { this[0] = new RuntimeSocket(); this[1] = new RuntimeSocket(); }
  }
  function RuntimeResponse(body, init = {}) {
    // Node's HTTP Response cannot express CF's 101+WebSocket extension. Only
    // that native boundary is replaced; ordinary responses are real Response.
    if (init.status === 101) return { status: 101, webSocket: init.webSocket };
    return new Response(body, init);
  }
  RuntimeResponse.json = Response.json.bind(Response);

  function makeCore(flags = {}) {
    const sqlite = new DatabaseSync(':memory:');
    t.after(() => sqlite.close());
    sqlite.exec(`CREATE TABLE commander_devices(
      device_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, state TEXT NOT NULL,
      revoked_at_utc TEXT, approval_mode TEXT, tunnel_mode TEXT, last_seen_at_utc TEXT)`);
    sqlite.prepare(`INSERT INTO commander_devices VALUES (?, ?, 'ACTIVE', NULL,
      'PERSISTENT_TRUSTED', 'OUTBOUND_RELAY', NULL)`).run(MEMBER.device_id, MEMBER.tenant_id);
    const sqlLog = [];
    const db = { prepare: sql => ({ bind: (...args) => ({
      run: async () => {
        sqlLog.push({ sql, args, method: 'run' });
        return { meta: { changes: sqlite.prepare(sql).run(...args).changes } };
      },
      first: async () => {
        sqlLog.push({ sql, args, method: 'first' });
        return sqlite.prepare(sql).get(...args) ?? null;
      },
    }) }) };
    const accepted = [], probes = new WeakMap(), storage = new Map();
    const ctx = {
      getWebSockets: () => [...accepted],
      acceptWebSocket: socket => accepted.push(socket),
      getWebSocketAutoResponseTimestamp: socket => probes.get(socket) ?? null,
      storage: { deleteAlarm: async () => {}, delete: async key => storage.delete(key),
        setAlarm: async () => {}, get: async key => storage.get(key),
        put: async (key, value) => storage.set(key, value) },
    };
    const env = { ...fixture().env, PRODUCT_DB: db,
      DEVICE_EVENT_V2_COMMERCIAL_0356_DEV_ENABLED: 'true',
      COMMANDER_RECOVERY_ALERTS_ENABLED: 'true', ...flags };
    const sandbox = {
      DurableObject: class {}, WebSocket: { OPEN: 1 }, WebSocketPair: RuntimePair,
      Response: RuntimeResponse, Request, URL, TextEncoder, Date: FixedDate,
      crypto: globalThis.crypto,
      captureQaWssStatus: (request, boundEnv, boundCtx, readDevice) =>
        captureQaWssStatus(request, boundEnv, boundCtx, readDevice, { now: () => NOW }),
    };
    vm.runInNewContext(coreSource.replace(/^import[^\n]*\n/gm, '').replace(/^export /gm, '')
      + '\nglobalThis.CoreUnderTest=DeviceChannel;', sandbox);
    return { channel: new sandbox.CoreUnderTest(ctx, env), accepted, probes, sqlite, sqlLog };
  }

  async function connect(f, commercial = false) {
    return f.channel.fetch(new Request('https://device-channel/connect', { headers: {
      'x-hara-channel-authenticated': '1', 'x-hara-tenant-id': MEMBER.tenant_id,
      'x-hara-device-id': MEMBER.device_id, upgrade: 'websocket',
      ...(commercial ? { 'x-hara-event-v2-contract': 'commercial-0.3.56-durable-dev.v1' } : {}),
    } }));
  }

  for (const disabled of [
    { R163_QA_WSS_WITNESS_ENABLED: undefined },
    { R163_QA_ISOLATED: 'false' }, { ENVIRONMENT: 'PROD' },
  ]) {
    const f = makeCore(disabled);
    assert.equal((await connect(f)).status, 101);
    assert.equal(f.accepted.length, 1);
    assert.equal(Object.hasOwn(f.accepted[0].deserializeAttachment(), 'connection_id'), false,
      'The legacy/default attachment must not acquire a QA witness identity');
  }

  const f = makeCore();
  assert.equal((await connect(f, true)).status, 101);
  const socket = f.accepted[0];
  const attachment = socket.deserializeAttachment();
  assert.match(attachment.connection_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(attachment.tenant_id, MEMBER.tenant_id);
  assert.equal(attachment.device_id, MEMBER.device_id);
  f.probes.set(socket, new Date(NOW));
  const response = await f.channel.fetch(internalRequest());
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.schema, 'hara.commander.r163.wss-status.v1');
  assert.equal(body.nonce, NONCE);
  for (const [key, value] of Object.entries({ ...COMMON, ...MEMBER })) assert.equal(body[key], value);
  assert.deepEqual(body.connections, [{ connection_id: attachment.connection_id,
    connected_at_ms: NOW, last_probe_ms: NOW }]);
  assert.equal(body.native_acceptance, false);
  const reads = f.sqlLog.filter(query => query.method === 'first');
  assert.ok(reads.length >= 1, 'The real commercialDevice method must read current D1 state');
  assert.deepEqual(reads.at(-1).args, [MEMBER.tenant_id, MEMBER.device_id]);
  assert.match(reads.at(-1).sql, /FROM commander_devices/);

  f.sqlite.prepare("UPDATE commander_devices SET state='REVOKED', revoked_at_utc=? WHERE device_id=?")
    .run('2026-10-25T00:00:00Z', MEMBER.device_id);
  assert.equal(socket.readyState, 1, 'The controlled socket remains OPEN while enrollment is revoked');
  const denied = await f.channel.fetch(internalRequest());
  assert.ok(denied.status >= 400, 'An OPEN handle cannot override revocation at the live D1 boundary');
  const deniedBody = await denied.json();
  assert.match(deniedBody.code, /^HOLD_/);
  assert.equal(deniedBody.connections, undefined);
});
