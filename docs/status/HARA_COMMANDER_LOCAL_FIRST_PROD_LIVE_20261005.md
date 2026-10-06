# H.A.R.A. Commander — Local-first Activity PROD live proof

Date: 2026-10-05
Canonical feature branch: local/commander-local-first-20261005
PROD Worker: bb1e2a9f-af25-4ca9-b77d-37598c696e7c
Rollback Worker: 3c20f2ff-34ea-4d2c-9007-a19e694b36f3
Agent release: 0.3.33

## PROD migration

Applied:

- 0022_device_local_activity_snapshot.sql

Pre-migration D1 export completed and was stored locally with mode 0600.

The migration is additive:

- activity_summary_json
- activity_summary_at_utc

Old Agents remain compatible and continue through the legacy fallback.

## Linux rollout

### nucleo-a

Update:

- 0.3.30 -> 0.3.33
- integrity PASS
- self-test/startup attestation PASS
- rollback-ready PASS
- service ACTIVE
- PERSISTENT_TRUSTED preserved

Local store after migration:

- operations.sqlite3 PASS
- mode 0600
- local activity rows: 6,752
- local terminal rows: 1,799
- raw payload/result columns: ABSENT

PROD cloud snapshot:

- snapshot bytes: 2,957
- 7d total calls: 1,799
- 7d completed: 1,784
- 7d failed: 14
- D1 point readback rows_read: 1

### sentinela-d

Update:

- 0.3.30 -> 0.3.33
- integrity PASS
- startup attestation PASS
- rollback-ready PASS
- service ACTIVE
- PERSISTENT_TRUSTED preserved

Local store:

- operations.sqlite3 PASS
- mode 0600
- local activity rows: 38
- local terminal rows: 3
- raw payload/result columns: ABSENT

PROD cloud snapshot:

- snapshot bytes: 1,484
- 7d total calls: 3
- 7d completed: 3
- 7d failed: 0
- D1 point readback rows_read: 1

H.A.R.A. Commander live health after rollout:

- nucleo-a: PASS / Agent 0.3.33
- sentinela-d: PASS / Agent 0.3.33

## Measured cloud-history reduction

For the Founder tenant, last 7 days at measurement time:

- active devices: 3
- devices with local snapshot: 2
- legacy cloud call-history rows in scope before local-first: 1,808
- rows belonging to not-yet-snapshot devices after local-first: 6

That is approximately 99.7% of call-history records removed from the Activity
scan scope by the hybrid path.

The remaining device is the older/offline Windows enrollment and remains on the
legacy fallback until Windows local-store parity is delivered.

## Privacy boundary

Live DEV canary and PROD source guarantees:

- detailed action summaries stay local
- cloud snapshot has no command/payload/result/arguments/stdout/stderr/
  action_summary/receipt-detail keys
- customer_content_synced=false
- cloud stores only bounded aggregate metadata
- billing, identity, tenant, entitlement and revocation remain cloud-authoritative

## State

LOCAL_FIRST_ACTIVITY_LINUX_PROD=CLOSED_PASS
LOCAL_FIRST_CLOUD_SNAPSHOT_PROD=CLOSED_PASS
LOCAL_FIRST_HYBRID_FALLBACK_PROD=CLOSED_PASS
WINDOWS_LOCAL_STORE_PARITY=PENDING
LOCALHOST_DIRECT_REFRESH=PENDING_NEXT_SLICE
