# Commander Event V2 — bounded multi-device DEV lane

Date: 2026-09-26
Owner: #163
Environment: DEV only
Status: SOURCE_READY / LIVE_PROOF_PENDING

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
MULTI_DEVICE_CONCURRENCY_PROOF=PENDING
WINDOWS_RUNTIME_ACCEPTANCE_OWNER=#240
PROD_CUTOVER=DENY
```
