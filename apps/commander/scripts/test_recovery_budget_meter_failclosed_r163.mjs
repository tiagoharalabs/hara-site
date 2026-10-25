// Local #163 boundary tests: real SQLite mutations, synthetic Cloudflare D1
// metadata. These numbers do not establish provider usage or native capacity.
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { budgeted, BUDGET_SCHEMA, readRecoveryQaStatus } from './recovery_queue_budget_r163.mjs';

const RESERVATION = Object.freeze({ reads: 64, writes: 32 });

function fixture(t, { meter = (_query, result) => result } = {}) {
  const sqlite = new DatabaseSync(':memory:');
  t.after(() => sqlite.close());
  sqlite.exec(BUDGET_SCHEMA);
  sqlite.exec('CREATE TABLE budget_work(id INTEGER PRIMARY KEY, value TEXT)');
  sqlite.prepare(`INSERT INTO r163_qa_budget
    (id, state, start_ms, deadline_ms, rows_read, rows_written)
    VALUES (1, 'ACTIVE', 1, ?, 100, 20)`).run(Date.now() + 60_000);
  const queries = [];
  let sent = 0;

  function bind(sql, args) {
    async function execute(method) {
      const query = {
        sql, method,
        kind: /\bbudget_work\b/i.test(sql) ? 'business' :
          /\bFROM\s+r163_qa_(?:jobs|dlq)\b/i.test(sql) ? 'status_read' :
          /reserved_read\s*=\s*reserved_read\s*\+/i.test(sql) ? 'reservation' :
          /reserved_read\s*=\s*reserved_read\s*-|invocations\s*=\s*invocations\s*\+/i.test(sql)
            ? 'settlement' : 'bookkeeping',
      };
      queries.push(query);
      const before = sqlite.prepare('SELECT total_changes() AS n').get().n;
      const statement = sqlite.prepare(sql);
      const rows = method === 'run' ? (statement.run(...args), []) : statement.all(...args);
      const writes = sqlite.prepare('SELECT total_changes() AS n').get().n - before;
      const result = { results: rows, meta: { rows_read: Math.max(1, rows.length), rows_written: writes } };
      const measured = await meter(query, result);
      // D1.first() returns a plain row, never provider metadata. Tests inject
      // missing metadata only into all()/run(); a first() fault can still model
      // the provider losing its response after the actual reservation commit.
      return method === 'first' ? measured?.results?.[0] ?? null : measured;
    }
    return {
      first: () => execute('first'),
      all: () => execute('all'),
      run: () => execute('run'),
    };
  }

  const raw = { prepare: sql => ({ bind: (...args) => bind(sql, args) }) };
  return {
    sqlite, queries,
    env: {
      ENVIRONMENT: 'DEV', R163_QA_ISOLATED: 'true', PRODUCT_DB: raw,
      RECOVERY_DELIVERY_QUEUE: { sendBatch: async entries => { sent += entries.length; } },
    },
    row: () => ({ ...sqlite.prepare('SELECT * FROM r163_qa_budget WHERE id = 1').get() }),
    work: () => sqlite.prepare('SELECT * FROM budget_work ORDER BY id').all().map(row => ({ ...row })),
    sent: () => sent,
  };
}

async function outcome(operation) {
  try { return { result: await operation() }; }
  catch (error) { return { error }; }
}

function requireStoppedHold(f, before, reservation = RESERVATION) {
  const row = f.row();
  const detail = JSON.stringify(row);
  assert.equal(row.state, 'STOPPED', `An unmeasured operation must stop the campaign: ${detail}`);
  assert.equal(row.reserved_read, before.reserved_read + reservation.reads, `Read hold must survive: ${detail}`);
  assert.equal(row.reserved_write, before.reserved_write + reservation.writes, `Write hold must survive: ${detail}`);
  assert.ok(row.rows_read >= before.rows_read, `Consumed reads cannot be replenished: ${detail}`);
  assert.ok(row.rows_written >= before.rows_written, `Consumed writes cannot be replenished: ${detail}`);
  assert.ok(row.anomaly, 'The durable stop must identify its anomaly');
}

for (const [name, counters] of [
  ['negative rows_read', { rows_read: -200, rows_written: 0 }],
  ['negative rows_written', { rows_read: 1, rows_written: -40 }],
]) {
  test(`${name} cannot replenish the campaign or release its unresolved reservation`, async t => {
    const f = fixture(t, { meter: (query, result) => query.kind === 'business'
      ? { ...result, meta: counters } : result });
    const before = f.row();
    const actual = await outcome(() => budgeted(f.env, RESERVATION,
      env => env.PRODUCT_DB.prepare('SELECT * FROM budget_work').bind().all()));
    requireStoppedHold(f, before);
    assert.match(actual.error?.message ?? '', /^HOLD_/, 'Invalid metadata must reject the invocation');
  });
}

