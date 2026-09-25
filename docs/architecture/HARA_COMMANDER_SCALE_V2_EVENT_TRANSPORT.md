# H.A.R.A. Commander Scale V2 — event-driven device transport

Issue: #163  
Status: **SOURCE/DESIGN FRONT — PROD CUTOVER NOT AUTHORIZED**

## 1. Why this exists

The current Agent 0.3.7 is a correct first-device baseline, but its steady-state
transport is intentionally simple:

```text
heartbeat: POST /api/device/heartbeat every 30 seconds
work poll: POST /api/device/calls/next every 2 seconds
```

At 20,000 online devices, before any real tool execution, this produces:

```text
idle call polling ~= 10,000 req/s
heartbeat         ~=    667 req/s
baseline          ~= 10,667 req/s
baseline/day      ~= 921,600,000 HTTP requests
```

The exact arithmetic is owned by
`apps/commander/scripts/commander_scale_capacity_model.py`.

This is a transport scaling defect, not a reason to reopen pairing, Identity,
quota, receipts or the five-tool contract.

## 2. Invariants that V2 must preserve

```text
HARA_SERVICES_OPERATIONAL_AUTHORITY=true
FIVE_TOOL_SURFACE_EXACT=true
ARBITRARY_SHELL=false
ARBITRARY_FILESYSTEM=false
PAIRING_TOKEN_SHORT_LIVED_ONE_TIME=true
DEVICE_TOKEN_REUSABLE_AFTER_RECONNECT=true
TENANT_DEVICE_BINDING_REQUIRED=true
SELECTED_DEVICE_SEMANTICS_UNCHANGED=true
REVOKED_DEVICE_DENIED=true
RECEIPT_STDOUT_BINDING_UNCHANGED=true
QUOTA_COMMIT_REQUIRES_VALID_TERMINAL_RECEIPT=true
IDEMPOTENT_RETRY_NO_DOUBLE_CHARGE=true
```

Transport permission never becomes execution authorization.

## 3. Target topology

```text
ChatGPT / Codex
      |
      v
mcp.haralabs.com.br
      |
      v
Commander Worker
      |
      +---- D1: durable product/device/call truth
      |
      +---- TenantQuota Durable Object: quota serialization
      |
      +---- DeviceChannel Durable Object shard
                  |
                  | WebSocket Hibernation
                  v
          HARA Commander Agent
                  |
                  v
          exact five-tool executor
```

The Agent keeps an outbound authenticated WebSocket. Idle devices do not perform
periodic `/api/device/calls/next` HTTP polling.

Cloudflare Durable Objects use the Hibernation WebSocket API so the connection
can remain attached while the object is not resident in memory.

## 4. Durable truth vs delivery

D1 remains authoritative durable transport/product state:

- device ownership / tenant / subject;
- selected-device relation;
- revocation state;
- call rows and call terminal state;
- receipts and durable correlation where currently owned.

The DeviceChannel Durable Object is an event-delivery accelerator. It is **not**
a second call database or second authorization authority.

Required law:

```text
D1_CALL_ROW=AUTHORITATIVE
WEBSOCKET_DELIVERY=NON_AUTHORITATIVE
DUPLICATE_DELIVERY=SAFE
CALL_CLAIM=ATOMIC_AND_IDEMPOTENT
TERMINAL_COMPLETION=EXACTLY_ONE_LOGICAL_RESULT
```

If a socket notification is lost, durable call state must remain recoverable.

## 5. DeviceChannel sharding

Do not place all customers into one global Durable Object.

Candidate key:

```text
channel_key = sha256(tenant_id + ":" + device_id) prefix shard
```

The final shard cardinality is measured, not guessed. The implementation must
allow increasing shard count without changing device identity or receipt
semantics.

For the first source canary it is acceptable to use one DO identity per device,
because it is simple and removes cross-device routing ambiguity. Consolidation
into larger shards is a later measured optimization.

## 6. WebSocket authentication

Connection sequence:

1. Agent opens `wss://commander.haralabs.com.br/api/device/channel`.
2. Existing device Bearer token authenticates the HTTP Upgrade request.
3. Worker resolves the exact ACTIVE device and tenant binding.
4. Revoked/unknown/mismatched devices fail closed before the socket is accepted.
5. Worker routes the upgrade to the exact DeviceChannel DO identity.
6. DO accepts with Hibernation API and serializes only non-secret attachment
   metadata required to restore connection identity.
7. Raw device token is never stored as WebSocket attachment or returned in
   messages.

No query-string token is permitted.

## 7. Event envelope

Server -> Agent:

```json
{
  "schema": "hara.commander-device-event.v2",
  "type": "CALL_AVAILABLE",
  "call_id": "opaque-id"
}
```

The notification should contain the minimum routing identifier. The Agent then
claims/reads the authoritative call under the existing device authorization
contract, or the server may push a fully validated call after an atomic claim.
The final choice must preserve current race/revoke guarantees.

Agent -> Server control messages are bounded and typed. No free-form command
message is accepted.

## 8. Presence

V1 presence is based on a 30-second heartbeat and a 90-second online window.

V2 should derive fast connection presence from the event channel while retaining
a lower-frequency durable liveness write so transient socket state is not the
only historical truth.

Target:

- socket connect/disconnect = fast ephemeral presence;
- bounded durable liveness checkpoint = durable dashboard state;
- no 30-second D1 write requirement unless measurements justify it;
- revocation closes or invalidates the active channel.

Exact interval is selected from load/cost tests.

## 9. Failure and reconnect semantics

Agent reconnect uses exponential backoff with jitter and an upper bound.

During EVENT_V2 outage:

- never silently broaden authorization;
- never generate a new pairing token;
- preserve the device token;
- reconnect to the same device identity;
- optional POLL_V1 fallback must be explicit/configured and rate-bounded;
- fallback must not create duplicate logical execution because D1 call claim
  remains authoritative.

```text
EVENT_V2_DOWN != DEVICE_REVOKED
NETWORK_RECONNECT != NEW_PAIRING
DUPLICATE_NOTIFICATION != DUPLICATE_EXECUTION
```

## 10. Migration

Phase A — current campaign:
- keep Agent 0.3.7 POLL_V1 as the E2E baseline;
- complete five-tool/receipt/quota proof.

Phase B — source-only:
- add capacity model;
- add DeviceChannel source + tests;
- add EVENT_V2-capable Agent behind default-off configuration;
- no PROD binding/cutover.

Phase C — canary:
- use one HARA-owned device;
- EVENT_V2 only after V1 baseline is terminal;
- repeat lifecycle + five tools + receipts + quota;
- prove rollback to POLL_V1.

Phase D — scale:
- synthetic 100 / 1k / 5k / 20k connection and dispatch tests in an isolated
  non-PROD environment;
- measure reconnect storms and command latency;
- establish per-shard budgets.

Phase E — PROD:
- only after measured acceptance and reversible migration.

## 11. Capacity acceptance

A 20k claim requires measurements, not architecture prose.

Required evidence:

```text
CONNECTED_DEVICES=20000_SYNTHETIC
IDLE_CALL_HTTP_POLL_RPS=0
CONNECTION_SUCCESS_RATE_MEASURED=true
RECONNECT_STORM_MEASURED=true
P50_P95_P99_DISPATCH_LATENCY_MEASURED=true
D1_READ_WRITE_RATE_MEASURED=true
DO_CPU_DURATION_MEASURED=true
ERROR_429_5XX_RATE_MEASURED=true
FIVE_TOOL_SECURITY_PARITY=PASS
RECEIPT_PARITY=PASS
QUOTA_PARITY=PASS
REVOCATION_PARITY=PASS
```

No load generator may target PROD by default. A PROD load target requires a
separate explicit operator gate.

## 12. Immediate source order

1. capacity model + regression validator;
2. DeviceChannel DO with hibernatable WebSocket and unit tests;
3. Worker upgrade route with existing device-token authentication;
4. enqueue notification hook after durable call creation;
5. Agent EVENT_V2 transport implementation;
6. reconnect/fallback tests;
7. isolated load harness;
8. canary package only after current #65 E2E baseline closes.
