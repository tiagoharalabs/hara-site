import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import vm from 'node:vm';
import { performance } from 'node:perf_hooks';

// Exact production class; synthetic contexts + independent in-memory SQLite.
// 1,000 local objects do not establish 1,000 authenticated cloud customers.
const workerPath = new URL('../src/worker.js', import.meta.url);
const worker = readFileSync(workerPath, 'utf8');
const begin = worker.indexOf('export class TenantQuota extends DurableObject {');
const end = worker.indexOf('\nasync function entitlementForTenant', begin);
assert(begin >= 0 && end > begin);
const classSource = worker.slice(begin, end).replace('export class TenantQuota', 'class TenantQuota');
const ttlExpression = worker.match(/const QUOTA_RESERVATION_TTL_SECONDS\s*=\s*([\d\s*]+)\s*;/)?.[1];
assert(ttlExpression);
const legacyTtl = Number(vm.runInNewContext(ttlExpression));
const approval = readFileSync(new URL('../src/approval-async-relay.mjs', import.meta.url), 'utf8');
const approvalTtl = Number(approval.match(/const ASYNC_APPROVAL_RESERVATION_TTL_SECONDS\s*=\s*(\d+)\s*;/)?.[1]);
assert.equal(legacyTtl, 600);
assert.equal(approvalTtl, 1800);
// Keep this contract anchored to both actual quota-routing call sites.
assert(worker.includes('quota = env.TENANT_QUOTA.getByName(context.tenant_id);'));
const count = 1000;
const base = Date.parse('2026-10-12T23:00:00.000Z');
let clock = base;
let sqlStatements = 0;
let quotaCalls = 0;
let assertions = 0;
const measured = [];
const fixtures = [];
class ClockDate extends Date {
  constructor(...args) { super(...(args.length ? args : [clock])); }
  static now() { return clock; }
}
class DurableObject { constructor(ctx) { this.ctx = ctx; } }
const runtime = vm.createContext({ DurableObject, Date: ClockDate,
  QUOTA_RESERVATION_TTL_SECONDS: legacyTtl,
  ASYNC_APPROVAL_RESERVATION_TTL_SECONDS: approvalTtl });
vm.runInContext(classSource + '\nglobalThis.QuotaClass = TenantQuota;', runtime);
const plain = value => JSON.parse(JSON.stringify(value));
function equal(actual, expected, label) { assertions++; assert.equal(actual, expected, label); }
function phase(name, fn) {
  const start = performance.now();
  fn();
  measured.push({ phase: name, local_wall_ms: Number((performance.now()-start).toFixed(3)) });
}
function invoke(f, method, ...args) { quotaCalls++; return plain(f.quota[method](...args)); }
function reserve(f, id, ttl = approvalTtl, subject = f.subject, period = '2026-10', fn = 'process.run') {
  return invoke(f, 'reserve', id, subject, period, fn, 6, ttl);
}
function balance(f) { return invoke(f, 'status', '2026-10', 6, false).consumed_units; }
function receipt(f, id) { return createHash('sha256').update(f.subject + ':' + id).digest('hex'); }
function row(f, id) { return f.db.prepare('SELECT * FROM request_state WHERE request_id=?').get(id); }

