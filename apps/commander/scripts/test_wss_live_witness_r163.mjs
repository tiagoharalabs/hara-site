// Source-only witness boundaries. No Services, Cloudflare, load campaign or
// native admission. The final case uses two explicit loopback WebSockets;
// it does not establish TLS, hibernation, production routing or hosted capacity.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { once } from 'node:events';

const require = createRequire(import.meta.url);
const NOW = 1_700_000_000_000;
const NONCE = 'a'.repeat(32);
const COMMON = Object.freeze({
  source_head: 'b'.repeat(40),
  worker_version: '10000000-0000-4000-8000-000000000001',
  resource_sha256: 'c'.repeat(64),
});
const COHORT = Object.freeze([
  Object.freeze({ tenant_id: 'tenant-a', device_id: 'device-a' }),
  Object.freeze({ tenant_id: 'tenant-b', device_id: 'device-b' }),
]);
const CONTRACT = 'commercial-0.3.56-durable-dev.v1';

function cohortDigest(cohort) {
  // Independent expected encoding: JSON object keys sorted, array order intact.
  const canonical = JSON.stringify(cohort.map(member => ({ device_id: member.device_id, tenant_id: member.tenant_id })));
  return createHash('sha256').update(canonical).digest('hex');
}

async function interfaceUnderTest() {
  return import('../src/wss-live-witness-r163.mjs');
}

function nativeFixture(binding, options = {}) {
  const attachment = {
    tenant_id: binding.tenant_id, device_id: binding.device_id,
    connection_id: options.id ?? '20000000-0000-4000-8000-000000000001',
    connected_at_ms: NOW - 1000, superseded: false, event_v2_contract: CONTRACT,
    ...options.attachment,
  };
  const socket = { readyState: options.readyState ?? 1, deserializeAttachment: () => ({ ...attachment }) };
  return { socket, probe: options.probe === undefined ? NOW - 100 : options.probe };
}

function nativeContext(entries) {
  return {
    getWebSockets: () => entries.map(entry => entry.socket),
    getWebSocketAutoResponseTimestamp: socket => {
      const probe = entries.find(entry => entry.socket === socket)?.probe;
      return probe == null ? null : new Date(probe);
    },
  };
}

