# Commander Event V2 context fast-path — live DEV proof

Date: 2026-09-26
Owner: #163
Environment: DEV only

## Deployment

```text
SOURCE_MAIN=f94ccd83c12bb7222e484a736fc338151c8b0c6d
DEV_WORKER_VERSION=0a69a5b8-435d-4c2a-b1e5-059177e19d9f
ROLLBACK_VERSION=e79c8648-925b-4f5b-a06c-dedae46b2787
PROD_MUTATION=FALSE
PROD_CUTOVER=DENY
```

Canonical DEV deployment readback passed for config, D1, secrets,
DeviceChannel, public health, OIDC PKCE and account switching.

## Query-shape decision

Previous transient common path used three sequential D1 awaits:

```text
identity / entitlement = 7 rows read
plan grants            = 4 rows read
selected device        = 2 rows read
TOTAL                   = 13 rows read / 0 writes
```
A CTE + GROUP BY consolidation was measured first and rejected:

```text
rows_read=20
rows_written=0
sql_duration_ms≈3.12
DECISION=REJECT
```

The selected scalar-subquery shape measured:

```text
queries=1
rows_read=13
rows_written=0
sql_duration_ms≈2.47
DECISION=ACCEPT_FOR_DEV_A_B
```

The fast-path returns identity/entitlement context, grants and selected
active device from that one query. Durable/MCP flows retain the existing
`mcpProductContext()` path. Shared policy validation remains centralized.

## Live A/B

Immediately prior DEV baseline used Worker `e79c8648...`.
The new fast-path used Worker `0a69a5b8...`.

Both series used 50 complete cycles:

```text
cycle = transient health + transient invoke + same-request replay
baseline_pass=50/50
fastpath_pass=50/50
```
Latency comparison:

```text
HEALTH
p50 649.790 -> 394.207 ms   (-39.33%)
p95 761.549 -> 439.385 ms   (-42.30%)

INVOKE
p50 914.615 -> 660.453 ms   (-27.79%)
p95 950.041 -> 711.329 ms   (-25.13%)

REPLAY
p50 773.705 -> 519.972 ms   (-32.80%)
p95 805.871 -> 541.461 ms   (-32.81%)

FULL CYCLE
p50 2335.764 -> 1578.467 ms (-32.42%)
p95 2480.738 -> 1633.680 ms (-34.15%)
```

The first-1k planning model keeps a conservative 1.0 second call-duration
envelope despite the lower observed Linux invoke p95 of 0.711329 seconds.

## Safety / cleanup

```text
D1_ROWS_READ_PER_TRANSIENT_HTTP=13
D1_ROWS_WRITTEN_PER_TRANSIENT_HTTP=0
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
TRANSIENT_CANARY_STOPPED_CLEANLY=TRUE
PUBLIC_AGENT_PROCESS_COUNT=1
LAST_ERROR_CODE=null
```
## Current remaining scale gates

The transport no longer shows a redesign requirement for the first-1k
consumer target. Remaining evidence is operational:

1. Durable Objects request/duration analytics for DeviceChannel and TenantQuota.
2. Bounded multi-device concurrency and reconnect-wave proof.
3. Windows runtime parity under #240.
4. PROD cutover remains denied until acceptance opens that gate.

Cloudflare documents Durable Object analytics through GraphQL datasets
including `durableObjectsInvocationsAdaptiveGroups`,
`durableObjectsPeriodicGroups`, `durableObjectsStorageGroups` and
`durableObjectsSubrequestsAdaptiveGroups`.

The current services host has a Wrangler OAuth session, but no dedicated
`CLOUDFLARE_API_TOKEN` environment variable. Existing OAuth credentials are
not copied out of Wrangler configuration for analytics collection.

```text
DO_GRAPHQL_COLLECTOR=BLOCKED_ON_EXPLICIT_READ_ONLY_CREDENTIAL_PATH
MULTI_DEVICE_CONCURRENCY=PENDING
WINDOWS_RUNTIME_PARITY=PENDING_#240
PROD_CUTOVER=DENY
```
