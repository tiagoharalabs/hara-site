# H.A.R.A. Commander — Public product boundary recovery

Date: 2026-10-06
State: PROD RELEASE CANDIDATE

## Product boundary

The public H.A.R.A. Commander product is the governed MCP bridge between a
customer computer and supported MCP clients.

Customer product surfaces:
- enrolled computers;
- plan and quota usage;
- MCP endpoint/client connection;
- simple device state;
- billing/checkout;
- support/recovery surfaces.

Not part of the public product:
- H.A.R.A. laboratory fleet;
- Sentinela/Nucleo topology;
- internal SLO incidents;
- p95/p99 engineering latency;
- transport-mode diagnostics;
- top tools/errors;
- internal escalation controls.

## Immediate public runtime changes

- public portal no longer fetches /api/portal/activity;
- public portal no longer fetches or operates /api/portal/slo;
- public SLO/activity endpoints return INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT;
- internal SLO cron is not scheduled in the public Worker;
- heartbeat no longer persists activity_summary_json/activity_summary_at_utc;
- old Agents may still send activity_snapshots, but the public Worker ignores them;
- heartbeat presence writes are throttled to 120 seconds unless device metadata changes;
- online grace is 240 seconds, so write throttling does not create false offline state;
- customer activity-detail persistence in cloud is explicitly false.

## Beta diagnostics

During development only, the Usage page may reveal a block marked:

DIAGNÓSTICO LOCAL · BETA

That block reads directly from the local Agent loopback/SQLite and is hidden
when local-loopback diagnostics are unavailable.

The GA gate must fail while that beta block exists.

## Supply-chain split

This PROD release intentionally keeps the currently signed Agent 0.3.40
artifacts unchanged.

A separate source lane contains Agent 0.3.41 with local MCP activity tools and
availability-only diagnostic SLO semantics. That Agent update remains pending
release-manifest re-signing and is not required for this public Worker/UI fix.

PUBLIC_PRODUCT_BOUNDARY=PASS
PUBLIC_CLOUD_ACTIVITY_HISTORY=DISABLED
PUBLIC_INTERNAL_SLO_UI=DISABLED
PUBLIC_INTERNAL_SLO_CRON=DISABLED
HEARTBEAT_PERSIST_SECONDS=120
DEVICE_ONLINE_GRACE_SECONDS=240
SIGNED_AGENT_RUNTIME=0.3.40_UNCHANGED
BETA_LOCAL_DIAGNOSTICS=DEVELOPMENT_ONLY
GA_BETA_DIAGNOSTICS_REMOVAL=PENDING
