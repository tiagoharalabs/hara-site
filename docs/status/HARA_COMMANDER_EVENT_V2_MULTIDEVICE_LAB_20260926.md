# Commander Event V2 — bounded multi-device DEV lane

Date: 2026-09-26
Owner: #163
Environment: DEV only
Status: LIVE_PROOF_PASS_10_DEVICES

## Currentness that triggered this lane

- main at entry: `ed7c2afbe3dc289e86a7c975bb40600967cce889` (#265 handoff only after #262/#264).
- existing Linux Event V2 canary on `nucleo-a` remains running and must not be duplicated.
- dedicated Durable Object Account Analytics Read token was not present in the governed token paths checked on `services`.
- therefore P1 remains blocked by credential provisioning and P2 is the next safe engineering path.
- PROD Event V2 cutover remains DENY.
- Windows live acceptance remains owned by #240.

## Source added

```text
apps/commander/scripts/commander_event_v2_dev_multidevice_lab.py
apps/commander/scripts/commander_event_v2_dev_multidevice_probe.py
```

The lab provisioner is bounded to 2..50 logical devices. Every device receives:

```text
distinct DEV subject
distinct identity binding
subject-scoped entitlement
distinct pairing/enrollment
distinct selected device
isolated XDG_CONFIG_HOME
isolated XDG_DATA_HOME
isolated local replay ledger
```

The existing canary root is not reused. New run roots are namespaced below:

```text
/tmp_hara/commander-event-v2-multidevice/<run-id>
```

No automatic deletion is implemented.

## Secret/privacy boundary

```text
DEVICE_TOKEN_IN_OPERATOR_MANIFEST=FALSE
PAIRING_TOKEN_IN_OPERATOR_MANIFEST=FALSE
DEVICE_CONFIG_MODE=0600
TOKEN_PRINT=DENY
CUSTOMER_CONTENT_OUTPUT=ABSENT
PROD_ORIGIN=DENY
PUBLIC_AGENT_MUTATION=FALSE
```

The concurrency probe emits aggregate counters/latency only. It does not emit
request IDs, receipt hashes, device IDs, payloads, results, or per-device
customer content.

## Planned bounded live proof

First live rung after source/CI acceptance:

```text
DEVICES=10 distinct identities/connections
WAVES=1 initially
per device:
  hara.health
  governed hara.functions.invoke
  same-request REPLAY_ONLY
```

Acceptance for the first rung:

```text
10/10 complete
quota state = COMMITTED
replay mode = REPLAY_ONLY
replay outcome = REPLAYED
privacy failures = 0
semantic failures = 0
duplicate device identities = 0
existing canonical canary untouched
PROD mutation = 0
```

Reconnect/offline waves remain a later rung after the first 10-device steady
concurrency proof is clean.

## CI

The Commander Scale V2 workflow now executes:

```text
commander_event_v2_dev_multidevice_lab.py --check
commander_event_v2_dev_multidevice_probe.py --check
validate_event_v2_transient_rpc.py
```

This closes the previous CI visibility gap for the transient validator.

## State

```text
DO_ANALYTICS_LIVE_TOKEN_GATE=PENDING
MULTI_DEVICE_CONCURRENCY_SOURCE=READY
MULTI_DEVICE_CONCURRENCY_PROOF=PASS_10_DEVICES
WINDOWS_RUNTIME_ACCEPTANCE_OWNER=#240
PROD_CUTOVER=DENY
```


## Live proof — 2026-09-26

Source and governance:

```text
SOURCE_MERGE=#266
SOURCE_MERGE_SHA=1fac41d6728fb016c9b1746984dfc92a43e52956
PROVENANCE_CI=SUCCESS
COMMANDER_SCALE_V2_CI=SUCCESS
DEV_WORKER_VERSION=0fd00030-5f1a-436d-b02e-29a8741b698d
DEV_HEALTH=PASS
EXISTING_CANARY_PROCESS_COUNT=1
EXISTING_CANARY_CONNECTED=TRUE
EXISTING_CANARY_ERROR=NONE
```

Bounded run:

```text
RUN_ID=md-20260926205232-04102b91
DEVICES=10
DISTINCT_SUBJECTS=10
DISTINCT_DEVICE_IDENTITIES=10
INITIAL_ALIVE=10
INITIAL_CONNECTED=10
INITIAL_ERROR_CODES=NONE
```

Initial concurrent wave:

```text
REQUESTED_CYCLES=10
COMPLETED_CYCLES=10
FAILED_CYCLES=0
WAVE_WALL_MAX_MS=1918.816
CYCLE_P50_MS=1864.631
CYCLE_P95_MS=1914.760
CYCLE_P99_MS=1914.760
INVOKE_P95_MS=740.364
REPLAY_P95_MS=573.883
PRIVACY_FAILURES=0
SEMANTIC_FAILURES=0
ERROR_CLASSES=NONE
TOKEN_EXPOSED=FALSE
```

Persistence readback after the initial wave:

```text
DEVICE_ROWS=10
EVENT_V2_ROWS=10
ACTIVE_ROWS=10
DURABLE_CALL_ROWS=0
```

Offline/reconnect boundary:

```text
GRACEFUL_STOPPED=10
LOCAL_ALIVE_AFTER_STOP=0
LOCAL_CONNECTED_AFTER_STOP=0
D1_TUNNEL_METADATA_IMMEDIATELY_AFTER_STOP=EVENT_V2_FOR_10
OFFLINE_HEALTH_RESULT=DEVICE_OFFLINE
OFFLINE_FAIL_CLOSED=PASS
RECONNECTED_ALIVE=10
RECONNECTED_CONNECTED=10
RECONNECT_OBSERVED_MS=4181
```

The D1 tunnel field remained in its refresh/grace window immediately after local
disconnect, but the actual transient dispatch returned `DEVICE_OFFLINE`. Stale
D1 metadata therefore did not authorize execution.

Post-reconnect concurrent wave:

```text
REQUESTED_CYCLES=10
COMPLETED_CYCLES=10
FAILED_CYCLES=0
WAVE_WALL_MAX_MS=1844.202
CYCLE_P50_MS=1816.317
CYCLE_P95_MS=1840.592
CYCLE_P99_MS=1840.592
INVOKE_P95_MS=752.769
REPLAY_P95_MS=554.307
PRIVACY_FAILURES=0
SEMANTIC_FAILURES=0
ERROR_CLASSES=NONE
TOKEN_EXPOSED=FALSE
```

Final bounded shutdown/readback:

```text
MULTIDEVICE_PROCESSES_FINAL=0
EXISTING_CANARY_PROCESS_COUNT_FINAL=1
EXISTING_CANARY_CONNECTED_FINAL=TRUE
EXISTING_CANARY_ERROR_FINAL=NONE
DEVICE_ROWS_FINAL=10
DURABLE_CALL_ROWS_FINAL=0
AUTO_DELETE=ABSENT
RAW_CUSTOMER_CONTENT_PERSISTENCE=ZERO_PROVEN_BY_DURABLE_CALL_ROW_READBACK
```

## Result

```text
MULTI_DEVICE_CONCURRENCY_PROOF=PASS_10_DEVICES
MULTI_DEVICE_RECONNECT_PROOF=PASS_10_DEVICES
MULTI_DEVICE_OFFLINE_FAIL_CLOSED=PASS
MULTI_DEVICE_DURABLE_CALL_ROWS=0
EXISTING_CANARY_PRESERVED=TRUE

DO_ANALYTICS_LIVE_TOKEN_GATE=PENDING
WINDOWS_RUNTIME_ACCEPTANCE_OWNER=#240
PROD_CUTOVER=DENY
```

This result closes the previously pending bounded multi-device concurrency proof
at 10 distinct devices. It does not claim a 50- or 100-device live proof.


## Next bounded scale rung — 50 devices

After the clean 10-device live proof, the source bound is raised to 50 devices
without changing the proven transport/privacy contract.

Provisioning is also optimized so DEV subject/identity/entitlement/pairing
fixtures are written in one D1 batch and device selections in one D1 batch.
Enrollment and per-device secret delivery remain isolated and secret-safe.

```text
SOURCE_MAX_DEVICES=50
NEXT_LIVE_RUNG=50
D1_FIXTURE_BATCHING=TRUE
D1_SELECTION_BATCHING=TRUE
DEVICE_TOKEN_OUTPUT=ABSENT
PAIRING_TOKEN_OUTPUT=ABSENT
AUTO_DELETE=ABSENT
PROD_CUTOVER=DENY
```

The existing `PASS_10_DEVICES` proof remains canonical until a separate
50-device live run passes and is published.


## 50-device provisioning hardening

The first 50-device provisioning attempt was intentionally blocked before any
agent start with the old generic error `MULTIDEVICE_COMMAND_FAILED:npx`.

Fresh D1 readback showed no partial new 50-device fixture rows; only the prior
10-device proof rows existed. A fresh filesystem census also found no new
50-device run root, which means the failure happened before remote source staging
and may have been the read-only template-context D1 lookup rather than the later
fixture batch.

The source is therefore hardened in two independent ways:

```text
D1_FIXTURE_BATCH_SIZE=10
D1_SELECTION_BATCH_SIZE=25
TEMPLATE_CONTEXT_READ_RETRY=BOUNDED_2_ATTEMPTS
WRITE_RETRY=DENY
D1_FAILURE_STAGE_CODES=ENABLED
FAILED_50_AGENT_STARTS=0
FAILED_50_PARTIAL_D1_FIXTURE_ROWS=0
AUTO_DELETE=ABSENT
```

Only the read-only template lookup may retry once. Fixture/selection writes do
not auto-retry because write failure is treated as potentially ambiguous. Future
failures identify `TEMPLATE_CONTEXT_QUERY`, `FIXTURE_BATCH`, or
`SELECTION_BATCH` without printing SQL or secrets.

The 50-device live rung must be retried only after this hardening passes CI.


## 50-device live rung — first wave and offline race

After #269 hardened provisioning, a fresh run was created:

```text
RUN_ID=md-20260926221942-0bd7ea80
DEVICES=50
PROVISION=PASS
TOKEN_EXPOSED=FALSE
INITIAL_ALIVE=50
INITIAL_CONNECTED=50
INITIAL_ERROR_CODES=NONE
```

Initial concurrent wave:

```text
REQUESTED_CYCLES=50
COMPLETED_CYCLES=50
FAILED_CYCLES=0
WAVE_WALL_MAX_MS=2567.125
CYCLE_P50_MS=2224.200
CYCLE_P95_MS=2373.115
CYCLE_P99_MS=2436.433
INVOKE_P95_MS=811.408
REPLAY_P95_MS=660.119
PRIVACY_FAILURES=0
SEMANTIC_FAILURES=0
ERROR_CLASSES=NONE
```

D1 readback after the wave:

```text
DEVICE_ROWS=50
EVENT_V2_ROWS=50
ACTIVE_ROWS=50
DURABLE_CALL_ROWS=0
```

The 50 agents were then stopped gracefully:

```text
STOPPED=50
LOCAL_ALIVE=0
LOCAL_CONNECTED=0
LOCAL_ERROR_CODES=NONE
```

A 50-way offline health wave had no unexpected successful execution, but the
public error contract split while D1 presence metadata was still inside its
grace window. A second bounded-concurrency readback observed:

```text
DEVICE_OFFLINE=39
CHANNEL_TRANSIENT_OFFLINE=11
UNEXPECTED_SUCCESS=0
```

Both codes are fail-closed, but exposing the internal
`CHANNEL_TRANSIENT_OFFLINE` creates an unnecessary race-dependent public
contract. The source fix maps only the pre-dispatch
`CHANNEL_TRANSIENT_OFFLINE` case to `DEVICE_OFFLINE`. It does not map
`CHANNEL_TRANSIENT_DISCONNECTED`, because disconnect after dispatch remains
execution-ambiguous and must preserve its distinct fail-closed semantics.

```text
FIFTY_DEVICE_STEADY_WAVE=PASS
FIFTY_DEVICE_DURABLE_CALL_ROWS=0
FIFTY_DEVICE_OFFLINE_UNEXPECTED_SUCCESS=0
FIFTY_DEVICE_PROOF_TERMINAL=NO_PENDING_OFFLINE_NORMALIZATION_AND_RECONNECT_RETEST
PROD_CUTOVER=DENY
```
