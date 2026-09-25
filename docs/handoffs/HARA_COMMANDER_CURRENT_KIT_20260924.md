# H.A.R.A. Commander — Current Kit — 2026-09-24

Status: **DEV FRONT CLOSED / PROD LIVE / AGENT 0.3.7 / TEST HOMOLOGATION NEXT / FIRST DEVICE READY BUT NOT YET PAIRED**

This file is the compact operational entrypoint for the current Commander state.

Current transition authority:
- `docs/handoffs/HARA_COMMANDER_DEV_TO_TEST_HANDOFF_20260925.md`

Full historical authority:
- `docs/handoffs/HARA_COMMANDER_SUCCESSOR_HANDOFF_20260923.md`
- GitHub issue #65

## 1. Current authority

Repository:
- source authority incorporated by this kit through PR #160: `d70f5e3856bcc33982a23ca78d8ad0e7340910a9`
- latest Commander source merge: PR #160 — stabilize desktop/mobile navigation after real-browser UX Wave 2 smoke
- open Commander PRs observed at kit creation: **0**

PROD:
- origin: `https://commander.haralabs.com.br`
- deployed source: `d70f5e3856bcc33982a23ca78d8ad0e7340910a9`
- Worker: `e7e7cc1f-2867-4066-a4b8-e29ed2056ee4`
- rollback Worker: `f54d495a-25c9-42a5-9336-f634b23c92d6`
- deployment: `1c5f16b2-5df2-4d40-89a5-aa248d52e9f5`
- migration 0009: **APPLIED**
- critical public assets: **CURRENT**
- UX Wave 2 #158–#160 live on PROD: onboarding/dashboard/device states/Connections/accessibility/mobile/loading — **PASS**
- real-browser desktop/mobile viewport smoke after #160 — **PASS**
- approved #154/#156 navigation + single sun/moon theme toggle live on PROD: **PASS**
- public health/auth-config minimal contracts: **PASS**
- public fail-closed smoke: **PASS**
- Identity live-readonly: **PASS**

DEV:
- Worker `hara-commander-dev-v2`: `cd641a3b-bd82-4694-93f0-f846a3acee41`
- rollback: `46aa8ef3-f07d-4ce8-bc3f-2ed43e7b7f23`
- deployed source: `d70f5e3856bcc33982a23ca78d8ad0e7340910a9`
- health: **DEV / REMOTE_DEV / HARA Identity configured**
- bootstrap public assets: byte-equal to canonical source in latest readback
- versioned DEV config: `apps/commander/wrangler.dev.jsonc`
- DEV config explicitly binds `hara-commander-product-dev` / `REMOTE_DEV`, never PROD routes/D1
- DEV secrets remain external to Git
- static anti-cross-environment validation is mandatory in source readiness
- live DEV deployment/binding/health readback exists
- do not infer DEV bindings/config from PROD when promoting backend behavior

## 1.1 Canonical customer architecture / cost law

This kit now carries two deliberately different MCP/data paths.

### H.A.R.A.-owned internal path

Our own engineering/agent path may traverse Services:

```text
OpenAI / HARA operator clients
  -> mcp.haralabs.com.br
  -> Cloudflare Tunnel
  -> HARA Services
  -> governed H.A.R.A. functions / receipts
```

This is H.A.R.A.-owned traffic and may be deeply monitored for engineering,
debugging, agent improvement and reliability under normal HARA governance.

### Customer product path

Normal customer device traffic MUST NOT traverse HARA Services:

```text
ChatGPT / Codex
  -> Commander / Cloudflare edge
  -> D1 + TenantQuota + DeviceChannel
  -> outbound Event V2 WebSocket
  -> HARA Agent
  -> customer machine
```

Canonical invariants:

```text
CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=FALSE
HARA_SERVICES_CUSTOMER_PROXY=FALSE
CUSTOMER_AGENT_CHANNEL=OUTBOUND_EVENT_V2
CUSTOMER_CONTENT_COLLECTION=FALSE
CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE
CUSTOMER_TRAFFIC_INSPECTION_DEFAULT=FALSE
CUSTOMER_OPERATIONAL_METADATA_ONLY=TRUE
HARA_SERVICES_NOC_AGGREGATION=TRUE
INTERNAL_HARA_MCP_MONITORING=ALLOWED
```

