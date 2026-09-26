# H.A.R.A. Commander Event V2 — Successor Handoff

**Timestamp:** 2026-09-26T20:23Z  
**Repository:** `tiagoharalabs/hara-site`  
**Primary owner:** #163 — **Event V2 implementation, optimization, Cloud cost, scale and transport engineering**  
**Product/Windows live acceptance owner:** #240 — **Commander Product Hardening & Launch**  
**Security adversarial owner:** #189  
**Successor entrypoint:** this document  
**PROD Event V2 cutover:** **DENY**

---

## 1. Executive state

This handoff supersedes:

```text
docs/handoffs/HARA_COMMANDER_EVENT_V2_SUCCESSOR_HANDOFF_20260926T0316Z.md
```

Fresh repository/currentness census at transfer:

```text
MAIN=202b46a2f04d9b51ac3d1cce464e1ff7b889cbd2
MAIN_TITLE=feat(commander): add read-only DO analytics collector (#262)
OPEN_EVENT_V2_PRS=NONE

DEV_ACTIVE_VERSION=0fd00030-5f1a-436d-b02e-29a8741b698d
DEV_ACTIVE_SOURCE_BASE=7e8bab8f367d30ab11634da217b4bc1de6c8f216
DEV_ROLLBACK_VERSION=0a69a5b8-435d-4c2a-b1e5-059177e19d9f

DEVICE_EVENT_V2_ENABLED=true
DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED=true
DEV_ANALYTICS_ENGINE_BINDING=ABSENT_BY_GATE

PUBLIC_AGENT_0_3_7_MUTATION=FALSE
PROD_EVENT_V2_MUTATION=FALSE
PROD_CUTOVER=DENY
```

The current front is no longer proving whether Event V2 works. Linux DEV transient
Event V2 is live-proven. The engineering problem has moved to **measured
efficiency, Durable Object observability, multi-device concurrency, and defects
returned by the acceptance front**.

Do not restart architecture design from first principles unless new measured
evidence invalidates the current design.

---

## 2. Canonical ownership boundary

```text
#163 COMMANDER EVENT V2
= IMPLEMENTATION
+ OPTIMIZATION
+ CLOUD COST
+ SCALE
+ TRANSPORT
+ DEFECT REMEDIATION

#240 COMMANDER PRODUCT HARDENING & LAUNCH
= WINDOWS LIVE LAB
+ PRODUCT ACCEPTANCE
+ SECURITY/REGRESSION COORDINATION
+ RELEASE ACCEPTANCE
+ LAUNCH

#189
= SECURITY ADVERSARIAL OWNER
```

Canonical flow:

```text
#163 implements/optimizes
        ↓
#240 tests live/product acceptance
        ↓
PASS -> acceptance/release path
FAIL -> defect returns to #163
        ↓
#163 remediates
        ↓
#240 retests
```

Do not create a competing Windows live acceptance campaign in #163.

The current canonical Windows lab under #240 is the VM `commander-win11` on
`nucleo-a`. Windows runtime parity is still not a #163 self-claim.

---

## 3. Current managed-relay architecture

Customer path:

```text
ChatGPT / Codex
  -> Commander Worker
  -> identity / entitlement / selected-device validation
  -> TenantQuota Durable Object when invoke is governed
  -> per-device DeviceChannel Durable Object
  -> hibernatable Event V2 WebSocket
  -> local HARA Agent
  -> customer machine
```

Planes:

```text
CONTROL PLANE
  identity | entitlement | quota | device | presence | billing metadata

TRANSIENT DATA PLANE
  validated request -> DeviceChannel -> Agent -> result
  request/result are not durable D1 call-content rows

LEARNING PLANE
  strict derived allowlist only
  no customer payload/result/content
```

Privacy truth:

```text
MANAGED_RELAY_CONTENT_IN_TRANSIT=TRUE
MANAGED_RELAY_DURABLE_CUSTOMER_CONTENT=FALSE_ON_TRANSIENT_PATH
D1_CUSTOMER_PAYLOAD_PERSISTENCE=FALSE
D1_CUSTOMER_RESULT_PERSISTENCE=FALSE
LEARNING_CUSTOMER_CONTENT=FALSE
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE
```

Do **not** claim hosted E2E opacity. The managed relay necessarily processes the
request/result transiently in memory. The guarantee is that this content does
not become H.A.R.A. durable product/learning data on the transient path.

