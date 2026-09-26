# Commander Event V2 transient RPC — 100-cycle DEV measurement

Date: 2026-09-26  
Owner: #163  
Environment: DEV only  
Device: HARA-owned `nucleo-a-event-v2-dev`

## Scope

This checkpoint advances the live scale evidence after PR #252. It does not
authorize PROD cutover and does not mutate the public Agent 0.3.7.

```text
MAIN_AT_START=a4029fcffe8286aeff6fe4575f84462b0f6d7611
DEV_SOURCE_ALIGNMENT=9fea10e0c802143d7549edf06a1c80a7092647a0
DEV_ACTIVE_VERSION=c5e1b681-959f-4b52-98bd-60aa5a8a65e9
PROD_MUTATION=FALSE
PROD_CUTOVER=DENY
```

## 100-cycle result

One cycle is:

```text
transient hara.health
  -> transient hara.functions.invoke
  -> same-request transient replay
```

All stages validate transport mode, quota/receipt state, privacy flags and
replay semantics before the cycle is counted PASS.

```text
CYCLES=100
TRANSIENT_HTTP_CALLS=300
PASS=100
FAIL=0
DOUBLE_EXECUTION=FALSE
```

Measured end-to-end latency from the services probe:

```text
HEALTH:
  p50=642.723 ms
  p95=671.410 ms
  p99=693.627 ms
  max=850.273 ms

INVOKE:
  p50=901.479 ms
  p95=942.058 ms
  p99=988.915 ms
  max=1038.017 ms

REPLAY:
  p50=882.865 ms
  p95=905.005 ms
  p99=923.592 ms
  max=924.171 ms

FULL_CYCLE:
  p50=2428.006 ms
  p95=2513.469 ms
  p99=2594.217 ms
  max=2666.435 ms
```

There was no progressive degradation:

```text
HEALTH_SECOND50_VS_FIRST50=-1.383%
INVOKE_SECOND50_VS_FIRST50=+0.260%
REPLAY_SECOND50_VS_FIRST50=-0.462%
CYCLE_SECOND50_VS_FIRST50=-0.440%
```

These are end-to-end application timings. They must not be relabeled as
Cloudflare billable Durable Object duration.

## Local idempotency / receipt effects

Before the series:

```text
LEDGER=30
RECEIPTS=208
```

After 100 cycles:

```text
LEDGER=230  delta=+200
RECEIPTS=408 delta=+200
```

Each cycle has exactly two first executions: health + invoke. The third request
is a replay of the invoke. Therefore +200 ledger entries and +200 receipts prove
that the 100 replay calls created neither a second execution ledger entry nor a
second receipt.

## D1 durable-content proof

Direct remote DEV D1 readback after the series:

```text
request_id LIKE 'TRANSIENT-INVOKE-%' -> 0 commander_device_calls rows
request_id LIKE 'TRANSIENT-HEALTH-%' -> 0 commander_device_calls rows
```

The transient data plane continues to create no durable call-content rows.

## Precise D1 hot-path row cost

Cloudflare D1 per-query metadata was used for the exact three queries executed
by the transient dispatch common path:

```text
MCP identity / entitlement context:
  rows_read=7
  rows_written=0
  sql_duration_ms=0.3406

plan grants:
  rows_read=4
  rows_written=0
  sql_duration_ms=0.0703

selected device:
  rows_read=2
  rows_written=0
  sql_duration_ms=0.1216

TOTAL PER TRANSIENT HTTP:
  rows_read=13
  rows_written=0
  measured SQL server time sum=0.5325 ms
```

D1 Insights was also captured before/after, but the rolling aggregate contained
other DEV traffic and asynchronous ingestion. It is retained as supporting
evidence, not used as the exact per-call billable-row number.

Official Cloudflare D1 pricing reference, current at this checkpoint:
https://developers.cloudflare.com/d1/platform/pricing/

## Offline grace and reconnect

Controlled clean disconnect:

```text
LOCAL_CONNECTED_FALSE=PASS
D1_EVENT_V2_OFFLINE=PASS
OFFLINE_GRACE_MS=57388
CONTRACT_WINDOW_MS=30000..60000
OFFLINE_TRANSIENT_REQUEST=DEVICE_OFFLINE
OFFLINE_REJECTION=PASS
```

Reconnect:

```text
LOCAL_CONNECTED_TRUE≈459 ms after process start
D1 last_seen/tunnel_mode updated in the same reconnect second
post-reconnect health=PASS
post-reconnect invoke=PASS
post-reconnect quota=COMMITTED
post-reconnect replay=REPLAY_ONLY/REPLAYED
```

The Wrangler polling process observed D1 later because each CLI query has
startup/network overhead; that polling delay is not reported as reconnect
latency.

Final cleanup:

```text
TRANSIENT_CANARY_RUNNING=FALSE
PUBLIC_AGENT_0_3_7_PROCESS_COUNT=1
LOCAL_EVENT_STATUS_CONNECTED=FALSE
LAST_ERROR_CODE=null
```

## First-1k measured planning envelope

The deterministic model now carries the measured D1 row cost and uses a
conservative `1.0 s` call-duration planning envelope, above the observed Linux
invoke p95 of 0.942058 s.

Assumptions for both profiles:
- 1,000 devices;
- all logical calls are governed invokes;
- one reconnect per device per day;
- four durable liveness checkpoints per device per day;
- hibernatable DeviceChannel WebSockets;
- 1.0 s DeviceChannel active-call planning envelope.

### 10 calls/device/day — primary first-1k target

```text
CALLS_DAY=10000
WORKER_HTTP_DAY=10000
TENANT_QUOTA_RPC_DAY=20000
RECONNECT_REQUEST_DAY=1000

DO_REQUEST_EQ_MONTH=951000
DO_REQUEST_OVERAGE_USD=0.00

DO_DEVICECHANNEL_GB_SECONDS_MONTH=37500
DO_DURATION_OVERAGE_USD=0.00

D1_TRANSIENT_ROWS_READ_MONTH=3900000
D1_CONTROL_ROWS_WRITTEN_MONTH=150000
D1_READ_OVERAGE_USD=0.00
D1_WRITE_OVERAGE_USD=0.00
```

### 100 calls/device/day — heavy stress envelope

```text
CALLS_DAY=100000
TENANT_QUOTA_RPC_DAY=200000

DO_REQUEST_EQ_MONTH=9186000
DO_REQUEST_OVERAGE_USD≈1.35

DO_DEVICECHANNEL_GB_SECONDS_MONTH=375000
DO_DURATION_OVERAGE_USD=0.00 before TenantQuota duration is added

D1_TRANSIENT_ROWS_READ_MONTH=39000000
D1_CONTROL_ROWS_WRITTEN_MONTH=150000
D1_READ_OVERAGE_USD=0.00
D1_WRITE_OVERAGE_USD=0.00
```

Official Cloudflare Durable Objects pricing reference, current at this
checkpoint:
https://developers.cloudflare.com/durable-objects/platform/pricing/

### Cost-boundary caveat

The request model includes TenantQuota RPC request-equivalents, but the duration
model intentionally does **not** invent TenantQuota active-duration data. At
100 calls/device/day, the DeviceChannel-only duration envelope reaches
375,000 of the current 400,000 included GB-s/month. Therefore the heavy profile
must not be called "fully free" until Durable Object GraphQL metrics measure
TenantQuota + DeviceChannel duration together.

The primary 10-calls/device/day profile has much larger duration headroom.

## Next gate

```text
1K_PRIMARY_ARCHITECTURE_REDESIGN_REQUIRED=NO_EVIDENCE
1K_10_CALLS_DAY_COST_HEADROOM=STRONG
DO_GRAPHQL_DURATION_MEASUREMENT=PENDING
MULTI_DEVICE_CONCURRENCY_PROOF=PENDING
WINDOWS_RUNTIME_PARITY=PENDING_#240
PROD_CUTOVER=DENY
```

Next engineering work should focus on a safe Durable Objects analytics collector
and bounded multi-device concurrency/reconnect simulation, not another transport
rewrite.