### Event V2 economy target

After the V1 real-device baseline is terminal, the next transport canary targets:

```text
IDLE_HTTP_POLLING=FALSE
HTTP_HEARTBEAT_30S=FALSE
SOCKET_PRESENCE=PRIMARY_EPHEMERAL_SIGNAL
APPLICATION_JSON_PING_STEADY_STATE=FALSE
WEBSOCKET_PROTOCOL_PING_IDLE_TARGET=60s
DURABLE_LIVENESS_CHECKPOINT_TARGET=6h
RECONNECT_FULL_JITTER=TRUE
RECONNECT_MAX_TARGET=60s
POLL_V1_FALLBACK_DEFAULT=OFF
```

D1 writes should follow meaningful state transitions and rare durable checkpoints,
not repetitive "ONLINE" writes.

For 1,000 continuously connected devices, a six-hour durable checkpoint represents
at most roughly 4,000 checkpoint opportunities/day before coalescing with real
state changes, instead of 2.88 million 30-second heartbeat requests/day.

### Privacy/NOC boundary

HARA Services may aggregate operational metrics from Cloudflare/Commander and
Storage Identity for NOC purposes:

- connected-device counts;
- connection duration;
- reconnect/fallback pressure;
- p50/p95/p99 delivery latency;
- success/error/timeout classes;
- Worker/D1/DO resource/cost counters;
- bounded bytes/messages counters;
- Agent version/state;
- quota/cost aggregates.

Routine NOC telemetry must not contain prompts, command payloads/results,
customer files, arbitrary filesystem contents, Authorization/Cookie headers or
OAuth/session/device/pairing secrets.

What the customer sees locally in their own console/logs is a separate boundary:
local execution output may be visible to that customer, but it is not routine
content telemetry exported to HARA Services.

Canonical detail:
- `docs/architecture/HARA_COMMANDER_SCALE_V2_EVENT_TRANSPORT.md`
- `docs/architecture/HARA_COMMANDER_PRIVACY_FIRST_TELEMETRY.md`

Agent release authority:
- stable Agent: **0.3.7**
- manifest: `apps/commander/public/release/agent-manifest.json`
- Linux/Windows Agent + installers are covered by release manifest and SHA256SUMS
- Agent 0.3.7 polling/30s heartbeat remains the **homologation baseline only**
- post-baseline customer transport target is Event V2/WebSocket Hibernation under issue #163
- Scale V2 architecture source is default-off/source-only until V1 E2E is terminal

## 2. What is already closed

### Identity / login

Closed in source/runtime:
- HARA Identity default redirect aligned to PROD
- PKCE S256
- account-selection behavior
- expired OIDC transaction cleanup
- terminal callback cookie cleanup
- open-redirect protection
- login runtime/public white-label validation
- same-origin portal mutation guard
- missing `Origin` on portal mutations fails closed with `403 PORTAL_ORIGIN_DENIED` in DEV
- explicit cross-origin portal mutations remain denied with 403
- malformed percent-encoded session cookies fail closed as unauthenticated instead of surfacing 500
- logout tolerates malformed session cookies and still clears the browser cookie
- OIDC multi-audience ID Tokens require the expected authorized party (`azp`), and any present `azp` must equal the Commander client ID
- OIDC `nbf` is enforced with a bounded 30-second clock-skew allowance; malformed/non-numeric `nbf` fails closed
- OIDC issuer query/fragment/embedded credentials are rejected; only trailing-slash canonicalization is allowed
- OIDC `iat` is required and numeric; audience entries and subject format are validated before identity binding
- any present OIDC `azp` must be a non-empty string before client-id comparison
- OIDC Discovery Authorization/Token/JWKS/UserInfo endpoints are validated as HTTPS; embedded credentials/fragments fail closed
- JWKS signing-key selection honors compatible `use=sig`, `alg=RS256` and `key_ops=verify` metadata when present
- `AUTH_CLIENT_AUTH` is authoritative and limited to `BASIC|NONE`; BASIC requires a secret and NONE ignores any stale secret binding
- credential-bearing Token/UserInfo subrequests use manual redirect handling and explicitly deny 3xx responses
- PROD alternate Worker/version URL surface disabled