test('missing metadata after a committed business write retains the entire unresolved reservation', async t => {
  const f = fixture(t, { meter: (query, result) => query.kind === 'business'
    ? { results: result.results } : result });
  const before = f.row();
  const actual = await outcome(() => budgeted(f.env, RESERVATION,
    env => env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'committed').run()));
  assert.deepEqual(f.work(), [{ id: 1, value: 'committed' }], 'The unknown spend really occurred in SQLite');
  assert.match(actual.error?.message ?? '', /^HOLD_/);
  requireStoppedHold(f, before);
});

test('a callback cannot swallow a metering anomaly, continue business work, or report success', async t => {
  const f = fixture(t, { meter: (query, result) => query.kind === 'business'
    ? { results: result.results } : result });
  const before = f.row();
  const actual = await outcome(() => budgeted(f.env, RESERVATION, async env => {
    try { await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'unknown spend').run(); }
    catch { /* The callback is not authorized to clear the durable stop. */ }
    try { await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(2, 'must not run').run(); }
    catch { /* Record outcomes from real state below. */ }
    try { await env.RECOVERY_DELIVERY_QUEUE.sendBatch([{ body: { id: 'must-not-send' } }]); }
    catch { /* Sending also remains fenced after a metering anomaly. */ }
    return 'incorrect success';
  }));
  assert.deepEqual(f.work(), [{ id: 1, value: 'unknown spend' }]);
  assert.equal(f.queries.filter(query => query.kind === 'business').length, 1);
  assert.equal(f.sent(), 0);
  assert.match(actual.error?.message ?? '', /^HOLD_/, 'A caught meter fault must still reject budgeted()');
  requireStoppedHold(f, before);
});

test('valid nonnegative provider counters settle normally without replenishing prior consumption', async t => {
  const f = fixture(t);
  const before = f.row();
  const value = await budgeted(f.env, RESERVATION, async env => {
    await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'measured').run();
    return 'complete';
  });
  const row = f.row();
  assert.equal(value, 'complete');
  assert.equal(row.state, 'ACTIVE');
  assert.equal(row.reserved_read, before.reserved_read);
  assert.equal(row.reserved_write, before.reserved_write);
  assert.ok(row.rows_read > before.rows_read);
  assert.ok(row.rows_written > before.rows_written);
  assert.deepEqual(f.work(), [{ id: 1, value: 'measured' }]);
});

for (const [name, field, value] of [
  ['fractional reads', 'rows_read', 0.5],
  ['fractional writes', 'rows_written', 0.5],
  ['unsafe reads', 'rows_read', Number.MAX_SAFE_INTEGER + 1],
  ['unsafe writes', 'rows_written', Number.MAX_SAFE_INTEGER + 1],
  ['NaN reads', 'rows_read', Number.NaN],
  ['infinite writes', 'rows_written', Number.POSITIVE_INFINITY],
  ['boolean reads', 'rows_read', true],
  ['string writes', 'rows_written', '1'],
]) {
  test(`${name} leave a durable stop and the entire unresolved reservation`, async t => {
    const f = fixture(t, { meter: (query, result) => query.kind === 'business'
      ? { ...result, meta: { rows_read: 0, rows_written: 0, [field]: value } } : result });
    const before = f.row();
    const actual = await outcome(() => budgeted(f.env, RESERVATION,
      env => env.PRODUCT_DB.prepare('SELECT * FROM budget_work').bind().all()));
    assert.match(actual.error?.message ?? '', /^HOLD_/);
    requireStoppedHold(f, before);
  });
}

for (const [name, meta] of [
  ['read', { rows_read: RESERVATION.reads + 1, rows_written: 0 }],
  ['write', { rows_read: 0, rows_written: RESERVATION.writes + 1 }],
]) {
  test(`${name} spend beyond its reservation cannot free the unresolved hold`, async t => {
    const f = fixture(t, { meter: (query, result) => query.kind === 'business'
      ? { ...result, meta } : result });
    const before = f.row();
    const actual = await outcome(() => budgeted(f.env, RESERVATION,
      env => env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'over reservation').run()));
    assert.deepEqual(f.work(), [{ id: 1, value: 'over reservation' }]);
    assert.match(actual.error?.message ?? '', /^HOLD_/);
    requireStoppedHold(f, before);
  });
}

test('a provider failure after a committed business query retains unknown spend and blocks more work', async t => {
  const f = fixture(t, { meter: (query, result) => {
    if (query.kind === 'business') throw Error('D1_BUSINESS_RESPONSE_LOST_AFTER_COMMIT');
    return result;
  } });
  const before = f.row();
  const actual = await outcome(() => budgeted(f.env, RESERVATION, async env => {
    try { await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'unknown receipt').run(); }
    catch { /* This committed query has no trusted resource receipt. */ }
    try { await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(2, 'blocked').run(); }
    catch { /* The durable outcome below must remain fail closed. */ }
  }));
  assert.deepEqual(f.work(), [{ id: 1, value: 'unknown receipt' }]);
  assert.equal(f.queries.filter(query => query.kind === 'business').length, 1);
  requireStoppedHold(f, before);
  assert.ok(actual.error, 'Losing the provider response cannot produce a successful invocation');
});

