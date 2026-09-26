# Commander Event V2 transient RPC — live DEV proof

Date: 2026-09-26  
Owner: #163  
Environment: DEV only  
HARA-owned canary device: `nucleo-a-event-v2-dev`

## Deployment census

```text
SOURCE_MAIN=9fea10e0c802143d7549edf06a1c80a7092647a0
SOURCE_VERSION=7dc20bd4-627c-43fc-bab6-7f1d64ca84c0
ACTIVE_VERSION=c5e1b681-959f-4b52-98bd-60aa5a8a65e9
ACTIVE_VERSION_SOURCE=SECRET_CHANGE
DEVICE_EVENT_V2_ENABLED=true
DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED=true
PROD_MUTATION=FALSE
```

The active Secret Change version preserves the same DEV bindings/flags as the
source-alignment version.

## Live result

```text
COMMANDER_EVENT_V2_TRANSIENT_LIVE=PASS
COMMANDER_EVENT_V2_TRANSIENT_HEALTH=PASS
COMMANDER_EVENT_V2_TRANSIENT_INVOKE=PASS
COMMANDER_EVENT_V2_TRANSIENT_QUOTA_COMMIT=COMMITTED
COMMANDER_EVENT_V2_TRANSIENT_REPLAY_MODE=REPLAY_ONLY
COMMANDER_EVENT_V2_TRANSIENT_REPLAY_OUTCOME=REPLAYED
COMMANDER_EVENT_V2_TRANSIENT_PAYLOAD_PERSISTED=FALSE
COMMANDER_EVENT_V2_TRANSIENT_RESULT_PERSISTED=FALSE
COMMANDER_EVENT_V2_TRANSIENT_LEARNING_CONTENT=FALSE
COMMANDER_EVENT_V2_TRANSIENT_TOKEN_EXPOSED=FALSE
```

The selected device returned by the Worker matched the expected HARA-owned
canary device. The first invoke executed and committed quota. Repeating the same
logical request returned `REPLAY_ONLY / REPLAYED`, proving that a committed
request is served from the customer-local idempotency ledger rather than being
executed again.

## Durable-cloud content readback

The live transient invoke request id was checked directly against DEV D1:

```text
FINAL_PROBE_REQUEST_ID=TRANSIENT-INVOKE-34de9f03714b440797426a4f55404799
SELECT COUNT(*) FROM commander_device_calls WHERE request_id=FINAL_PROBE_REQUEST_ID
rows_found=0
rows_written=0
```

Therefore the transient path created no durable `commander_device_calls`
payload/result row for this live execution.

## Customer-local replay ledger

On `nucleo-a`, the exact request's ledger entry read back as:

```text
LEDGER_EXISTS=TRUE
LEDGER_MODE=600
LEDGER_SCHEMA=hara.commander-transient-ledger.v1
LEDGER_STATE=COMPLETED
LEDGER_HAS_RAW_PAYLOAD=FALSE
LEDGER_HAS_PAYLOAD_SHA256=TRUE
LEDGER_HAS_RESULT=TRUE
LEDGER_REQUEST_MATCH=TRUE
```

The replay result is intentionally customer-local because retry semantics require
the Agent to answer a lost-response replay without re-execution. The H.A.R.A.
cloud learning plane still receives only the whitelisted derived signal.

## Boundary

```text
MANAGED_RELAY_CONTENT_IN_TRANSIT=TRUE
HARA_DURABLE_CUSTOMER_CONTENT=FALSE_ON_TRANSIENT_PATH
LEARNING_CUSTOMER_CONTENT=FALSE
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
PROD_CUTOVER=DENY
WINDOWS_RUNTIME_PARITY=NOT_CLAIMED
```

## Next gate

The architecture is now live-proven for one HARA-owned Linux canary. The next
#163 gate is a bounded live measurement campaign, not another architecture
rewrite:

1. 10 sequential transient calls;
2. 10-call replay/idempotency sample;
3. 100-call bounded series;
4. Worker/DO/D1 latency and row-cost census;
5. reconnect/offline grace sample;
6. only then synthetic 1k modeling/readiness evidence.