Live DEV regression / resolution:
- source through #145 was briefly canaried in DEV and exposed `GET /auth/login` returning 500;
- operational bisect proved #141 returns 302 while #143 returns 500, isolating the regression to `redirect=error` on the Worker-side Discovery subrequest;
- DEV was restored to #141 while #146 was reviewed;
- #146 replaced the unsafe broad policy with Cloudflare-compatible handling: Discovery/JWKS carry no credentials and use normal fetch behavior; Token/UserInfo carry sensitive headers and use manual redirects with explicit 3xx denial;
- final live DEV proof on Worker `4e641bb4-1daf-471f-800e-bfdf13edb3f6`: login 302 to HARA Identity, Authorization Code + PKCE S256, account switch `max_age=0`, anonymous/malformed sessions 401, missing-Origin logout 403, exact same-origin logout 204;
- historical failed/bisect Worker IDs are evidence only and are not rollback targets for new work: `501b8736-ca2d-4ec5-addf-b261fa7db1b8` and `2dc36978-df0e-4908-a073-844a9570232d`.

Still human-only:
- fresh private-browser login/callback
- authenticated top header
- logout
- account switch
- prove no DEV redirect / stale-login loop

### Portal / authorization / lifecycle

Closed:
- REVIEWER least privilege
- invalid client input returns 400 rather than 500
- portal dashboard PROD schema canonicalized
- pairing token supersession: one current token per tenant/subject
- terminal pairing retention
- portal-session retention: 30 days, bounded cleanup
- OIDC transaction hygiene bounded to 10 minutes
- device select/revoke/enqueue/complete races hardened
- post-auth claim-after-revoke TOCTOU blocked
- invite identity-claim race serialized
- device-call expiry cause normalized to `DEVICE_CALL_EXPIRED`
- abandoned quota reservations automatically release after 600 seconds

### UX already closed

Closed:
- duplicate internal signed-in identity removed from all protected pages
- signed-in identity remains once in the global top header
- obsolete `.user-chip` CSS removed
- Trial data aligned to live backend: 100 executions/month
- Standard/Scale not presented as active production plans
- fake/demo production actions removed
- ChatGPT/Codex remain disabled / homologation state
- mobile support access preserved
- pairing expiry/copy state hardened
- offline device is visually distinguishable from online/no-selection
- operator-approved workspace navigation from #154/#156 is canonical: single H.A.R.A. Labs Commander brand in the header, no duplicate sidebar brand, no center Produto/H.A.R.A. Labs navigation, one light/dark sun-moon theme toggle in the top-right header, Suporte inside the sidebar, top-right account + Sair, custom SVG menu icons and hover/active motion
- UX Wave 2 from #158–#160 is canonical and PROD-proven: single guided pairing flow, real quota progress/status cards, Trial temporary-plan treatment, selected/online/offline device hierarchy, honest ChatGPT/Codex readiness, keyboard/focus accessibility, bottom mobile navigation with Mais, skeleton/loading states and real-browser desktop/mobile smoke

### Agent / device security

Current release **0.3.7** includes:
- only governed five-tool surface
- arbitrary function/shell denied
- server-side payload contract before queueing/quota
- Linux config file mode / secret custody hardening
- Windows encrypted device token + ACLs
- bounded/rate-limited operator diagnostics
- V1 explicit heartbeat as presence authority **for the current 0.3.7 homologation baseline**
- no idle poll presence writes
- V2 target removes the 30-second HTTP heartbeat and derives live presence from the WebSocket channel
- startup attestation on install/update
- redirect fail-closed transport on Linux/Windows
- canonical PROD enrollment-origin pinning
- Windows pairing plaintext lifetime minimized
- bootstrap fetch failure propagation
- invoke receipt binds exact stdout through:
  - `result_binding=STDOUT_SHA256_V1`
  - `result_stdout_sha256`