---

## 4. Major successor-era PR ledger

The following work is merged and **must not be recreated**.

### Transient data plane / privacy

- **#246** — DEV-only transient Event V2 data plane, Linux local idempotency
  ledger, metadata-only learning signal, first-1k transient model.
- **#248** — Windows transient Event V2 source parity slice, real PowerShell
  parser gate, Windows local idempotency source.
- **#249** — transient invoke bound to quota lifecycle:
  reserve -> dispatch -> receipt -> commit/release; ambiguous timeout keeps
  RESERVED; committed retry is REPLAY_ONLY.
- **#250** — TenantQuota repeated SQL work reduction.
- **#251** — bounded durable-call customer-content redaction fallback. Do not
  confuse this fallback cleanup with the transient path, which writes no call
  content row.

### Live proof / scale

- **#252** — first live DEV transient proof:
  health PASS, invoke PASS, quota COMMITTED, same-request replay
  REPLAY_ONLY/REPLAYED, zero `commander_device_calls` row.
- **#253** — 100-cycle live DEV measurement and first-1k cost calibration.
- **#254** — committed replay fast-path removes redundant second TenantQuota
  commit RPC.
- **#255** — secondary MCP bootstrap only when explicit provider/email hints
  exist; unprovisioned no-hint identity returns
  `IDENTITY_NOT_PROVISIONED`.

### Context/latency optimization

- **#257** — transient context fast path collapses identity/entitlement +
  plan grants + selected device from three sequential D1 awaits into one query
  while preserving 13 rows-read / 0 writes.
- **#259** — canonical live evidence for the #257 context fast path.

### Privacy-safe learning / account feature gate

- **#261** — source-ready DEV-only privacy-safe learning aggregation using
  Workers Analytics Engine; strict derived allowlist.
- **#264** — canonical account-level gate after Cloudflare rejected Analytics
  Engine activation with API code 10089. DEV/PROD configs intentionally omit
  the binding until explicit account feature enablement.

### Durable Object analytics

- **#262** — canonical read-only Durable Object GraphQL analytics collector.
  Aggregate-only, DEV namespaces only, dedicated read token required.

Current `main` ends at #262.

---

## 5. Current live performance evidence

### Original series100 baseline before replay/context fast paths

```text
CYCLES=100
HTTP_CALLS=300
PASS=100
FAIL=0

health:
  p50=642.723ms
  p95=671.410ms

invoke:
  p50=901.479ms
  p95=942.058ms
  p99=988.915ms

replay:
  p50=882.865ms
  p95=905.005ms

full cycle:
  p50=2428.006ms
  p95=2513.469ms
```

No progressive degradation was observed:

```text
second50_vs_first50_cycle_mean=-0.440%
second50_vs_first50_invoke_mean=+0.260%
```

### Replay fast-path live A/B after #254/#255

50/50 complete cycles PASS.

```text
REPLAY:
  before p50=882.865ms
  after  p50=773.705ms
  delta≈-12.4%

  before p95=905.005ms
  after  p95=805.871ms
  delta≈-11.0%

INVOKE:
  p50=914.615ms
  p95=950.041ms
```

### Context fast-path live A/B after #257

50/50 complete cycles PASS.

Versus the immediately prior replay-fastpath baseline:

```text
health:
  p50 649.790 -> 394.207ms  (-39.33%)
  p95 761.549 -> 439.385ms  (-42.30%)

invoke:
  p50 914.615 -> 660.453ms  (-27.79%)
  p95 950.041 -> 711.329ms  (-25.13%)

replay:
  p50 773.705 -> 519.972ms  (-32.80%)
  p95 805.871 -> 541.461ms  (-32.81%)

full cycle:
  p50 2335.764 -> 1578.467ms (-32.42%)
  p95 2480.738 -> 1633.680ms (-34.15%)
```

Keep the first-1k economic model at the conservative **1.0 second/call** planning
envelope despite lower current measured Linux p95.

---

## 6. Idempotency / privacy / D1 evidence

100-cycle evidence:

```text
ledger:   30 -> 230  (+200)
receipts: 208 -> 408 (+200)
```

Each cycle contained two first executions (health + invoke) and one replay.
Therefore 100 replay requests created neither a second ledger entry nor a second
receipt.

Direct DEV D1 readback:

