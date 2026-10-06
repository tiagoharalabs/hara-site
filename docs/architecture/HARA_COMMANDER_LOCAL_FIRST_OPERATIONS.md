# H.A.R.A. Commander — Local-first operations architecture

Date: 2026-10-05
Status: DEV canary candidate

## Authority split

Cloud authority remains responsible for:

- HARA Identity and account authentication
- tenant and user membership
- roles and grants
- billing / Stripe state
- entitlements and administrative revocation
- remote device enrollment and coordination
- remote call idempotency / receipt correlation where required

The customer device is authoritative for detailed operational history:

- commands/tools executed
- local action summary
- execution state and error code
- execution latency
- receipt hash
- process/session metadata
- detailed Activity history

Raw command history, payloads and results are not copied into the cloud Activity
store by this architecture.

## Linux local store

Commander Agent 0.3.33 introduces:

`~/.local/share/hara-commander/operations.sqlite3`

Properties:

- SQLite
- mode 0600
- WAL mode
- metadata-oriented `activity_events` table
- no `payload_json` or `result_json` columns
- local mutation/process `action_summary` retained on the customer's device
- sensitive command tokens/password-like values use the existing local redaction
- existing `console-events.jsonl` is migrated once and remains a compatibility
  sink during rollout

Simple MCP `get_activity` now reads the local SQLite store.

## Cloud snapshot

The existing 30-second device heartbeat carries a bounded, privacy-safe
aggregate snapshot for:

- 24h
- 7d
- 30d

Each window contains only:

- counts
- success/failure totals
- average latency
- under-3-second percentage
- transport modes
- top tool IDs
- top sanitized error codes

It contains no command text, arguments, payloads, results or local action
summaries.

The snapshot is capped at 32 KiB and stored on the device row through migration
`0022_device_local_activity_snapshot.sql`.

No extra per-call cloud transaction is introduced; the aggregate rides the
heartbeat that already exists.

## Portal read path

For OWNER/ADMIN Activity:

1. read active device rows and their aggregate snapshots;
2. use local snapshots for upgraded devices;
3. exclude those device IDs from the legacy cloud-history scan;
4. query `commander_device_calls` only for not-yet-upgraded devices;
5. merge both summaries without double counting;
6. once all active devices have snapshots, skip the cloud call-history scan
   completely.

For MEMBER users, the existing subject-scoped cloud path remains during this
phase to preserve per-user privacy isolation.

The portal shows snapshot coverage as a local percentage.

When detailed transactions are local-only, the portal explicitly says:

`Histórico detalhado fica no computador`

## Migration strategy

This is deliberately progressive:

- old Agents continue working;
- devices without snapshots use the legacy cloud fallback;
- Linux 0.3.33 writes SQLite locally and supplies snapshots;
- Windows 0.3.33 remains compatible but uses the legacy Activity fallback in
  this first canary;
- Windows local-store parity is a subsequent slice;
- remote execution coordination remains unchanged.

## Safety boundary

This change does not move commercial authority to the customer device.

A modified local SQLite database cannot grant:

- Pro/paid access
- tenant membership
- roles
- billing state
- administrative privileges
- enrollment/revocation authority

Those remain cloud-authoritative.

## Expected product effect

- faster Activity refresh as devices upgrade
- lower D1 rows-read for operational history
- fewer historical cloud queries
- detailed customer activity remains on the customer's machine
- cloud retains only authority data and bounded operational aggregates
- rollout can be reversed per device without breaking existing Agents