- receipt proof is required before quota COMMIT

## 3. Supply-chain posture

Current protections:
- installers + Agents present in release manifest
- SHA256SUMS available
- Linux/Windows post-bootstrap Agent integrity enforced
- Agent version validation
- dynamic Agent self-test gate
- startup attestation
- canonical PROD origin pin
- redirect denial
- Linux TLS 1.2+ floor
- Linux bootstrap downloads to a temporary file before execution; no `curl | bash`
- Windows bootstrap fetch is terminating and rejects empty content; no `irm | iex`
- runtime drift gate checks the critical customer-facing release assets byte-for-byte

Honest remaining maturity gap:
- initial bootstrap still trusts the Commander HTTPS origin
- there is **no independent package/signature trust anchor yet**
- future target can be signed/package-managed distribution
- do not claim this is already solved

## 4. E2E / quota advances

Canonical operator harness:
- `apps/commander/scripts/commander_e2e_harness.py`

Two modes:
- `quota-roundtrip`
- `five-tool`

Already proven live in PROD:
```text
COMMANDER_E2E_QUOTA_RESERVE=PASS
COMMANDER_E2E_QUOTA_RELEASE=PASS
COMMANDER_E2E_QUOTA_RELEASE_REPLAY=DENIED
COMMANDER_E2E_QUOTA_NET_USAGE=ZERO
COMMANDER_E2E_SECRET_EXPOSED=FALSE
COMMANDER_E2E_MODE_QUOTA_ROUNDTRIP=PASS
```

Additional quota protection:
- PR #127 adds a 600-second crash-safety TTL
- stale `RESERVED` becomes terminal `RELEASED` with units=0
- fresh reservations remain reserved
- committed charges remain committed
- stale request-id replay remains terminal

Five-tool harness now proves:
- one stable selected device for the full run
- exact device/request/tool correlation
- Agent release-version parity
- semantic result validation
- invoke stdout hash binding
- `hara.receipts.get` proof before quota COMMIT
- bad/missing receipt proof releases quota instead of charging it
- ambiguous COMMIT/RELEASE transport outcomes reconcile through idempotent request-state readback

Still pending:
- **real COMMIT with a real paired device**
- this requires a completed real `hara.functions.invoke` and a valid Agent-generated receipt

## 5. First-device readiness

Candidate:
- host: `nucleo-a`
- Linux x86_64
- public Agent: **0.3.7**

Non-mutating preflight authority:
`apps/commander/scripts/commander_first_device_preflight.py --json`

Latest candidate posture:
```text
COMMANDER_FIRST_DEVICE_CANDIDATE_STATUS=PASS
COMMANDER_FIRST_DEVICE_CANDIDATE_RESIDUE=ABSENT
COMMANDER_FIRST_DEVICE_CANDIDATE_PERSISTENCE=READY
COMMANDER_FIRST_DEVICE_CANDIDATE_MUTATION=FALSE
COMMANDER_FIRST_DEVICE_CANDIDATE_TOKEN_EXPOSED=FALSE
COMMANDER_FIRST_DEVICE_CANDIDATE=READY
```

The preflight also checks:
- no prior enrollment/residue
- Agent inactive/disabled before homologation
- systemd-user readiness
- public/local installer + manifest byte parity
- custom XDG roots
- relative XDG roots fail closed

Do not pair/install until the operator intentionally opens the real-device gate.

## 6. Current live-readonly production proof

Canonical command:

```bash
python3 apps/commander/scripts/validate_preprod_readiness.py \
  --live-readonly \
  --expect-prod-migration applied \
  --expect-prod-assets current \
  --expect-prod-worker-version e7e7cc1f-2867-4066-a4b8-e29ed2056ee4
```