```text
request_id LIKE 'TRANSIENT-INVOKE-%'
  -> commander_device_calls rows = 0

request_id LIKE 'TRANSIENT-HEALTH-%'
  -> commander_device_calls rows = 0
```

Local replay ledger:

```text
MODE=0600
RAW_PAYLOAD_FIELD=ABSENT
PAYLOAD_SHA256=PRESENT
RESULT=PRESENT_LOCAL_ONLY
RETENTION=24h
CLEANUP_BATCH=32
```

A committed replay after #254 now uses:

```text
TenantQuota.reserve -> COMMITTED + canonical receipt
Agent -> REPLAY_ONLY
Worker -> compare replay receipt against committed receipt
second TenantQuota.commit RPC -> ABSENT
```

Receipt mismatch fails closed.

---

## 7. D1 hot path and first-1k envelope

The current context fast path preserves the measured row budget:

```text
D1_ROWS_READ_PER_TRANSIENT_HTTP=13
D1_ROWS_WRITTEN_PER_TRANSIENT_HTTP=0
```

The earlier three-query decomposition was:

```text
identity/context = 7 rows
plan grants      = 4 rows
selected device  = 2 rows
TOTAL            = 13 rows
```

#257 selected the scalar-subquery consolidated shape because the rejected
CTE/GROUP BY prototype read 20 rows and was slower.

Primary first-1k planning envelope:

Assumptions:

```text
DEVICES=1000
CALLS_PER_DEVICE_DAY=10
ALL_LOGICAL_CALLS=GOVERNED_INVOKES
RECONNECTS_PER_DEVICE_DAY=1
DURABLE_LIVENESS_PER_DEVICE_DAY=4
CALL_DURATION_PLANNING_ENVELOPE=1.0s
```

Model:

```text
CALLS_DAY=10000
TENANT_QUOTA_RPC_DAY=20000
DO_REQUEST_EQ_MONTH≈951000
DEVICECHANNEL_GB_SECONDS_MONTH≈37500

D1_TRANSIENT_ROWS_READ_MONTH≈3900000
D1_CONTROL_ROWS_WRITTEN_MONTH≈150000
```

At the current published Workers Paid inclusions used by the model, these
dimensions remain inside included capacity.

Heavy stress profile:

```text
1000 devices x 100 calls/device/day

DO_REQUEST_EQ_MONTH≈9186000
DO_REQUEST_OVERAGE_MODEL≈USD 1.35

DEVICECHANNEL_GB_SECONDS_MONTH≈375000
D1_ROWS_READ_MONTH≈39000000
D1_CONTROL_ROWS_WRITTEN_MONTH≈150000
```

**Do not call the heavy profile cost-final.** TenantQuota + DeviceChannel
active-duration still requires live Durable Object GraphQL measurement.

---

## 8. Offline / reconnect evidence

Controlled clean disconnect:

```text
LOCAL_CONNECTED_FALSE=PASS
D1_EVENT_V2_OFFLINE=PASS
OFFLINE_GRACE_MS=57388
CONTRACT=30000..60000ms
OFFLINE_TRANSIENT_REQUEST=DEVICE_OFFLINE
OFFLINE_REJECTION=PASS
```

Reconnect:

```text
LOCAL_CONNECTED_TRUE≈459ms after process start
D1 tunnel/last_seen updated in the same reconnect second
post-reconnect health=PASS
post-reconnect invoke=PASS
post-reconnect quota=COMMITTED
post-reconnect replay=REPLAY_ONLY/REPLAYED
```

Do not report Wrangler CLI polling delay as reconnect latency; CLI startup and
network overhead dominate that observation path.

---

## 9. Learning plane current state

Source contract is canonical and privacy-safe.

Allowed learning signal fields remain strictly derived:

```text
schema
tool_id
tool_family
outcome
latency_bucket
result_bytes_bucket
platform
agent_version
transport_mode
privileged_attempt=false
customer_content_collected=false
```

Forbidden from learning telemetry include customer identifiers, request/call/
receipt IDs, email/issuer, payload/result, prompt, arguments, argv, path,
filename, command, stdout/stderr and file content.

#261 prepared a DEV-only Analytics Engine write path and model:

```text
1k x 10 calls/day ≈ 300000 points/month
1k x 100 calls/day ≈ 3000000 points/month
```

