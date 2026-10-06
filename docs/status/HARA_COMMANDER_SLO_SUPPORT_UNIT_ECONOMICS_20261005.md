# H.A.R.A. Commander — SLO, support bundle and local-first unit economics

Date: 2026-10-05
State: SOURCE/PREPROD PASS — LIVE CANARY PENDING

## Internal beta SLO

This is an internal operational SLO, not a customer contractual SLA.

Profile:
- INTERNAL_BETA_V1
- success rate >= 99.0%
- p50 <= 1,000 ms
- p95 <= 6,000 ms
- p99 <= 12,000 ms
- minimum latency sample size: 20

Latency percentiles are calculated on the customer machine from completed
operations in the local SQLite Activity store.

Privacy:
- raw command/payload/result content is not synchronized;
- only aggregate percentiles/sample counts/status are included in heartbeat
  snapshots;
- latency sampling is bounded to the most recent 5,000 completed operations in
  the selected window.

Tenant/fleet aggregation uses the worst device percentile instead of averaging
percentiles.

## Support bundle V2

Installed Linux Agent support now emits:
- Agent/device/version metadata
- approval/session state
- heartbeat + last sanitized error class
- 24h Activity summary
- internal SLO summary
- product lease plan/mode/expiry and signed-token presence boolean
- local-budget counters/state, never the lease token
- local operations DB size/mode
- recent receipt SHA-256 values only

Explicit privacy flags:
- secret_material_exposed=false
- customer_content_included=false
- command_content_included=false
- payload_content_included=false
- result_content_included=false

The installer keeps support-report.v1 as a compatibility fallback when no
installed Agent is available.

## Local-first unit economics

The model intentionally does not invent USD cost without live Cloudflare
Analytics.

At the full Free allowance:
- calls/month/user = 10,000
- legacy cloud quota reserve+terminal RPCs = 20,000
- local budget block size = 100
- maximum block allocations = 100
- quota-plane decision reduction = 99.5%
- budget reports piggyback existing heartbeat traffic
- detailed Activity cloud history is not required for local-first devices
- TenantQuota fallback status complexity = O(1)

Scale rung, all Free at full allowance:
- 100 users: 1,000,000 calls/month; 2,000,000 legacy quota RPCs vs <=10,000
  block allocations
- 1,000 users: 10,000,000 calls/month; 20,000,000 legacy quota RPCs vs
  <=100,000 block allocations

Live USD economics still require read-only analytics for:
- Worker CPU
- Durable Object requests/duration
- D1 rows read/written
- egress bytes

## Source/preprod

PASS:
- Linux local percentile/SLO source
- Windows local percentile/SLO source parity
- Worker snapshot sanitizer
- conservative tenant p50/p95/p99 aggregation
- cloud fallback preserves local SLO
- SLO probe self-test
- support bundle v2 dynamic privacy test
- local-first unit economics deterministic model
- Agent/installer/manifest validation
- E2E harness
- full preprod readiness

## Promotion boundary

1. deploy to DEV;
2. update a HARA Linux device to 0.3.38;
3. verify support-report.v2 live;
4. verify heartbeat carries percentiles/SLO;
5. run DEV operational SLO probe;
6. then promote to PROD and update HARA Linux devices one-by-one.

## DEV live proof

Worker:
- 398b55e0-1c1b-4935-8179-d8591d37c7d6
- rollback: 8fa82e3d-00d6-441f-aa6a-9e650a52b616

DEV readback:
- config/secrets/D1/DeviceChannel PASS
- health/login/PKCE/cookie/account-switch PASS

Disposable 0.3.38 SLO heartbeat canary:
- local SQLite generated 25 completed operations
- p50=500 ms
- p95=5,000 ms
- p99=5,000 ms
- INTERNAL_BETA_V1 status=PASS
- heartbeat accepted
- Worker stored aggregate percentile/SLO fields
- raw events/action summary/payload/result/command fields absent
- fixture cleanup PASS

