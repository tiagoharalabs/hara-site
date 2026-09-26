# Commander Event V2 — bounded multi-device DEV lane

Date: 2026-09-26
Owner: #163
Environment: DEV only
Status: LIVE_PROOF_PASS_100_DEVICES

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

The lab provisioner is bounded to 2..100 logical devices. Every device receives:

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
MULTI_DEVICE_CONCURRENCY_PROOF=PASS_100_DEVICES
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


## 50-device terminal proof — 2026-09-26

Governance/source:

```text
PREP_PR=#268
PREP_MERGE_SHA=50ee597f722219f7ed222ef0c1da137f14553e2f
HARDENING_PR=#269
HARDENING_MERGE_SHA=074995e80b19b395809599a14ab31331943e09cb
OFFLINE_NORMALIZATION_PR=#270
OFFLINE_NORMALIZATION_MERGE_SHA=d83e633d4ddf38dfb1a363cf60254aeaf893a34f
PROVENANCE_CI=SUCCESS
COMMANDER_SCALE_V2_CI=SUCCESS
```

DEV promotion:

```text
ROLLBACK_VERSION=0fd00030-5f1a-436d-b02e-29a8741b698d
ACTIVE_VERSION=52bb6dda-624b-4453-984b-f94a3e6ebb27
DEV_HEALTH=PASS
PROD_MUTATION=FALSE
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
```

Fresh bounded run:

```text
RUN_ID=md-20260926221942-0bd7ea80
DEVICES=50
DISTINCT_SUBJECTS=50
DISTINCT_DEVICE_IDENTITIES=50
PROVISION=PASS
TOKEN_EXPOSED=FALSE
INITIAL_ALIVE=50
INITIAL_CONNECTED=50
INITIAL_ERROR_CODES=NONE
```

Initial 50-way concurrent wave:

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
DURABLE_CALL_ROWS=0
```

Offline contract discovery before #270:

```text
STOPPED=50
LOCAL_ALIVE=0
LOCAL_CONNECTED=0
UNEXPECTED_SUCCESS=0

BOUNDED_CONCURRENCY_10:
  DEVICE_OFFLINE=39
  CHANNEL_TRANSIENT_OFFLINE=11
```

The internal `CHANNEL_TRANSIENT_OFFLINE` response occurred pre-dispatch while
D1 presence was still inside its grace window. #270 normalized only that
pre-dispatch condition to the product contract `DEVICE_OFFLINE`; ambiguous
post-dispatch `CHANNEL_TRANSIENT_DISCONNECTED` remains distinct.

Post-#270 offline proof with all 50 agents still stopped:

```text
OFFLINE_REQUESTED=50
DEVICE_OFFLINE=50
UNEXPECTED_SUCCESS=0
OTHER_ERROR_CODES=0
OFFLINE_PUBLIC_CONTRACT=PASS
```

Reconnect orchestration:

```text
RECONNECTED_ALIVE=50
RECONNECTED_CONNECTED=50
RECONNECT_ERROR_CODES=NONE
ORCHESTRATION_START_PLUS_SERIAL_STATUS_MS=20938
```

The 20.938s figure is not per-device reconnect latency. It includes serial SSH
start/status orchestration for 50 processes and must not be used as transport
latency.

Post-reconnect 50-way concurrent wave:

```text
REQUESTED_CYCLES=50
COMPLETED_CYCLES=50
FAILED_CYCLES=0
WAVE_WALL_MAX_MS=2625.437
CYCLE_P50_MS=2289.297
CYCLE_P95_MS=2555.064
CYCLE_P99_MS=2599.899
INVOKE_P95_MS=960.717
REPLAY_P95_MS=785.692
PRIVACY_FAILURES=0
SEMANTIC_FAILURES=0
ERROR_CLASSES=NONE
```

Final readback/shutdown:

```text
DEVICE_ROWS_FINAL=50
DURABLE_CALL_ROWS_FINAL=0
MULTIDEVICE_PROCESSES_FINAL=0
MULTIDEVICE_CONNECTED_FINAL=0
EXISTING_CANARY_PROCESS_COUNT_FINAL=1
EXISTING_CANARY_CONNECTED_FINAL=TRUE
EXISTING_CANARY_ERROR_FINAL=NONE
DEV_HEALTH_FINAL=PASS
AUTO_DELETE=ABSENT
```

## Canonical result after 50-device rung

```text
MULTI_DEVICE_CONCURRENCY_PROOF=PASS_50_DEVICES
MULTI_DEVICE_RECONNECT_PROOF=PASS_50_DEVICES
MULTI_DEVICE_OFFLINE_FAIL_CLOSED=PASS_50_DEVICES
MULTI_DEVICE_OFFLINE_PUBLIC_CONTRACT=DEVICE_OFFLINE_50_OF_50
MULTI_DEVICE_DURABLE_CALL_ROWS=0
EXISTING_CANARY_PRESERVED=TRUE