However, Cloudflare account activation rejected the Analytics Engine binding
with API code **10089**.

Therefore current canonical state is:

```text
LEARNING_SOURCE=READY
LEARNING_ANALYTICS_BINDING_DEV=ABSENT_BY_GATE
LEARNING_ANALYTICS_BINDING_PROD=ABSENT
ACCOUNT_FEATURE_ENABLEMENT_REQUIRED=TRUE
FORCE_ENABLE_OR_WORKAROUND=DENY
```

Do not repeatedly redeploy the rejected binding. This is an account
capability/billing/owner gate, not a code defect.

---

## 10. Durable Object analytics collector

#262 is merged and is the only canonical path for live DO analytics.

Contract:

```text
MODE=READ_ONLY
SCOPE=DEV_ONLY
QUERY_CLASS=AGGREGATE_ONLY
CONTENT_DIMENSIONS=DENY

DATASETS:
  DurableObjectsInvocationsAdaptiveGroups
  DurableObjectsPeriodicGroups
  DurableObjectsStorageGroups
  DurableObjectsSubrequestsAdaptiveGroups
```

Security law:

```text
DEDICATED_TOKEN_REQUIRED=TRUE
REQUIRED_SCOPE=Account / Account Analytics / Read
TOKEN_FILE_MODE=0600
TOKEN_FILE_OWNER=current user
O_NOFOLLOW=when available
TOKEN_PRINT=DENY

CLOUDFLARE_API_TOKEN_ENV_FALLBACK=DENY
WRANGLER_OAUTH_REUSE=DENY
WRANGLER_DEFAULT_TOML_REUSE=DENY

PROD_QUERY=DENY
DEV_DEVICECHANNEL_NAMESPACE_ONLY=TRUE
DEV_TENANTQUOTA_NAMESPACE_ONLY=TRUE
```

The broad Wrangler OAuth credential on `services` must **not** be repurposed
for GraphQL analytics.

Live DO duration measurement is still pending the dedicated read-only token.

---

## 11. DEV deployment state

Current deployed DEV Worker:

```text
ACTIVE_VERSION=0fd00030-5f1a-436d-b02e-29a8741b698d
ACTIVE_SOURCE_BASE=7e8bab8f367d30ab11634da217b4bc1de6c8f216
ROLLBACK=0a69a5b8-435d-4c2a-b1e5-059177e19d9f
TRAFFIC=100%
```

Current `main`:

```text
202b46a2f04d9b51ac3d1cce464e1ff7b889cbd2
```

The difference after the deployed source is tooling/docs/read-only collector;
there is no requirement to deploy #262 merely to use the collector.

Post-#264 DEV deployment readback already passed for health and protected DEV
health behavior.

At the last smoke attempt, another HARA-owned runtime-backpressure canary was
using the same canary device identity. The temporary competing canary was
stopped and the existing process was left untouched.

**Successor rule:** census processes/device identity before starting any DEV
canary. Never run two canaries with the same device identity concurrently.

---

## 12. Windows / #240 boundary

#240 remains authoritative for Windows live acceptance.

Last known #240 state includes:

```text
CANONICAL_VM=commander-win11
HOST=nucleo-a
WINDOWS_DESKTOP_REACHED=TRUE
VCPU=8
RAM=16GiB
Q35+UEFI+SECURE_BOOT+TPM2=TRUE
AUTOSTART=DISABLED
GAMES_2TB=DO_NOT_TOUCH
```

A secondary domain `hara-commander-win11` was recorded separately as
non-canonical pending review and must not be deleted or mutated from #163.

#163 owns only Event V2 implementation/remediation returned from #240.

---

## 13. DO_NOT_REPLAY / hard prohibitions

```text
DO_NOT_REPLAY:
- D1 migration 0010
- D1 migration 0011
- prior Linux Event V2 terminal canary campaigns
- PR #246/#248/#249/#250/#252/#253/#254/#255/#257/#259/#261/#262/#264 work
- rejected 300ms terminal-settle experiment
- rejected Analytics Engine binding deployment while account feature is disabled

DENY:
- public Agent 0.3.7 mutation
- PROD Event V2 cutover
- customer traffic through HARA Services
- customer payload/result learning
- generic raw diagnostics
- reusing Wrangler OAuth/default.toml for DO GraphQL
- broad-token extraction from host config
- duplicate DEV canary using the same device identity
- competing Windows live acceptance campaign in #163
- claiming 20k or heavy 100-calls/day profile cost-final without live DO duration
```