const started = performance.now();
let report;
try {
  const pending = [];
  const createStarted = performance.now();
  for (let i=0; i<count; i++) {
    const db = new DatabaseSync(':memory:');
    const ctx = {
      blockConcurrencyWhile(callback) { const p = callback(); pending.push(p); return p; },
      storage: { sql: { exec(sql, ...binds) {
        sqlStatements++;
        if (!binds.length && (/CREATE TABLE IF NOT EXISTS/.test(sql) || /DELETE FROM period_usage;/.test(sql))) {
          db.exec(sql); return [];
        }
        return db.prepare(sql).all(...binds);
      } } },
    };
    const quota = new runtime.QuotaClass(ctx, {});
    fixtures.push({ db, quota, subject: 'SYNTHETIC-SUBJECT-' + i });
  }
  await Promise.all(pending);
  measured.push({ phase: 'create_1000_simultaneously_open_isolated_sqlite_objects',
    local_wall_ms: Number((performance.now()-createStarted).toFixed(3)) });
  phase('same_ids_independent_accounting_and_terminal_replay', () => {
    for (const f of fixtures) {
      for (let j=0; j<3; j++) {
        const id = 'COMMON-COMMIT-' + j;
        equal(reserve(f, id).state, 'RESERVED');
        equal(invoke(f, 'commit', id, f.subject, receipt(f, id), 6).state, 'COMMITTED');
        equal(invoke(f, 'commit', id, f.subject, receipt(f, id), 6).existing, true);
      }
      for (let j=0; j<2; j++) {
        const id = 'COMMON-RELEASE-' + j;
        equal(reserve(f, id).state, 'RESERVED');
        equal(invoke(f, 'release', id, f.subject, 6).state, 'RELEASED');
        equal(invoke(f, 'release', id, f.subject, 6).existing, true);
      }
      equal(reserve(f, 'COMMON-PENDING').state, 'RESERVED');
      for (let j=3; j<5; j++) {
        const id = 'COMMON-COMMIT-' + j;
        equal(reserve(f, id).state, 'RESERVED');
        equal(invoke(f, 'commit', id, f.subject, receipt(f, id), 6).state, 'COMMITTED');
      }
      equal(balance(f), 6);
      equal(reserve(f, 'COMMON-DENIED').code, 'QUOTA_EXCEEDED');
      equal(reserve(f, 'COMMON-DENIED').existing, true);
      equal(row(f, 'COMMON-DENIED').units, 0);
      equal(balance(f), 6);
    }
  });
  phase('foreign_subject_function_period_conflicts_do_not_change_rows', () => {
    for (let i=0; i<count; i++) {
      const f = fixtures[i];
      const before = JSON.stringify(row(f, 'COMMON-COMMIT-0'));
      const foreign = fixtures[(i+1)%count].subject;
      equal(reserve(f, 'COMMON-COMMIT-0', approvalTtl, foreign).code, 'IDEMPOTENCY_CONFLICT');
      equal(reserve(f, 'COMMON-COMMIT-0', approvalTtl, f.subject, '2026-11').code, 'IDEMPOTENCY_CONFLICT');
      equal(reserve(f, 'COMMON-COMMIT-0', approvalTtl, f.subject, '2026-10', 'filesystem.write').code, 'IDEMPOTENCY_CONFLICT');
      equal(invoke(f, 'commit', 'COMMON-COMMIT-0', foreign, receipt(f, 'COMMON-COMMIT-0'), 6).code, 'IDEMPOTENCY_CONFLICT');
      equal(invoke(f, 'release', 'COMMON-PENDING', foreign, 6).code, 'IDEMPOTENCY_CONFLICT');
      equal(JSON.stringify(row(f, 'COMMON-COMMIT-0')), before);
      equal(balance(f), 6);
    }
  });
  phase('noisy_object_500_denials_do_not_consume_quiet_object_quota', () => {
    const quietBefore = fixtures.slice(1).map(balance);
    for (let j=0; j<500; j++) equal(reserve(fixtures[0], 'NOISY-DENIED-' + j).code, 'QUOTA_EXCEEDED');
    for (let i=1; i<count; i++) equal(balance(fixtures[i]), quietBefore[i-1]);
    equal(balance(fixtures[0]), 6);
  });
  phase('15min_pending_replay_keeps_original_30min_quota_reservation', () => {
    clock = base + 900000;
    for (const f of fixtures) {
      const expires = row(f, 'COMMON-PENDING').reservation_expires_at_utc;
      equal(reserve(f, 'COMMON-PENDING').existing, true);
      equal(row(f, 'COMMON-PENDING').state, 'RESERVED');
      equal(row(f, 'COMMON-PENDING').reservation_expires_at_utc, expires);
      equal(balance(f), 6);
    }
  });
  phase('exact_30min_expiry_maintains_terminal_receipts_and_aggregate', () => {
    clock = base + 1800000;
    for (const f of fixtures) {
      equal(invoke(f, 'status', '2026-10', 6).consumed_units, 5);
      equal(row(f, 'COMMON-PENDING').state, 'RELEASED');
      equal(invoke(f, 'commit', 'COMMON-PENDING', f.subject, receipt(f, 'COMMON-PENDING'), 6).code, 'RESERVATION_NOT_ACTIVE');
      equal(invoke(f, 'commit', 'COMMON-COMMIT-0', f.subject, receipt(f, 'COMMON-COMMIT-0'), 6).existing, true);
      equal(balance(f), f.db.prepare("SELECT COALESCE(SUM(units),0) AS n FROM request_state WHERE period_key='2026-10' AND state IN ('RESERVED','COMMITTED')").get().n);
      equal(balance(f), 5);
      equal(row(f, 'COMMON-COMMIT-0').receipt_sha256, receipt(f, 'COMMON-COMMIT-0'));
    }
  });
  const queryPlan = fixtures[0].db.prepare('EXPLAIN QUERY PLAN SELECT consumed_units FROM period_usage WHERE period_key=?')
    .all('2026-10').map(r => r.detail);
  assert(queryPlan.some(x => x.includes('sqlite_autoindex_period_usage')));
  const counts = fixtures.reduce((sum, f) => {
    const rows = f.db.prepare('SELECT state,COUNT(*) AS n FROM request_state GROUP BY state').all();
    for (const r of rows) sum[r.state] = (sum[r.state] || 0) + Number(r.n);
    return sum;
  }, {});
  equal(counts.COMMITTED, 5000);
  equal(counts.RELEASED, 3000);
  equal(counts.DENIED, 1500);
  equal(counts.RESERVED || 0, 0);
  report = {
    schema: 'hara.commander-quota-1000-local-object-workload.v1', state: 'PASS',
    scope: 'EXACT_PRODUCTION_TENANTQUOTA_CLASS_INDEPENDENT_LOCAL_SQLITE_OBJECTS',
    at_utc: new Date().toISOString(),
    production_worker_sha256: createHash('sha256').update(worker).digest('hex'),
    production_quota_class_sha256: createHash('sha256').update(classSource).digest('hex'),
    approval_relay_sha256: createHash('sha256').update(approval).digest('hex'),
    validator_sha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),
    local_simultaneously_open_objects: count, synthetic_subjects: count,
    quota_method_calls: quotaCalls, sql_statements: sqlStatements, assertions,
    preserved_committed_receipts: 5000, terminal_rows: counts,
    local_elapsed_ms: Number((performance.now()-started).toFixed(3)),
    diagnostic_memory_rss_bytes: process.memoryUsage().rss,
    aggregate_query_plan: queryPlan, phases: measured,
    authenticated_cloud_tenants_tested: 0, authenticated_agents_tested: 0,
    measured_cloud_cost: false, real_network_reconnect_tested: false,
    cloud_soak_hours: 0, production_load_certification: false,
    fairness_scope: 'independent quota balances only; no real scheduler, cloud latency or authentication fairness',
  };
} finally {
  let closed = 0;
  for (const f of fixtures) { f.db.close(); closed++; }
  if (report) { report.local_sqlite_objects_closed = closed; report.cleanup_verified = closed === count; }
}
console.log(JSON.stringify(report, null, 2));
