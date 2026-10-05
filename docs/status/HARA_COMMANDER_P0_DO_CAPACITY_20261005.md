# H.A.R.A. Commander — Durable Object capacity P0

Date: 2026-10-05
Workstream: `local/commander-do-capacity-20261005`
Base when implementation started: `b28db489e72fe1d1b0325f94f5aaaa95c681f558`

## Problem

Two public-beta P0 gates were blocked by Durable Object capacity:

- live multitenant portal select/revoke + TenantQuota proof;
- fresh-customer DEV enrollment.

Observed runtime failures:

- `Exceeded_allowed_rows_read_in_Durable_Objects_free_tier_`
- `STRICT_RATE_LIMIT_CHECK_FAILED`
- TenantQuota authorize HTTP 500 / `INTERNAL_ERROR`

A parallel workstream later added strict-rate-limit outage resilience. This workstream targets a different issue: the hot-path storage complexity of `TenantQuota`.

## Root cause in TenantQuota hot path

Before this change:

1. `expireStaleReservations()` executed an UPDATE filtered by `state='RESERVED' AND updated_at_utc<=?` without a matching composite index.
2. `status(periodKey,...)` executed `SUM(units)` over all RESERVED/COMMITTED rows for the period.
3. Product/usage refreshes call `TenantQuota.status`.
4. For `LIFETIME` entitlements, the amount of historical `request_state` data can grow indefinitely, so rows-read per status call grows with history.

## P0.1 — indexed reservation expiry

Added:

`idx_request_state_expiry ON request_state(state, updated_at_utc)`

Validation:

- expiry semantics unchanged;
- TTL remains 600 seconds;
- stale reservations become RELEASED with units=0;
- committed/fresh reservations preserved;
- SQLite query plan uses `idx_request_state_expiry`.

## P0.2 — O(1) period usage

Added persisted aggregate:

`period_usage(period_key PRIMARY KEY, consumed_units)`

Added schema marker:

`quota_meta(id=1, usage_schema_version)`

Upgrade/backfill:

- existing `request_state` rows are aggregated once when usage schema version < 1;
- the marker is then set to version 1;
- normal hot-path status does not re-run the aggregate backfill.

Atomic accounting is maintained with SQLite triggers:

- INSERT of RESERVED/COMMITTED adds units;
- same-period state/unit UPDATE applies one net delta;
- period-changing UPDATE decrements old period and adds to new period;
- DELETE decrements active usage for future retention safety;
- CHECK `consumed_units >= 0` remains fail-closed.

Hot-path `status()` now executes:

`SELECT consumed_units FROM period_usage WHERE period_key = ?`

The previous `SUM(units)` is absent from the status hot path.

## Validation

Passed:

- `COMMANDER_TENANT_QUOTA_EXPIRY_INDEX=PASS`
- `COMMANDER_TENANT_QUOTA_AGGREGATE_BACKFILL=PASS`
- `COMMANDER_TENANT_QUOTA_TRIGGER_ACCOUNTING=PASS`
- `COMMANDER_TENANT_QUOTA_STATUS_SUM_QUERY=ABSENT`
- `COMMANDER_TENANT_QUOTA_STATUS_COMPLEXITY=O1`
- `COMMANDER_TENANT_QUOTA_STORAGE_EFFICIENCY_P02=PASS`
- reservation TTL validator PASS;
- Event V2 quota source probe PASS;
- multitenant source model PASS;
- full E2E harness PASS, including reserve/release/commit idempotency and receipt binding.

One invalid trigger design was caught before deploy: an UPSERT carrying a negative INSERT value tripped the aggregate CHECK before conflict resolution. It was replaced with direct UPDATE/net-delta triggers. No broken variant was deployed.

## Runtime state

This source optimization has not yet been promoted to PROD.

Before live promotion:
1. reconcile on top of current canonical;
2. run broad regression;
3. deploy to DEV only;
4. rerun:
   - `commander_multitenant_live_dev_probe.py`
   - `commander_fresh_customer_dev_acceptance.py`
5. inspect Durable Object behavior/cost if analytics credentials are available;
6. promote only after DEV gates remain fail-closed and isolation/acceptance improve.

## Success criteria for successor

- TenantQuota status remains O(1);
- TTL/idempotency/receipt semantics unchanged;
- multitenant live DEV reaches PASS;
- fresh-customer DEV reaches enrollment and Simple MCP acceptance;
- no regression in strict-rate-limit fail-closed/resilience behavior;
- no PROD deployment before DEV proof.

## DEV live continuation on current canonical

The published candidate 5c06765 was reconciled onto current canonical f7f7d37 in a clean successor worktree.

Reconciled candidate:
4157dff806514e9192bcfcc7d4fd5d2f5c17de69

All requested source/regression gates passed before deployment.

DEV-only Worker deployment and readback passed. After canonical DEV canary secret synchronization, the live Worker version was:
122cd8ce-8abc-4b7f-9d06-5fe2340245ce

Live multitenant execution proved portal select/revoke tenant isolation, but TenantQuota authorize still returned HTTP 500.

A filtered live Worker tail captured the exact Durable Objects platform exception in:
- SecurityRateLimit
- TenantQuota

Exception:
Exceeded allowed rows read in Durable Objects free tier.

This continuation does not claim that P0.2 removed an already-exhausted account-level daily budget. It proves:
- optimized source/regression model intact
- DEV bundle/readback healthy
- portal isolation reaches and passes select/revoke
- remaining TenantQuota live proof is blocked by the account rows-read budget

No PROD promotion was performed.

Next gate:
- wait for Durable Objects rows-read capacity reset or upgrade account capacity
- rerun the unchanged multitenant probe
- require tenant A and tenant B to independently reserve the same request ID in separate TenantQuota namespaces
- only then consider promotion