DEV_SLO_HEARTBEAT=PASS
DEV_SLO_RAW_CONTENT_SYNCED=FALSE

## PROD live proof

Worker:
- 9bb49ba2-2955-4b22-b96f-ad8833247200
- rollback: 7491e096-4e98-4978-8e09-c2b1f6ef5d0c
- fail-closed suite PASS
- public Agent release 0.3.38

nucleo-a:
- Agent 0.3.38
- health PASS
- support schema hara.commander-support-report.v2
- SLO status PASS
- success 99.2%
- p50 700 ms at initial support read
- p95 5,749 ms
- p99 10,341 ms
- latency sample >300
- Founder lease metadata present without token disclosure
- recent receipt hashes exposed as SHA-256 only
- secret/customer content flags false

sentinela-d:
- Agent 0.3.38
- health PASS
- support schema hara.commander-support-report.v2
- success 100%
- p50 338 ms
- p95 3,530 ms
- p99 3,530 ms
- latency sample 16
- SLO status INSUFFICIENT_DATA (correct minimum-sample behavior)
- secret exposure false

Cloud aggregate:
- D1 heartbeat snapshot contains percentile/SLO aggregates
- raw events/action summary/command/payload/result/stdout/stderr absent

Fleet 24h SLO at acceptance:
- fleet_state PASS
- online devices 2
- evaluable devices 1
- PASS devices 1
- degraded devices 0
- insufficient-data devices 1
- missing snapshots 0
- stale snapshots 0
- weighted success rate 99.259%
- worst-device p50 704 ms
- worst-device p95 5,749 ms
- worst-device p99 10,341 ms

## Unit economics acceptance

At one Free user consuming the full 10,000 monthly allowance:
- old per-call quota model: 20,000 cloud reserve/terminal quota RPCs
- local-budget model: <=100 cloud block allocations
- quota-plane decision reduction: 99.5%

At 100 all-Free users consuming full allowance:
- 1,000,000 calls/month
- 2,000,000 legacy quota RPCs
- <=10,000 block allocations
- 1,990,000 quota RPCs avoided

At 1,000 all-Free users consuming full allowance:
- 10,000,000 calls/month
- 20,000,000 legacy quota RPCs
- <=100,000 block allocations
- 19,900,000 quota RPCs avoided

USD cost remains intentionally unclaimed until live read-only analytics provides
Worker CPU, DO requests/duration, D1 rows and egress.

## Final state

INTERNAL_BETA_SLO_SOURCE=CLOSED_PASS
INTERNAL_BETA_SLO_DEV=CLOSED_PASS
INTERNAL_BETA_SLO_PROD=CLOSED_PASS
SUPPORT_BUNDLE_V2_SOURCE=CLOSED_PASS
SUPPORT_BUNDLE_V2_LINUX_PROD=CLOSED_PASS
LOCAL_FIRST_UNIT_ECONOMICS=CLOSED_PASS
LIVE_USD_COST=PENDING_READ_ONLY_ANALYTICS
PROD_ROLLBACK_READY=7491e096-4e98-4978-8e09-c2b1f6ef5d0c

## Current SLO follow-up

A later natural-traffic readback after both Linux Agents remained on 0.3.38
moved sentinela-d beyond the minimum sample threshold.

Current 24h fleet checkpoint:
- fleet_state PASS
- online devices 2
- evaluable devices 2
- PASS devices 2
- degraded devices 0
- insufficient-data devices 0
- missing snapshots 0
- stale snapshots 0
- weighted success rate 99.263%
- worst-device p50 700 ms
- worst-device p95 5,749 ms
- worst-device p99 10,413 ms

This supersedes only the sample-sufficiency state of the earlier acceptance
checkpoint; the earlier measurements remain valid evidence of rollout behavior.

INTERNAL_BETA_SLO_CURRENT=PASS_2_OF_2