Expected high-level state:
```text
COMMANDER_SOURCE_PREPROD_READY=PASS
COMMANDER_IDENTITY_LIVE_READONLY=PASS
COMMANDER_PROD_D1_LIVE_READONLY=PASS
COMMANDER_PROD_RUNTIME_LIVE_READONLY=PASS
COMMANDER_PROD_FAIL_CLOSED_LIVE_READONLY=PASS
COMMANDER_PROD_WORKER_LIVE_READONLY=PASS
COMMANDER_PROD_D1_MIGRATION_0009=APPLIED
COMMANDER_PROD_SESSION_RETENTION_WINDOW_DAYS=30
COMMANDER_PROD_SESSION_RETENTION_ELIGIBLE=0
COMMANDER_PROD_RUNTIME_ASSETS=CURRENT
COMMANDER_PROD_WORKER_DEPLOYMENT=PROVEN
COMMANDER_PROD_WORKER_VERSION=e7e7cc1f-2867-4066-a4b8-e29ed2056ee4
COMMANDER_HUMAN_HOMOLOGATION=PENDING_OPERATOR_GATE
COMMANDER_FIRST_DEVICE_E2E=PENDING_HOMOLOGATION
```

Latest structural PROD posture:
- devices = 0
- selections = 0
- calls = 0
- foreign-key/integrity defects = 0
- retention-eligible portal sessions = 0
- device count remains zero until first real pairing

## 7. Recent delivery map — #91 to #161

Key progression after the original promotion/UI cleanup:

- #91 — remove dead `.user-chip` styles
- #92 — canonical E2E/quota harness
- #93 — Agent 0.3.4 supply-chain hardening
- #94 — E2E product-token origin + redirect hardening
- #95 — server-side five-tool payload contract
- #97 — ambiguous quota transition reconciliation
- #98 — Agent 0.3.5 startup attestation
- #100 — first-device non-mutating candidate preflight
- #101/#102 — session-retention readback + readiness exposure
- #103 — terminal pairing retention
- #104 — OIDC transaction hygiene
- #105 — semantic five-tool result validation
- #106/#108 — XDG residue/path fail-closed preflight
- #107 — same-device/release/request/receipt correlation
- #110 — MCP product-token custody hardening
- #111 — installer + manifest parity before first-device READY
- #112 — token symlink bypass closure + error-output redaction
- #113 — Agent 0.3.6 redirect fail-closed
- #115 — Windows device-token plaintext lifetime minimization
- #116 — customer bootstrap redirect denial + Linux TLS floor
- #118 — canonical enrollment-origin pin
- #120 — bootstrap fetch-failure/pipe masking closure
- #122 — Agent 0.3.7 receipt/result binding + proof-before-quota-commit
- #125 — canonical device-call expiry cause
- #127 — abandoned quota reservation TTL / crash safety
- #128 — current PROD quota-TTL rollout receipt
- #129 — versioned DEV runtime config + DEV-only binding/readback authority — DEV promoted
- #132 — portal mutation guard now requires an exact `Origin`; DEV promoted to Worker `406247fc-9c41-4088-8251-83c0c249ab93`, missing-Origin logout probe now returns 403
- #134 — malformed session-cookie decoding no longer raises 500; DEV promoted to Worker `c2acc69c-2773-4c4b-b20a-fbea94b48274`; live malformed-cookie probes return 401 on session read and 204 + cookie clear on logout
- #136 — OIDC authorized-party (`azp`) validation with cryptographic RS256 regression coverage
- #137 — OIDC `nbf` not-before enforcement and malformed-claim denial
- #138 — OIDC issuer / `iat` / audience / subject claim-shape hardening; DEV promoted to Worker `71031640-7e02-4bbc-940c-4af8da3472d9`, rollback `c2acc69c-2773-4c4b-b20a-fbea94b48274`
- #140 — `azp` claim-shape enforcement
- #141 — HTTPS validation for OIDC Discovery endpoints
- #142 — Commander validation hygiene (local ESM boundary, Python cache ignore)
- #143 — initial all-subrequest redirect hardening; **superseded after live DEV regression**
- #144 — JWKS signing-key metadata selection hardening
- #145 — explicit `AUTH_CLIENT_AUTH` enforcement
- #146 — live-regression hotfix: Discovery/JWKS reads restored to compatible fetch behavior; Token/UserInfo remain manual-redirect fail-closed; DEV promoted and login 302 re-proven
- #147 — canonical docs updated after OIDC hardening/live bisect
- #148 — DEV deployment readback now requires live login redirect, PKCE S256, transaction-cookie and account-switch proof
- #149 — rich `/api/dev/health` diagnostics require `DEV_ACCESS_TOKEN`
- #150 — public `/api/health` minimized to `{ok, service}`; runtime fingerprinting removed; DEV promoted to Worker `a60a3408-4358-429a-af9a-0b1c406882b0`, rollback `2eabd96b-78f4-4dc1-a488-b2195ad5d13d`
- #151 — canonical kit/successor guide synchronized through #150
- #152 — public `/api/portal/auth-config` minimized to `{configured}`; provider/client-auth fingerprinting removed; DEV promoted to Worker `38366557-1ffb-4eeb-a489-eeb4ec1d0891`, rollback `a60a3408-4358-429a-af9a-0b1c406882b0`
- #153 — canonical kit/successor guide synchronized through #152
- #154 — operator-approved workspace navigation/layout: header brand only, support moved into sidebar, duplicate sidebar brand/logout removed, custom SVG navigation icons + hover/active motion; DEV promoted to Worker `b46fd897-8a7e-4093-b588-deff5008366e`
- #155 — canonical kit/successor guide synchronized after the approved layout rollout
- #156 — restored the operator-requested single sun/moon theme toggle while preserving the approved navigation; DEV promoted to Worker `442691d0-a862-4e9f-b1fe-69eb98ce66e8`; PROD promoted to Worker `f54d495a-25c9-42a5-9336-f634b23c92d6`, rollback `2a4ca063-32e4-4efa-92fb-3f775fdbf753`
- #158 — dashboard/device onboarding Wave 2A: quota progress, Trial status treatment, selected/online/offline device hierarchy and one guided Linux/Windows pairing flow
- #159 — UX Wave 2B: honest Connections readiness, accessibility/focus/keyboard, mobile bottom navigation and loading/empty-state polish
- #160 — real-browser viewport correction: Mais hard-hidden on desktop and primary mobile navigation hard-visible; final DEV Worker `cd641a3b-bd82-4694-93f0-f846a3acee41`; PROD Worker `e7e7cc1f-2867-4066-a4b8-e29ed2056ee4`, rollback `f54d495a-25c9-42a5-9336-f634b23c92d6`
- #161 — canonical docs synchronized after UX Wave 2 PROD rollout; no runtime mutation

For the earlier #64–#90 history, use the canonical successor guide.

## 8. Remaining work — dedicated TEST/HOMOLOGATION front

The development/UX front is **CLOSED**. Do not start another polish wave before the real campaign unless a test exposes a concrete defect.

Canonical transition handoff: `docs/handoffs/HARA_COMMANDER_DEV_TO_TEST_HANDOFF_20260925.md`.

### Operator / human gate

These are not source defects:

1. Fresh private-browser auth homologation:
   - login
   - callback
   - authenticated header
   - logout
   - account switch
   - no DEV redirect / stale loop

2. Intentionally open the first real PROD device gate.

3. Pair `nucleo-a` and approve the E2E campaign.

### Deterministic/backend front

After operator pairing, first prove the current V1 baseline:
- prove 0.3.7 heartbeat and online/offline state
- prove selected-device behavior
- prove revoke + expiry behavior
- run canonical five-tool E2E
- prove real invoke receipt
- prove quota COMMIT
- prove `receipts.get` correlation
- preserve zero secret/token leakage in evidence
- observe the Agent/local console behavior and classify what is customer-local output versus exportable operational metadata