function status(member, index = 0, changes = {}) {
  return {
    schema: 'hara.commander.r163.wss-status.v1', ...COMMON, ...member,
    nonce: NONCE, captured_ms: NOW - 10,
    connections: [{ connection_id: `30000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      connected_at_ms: NOW - 1000, last_probe_ms: NOW - 100 }],
    native_acceptance: false, ...changes,
  };
}

function options(cohort = COHORT, changes = {}) {
  return { binding: COMMON, nonce: NONCE, now: () => NOW, maxConcurrent: 2,
    maxSpanMs: 5000, maxProbeAgeMs: 90_000, cohortSha256: cohortDigest(cohort), ...changes };
}

test('capture reads open native socket objects, excludes closing/superseded, and binds its nonce', async () => {
  const { captureWssStatus } = await interfaceUnderTest();
  const binding = { ...COMMON, ...COHORT[0] };
  const valid = nativeFixture(binding);
  const superseded = nativeFixture(binding, { probe: null, attachment: { superseded: true } });
  const closing = nativeFixture(binding, { readyState: 2, probe: null });
  const result = await captureWssStatus(nativeContext([valid, superseded, closing]), binding,
    { nonce: NONCE, now: () => NOW });
  assert.equal(result.schema, 'hara.commander.r163.wss-status.v1');
  for (const [key, value] of Object.entries(binding)) assert.equal(result[key], value);
  assert.equal(result.nonce, NONCE);
  assert.equal(result.captured_ms, NOW);
  assert.deepEqual(result.connections, [{ connection_id: valid.socket.deserializeAttachment().connection_id,
    connected_at_ms: NOW - 1000, last_probe_ms: NOW - 100 }]);
  assert.equal(result.native_acceptance, false);
});

test('an active zombie, missing, stale or future probe is HOLD even beside a healthy socket', async () => {
  const { captureWssStatus } = await interfaceUnderTest();
  const binding = { ...COMMON, ...COHORT[0] };
  for (const probe of [null, NOW - 90_001, NOW + 1]) {
    const entries = [nativeFixture(binding), nativeFixture(binding, {
      id: '20000000-0000-4000-8000-000000000002', probe,
    })];
    await assert.rejects(async () => captureWssStatus(nativeContext(entries), binding,
      { nonce: NONCE, now: () => NOW, maxProbeAgeMs: 90_000 }), /HOLD_WSS_PROBE/);
  }
});

test('cross-tenant active sockets and malformed pins or approval flags cannot create a witness', async () => {
  const { captureWssStatus } = await interfaceUnderTest();
  const binding = { ...COMMON, ...COHORT[0] };
  for (const field of ['tenant_id', 'device_id']) {
    const entries = [nativeFixture(binding), nativeFixture(binding, {
      attachment: { [field]: 'other-scope' },
    })];
    await assert.rejects(async () => captureWssStatus(nativeContext(entries), binding,
      { nonce: NONCE, now: () => NOW }), /HOLD_WSS_BINDING/);
  }
  for (const change of [
    { source_head: 'invalid' }, { worker_version: '' },
    { resource_sha256: 'invalid' }, { approved: true },
  ]) {
    await assert.rejects(async () => captureWssStatus(nativeContext([nativeFixture(binding)]),
      { ...binding, ...change }, { nonce: NONCE, now: () => NOW }), /HOLD/);
  }
  await assert.rejects(async () => captureWssStatus(nativeContext([nativeFixture(binding)]),
    binding, { nonce: 'invalid', now: () => NOW }), /HOLD/);
});

test('collector covers the exact cohort with bounded callbacks and reports source evidence only', async () => {
  const { collectWssWitness } = await interfaceUnderTest();
  let inFlight = 0, highWater = 0;
  const requested = [];
  const result = await collectWssWitness(COHORT, async member => {
    requested.push({ ...member });
    inFlight++;
    highWater = Math.max(highWater, inFlight);
    await new Promise(resolve => setImmediate(resolve));
    inFlight--;
    return status(member, COHORT.findIndex(item => item.device_id === member.device_id));
  }, options());
  assert.deepEqual(requested.sort((a, b) => a.device_id.localeCompare(b.device_id)), [...COHORT]);
  assert.ok(highWater <= 2);
  assert.equal(result.schema, 'hara.commander.r163.wss-witness.v1');
  assert.equal(result.live_wss, 2);
  assert.ok(result.observed_at_ms >= NOW - 10 && result.observed_at_ms <= NOW);
  assert.equal(result.records.length, 2);
  assert.equal(result.native_acceptance, false);
  assert.equal(result.execute_allowed, false);
});

test('collector rejects changed nonce, identity, source, version, resources or claimed approval', async () => {
  const { collectWssWitness } = await interfaceUnderTest();
  for (const [field, value] of [
    ['nonce', 'd'.repeat(32)], ['tenant_id', 'other-tenant'], ['device_id', 'other-device'],
    ['source_head', 'e'.repeat(40)], ['worker_version', 'other-worker-version'],
    ['resource_sha256', 'f'.repeat(64)], ['approved', true],
  ]) {
    await assert.rejects(async () => collectWssWitness(COHORT,
      async member => status(member, member.device_id === 'device-a' ? 0 : 1, { [field]: value }),
      options()), /HOLD/);
  }
});

test('missing or extra members, duplicate connection IDs and a changed cohort pin are HOLD', async () => {
  const { collectWssWitness } = await interfaceUnderTest();
  for (const failure of ['missing', 'extra', 'duplicate-connection']) {
    await assert.rejects(async () => collectWssWitness(COHORT, async member => {
      const value = status(member, member.device_id === 'device-a' ? 0 : 1);
      if (failure === 'missing') return null;
      if (failure === 'extra') value.connections.push({ ...value.connections[0], connection_id: randomUUID() });
      if (failure === 'duplicate-connection') value.connections[0].connection_id = '40000000-0000-4000-8000-000000000001';
      return value;
    }, options()), /HOLD/);
  }
  let called = 0;
  await assert.rejects(async () => collectWssWitness(COHORT, async member => {
    called++;
    return status(member);
  }, options(COHORT, { cohortSha256: '0'.repeat(64) })), /HOLD/);
  assert.equal(called, 0, 'The independent cohort pin must be checked before querying members');
});

test('fresh probes, a simultaneous interval and the bounded capture span are required', async () => {
  const { collectWssWitness } = await interfaceUnderTest();
  for (const failure of ['stale', 'future-probe', 'no-overlap', 'span']) {
    await assert.rejects(async () => collectWssWitness(COHORT, async member => {
      const index = member.device_id === 'device-a' ? 0 : 1;
      const value = status(member, index);
      if (failure === 'stale') value.connections[0].last_probe_ms = NOW - 90_001;
      if (failure === 'future-probe') value.connections[0].last_probe_ms = NOW + 1;
      if (failure === 'no-overlap') {
        value.captured_ms = NOW - (index === 0 ? 50 : 0);
        value.connections[0].connected_at_ms = NOW - (index === 0 ? 100 : 25);
        value.connections[0].last_probe_ms = value.captured_ms;
      }
      if (failure === 'span') {
        value.captured_ms = NOW - (index === 0 ? 6000 : 0);
        value.connections[0].connected_at_ms = NOW - 10_000;
        value.connections[0].last_probe_ms = value.captured_ms;
      }
      return value;
    }, options()), /HOLD/);
  }
});

test('collector snapshots cohort and binding before asynchronous callbacks', async () => {
  const { collectWssWitness } = await interfaceUnderTest();
  const outcomes = [];
  for (const mutation of ['cohort', 'binding']) {
    const cohort = [{ ...COHORT[0] }];
    const binding = { ...COMMON };
    const originalPin = cohortDigest(cohort);
    try {
      await collectWssWitness(cohort, async member => {
        await new Promise(resolve => setImmediate(resolve));
        if (mutation === 'cohort') {
          // A callback has the original member reference, and an independent
          // caller can also edit its input while the status I/O is awaiting.
          member.device_id = 'unlisted-device-b';
          cohort[0].device_id = 'unlisted-device-b';
        } else {
          binding.source_head = 'e'.repeat(40);
        }
        return status(member, 0, mutation === 'binding'
          ? { source_head: binding.source_head } : {});
      }, options(cohort, { binding, maxConcurrent: 1, cohortSha256: originalPin }));
      outcomes.push({ mutation, rejected: false });
    } catch (error) {
      outcomes.push({ mutation, rejected: /^HOLD_WSS_/.test(error?.message) });
    }
  }
  assert.deepEqual(outcomes, [
    { mutation: 'cohort', rejected: true },
    { mutation: 'binding', rejected: true },
  ], 'A witness cannot attribute changed members or source binding to the original pins');
});

test('collector stops new callbacks on any rejection and aborts a timed out lookup', async () => {
  const { collectWssWitness } = await interfaceUnderTest();
  for (const reason of [undefined, null, false, 0, '']) {
    let calls = 0;
    await assert.rejects(() => collectWssWitness(COHORT, async () => {
      calls++;
      throw reason;
    }, options(COHORT, { maxConcurrent: 1 })), /HOLD_WSS_/);
    assert.equal(calls, 1, 'Even a falsy rejection must stop further status requests');
  }
  let calls = 0, signal;
  await assert.rejects(() => collectWssWitness(COHORT, async (member, request) => {
    calls++; signal = request.signal;
    await new Promise(resolve => signal.addEventListener('abort', resolve, { once: true }));
    return status(member);
  }, options(COHORT, { maxConcurrent: 1, maxSpanMs: 10 })), /HOLD_WSS_COLLECTION_TIMEOUT/);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(signal.aborted, true);
  assert.equal(calls, 1, 'A deadline must not schedule the next member after abort');
});

test('two explicit local WebSockets carry probes and become two source witness records', async t => {
  const { captureWssStatus, collectWssWitness } = await interfaceUnderTest();
  // Resolve only a caller-provided/local dependency. CI or the operator supplies
  // NODE_PATH; this source test neither installs packages nor embeds a temp path.
  const { WebSocket, WebSocketServer } = require('ws');
  const server = new WebSocketServer({ host: '127.0.0.1', port: 0, maxPayload: 1024 });
  const clients = [];
  const attachments = new WeakMap();
  const probes = new WeakMap();
  let accepted = 0;
  t.after(async () => {
    for (const client of clients) client.terminate();
    for (const socket of server.clients) socket.terminate();
    await new Promise(resolve => server.close(resolve));
  });
  server.on('connection', socket => {
    const member = COHORT[accepted++];
    const attachment = { ...member, connection_id: randomUUID(), connected_at_ms: Date.now(),
      superseded: false, event_v2_contract: CONTRACT };
    attachments.set(socket, attachment);
    socket.deserializeAttachment = () => ({ ...attachment });
    socket.on('message', raw => {
      if (raw.toString() !== NONCE) return;
      probes.set(socket, new Date());
      socket.send(JSON.stringify({ nonce: NONCE, type: 'LOCAL_PROBE_ACK' }));
    });
  });
  await once(server, 'listening');
  const port = server.address().port;
  for (const _member of COHORT) {
    const client = new WebSocket(`ws://127.0.0.1:${port}`);
    clients.push(client);
    await once(client, 'open');
    const acknowledged = once(client, 'message');
    client.send(NONCE);
    const [raw] = await acknowledged;
    assert.deepEqual(JSON.parse(raw.toString()), { nonce: NONCE, type: 'LOCAL_PROBE_ACK' });
  }
  const result = await collectWssWitness(COHORT, async member => {
    const ctx = {
      getWebSockets: () => [...server.clients].filter(socket => attachments.get(socket).device_id === member.device_id),
      getWebSocketAutoResponseTimestamp: socket => probes.get(socket) ?? null,
    };
    return captureWssStatus(ctx, { ...COMMON, ...member }, { nonce: NONCE, now: Date.now });
  }, options(COHORT, { now: Date.now }));
  assert.equal(accepted, 2, 'The witness functions do not open extra sockets');
  assert.equal(result.live_wss, 2);
  assert.equal(result.records.length, 2);
  assert.equal(result.native_acceptance, false);
  assert.equal(result.execute_allowed, false);
});
