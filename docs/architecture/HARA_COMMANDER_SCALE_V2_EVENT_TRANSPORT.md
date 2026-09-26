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

Customer transport separation is also mandatory:

```text
CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=false
CUSTOMER_AGENT_CHANNEL=OUTBOUND_TO_CLOUDFLARE_EVENT_V2
HARA_SERVICES_CUSTOMER_PROXY=false
HARA_SERVICES_ROLE_FOR_CUSTOMER_PLANE=NOC_CONTROL_ONLY
INTERNAL_HARA_MCP_MONITORING=ALLOWED
CUSTOMER_CONTENT_MONITORING=false
```

The HARA-owned internal MCP path may continue to traverse HARA Services and may be deeply monitored under operator governance. This exception does not extend to customer traffic.

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

## 8. Presence and low-cost heartbeat

V1 presence is based on a 30-second HTTP heartbeat and a 90-second online window.

V2 removes that steady-state cost pattern.

Target policy:

```text
HTTP_HEARTBEAT_30S=FALSE
IDLE_HTTP_POLLING=FALSE
SOCKET_PRESENCE=PRIMARY_EPHEMERAL_SIGNAL
APPLICATION_JSON_PING_STEADY_STATE=FALSE
WEBSOCKET_PROTOCOL_PING_IDLE_TARGET=60s
DURABLE_LIVENESS_CHECKPOINT_TARGET=6h
D1_WRITE_ON_MEANINGFUL_STATE_CHANGE=TRUE
```

Rules:

- socket connect/disconnect = fast ephemeral presence;
- protocol-level WebSocket ping is only a transport keepalive after an idle
  interval, not a product heartbeat;
- normal traffic resets the keepalive timer;
- incoming WebSocket protocol ping frames are handled by the Cloudflare runtime
  without waking the Durable Object;
- application-level JSON `PING/PONG` is denied on the customer channel; protocol
  control frames are the only idle keepalive;
- D1 is updated immediately for meaningful durable transitions such as connect,
  revoke, supersession, version change or terminal lifecycle events;
- a very low-frequency durable liveness checkpoint may be emitted at most once
  per target interval when no other durable event has refreshed state;
- the initial durable checkpoint target is **6 hours**, then measured and tuned;
- dashboard live presence should prefer DeviceChannel socket state. Historical
  D1 state must be labeled stale/last-known rather than pretending it is live.

For 1,000 continuously connected devices, a 6-hour durable checkpoint is only
about 4,000 checkpoint opportunities/day before coalescing with real state
changes, instead of 2.88 million 30-second heartbeats/day.

Exact production values remain canary-measured, but any change that materially
increases idle writes requires cost evidence.

## 9. Failure and reconnect semantics

Agent reconnect uses exponential backoff with full jitter and an upper bound.

Source target:

```text
RECONNECT_INITIAL_MAX=10s
RECONNECT_EXPONENTIAL=true
RECONNECT_FULL_JITTER=true
RECONNECT_MAX=15s
SYNCHRONIZED_RECONNECT=DENY
POLL_V1_FALLBACK_DEFAULT=OFF
```

If an explicit temporary polling fallback is ever enabled, it must start slow,
back off, jitter, and remain bounded. The old fixed 2-second idle loop is not a
valid fallback.

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

## 10.1 Active-call query locality for the first 1k target

The Event V2 idle path is intentionally near-zero, so the next scale pressure is
the D1 work performed by real calls. The active queue, stale-call cleanup and
device claim paths must remain local to the selected device.

The schema already owns:

```text
idx_device_calls_poll(device_id, state, created_at_utc)
```

The Worker explicitly uses that existing index for active-call hot paths instead
of allowing SQLite to prefer the global state-plus-expiry index. This keeps
PENDING/EXECUTING scans bounded to one device/state set and does not add a new
index or new index-write amplification.

```text
ACTIVE_CALL_QUERY_SCOPE=DEVICE_STATE
ACTIVE_CALL_INDEX=idx_device_calls_poll
NEW_INDEX_FOR_1K_HOT_PATH=FALSE
D1_MIGRATION_REQUIRED=FALSE
```

This is a source/query-plan optimization only. D1 remains durable truth and all
queue, expiry, tenant, subject and revocation predicates remain unchanged.

## 10.2 Active-workload budget for the first 1k target

The canonical 30-call DEV run with the 500ms settle returned 26/30 terminal
results directly from enqueue and required only 4 status polls total. The
active-load budget preserves that measured status-poll ratio as a regression
baseline, not as an SLA.

The deterministic model lives at:

```text
apps/commander/scripts/commander_event_v2_active_1k_model.py
```

It reports 1, 10 and 100 calls/device/day for 1,000 devices and separates:

- enqueue/status/claim/complete HTTP request shape;
- isolated-call versus packed-8 drain behavior;
- per-call DeviceChannel notify request equivalents;
- six-hour liveness request equivalents;
- comparison against the old V1 idle HTTP baseline.