The old durable V1 fallback remains a fallback. Do not delete it until product
acceptance and rollback policy explicitly authorize retirement.

---

## 14. Successor priority order

### P0 — Fresh currentness / process census

Before any live DEV work:

```text
fetch origin/main
read #163 latest comments
read #240 latest acceptance state
check DEV active Worker version
census nucleo-a canary processes/device identity
confirm PROD_CUTOVER=DENY
```

### P1 — Live Durable Object analytics

If and only if a dedicated Cloudflare **Account Analytics Read** token is
available in a secure 0600 file:

1. run the canonical #262 collector against DEV;
2. measure DeviceChannel and TenantQuota separately;
3. collect invocations, periodic, storage, subrequests and active duration;
4. reconcile measured duration against the 1k 10-calls/day and heavy
   100-calls/day models;
5. publish aggregate-only evidence to #163.

If the token is unavailable, **do not extract/reuse Wrangler OAuth**. Move to P2.

### P2 — Bounded multi-device concurrency

Design the next scale campaign with **distinct HARA-owned device identities**.
Do not reuse one device identity for simultaneous agents.

Recommended progression:

```text
10 distinct devices/connections
  -> steady transient calls
  -> concurrent invoke/replay
  -> reconnect wave
  -> offline grace

then 50/100 if clean
```

Measure:

```text
success/failure
p50/p95/p99
DEVICE_BUSY/backpressure
reconnect bucket distribution
D1 read/write
DO requests/duration when collector token exists
stuck/expired calls
double execution=0
customer-content durable rows=0
```

### P3 — Consume #240 Windows defects

When #240 reports a Windows Event V2 defect, #163 owns remediation and source
parity. Do not self-promote Windows runtime parity.

### P4 — Learning-plane activation

Only after account-level Analytics Engine enablement is explicitly approved and
available:

1. restore DEV binding;
2. deploy DEV only;
3. prove customer-call non-regression;
4. use a dedicated read-only analytics token for readback;
5. keep PROD binding absent until a separate product gate.

---

## 15. Separate future product work

OpenAI connector registration/publishing is a separate Product/Launch concern,
not Event V2 transport engineering.

When that work begins, use current official OpenAI documentation for connector/
MCP registration, authentication, review/publishing and privacy requirements.
Do not add it to #163 unless ownership explicitly changes.

---

## 16. Successor start command in plain language

The successor should begin with:

```text
Read this handoff first.
Then revalidate:
- origin/main
- #163
- #240
- DEV Worker deployment
- nucleo-a canary/process ownership

Do not replay completed PRs/canaries.
Do not enable Analytics Engine by workaround.
Do not reuse Wrangler OAuth for DO analytics.
Do not touch PROD Event V2.

If the dedicated DO analytics token exists:
  run #262 collector and close the duration-cost gap.

Otherwise:
  prepare bounded distinct-device multi-device concurrency/reconnect evidence.
```

---

## 17. Terminal transfer state

```text
THIS_FRONT=COMMANDER_EVENT_V2
THIS_INSTANCE_STATUS=TRANSFER_READY

MAIN=202b46a2f04d9b51ac3d1cce464e1ff7b889cbd2
OPEN_EVENT_V2_PRS=NONE

LINUX_TRANSIENT_LIVE_PROVEN=TRUE
SERIES100_PASS=TRUE
REPLAY_FASTPATH_LIVE_PROVEN=TRUE
CONTEXT_FASTPATH_LIVE_PROVEN=TRUE
D1_TRANSIENT_ROWS_READ_PER_HTTP=13
D1_TRANSIENT_CALL_CONTENT_WRITES=0

LEARNING_SOURCE_READY=TRUE
LEARNING_ANALYTICS_ACCOUNT_GATE=BLOCKED_BY_PROVIDER_FEATURE
DO_ANALYTICS_COLLECTOR_SOURCE_READY=TRUE
DO_ANALYTICS_LIVE_TOKEN_GATE=PENDING

MULTI_DEVICE_CONCURRENCY_PROOF=PENDING
WINDOWS_RUNTIME_ACCEPTANCE_OWNER=#240
PROD_CUTOVER=DENY
```

This instance may be retired after this handoff is merged and #163 points to it.
