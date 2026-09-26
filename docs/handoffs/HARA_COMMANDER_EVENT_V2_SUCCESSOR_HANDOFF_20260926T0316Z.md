# H.A.R.A. Commander Event V2 — Successor Handoff

**Timestamp:** 2026-09-26T03:16Z  
**Repository:** `tiagoharalabs/hara-site`  
**Primary owner:** #163 — Commander Scale V2 / Event-driven device transport  
**Successor entrypoint:** this document  
**Related owners:** #167 human/session cost only; hara-platform#851 product acceptance; hara-platform#1000 stable Agent capability; hara-platform#1486 customer MCP auth/cost; hara-platform#1533 Commander NOC contract  
**PROD cutover:** **DENY**

---

## 1. Executive state

The Linux Event V2 path is no longer speculative.

```text
V1_PROD_HOMOLOGATION=PASS
STABLE_PUBLIC_AGENT=0.3.7
DEV_EVENT_V2_CANARY=PASS
FIVE_TOOL_PARITY=PASS
RECEIPT_PARITY=PASS
QUOTA_PARITY=PASS
OFFLINE_ONLINE_PARITY=PASS
NORMAL_DO_WAKE=PASS
LINUX_RC_INSTALL_ROLLBACK_SOURCE=READY
LINUX_RC_ROLLBACK_LIVE=PASS
LINUX_RC_POSITIVE_DEV_CONNECTION=PASS
LINUX_RC_CLEAN_SHUTDOWN=PASS
PRACTICAL_1K_PATH=HARDENED

WINDOWS_EVENT_V2_TRANSPORT_SOURCE=READY_UNPROVEN
WINDOWS_EVENT_V2_AGENT_ADAPTER_IMPLEMENTED=TRUE
WINDOWS_RC_INSTALL_ROLLBACK_SOURCE=READY
WINDOWS_EVENT_V2_RUNTIME_PROVEN=FALSE
WINDOWS_FIVE_TOOL_LIVE_PARITY=FALSE
WINDOWS_ROLLBACK_LIVE_PROOF=FALSE
CROSS_PLATFORM_EVENT_V2_PARITY=FALSE

SYNTHETIC_20K_IDLE_MODEL=PASS
SYNTHETIC_20K_RECONNECT_MODEL=PASS_WITH_D1_PRESSURE_WARNING
20K_SCALE_READY=FALSE

PROD_CUTOVER=DENY
```

The next front should **not** reopen Linux architecture work first. The current source/runtime gap is a **real Windows Event V2 RC canary**.

---

## 2. Canonical product architecture

### Customer path

```text
ChatGPT / Codex
  -> Commander / Cloudflare edge
  -> D1 durable product truth
  -> TenantQuota Durable Object
  -> per-device DeviceChannel Durable Object
  -> outbound Event V2 WebSocket
  -> HARA Agent
  -> customer machine
```

### Internal H.A.R.A. path

```text
OpenAI / HARA operator clients
  -> HARA-owned MCP
  -> Cloudflare Tunnel
  -> HARA Services
  -> governed H.A.R.A. internal functions
```

These paths are intentionally different.

```text
CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=FALSE
HARA_SERVICES_CUSTOMER_PROXY=FALSE
INTERNAL_HARA_MCP_THROUGH_SERVICES=ALLOWED
CUSTOMER_CONTENT_COLLECTION=FALSE
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE
CUSTOMER_OPERATIONAL_METADATA_ONLY=TRUE
SERVICES_NOC_AGGREGATION=TRUE
```

Do not reintroduce Services into the normal customer command data path.

---

## 3. Event V2 economic laws already canonical

The Event V2 target removes steady-state V1 cost:

```text
IDLE_HTTP_POLLING_2S=FALSE
HTTP_HEARTBEAT_30S=FALSE
SOCKET_PRESENCE=PRIMARY
PROTOCOL_PING_IDLE=60s
APPLICATION_JSON_HEARTBEAT_IDLE=FALSE
DURABLE_LIVENESS_TARGET=6h
D1_WRITE_ON_MEANINGFUL_STATE_CHANGE=TRUE
D1_DURABLE_CALL_TRUTH=TRUE
```