D1 rows read/written are intentionally not guessed from statement counts. That
dimension remains MEASURE_LIVE using D1 query metadata before any higher-scale
claim.

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


## 13. Customer privacy and NOC observability

The customer data plane and HARA NOC plane are deliberately separate.

```text
CUSTOMER
ChatGPT/Codex
  -> Commander edge
  -> D1 / TenantQuota / DeviceChannel
  -> outbound Agent channel
  -> customer machine

NOC
Cloudflare native aggregate metrics
  + Storage Identity metrics
  + bounded metadata-only Commander metrics
  -> HARA Services
  -> alerts / capacity / cost / reliability
```

HARA Services consumes aggregate or pseudonymous operational facts. It does not
sit inline with the customer command stream.

Allowed customer operational telemetry:

- active/connected device counts;
- connection duration;
- reconnect/fallback counters;
- send-to-ack latency distributions;
- success/failure/timeout classes;
- Worker/D1/DO request and resource counters;
- bytes/messages counters;
- agent version/state;
- quota/cost aggregates.

Routine customer telemetry must not contain:

- prompt/conversation text;
- command payloads or command results;
- customer file contents;
- arbitrary filesystem contents;
- Authorization/Cookie headers;
- OAuth, session, pairing or device secrets.

```text
CUSTOMER_CONTENT_PRIVATE_BY_DEFAULT=true
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=false
CUSTOMER_TRAFFIC_INSPECTION_DEFAULT=false
NOC_METADATA_ONLY=true
```

This privacy boundary does not restrict deep monitoring of HARA-owned internal
MCP/OpenAI engineering traffic.


## 14. Reconnect-storm capacity guard

The first Event V2 reconnect window is intentionally wider than the original
1-second target.

```text
RECONNECT_BASE_SECONDS=10
RECONNECT_MAX_SECONDS=15
RECONNECT_FULL_JITTER=true
```

Reason: a fleet-wide network or edge interruption can disconnect every Agent at
nearly the same instant. Full jitter over a 1-second first window still permits
nearly the entire fleet to reconnect in one second. The 10-second first window
reduces that synchronized pressure while keeping reconnect latency comfortably
below the 50-second device-call TTL.

The deterministic CI model
`apps/commander/scripts/commander_event_v2_reconnect_storm_model.py`
uses the real client policy and a stable entropy stream.

Current modeled first-wave maxima:

```text
1,000 devices  -> <= 117 reconnect attempts in the busiest 1s bucket
20,000 devices -> <= 2,052 reconnect attempts in the busiest 1s bucket
```

The 20k result is architecture headroom only. It does not by itself prove that
a single D1 product database can absorb every reconnect presence write. D1 write
pressure remains a separate guard because a single D1 database is serialized.


## 15. Transient disconnect coalescing

Event V2 disconnects are not written to D1 immediately.

The DeviceChannel schedules a per-device Durable Object alarm with a deterministic
30–60 second grace window:

```text
OFFLINE_GRACE_BASE=30s
OFFLINE_GRACE_JITTER=0..30s
SHORT_BLIP_OFFLINE_WRITE=0
RECONNECT_WITHIN_GRACE_CANCELS_OFFLINE=true
```

On reconnect, the pending offline alarm is cancelled. If D1 already says
`EVENT_V2` and its durable presence is still fresh, the reconnect does not
rewrite `last_seen_at_utc`.

This turns a short fleet-wide network blip from:

```text
disconnect -> D1 OFFLINE write
reconnect  -> D1 ONLINE write
```

into:

```text
disconnect -> DO-local pending alarm
reconnect  -> alarm cancelled
D1 writes  -> zero
```

For a prolonged outage, offline writes are still required, but are distributed
across the grace window. The deterministic source model currently yields:

```text
1,000 devices  -> <= 39 OFFLINE writes in the busiest 1s bucket
20,000 devices -> <= 722 OFFLINE writes in the busiest 1s bucket
```

The 1k result is the practical product target. The 20k result remains architecture
headroom and still carries a D1 pressure warning rather than a scale-ready claim.


## 10.3 Managed relay transient data plane — first-1k successor

The durable D1 call lane remains the proven fallback while this successor is
source/DEV-only. The target managed-relay architecture separates three planes:

```text
CONTROL PLANE
  identity | entitlement | quota | device | presence | billing metadata

TRANSIENT DATA PLANE
  validated tool request -> DeviceChannel -> Agent -> tool result
  request/result are transported in memory and are not durable D1 content

LEARNING PLANE
  Agent-derived, whitelisted operational signal only
  no arguments, paths, prompts, stdout, file content or raw result
```

Canonical privacy/cost contract:

```text
TRANSIENT_RPC_ENV=DEV_ONLY
MANAGED_RELAY_CONTENT_IN_TRANSIT=TRUE
D1_CUSTOMER_PAYLOAD_PERSISTENCE=FALSE
D1_CUSTOMER_RESULT_PERSISTENCE=FALSE
LEARNING_SIGNAL_DERIVED_METADATA_ONLY=TRUE
LEARNING_SIGNAL_CUSTOMER_CONTENT=FALSE
PUBLIC_AGENT_0_3_7_MUTATION=FALSE
PROD_CUTOVER=DENY
```

MANAGED_RELAY_CONTENT_IN_TRANSIT=TRUE is intentional and explicit: a standard
hosted MCP relay must process the request/result while forwarding it. The
privacy guarantee at this stage is no durable customer-content collection by
H.A.R.A., not a false claim that the managed relay is cryptographically unable
to see plaintext in memory.

The DEV source path is:

```text
internal MCP dispatch
      -> Worker authorization / selected-device validation
      -> DeviceChannel /dispatch
      -> CALL_TRANSIENT over the existing hibernatable WebSocket
      -> Agent local allowlisted executor
      -> CALL_RESULT over the same WebSocket
      -> Worker response

commander_device_calls payload_json/result_json
      -> NOT USED by this path
```

While a transient call is active, the per-device Durable Object request remains
in flight and therefore is not hibernatable. Once the call completes, the
existing Hibernation WebSocket design becomes eligible for idle hibernation
again. The source path is bounded to one transient call in flight per device and
45 seconds per dispatch until live evidence justifies another value.

Promotion is denied until all of these are proven:

```text
LOCAL_IDEMPOTENCY_LEDGER_LINUX=PASS
WINDOWS_LOCAL_IDEMPOTENCY_LEDGER=PASS
RETRY_AFTER_LOST_RESPONSE=PASS
WINDOWS_TRANSIENT_RPC_PARITY=PASS
QUOTA_RESERVE_COMMIT_RELEASE_PARITY=PASS
RECEIPT_PARITY=PASS
CANCELLATION_AND_TIMEOUT_PARITY=PASS
DEV_LIVE_ROW_COST=MEASURED
DEV_LIVE_DO_DURATION=MEASURED
1K_SYNTHETIC=PASS
CUSTOMER_CONTENT_LOGGING=ABSENT
ROLLBACK_TO_DURABLE_LANE=PASS
```

The deterministic economics envelope lives at:

```text
apps/commander/scripts/commander_event_v2_transient_1k_model.py
```

It does not claim measured production latency. It models 0.5s / 2s / 10s
average active-call durations so Durable Object wall-time cost is visible before
cutover.


## 10.4 Transient quota/idempotency orchestration

The DEV transient path must not become a quota bypass just because it removes
durable call-content rows. `hara.functions.invoke` therefore owns its quota
transition inside the transient dispatch orchestration.

Source contract:

```text
NEW_OR_EXISTING_RESERVED
  -> execution_mode=EXECUTE_OR_REPLAY
  -> dispatch
  -> COMPLETED + valid receipt -> COMMIT
  -> FAILED -> RELEASE

EXISTING_COMMITTED
  -> execution_mode=REPLAY_ONLY
  -> Agent may return only a customer-local ledger replay
  -> missing local replay -> TRANSIENT_REPLAY_MISS
  -> never re-execute a previously committed request_id

EXISTING_RELEASED
  -> REQUEST_USAGE_TERMINAL
  -> no dispatch

OFFLINE_OR_BUSY_BEFORE_SEND
  -> RELEASE reservation
  -> caller must use a new logical request_id

TIMEOUT_OR_DISCONNECT_AFTER_DISPATCH
  -> KEEP_RESERVED
  -> execution outcome is ambiguous
  -> retry with the same request_id reconciles against the local ledger
```

This deliberately prefers a temporarily held quota reservation over a
double-execution or a free execution when the network outcome is ambiguous.
The existing quota TTL releases stale reservations after the bounded recovery
window.

The transient protocol therefore carries a server-selected execution mode:

```text
EXECUTE_OR_REPLAY
REPLAY_ONLY
```

The Agent never derives this mode from customer payload. Linux and Windows
source both fail closed on any other value.

The deterministic first-1k model assumes the conservative case where every
logical call is `hara.functions.invoke`. At 1,000 devices and 10 calls per
device per day:

```text
LOGICAL_CALLS_DAY=10000
WORKER_HTTP_DAY=10000
TENANT_QUOTA_RPC_DAY=20000
DEVICE_CHANNEL_PLUS_WS_AND_QUOTA_DO_REQUEST_EQ_DAY=30700
D1_CALL_TABLE_PAYLOAD_WRITES_PER_CALL=0
D1_CALL_TABLE_RESULT_WRITES_PER_CALL=0
```

Cloudflare currently bills each Durable Object RPC method call as one request;
incoming WebSocket messages use the 20:1 billing ratio. TenantQuota execution
duration/SQLite row cost remains a live-measurement item rather than being
invented in the deterministic transport model.

Promotion remains blocked on live DEV quota reconciliation, lost-response
replay, receipt parity, Windows runtime proof and the 1k synthetic campaign.