DO_ANALYTICS_LIVE_TOKEN_GATE=PENDING
WINDOWS_RUNTIME_ACCEPTANCE_OWNER=#240
PROD_CUTOVER=DENY
```

This proof is terminal for the bounded 50-device rung. It does not claim a
100-device live proof.


## Next bounded scale rung — 100 devices

The 50-device rung is terminal PASS. The next source bound is raised to 100
while preserving the same privacy, idempotency, quota and PROD-deny contracts.

Because DEV device enrollment is client-rate-limited, provisioning adds bounded
pacing rather than attempting a burst enrollment:

```text
SOURCE_MAX_DEVICES=100
NEXT_LIVE_RUNG=100
D1_FIXTURE_BATCH_SIZE=10
D1_SELECTION_BATCH_SIZE=25
ENROLL_MIN_INTERVAL_SECONDS=1.10
PAIRING_TOKEN_TTL=10_MINUTES
AUTO_DELETE=ABSENT
PROD_CUTOVER=DENY
```

The canonical live proof remains `PASS_50_DEVICES` until a separate
100-device run passes and is published.


## 100-device terminal proof — 2026-09-26

Source/governance:

```text
PREP_PR=#272
PREP_MERGE_SHA=4b3b3ff791bc6ac2f3308dfbbac8f9845be18b2e
SOURCE_MAX_DEVICES=100
D1_FIXTURE_BATCH_SIZE=10
D1_SELECTION_BATCH_SIZE=25
ENROLL_MIN_INTERVAL_SECONDS=1.10
PROVENANCE_CI=SUCCESS
COMMANDER_SCALE_V2_CI=SUCCESS
```

Runtime boundary:

```text
DEV_ACTIVE_VERSION=52bb6dda-624b-4453-984b-f94a3e6ebb27
DEV_ROLLBACK_VERSION=0fd00030-5f1a-436d-b02e-29a8741b698d
DEV_HEALTH=PASS
PROD_MUTATION=FALSE
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
```

Fresh 100-device run:

```text
RUN_ID=md-20260926223256-3f87c64d
DEVICES=100
DISTINCT_SUBJECTS=100
DISTINCT_DEVICE_IDENTITIES=100
PROVISION=PASS
PROVISION_RUNTIME_SECONDS=154.02
TOKEN_EXPOSED=FALSE
INITIAL_ALIVE=100
INITIAL_CONNECTED=100
INITIAL_ERROR_CODES=NONE
```

Initial 100-way concurrent wave:

```text
REQUESTED_CYCLES=100
COMPLETED_CYCLES=100
FAILED_CYCLES=0
WAVE_WALL_MAX_MS=6035.542
CYCLE_P50_MS=3440.541
CYCLE_P95_MS=5037.774
CYCLE_P99_MS=5732.404
INVOKE_P95_MS=2368.857
REPLAY_P95_MS=2007.808
PRIVACY_FAILURES=0
SEMANTIC_FAILURES=0
ERROR_CLASSES=NONE
TOKEN_EXPOSED=FALSE
```

Persistence readback after the initial wave:

```text
DEVICE_ROWS=100
EVENT_V2_ROWS=100
ACTIVE_ROWS=100
DURABLE_CALL_ROWS=0
```

Offline boundary:

```text
GRACEFUL_STOPPED=100
LOCAL_ALIVE_AFTER_STOP=0
LOCAL_CONNECTED_AFTER_STOP=0
LOCAL_ERROR_CODES=NONE