Reconnect/current policy:

```text
FULL_JITTER=TRUE
INITIAL_WINDOW=10s
MAX=15s
OFFLINE_GRACE=deterministic 30..60s/device
FIXED_2S_FALLBACK=DENY
```

Measured transient-blip proof showed a reconnect inside the offline grace generated **zero OFFLINE/ONLINE D1 writes**.

Modeled reconnect pressure:

```text
1K_FIRST_WAVE_MAX_1S_BUCKET=117 attempts
1K_PROLONGED_OUTAGE_OFFLINE_WRITE_MAX_1S_BUCKET=39 writes/s

20K_FIRST_WAVE_MAX_1S_BUCKET=2052 attempts
20K_PROLONGED_OUTAGE_OFFLINE_WRITE_MAX_1S_BUCKET=722 writes/s
```

Interpretation:
- practical 100 -> 1,000 path is hardened;
- 20k has modeled headroom but still carries a D1 serialized-write pressure warning;
- do not claim 20k scale-ready.

---

## 4. Core Event V2 PR ledger

### Architecture / transport

- PR #188 — `31bb86afbef5bd7c7238001913b6e0f430467f97`  
  Private low-cost Event V2 architecture, DeviceChannel, hibernation, keepalive, reconciliation, privacy/NOC laws.

### DEV canary enablement

- PR #198 — `92a65aa82849a8f30a2392cd97b3b0f217edef40`  
  Secret-safe DEV canary provisioner.
- PR #202 — `62dd2070f903c6feb5f34f4c25e5176847164b23`  
  D1 migration 0011; transport enum = `OUTBOUND_RELAY|EVENT_V2|EVENT_V2_OFFLINE`.
- PR #203 — `ede9b9d070122464e43c34952dc0e6fc445130e1`  
  Pairing SHA-256 representation aligned to Worker base64url format.
- PR #205 — `7061b95b76282b9573a3e14cf7196d3f699d00ee`  
  Secret-safe DEV wake probe.
- PR #206 — `3b193f4479850eaa6dddc7b4a5756098ee7c4e30`  
  Isolated secondary DEV canary MCP token; PROD binding absent.
- PR #209 — `fa71717d8480eb577a99079de6f6e66faa564a5c`  
  Terminal functional canary + quota parity + reconnect hardening.

### Hot path / backpressure

- PR #215 — `68b8d9942fcec409cc6606459889a1f4d443ee47`  
  Adaptive status retry + per-device queue backpressure.
- PR #224 — `deac4aba130e3b9f457b643702aeed83d1723027`  
  Temporary 300ms settle experiment.
- PR #225 — `00abec73d359bd693f47e05cb85764d34f111395`  
  Reverted to proven 500ms settle after negative live A/B.
- PR #226 — `e266382391707a5bab5891d4032cd1213c5e921e`  
  Removed duplicate selected-device D1 state read.
- PR #227 — `cbfd273f04b330b37f1170fe8ec55fb6bb218c38`  
  Clean Event V2 top-level shutdown; no traceback.

### Linux RC productization

- PR #220 — `7f429896de8606c7b1faaab128e7edd3bb25c029`  
  Linux Event V2 RC install + rollback source.
- PR #221 — `38c119d6cc4119c016b6875db5766622dfb31f81`  
  Requires real Event V2 connection attestation before activation.
- PR #223 — `e078200a5ff1943828b3fbddb172914fa3dd2739`  
  Clears connected status correctly on SIGTERM.
- PR #227 — `cbfd273f04b330b37f1170fe8ec55fb6bb218c38`  
  Final clean-shutdown UX fix.

### Windows RC source

- PR #229 — `e9b9368657954c37a2292fb68e2c206ab553a03b`  
  Fail-closed Windows Event V2 RC contract + source-only ClientWebSocket boundary.
- PR #231 — `d70170489a57a9664a873188e1789cff91aef9b4`  
  Windows Event V2 agent adapter.
- PR #233 — `b8137122d73de6f7c76435f98b9711b6c6ef061b`  
  Reversible Windows RC installer/activation/rollback source.