Only after the V1 baseline is terminal, advance the already source-prepared Event V2 canary:
- one HARA-owned device first
- prove idle 2-second polling = 0
- prove 30-second HTTP heartbeat = 0 on the Event path
- prove WebSocket connect/disconnect presence
- prove protocol keepalive does not become application telemetry spam
- prove rare/coalesced durable liveness checkpoint behavior
- prove exponential reconnect + full jitter + bounded maximum
- prove D1 remains durable truth if an event notification is lost
- repeat lifecycle + five tools + receipts + quota under Event V2
- prove rollback to V1 remains available until V2 acceptance is terminal

Can continue before pairing only on deterministic maturity items:
- independent bootstrap/package trust-anchor design
- Windows-host dynamic runtime evidence when a reviewed Windows host is available
- current Identity operational residue inspection

### Astra — preferred ownership

Astra should focus on UX/information architecture, not backend security:

1. Authenticated navigation de-duplication — **CLOSED by operator approval / PR #154**:
   - `Sair` is canonical in the top-right session controls
   - `Suporte` is canonical inside the sidebar menu
   - H.A.R.A. Labs Commander brand appears only in the top-left header and opens the H.A.R.A. Labs site
   - do not reintroduce center product links or duplicate sidebar branding; the single sun/moon theme toggle restored by #156 is canonical

2. Pairing onboarding UX — **CLOSED by PR #158**:
   - canonical flow is generate token -> choose Linux/Windows -> copy installer -> paste token -> wait for heartbeat
   - pairing token remains OS-independent and backend one-current-token semantics are unchanged

3. Connections / ChatGPT / Codex — **CLOSED for pre-E2E UX by PR #159**:
   - ChatGPT/Codex remain explicitly in homologation
   - activation order and proven capabilities are shown without a fake CTA
   - do not enable authorization before real-device E2E

4. Offline selected-device presentation — **CLOSED by PR #158**:
   - persistent selection / ACTIVE-offline semantics preserved
   - selected, online, offline and last-contact presentation is canonical
   - invocation remains denied offline

5. Responsive/workspace polish — **CLOSED for current V1 by PR #159/#160**:
   - desktop sidebar remains canonical
   - mobile uses bottom navigation: Visão geral / Computadores / Conexões / Mais
   - Mais owns Uso / Plano / Segurança / Suporte on mobile
   - skip-link, focus-visible, keyboard OS selector, loading skeletons and reduced-motion support are canonical

## 9. Non-blocking operational residues

Identity SMTP:
- current branded provider/runtime is healthy
- 587/STARTTLS fallback alignment remains a maturity item
- helper for 465 exists but was intentionally not executed
- current ZITADEL 4.x SMTP update behavior has credential-preservation risk
- do not blind-mutate 587 -> 465

Login V2 custom translation:
- recurring upstream/system-locale warning for `pt`
- bundled locale fallback remains active
- container health remains PASS
- treat as upstream/non-blocking residue
- do not disable Portuguese or patch around blindly

## 10. Guardrails / do not repeat

Do not:
- reapply migration 0009 while readback says APPLIED
- edit ZITADEL projections/event store directly
- reapply Login Policy redirect while readback is PASS
- expose product token, device token, PATs or D1 export URLs in Git evidence
- revive PR #66 backend
- enable arbitrary shell/filesystem access
- enable ChatGPT/Codex activation before real E2E
- advertise Standard/Scale as active plans
- redeploy PROD just to reproduce evidence
- infer DEV binding/config from PROD
- weaken pairing supersession, receipt binding or quota terminal-state semantics
- route normal customer command traffic through HARA Services
- collect customer command/file/conversation content as routine telemetry
- use customer content for model training
- reintroduce fixed 2-second idle polling as an Event V2 fallback

## 11. Handoff order for the TEST front

Read in this order:
1. this kit
2. `docs/handoffs/HARA_COMMANDER_DEV_TO_TEST_HANDOFF_20260925.md`
3. `docs/handoffs/HARA_COMMANDER_SUCCESSOR_HANDOFF_20260923.md`
4. issue #65 current body + newest comments
5. current `main`

The next front owns PROD human homologation and first-device E2E. It should not perform feature work unless testing exposes a concrete defect. Coordinate all findings through issue #65.