OFFLINE_REQUESTED=100
DEVICE_OFFLINE=100
UNEXPECTED_SUCCESS=0
OTHER_ERROR_CODES=0
OFFLINE_PUBLIC_CONTRACT=PASS
```

Reconnect orchestration:

```text
RECONNECTED_ALIVE=100
RECONNECTED_CONNECTED=100
RECONNECT_ERROR_CODES=NONE
ORCHESTRATION_START_PLUS_SERIAL_STATUS_MS=42070
```

The 42.070s figure is orchestration time across serial SSH start/status work for
100 processes. It is not per-device Event V2 reconnect latency and must not be
reported as transport reconnect latency.

Post-reconnect 100-way concurrent wave:

```text
REQUESTED_CYCLES=100
COMPLETED_CYCLES=100
FAILED_CYCLES=0
WAVE_WALL_MAX_MS=4358.424
CYCLE_P50_MS=2395.942
CYCLE_P95_MS=3214.997
CYCLE_P99_MS=3614.731
INVOKE_P95_MS=1693.426
REPLAY_P95_MS=795.492
PRIVACY_FAILURES=0
SEMANTIC_FAILURES=0
ERROR_CLASSES=NONE
TOKEN_EXPOSED=FALSE
```

Final readback/shutdown:

```text
DEVICE_ROWS_FINAL=100
DURABLE_CALL_ROWS_FINAL=0
MULTIDEVICE_PROCESSES_FINAL=0
MULTIDEVICE_CONNECTED_FINAL=0
EXISTING_CANARY_PROCESS_COUNT_FINAL=1
EXISTING_CANARY_CONNECTED_FINAL=TRUE
EXISTING_CANARY_ERROR_FINAL=NONE
DEV_HEALTH_FINAL=PASS
DEV_ACTIVE_VERSION_FINAL=52bb6dda-624b-4453-984b-f94a3e6ebb27
AUTO_DELETE=ABSENT
```

## Canonical result after 100-device rung

```text
MULTI_DEVICE_CONCURRENCY_PROOF=PASS_100_DEVICES
MULTI_DEVICE_RECONNECT_PROOF=PASS_100_DEVICES
MULTI_DEVICE_OFFLINE_FAIL_CLOSED=PASS_100_DEVICES
MULTI_DEVICE_OFFLINE_PUBLIC_CONTRACT=DEVICE_OFFLINE_100_OF_100
MULTI_DEVICE_DURABLE_CALL_ROWS=0
EXISTING_CANARY_PRESERVED=TRUE