Public Linux/Windows Agent **0.3.7 remains unchanged**.

---

## 5. DEV canary terminal evidence

HARA-owned Linux canary: `nucleo-a`.

Functional result:

```text
EVENT_V2_CONNECT=PASS
EVENT_V2_DISCONNECT=PASS
NORMAL_DO_WAKE=PASS
NORMAL_DO_WAKE_LATENCY_MS≈2212
FIVE_TOOL_PARITY=PASS
RECEIPT_PARITY=PASS
QUOTA_PARITY=PASS
QUOTA_RELEASE_REPLAY=TERMINAL
QUOTA_COMMIT=COMMITTED
QUOTA_COMMIT_IDEMPOTENT=TRUE
QUOTA_DOUBLE_CHARGE=FALSE
OFFLINE_ONLINE_PARITY=PASS
CUSTOMER_AUTHORITY=HARA_COMMANDER
CUSTOMER_SERVICES_PROXY=FALSE
TOKEN_EXPOSED=FALSE
```

Five-tool surface proven:

- `hara.health`
- `hara.functions.list`
- `hara.functions.describe`
- `hara.functions.invoke`
- `hara.receipts.get`

Receipt proof retained:

```text
transport_mode=EVENT_V2
operational_authority=HARA_COMMANDER
result_binding=STDOUT_SHA256_V1
```

---

## 6. Measured latency / backpressure evidence

Canonical live 30-call baseline with **500ms terminal settle**:

```text
SAMPLES=30
LATENCY_P50_MS=1692
LATENCY_P95_MS=2352
LATENCY_P99_MS=2410
ENQUEUE_P50_MS=1686
STATUS_POLLS_TOTAL=4
TERMINAL_FROM_ENQUEUE=26/30
```

The 300ms experiment was worse:

```text
LATENCY_P50_MS=2139
LATENCY_P95_MS=2252
LATENCY_P99_MS=2324
ENQUEUE_P50_MS=1480
STATUS_POLLS_TOTAL=30
TERMINAL_FROM_ENQUEUE=0/30
```

Therefore:

```text
EVENT_V2_SETTLE_300MS=REJECTED_BY_LIVE_A_B
CANONICAL_SETTLE=500ms
```

**DO NOT REINTRODUCE 300ms** without fresh measured evidence.

Same-device burst:

```text
10 concurrent:
COMPLETED=10
FAILED=0
SERIAL_EXECUTION_PRESERVED=TRUE

20 concurrent:
ACTIVE_QUEUE_LIMIT=16
COMPLETED=16
DEVICE_BUSY=4
EXPIRED=0
STUCK=0
DEVICE_BUSY_HTTP=429
DEVICE_BUSY_RETRY_AFTER_MS=1000
```

Do not parallelize local command execution at this stage.

PR #226 removed a duplicate D1 state read, but its exact post-change latency A/B was not safely measurable in the prior execution environment. **Do not claim a measured latency gain for #226 until remeasured.**

---

## 7. Linux RC live status

Linux RC is the proven leading implementation.

Live `nucleo-a` evidence:

```text
RC_INSTALL=PASS
RC_DEFAULT_TRANSPORT=POLL_V1
RC_AUTO_START=FALSE
STABLE_0_3_7=ACTIVE
RC_SERVICE=INACTIVE_AFTER_ROLLBACK
DEVICE_ENV_MODE=0600
```

Negative activation against current PROD, where Event V2 is intentionally unavailable:

```text
RC_EVENT_V2_CONNECTION_ATTESTATION_FAILED_ROLLED_BACK
COMMANDER_AGENT_RC_ROLLBACK=PASS
POST_STABLE=active
POST_RC=inactive
DEVICE_ENV_SHA_BEFORE=DEVICE_ENV_SHA_AFTER
RC_ENV=HARA_DEVICE_TRANSPORT_MODE=POLL_V1
```

Positive isolated DEV proof:

```text
TRANSPORT_MODE=EVENT_V2
CONNECTED=TRUE
STATUS_MODE=0600
STABLE_PROD_0_3_7=ACTIVE
```

