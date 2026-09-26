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

The lab provisioner is bounded to 2..10 logical devices. Every device receives:

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