for (const mode of ['throw', 'lost-row']) {
  test(`a ${mode} response after reservation commit cannot start the callback or leave ACTIVE`, async t => {
    let injected = false;
    const f = fixture(t, { meter: (query, result) => {
      if (query.kind === 'reservation' && !injected) {
        injected = true;
        if (mode === 'throw') throw Error('D1_RESERVATION_RESPONSE_LOST_AFTER_COMMIT');
        return { results: [] }; // Lost acknowledgement, including any metadata.
      }
      return result;
    } });
    const before = f.row();
    let entered = 0;
    const actual = await outcome(() => budgeted(f.env, RESERVATION, async env => {
      entered++;
      await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'must not run').run();
    }));
    assert.ok(injected, 'The reservation SQL was actually applied before the response fault');
    assert.equal(entered, 0);
    assert.deepEqual(f.work(), []);
    assert.ok(actual.error);
    requireStoppedHold(f, before);
  });
}

for (const mode of ['missing-meta', 'throw']) {
  test(`a ${mode} settlement response cannot approve an invocation or refund unknown spend`, async t => {
    let injected = false;
    const f = fixture(t, { meter: (query, result) => {
      if (query.kind === 'settlement' && !injected) {
        injected = true;
        if (mode === 'throw') throw Error('D1_SETTLEMENT_RESPONSE_LOST_AFTER_COMMIT');
        return { results: result.results };
      }
      return result;
    } });
    const before = f.row();
    const actual = await outcome(() => budgeted(f.env, RESERVATION,
      env => env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'measured business').run()));
    assert.ok(injected, 'A real settlement mutation preceded the synthetic response fault');
    assert.deepEqual(f.work(), [{ id: 1, value: 'measured business' }]);
    requireStoppedHold(f, before);
    assert.ok(actual.error, 'A missing settlement receipt is a HOLD, never approval');
  });
}

test('an already STOPPED campaign executes no business query or external queue send', async t => {
  const f = fixture(t);
  f.sqlite.exec("UPDATE r163_qa_budget SET state = 'STOPPED', anomaly = 'PREVIOUS_UNKNOWN_SPEND'");
  const before = f.row();
  let entered = 0;
  await assert.rejects(() => budgeted(f.env, RESERVATION, async env => {
    entered++;
    await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES (?, ?)').bind(1, 'must not run').run();
    await env.RECOVERY_DELIVERY_QUEUE.sendBatch([{ body: {} }]);
  }));
  assert.equal(entered, 0);
  assert.deepEqual(f.work(), []);
  assert.equal(f.sent(), 0);
  assert.equal(f.row().reserved_read, before.reserved_read);
  assert.equal(f.row().reserved_write, before.reserved_write);
});

for (const mode of ['negative-reads', 'missing-meta']) {
  test(`status ${mode} cannot replenish a paused campaign or release its unresolved 1024/4 hold`, async t => {
    const f = fixture(t, { meter: (query, result) => {
      if (query.kind !== 'status_read') return result;
      return mode === 'negative-reads'
        ? { ...result, meta: { rows_read: -200, rows_written: 0 } }
        : { results: result.results };
    } });
    f.sqlite.exec("UPDATE r163_qa_budget SET state = 'PAUSED'");
    const before = f.row();
    const actual = await outcome(() => readRecoveryQaStatus(f.env));
    requireStoppedHold(f, before, { reads: 1024, writes: 4 });
    assert.match(actual.error?.message ?? '', /^HOLD_/, 'Status without trustworthy metadata is not approved');
    assert.equal(f.queries.filter(query => query.kind === 'status_read').length, 1,
      'The first status anomaly must stop the second status query');
    assert.equal(f.row().deadline_ms, before.deadline_ms);
    assert.equal(f.sent(), 0);
  });
}

test('a fully measured status read never resumes or renews a paused campaign', async t => {
  const f = fixture(t);
  f.sqlite.exec("UPDATE r163_qa_budget SET state = 'PAUSED'");
  const before = f.row();
  const result = await readRecoveryQaStatus(f.env);
  const row = f.row();
  assert.equal(result.budget.state, 'PAUSED');
  assert.equal(row.state, 'PAUSED');
  assert.equal(row.deadline_ms, before.deadline_ms);
  assert.equal(row.start_ms, before.start_ms);
  assert.equal(row.active_ms_used, before.active_ms_used);
  assert.equal(row.reserved_read, before.reserved_read);
  assert.equal(row.reserved_write, before.reserved_write);
  assert.ok(row.rows_read > before.rows_read);
  assert.ok(row.rows_written > before.rows_written);
  assert.equal(f.sent(), 0);
});