Clean shutdown after PR #227:

```text
SOCKET_CLOSE_ON_SHUTDOWN=PASS
CONNECTED_FALSE_ON_SHUTDOWN=PASS
TOPLEVEL_TRACEBACK=ABSENT
EVENT_ERROR=None
STABLE_0_3_7=ACTIVE
```

---

## 8. Windows RC current boundary

Source is prepared, runtime is **not** proven.

```text
WINDOWS_PUBLIC_AGENT_0_3_7=POLL_V1_UNCHANGED
WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1
WINDOWS_EVENT_V2_TRANSPORT_SOURCE=READY_UNPROVEN
WINDOWS_EVENT_V2_AGENT_ADAPTER_IMPLEMENTED=TRUE
WINDOWS_RC_INSTALL_ROLLBACK_SOURCE=READY
WINDOWS_RC_AUTO_START=FALSE
WINDOWS_RC_REUSES_EXISTING_IDENTITY=TRUE
WINDOWS_RC_REENROLLMENT=FALSE
WINDOWS_RC_DUAL_AGENT=DENY

WINDOWS_EVENT_V2_RUNTIME_PROVEN=FALSE
WINDOWS_EVENT_V2_FIVE_TOOL_LIVE_PARITY=FALSE
WINDOWS_ROLLBACK_LIVE_PROOF=FALSE
CROSS_PLATFORM_EVENT_V2_PARITY=FALSE
```

Windows source laws:

- .NET `ClientWebSocket`;
- WSS-only;
- bearer only during upgrade;
- 60s keepalive target;
- max event payload 4096 bytes;
- non-text / fragmented / content-bearing wake denied;
- D1 remains durable authority;
- `CALL_AVAILABLE` is wake-only;
- drain bound = 8;
- full jitter reconnect;
- idle 2s poll absent;
- 30s HTTP heartbeat absent;
- arbitrary tool denied;
- stable public installer/manifest unchanged.

---

## 9. Fresh live currentness at handoff

Fresh readback performed immediately before this handoff:

```text
MAIN_HEAD=29faae4845a9ec2a53aa5c46b17fb9bbcf61439c
DEV_WORKER_VERSION=7b0592d9-386f-4902-8f24-434253a80648
DEV_DEPLOYMENT_CREATED=2026-09-26T02:26:52.541272Z
DEV_D1_PENDING_MIGRATIONS=0

NUCLEO_A_STABLE_AGENT=active
NUCLEO_A_RC_SERVICE=inactive
NUCLEO_A_EVENT_V2_CANARY_PROCESS=none
```

Do not replay migrations 0010/0011.

---

## 10. NOC / privacy sibling state

HARA Platform NOC sources are separate from #163 transport implementation.

Canonical sibling work:

- hara-platform PR #1534 — `8e5c3a690ba53ab737b8996296ecabac7d243f8f`  
  Commander aggregate telemetry contract.
- hara-platform PR #1554 — `bcb647c8864c61476971244e980cfd5bcce2e4d0`  
  Credential-free public Commander health/latency probe source.

NOC law:

```text
SERVICES_NOC_AGGREGATION=TRUE
SERVICES_CUSTOMER_PROXY=FALSE
CUSTOMER_CONTENT_COLLECTION=FALSE
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE
PROMETHEUS_HIGH_CARDINALITY_IDS=DENY
NATIVE_CLOUDFLARE_METRICS_FIRST=TRUE
```

Customer prompts, commands/results, files and secrets must not become routine HARA Services telemetry.

---

## 11. Anti-concurrency / ownership

```text
#163=SOLE_EVENT_V2_IMPLEMENTATION_OWNER
#167=HUMAN_SESSION_IDENTITY_COST_ONLY
#172=DRAFT_FUTURE_10K_EVIDENCE_DO_NOT_MERGE_NOW

hara-platform#851=PRODUCT_INTEGRATION_ACCEPTANCE_ONLY
hara-platform#1000=STABLE_AGENT_CAPABILITY_NO_PARALLEL_EVENT_V2
hara-platform#1486=CUSTOMER_MCP_AUTH_COST_ONLY
hara-platform#1189=RETIREMENT_HOLD_UNTIL_PRODUCT_PATH_PROVEN
```

