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
