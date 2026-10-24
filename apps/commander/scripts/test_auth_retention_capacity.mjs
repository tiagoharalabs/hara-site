import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { runAuthRetentionMaintenance } from '../src/auth.js';

// Actual exported Worker maintenance + actual SQL; isolated in-memory SQLite.
// This is NOT D1 latency, real cloud users, or a production load certification.
const now = Date.parse('2026-10-11T12:00:00.000Z');
const iso = (offsetDays = 0) => new Date(now + offsetDays * 86400000).toISOString();
const originalNow = Date.now;
Date.now = () => now;
const findings = [];

function fixture() {
  const db = new DatabaseSync(':memory:');
  const migrations = new URL('../migrations/', import.meta.url);
  for (const file of readdirSync(migrations).filter(f => f.endsWith('.sql')).sort()) {
    db.exec(readFileSync(new URL(file, migrations), 'utf8'));
  }
  db.prepare('INSERT INTO tenants VALUES (?,?,?,?,?)')
    .run('CAPACITY-T', 'Synthetic capacity tenant', 'ACTIVE', 'PRODUCTION', iso(-60));
  db.prepare(`INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc)
    VALUES (?,?,?,?,?,?,?)`).run('CAPACITY-U', 'CAPACITY-T', 'https://example.invalid/',
      'capacity-user', 'ACTIVE', 'OWNER', iso(-60));
  const calls = [];
  const env = { PRODUCT_DB: { prepare(sql) {
    return { bind(...params) { return { async run() {
      calls.push({ sql, params });
      const result = db.prepare(sql).run(...params);
      return { meta: { changes: Number(result.changes) } };
    } }; } };
  } } };
  const session = db.prepare(`INSERT INTO portal_sessions
    (session_hash,subject_id,created_at_utc,expires_at_utc,last_seen_at_utc,revoked_at_utc)
    VALUES (?,?,?,?,?,?)`);
  const tx = db.prepare(`INSERT INTO oidc_transactions
    (state_hash,browser_binding_hash,code_verifier,nonce,return_to,created_at_utc,expires_at_utc)
    VALUES (?,?,?,?,?,?,?)`);
  function sessions(prefix, n, expires, revoked = null) {
    db.exec('BEGIN');
    for (let i=0; i<n; i++) session.run(`${prefix}-${i}`, 'CAPACITY-U', iso(-60), expires, iso(-60), revoked);
    db.exec('COMMIT');
  }
  function transactions(prefix, n, expires) {
    db.exec('BEGIN');
    for (let i=0; i<n; i++) tx.run(`${prefix}-${i}`, 'synthetic', 'synthetic', 'synthetic', '/', iso(-60), expires);
    db.exec('COMMIT');
  }
  const count = table => Number(db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n);
  return { db, env, calls, sessions, transactions, count };
}

try {
  {
    const f = fixture();
    f.sessions('active', 10000, iso(1));
    f.sessions('expired', 1105, iso(-31));
    f.sessions('revoked', 1105, iso(1), iso(-31));
    f.sessions('both', 5, iso(-31), iso(-31));
    f.sessions('recent-expired', 10, iso(-1));
    f.sessions('recent-revoked', 10, iso(1), iso(-1));
    f.sessions('boundary', 1, iso(-30));
    f.transactions('expired-tx', 1205, iso(-1));
    f.transactions('active-tx', 10, iso(1));
    const report = await runAuthRetentionMaintenance(f.env);
    assert.equal(report.state, 'PASS');
    assert.equal(report.sessions_deleted, 2216);
    assert.equal(report.transactions_deleted, 1205);
    assert.equal(report.budget_exhausted, false);
    assert(report.rounds > 1 && report.rounds <= 20);
    assert.equal(f.count('portal_sessions'), 10020);
    assert.equal(f.count('oidc_transactions'), 10);
    assert.equal(Number(f.db.prepare("SELECT COUNT(*) AS n FROM portal_sessions WHERE session_hash LIKE 'active-%'").get().n), 10000);
    const cleanup = f.calls.find(c => c.sql.includes('DELETE FROM portal_sessions'));
    const plan = f.db.prepare('EXPLAIN QUERY PLAN ' + cleanup.sql).all(...cleanup.params)
      .map(r => r.detail).join('\n');
    assert(plan.includes('idx_portal_sessions_expiry'));
    assert(plan.includes('idx_portal_sessions_revoked'));
    assert(!/SCAN portal_sessions\b/i.test(plan));
    assert(!/USE TEMP B-TREE FOR ORDER BY/i.test(plan));
    findings.push({case:'mixed_backlog_10000_active_preserved', ...report, indexed_cleanup:true, active_sessions_preserved:10000});
    f.db.close();
  }
  {
    const f = fixture();
    f.transactions('backlog', 5000, iso(-1));
    f.sessions('old-expired', 5000, iso(-31));
    f.sessions('old-revoked', 5000, iso(1), iso(-31));
    const report = await runAuthRetentionMaintenance(f.env);
    assert.equal(report.rounds, 20);
    assert.equal(report.transactions_deleted, 2000);
    assert.equal(report.sessions_deleted, 4000);
    assert.equal(report.budget_exhausted, true);
    assert.equal(f.count('oidc_transactions'), 3000);
    assert.equal(f.count('portal_sessions'), 6000);
    assert.equal(f.calls.length, 40);
    findings.push({case:'hard_round_and_row_bounds', ...report, sql_statements:40});
    f.db.close();
  }
  {
    const f = fixture();
    const report = await runAuthRetentionMaintenance(f.env);
    assert.equal(report.rounds, 1);
    assert.equal(report.budget_exhausted, false);
    assert.equal(f.calls.length, 2);
    findings.push({case:'empty_backlog_early_exit', ...report});
    f.db.close();
  }
  {
    let calls = 0;
    const env = { PRODUCT_DB: { prepare() { return { bind() { return { async run() {
      calls++; throw new Error('synthetic database unavailable');
    } }; } }; } } };
    const report = await runAuthRetentionMaintenance(env);
    assert.equal(report.state, 'DEGRADED');
    assert.equal(report.rounds, 1);
    assert.equal(calls, 2);
    assert.equal(report.budget_exhausted, false);
    findings.push({case:'database_failure_not_misreported_as_drained', ...report});
  }
  {
    let elapsed = 0;
    Date.now = () => now + elapsed;
    const env = { PRODUCT_DB: { prepare() { return { bind() { return { async run() {
      elapsed += 3000;
      return { meta: { changes: 100 } };
    } }; } }; } } };
    const report = await runAuthRetentionMaintenance(env);
    assert.equal(report.rounds, 1);
    assert.equal(report.budget_exhausted, true);
    // Soft wall budget checked BETWEEN rounds; never claims to cancel in-flight D1.
    assert.equal(report.elapsed_ms, 6000);
    findings.push({case:'soft_time_budget_stops_next_round', ...report});
  }
  console.log(JSON.stringify({state:'PASS',scope:'LOCAL_SQLITE_EXACT_WORKER_MAINTENANCE',
    real_cloudflare_clients_tested:0, tests:findings}, null, 2));
} finally {
  Date.now = originalNow;
}