DO_ANALYTICS_LIVE_TOKEN_GATE=PENDING
WINDOWS_RUNTIME_ACCEPTANCE_OWNER=#240
PROD_CUTOVER=DENY
```

This proof closes the bounded 10 -> 50 -> 100 progression requested by the
successor handoff. It does not claim a higher-scale live proof or a cost-final
heavy profile; live Durable Object duration remains gated on the dedicated
Account Analytics Read token.


## Lab lifecycle orchestration optimization

After the terminal 100-device proof, the lab orchestration itself remains a
tooling optimization target. The prior start/status/stop implementation issued
SSH operations serially, which inflated observed orchestration time and must not
be confused with Event V2 transport latency.

The lab lifecycle is now bounded-parallel:

```text
LIFECYCLE_MAX_WORKERS=16
START_PARALLEL=TRUE
STATUS_PARALLEL=TRUE
STOP_PARALLEL=TRUE
ENROLLMENT_PARALLEL=FALSE
ENROLL_MIN_INTERVAL_SECONDS=1.10
RUNTIME_PRODUCT_CHANGE=FALSE
PROD_MUTATION=FALSE
```

Enrollment remains paced and serial because it is governed by DEV rate-limit and
pairing semantics. This change affects only H.A.R.A.-owned scale-lab
orchestration; it does not change customer Event V2 transport/runtime behavior.


## Lifecycle parallelism hardening after #274 live benchmark

A live benchmark of the #274 bounded-parallel lifecycle exposed an orchestration
defect before any customer-call probe was run.

Observed with the existing 100-device manifest:

```text
#274_LIFECYCLE_MAX_WORKERS=16
START_COMMAND_REPORTED=PASS
STATUS_COMMAND=FAIL:MULTIDEVICE_COMMAND_FAILED:ssh
LIVE_PROCESS_CENSUS_AFTER_FAILURE=82
CONNECTED_STATUS_FILES=82
STATUS_ERRORS=0
SINGLE_SSH_AFTER_FAILURE=PASS
EVENT_V2_RUNTIME_DEFECT=FALSE
TOOLING_PARTIAL_START_DEFECT=TRUE
```

The 82 processes were then rolled back locally using only manifest-owned PID
files plus exact Event V2 loop cmdline validation:

```text
ROLLBACK_MATCHED=82
ROLLBACK_STILL_ALIVE=0
ROLLBACK_CMDLINE_MISMATCH=0
MULTIDEVICE_PROCESS_COUNT_FINAL=0
EXISTING_CANARY_PROCESS_COUNT=1
```

Hardening changes:

```text
LIFECYCLE_MAX_WORKERS=4
START_IDEMPOTENT_FOR_MANIFEST_OWNED_ACTIVE_PROCESS=TRUE
STOP_IDEMPOTENT_FOR_MISSING_OR_DEAD_PROCESS=TRUE
START_FAILURE_ROLLBACK=SERIAL_MAX_WORKERS_1
START_FAILURE_RESIDUAL_PROCESS_POLICY=ZERO
AUTO_DELETE=ABSENT
PROD_MUTATION=FALSE
```

The lower bound intentionally prefers deterministic SSH behavior over maximum
lab orchestration throughput. This changes H.A.R.A.-owned test tooling only and
does not change the Event V2 customer transport/runtime contract.


## Post-#276 live lifecycle validation

The hardening in #276 was validated live with the existing 100-device manifest.

Initial post-merge start/status:

```text
SOURCE_MERGE=#276
SOURCE_MERGE_SHA=ffce36e0963bfdacb70e641c951fea03e7dd5afd
LIFECYCLE_MAX_WORKERS=4

STARTED=100
FIRST_STATUS_ALIVE=100
FIRST_STATUS_CONNECTED=99
FIRST_STATUS_ERROR_CODES=NONE
SSH_PARTIAL_START_FAILURE=ABSENT
```

The first status snapshot occurred while one agent was still completing its
Event V2 handshake. A follow-up readiness snapshot after a short bounded delay
closed at:

```text
ALIVE=100
CONNECTED=100
ERROR_CODES=NONE
STATUS_ORCHESTRATION_MS=5595
```

Bounded stop:

```text
STOPPED=100
STOP_ORCHESTRATION_MS=8042
FINAL_ALIVE=0
FINAL_CONNECTED=0
FINAL_ERROR_CODES=NONE
MULTIDEVICE100_PROCESS_COUNT_FINAL=0
```

Existing canonical canary:

```text
ORIGINAL_CANARY_PROCESS_COUNT=1
ORIGINAL_CANARY_CONNECTED=TRUE
ORIGINAL_CANARY_ERROR=NONE
```

Result:

```text
LIFECYCLE_PARTIAL_START_DEFECT=FIXED
SSH_FANOUT_FAILURE_REPRODUCED_AFTER_FIX=FALSE
START_FAILURE_ROLLBACK_GUARD=ENABLED
100_DEVICE_LIFECYCLE_RETEST=PASS
PROD_MUTATION=FALSE
```

This validation concerns scale-lab orchestration only. It does not replace or
change the terminal Event V2 customer transport proof at 100 devices.
