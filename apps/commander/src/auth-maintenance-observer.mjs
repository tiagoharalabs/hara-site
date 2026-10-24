import { runAuthRetentionMaintenance } from './auth.js';

const COUNTERS = ['rounds', 'transactions_deleted', 'sessions_deleted', 'elapsed_ms'];

// One aggregate event per scheduled run, never per login or per device.
// Explicit fields only: session identifiers, SQL, errors and tokens must not leak.
export function retentionLogRecord(report) {
  const validCounters = COUNTERS.every(key =>
    Number.isFinite(report?.[key]) && report[key] >= 0);
  const validState = report?.state === 'PASS' || report?.state === 'DEGRADED';
  const record = {
    scope: 'AUTH_RETENTION',
    state: validState && validCounters ? report.state : 'DEGRADED',
    budget_exhausted: report?.budget_exhausted === true,
  };
  for (const key of COUNTERS) {
    record[key] = Number.isFinite(report?.[key]) && report[key] >= 0
      ? Math.floor(report[key]) : 0;
  }
  return record;
}

export async function runObservedAuthRetentionMaintenance(
  env, { run = runAuthRetentionMaintenance, logger = console } = {},
) {
  let report;
  try {
    report = await run(env);
  } catch {
    logger.error(JSON.stringify({
      scope: 'AUTH_RETENTION', state: 'FAILED', code: 'AUTH_RETENTION_EXECUTION_FAILED',
    }));
    // Keep scheduled failure visible, but do not echo database errors or secrets.
    throw new Error('AUTH_RETENTION_EXECUTION_FAILED');
  }
  const record = retentionLogRecord(report);
  const level = record.state === 'PASS' && !record.budget_exhausted ? 'info' : 'warn';
  logger[level](JSON.stringify(record));
  return report;
}
