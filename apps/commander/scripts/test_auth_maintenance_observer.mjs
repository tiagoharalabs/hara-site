import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  retentionLogRecord, runObservedAuthRetentionMaintenance,
} from '../src/auth-maintenance-observer.mjs';

const base = {
  scope: 'AUTH_RETENTION', state: 'PASS', rounds: 1,
  transactions_deleted: 0, sessions_deleted: 0,
  budget_exhausted: false, elapsed_ms: 2,
};
function sink() {
  const events = [];
  const logger = Object.fromEntries(['info', 'warn', 'error'].map(level =>
    [level, value => events.push({ level, record: JSON.parse(value) })]));
  return { events, logger };
}
let cases = 0;
for (const [changes, expectedLevel] of [
  [{}, 'info'],
  [{ budget_exhausted: true, rounds: 20 }, 'warn'],
  [{ state: 'DEGRADED' }, 'warn'],
  [{ elapsed_ms: Infinity }, 'warn'],
  [{ sessions_deleted: -1 }, 'warn'],
  [{ state: 'secret-database-error' }, 'warn'],
]) {
  const { events, logger } = sink();
  const report = { ...base, ...changes, token: 'DO_NOT_LOG', sql: 'DO_NOT_LOG' };
  const returned = await runObservedAuthRetentionMaintenance({}, {
    run: async () => report, logger,
  });
  assert.equal(returned, report);
  assert.equal(events.length, 1);
  assert.equal(events[0].level, expectedLevel);
  assert(!JSON.stringify(events).includes('DO_NOT_LOG'));
  assert(!JSON.stringify(events).includes('secret-database-error'));
  assert.equal(Object.keys(events[0].record).length, 7);
  cases++;
}
{
  const { events, logger } = sink();
  await assert.rejects(runObservedAuthRetentionMaintenance({}, {
    run: async () => { throw new Error('DO_NOT_LOG session token SQL'); }, logger,
  }), { message: 'AUTH_RETENTION_EXECUTION_FAILED' });
  assert.equal(events.length, 1);
  assert.equal(events[0].level, 'error');
  assert(!JSON.stringify(events).includes('DO_NOT_LOG'));
  cases++;
}
{
  // Default runner executes the actual Worker maintenance against an empty mock.
  const { events, logger } = sink();
  let statements = 0;
  const env = { PRODUCT_DB: { prepare() { return { bind() { return {
    async run() { statements++; return { meta: { changes: 0 } }; },
  }; } }; } } };
  const report = await runObservedAuthRetentionMaintenance(env, { logger });
  assert.equal(report.state, 'PASS');
  assert.equal(statements, 2);
  assert.equal(events.length, 1);
  assert.equal(events[0].record.rounds, 1);
  cases++;
}
assert.equal(retentionLogRecord(null).state, 'DEGRADED');
const worker = readFileSync(new URL('../src/worker.js', import.meta.url), 'utf8');
assert(worker.includes('ctx.waitUntil(runObservedAuthRetentionMaintenance(env));'));
assert.equal(worker.split('runObservedAuthRetentionMaintenance(env)').length - 1, 1);
console.log(JSON.stringify({ state: 'PASS', cases: cases + 2,
  scope: 'LOCAL_AUTH_MAINTENANCE_OBSERVABILITY', client_data_logged: false }));