Do not open a second Event V2 implementation owner while #163 remains active.

---

## 12. Successor execution order

The successor should start from **fresh main**, re-read #163 and this handoff, then:

### P1 — Windows HARA-owned canary

1. Select one **HARA-owned Windows canary target**. Do not use a customer machine.
2. Freshly census stable Windows Agent state and DPAPI `device.json` without exposing secrets.
3. Install the RC using the source from PR #233.
4. Prove:
   - install inert;
   - stable 0.3.7 remains default;
   - RC auto-start = false;
   - same identity reused;
   - no reenrollment;
   - no dual-agent use.
5. Activate Event V2 **against DEV only**.
6. Require real connection attestation.
7. Prove five-tool live parity:
   - health
   - list
   - describe
   - invoke
   - receipts.get
8. Prove receipt correlation and quota reserve/commit/release parity.
9. Prove clean shutdown/disconnect.
10. Prove manual rollback.
11. Prove failed Event V2 activation automatically restores stable V1.
12. Publish evidence to #163.

Only after these are fresh PASS may:

```text
WINDOWS_EVENT_V2_RUNTIME_PROVEN=TRUE
WINDOWS_EVENT_V2_FIVE_TOOL_LIVE_PARITY=TRUE
WINDOWS_ROLLBACK_LIVE_PROOF=TRUE
CROSS_PLATFORM_EVENT_V2_PARITY=TRUE
```

### P2 — Measure PR #226 exact live A/B

Only if canary credentials/access permit a safe exact comparison:

- measure the current one-read selected-device path;
- compare against the retained pre-#226 baseline;
- do not change the canonical 500ms terminal settle while measuring;
- do not infer gains without measured evidence.

### P3 — 20k later, not now

Do **not** prioritize 20k runtime promotion ahead of the practical 100->1k path.

The current warning to solve later is prolonged-outage D1 presence-write pressure. Do not claim 20k readiness from offline models alone.

---

## 13. Explicit DO NOT REPLAY

```text
DO_NOT_REOPEN=#65_V1_PROD_HOMOLOGATION
DO_NOT_REPLAY=D1_MIGRATION_0010
DO_NOT_REPLAY=D1_MIGRATION_0011
DO_NOT_REINTRODUCE=2S_IDLE_POLLING
DO_NOT_REINTRODUCE=30S_HTTP_HEARTBEAT_ON_EVENT_PATH
DO_NOT_REINTRODUCE=300MS_TERMINAL_SETTLE_WITHOUT_NEW_EVIDENCE
DO_NOT_ROUTE=CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES
DO_NOT_COLLECT=CUSTOMER_CONTENT_FOR_TELEMETRY_OR_TRAINING
DO_NOT_MUTATE=PUBLIC_AGENT_0_3_7_UNTIL_RC_ACCEPTANCE
DO_NOT_CUTOVER_PROD=UNTIL_CROSS_PLATFORM_RC_PARITY_AND_ACCEPTANCE
```

Preserve the stable V1 rollback path until the release-candidate acceptance is terminal.

---

## 14. Successor first message / operational prompt

Use this as the new front entrypoint:

```text
Read first:
docs/handoffs/HARA_COMMANDER_EVENT_V2_SUCCESSOR_HANDOFF_20260926T0316Z.md

Then re-read hara-site#163 and fresh main.

Do not reopen V1 homologation, do not replay D1 migrations 0010/0011, do not
reintroduce 2s polling/30s HTTP heartbeat, and do not route customer traffic
through HARA Services.

Linux Event V2 DEV canary and Linux RC are already proven.
The current next gap is Windows Event V2 RC live canary/parity.

Start with a fresh census of the chosen HARA-owned Windows target, preserve
stable 0.3.7, install RC inert, activate only against DEV, prove live connection,
five tools, receipt/quota parity and rollback, then update #163 with evidence.

PROD_CUTOVER remains DENY.
```
