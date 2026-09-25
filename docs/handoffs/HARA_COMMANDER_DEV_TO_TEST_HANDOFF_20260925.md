# H.A.R.A. Commander — DEV front closure / TEST handoff — 2026-09-25

Status: **DEV FRONT CLOSED / PROD LIVE / TEST & HOMOLOGATION FRONT NEXT**

This handoff closes the Commander development/hardening/UX front and transfers authority to the dedicated PROD homologation and first-device E2E front.

It does not open the first-device gate by itself. Pairing remains an explicit operator action.

## 1. Canonical product/runtime authority

Repository:
- product/runtime source: `d70f5e3856bcc33982a23ca78d8ad0e7340910a9` (PR #160)
- docs authority immediately before this closure: `cf5e7dc6c3129c3fada826b20d8f39562da5bb8f` (PR #161)
- open PRs observed immediately before closure: **0**

PROD:
- origin: `https://commander.haralabs.com.br`
- source: `d70f5e3856bcc33982a23ca78d8ad0e7340910a9`
- Worker: `e7e7cc1f-2867-4066-a4b8-e29ed2056ee4`
- rollback Worker: `f54d495a-25c9-42a5-9336-f634b23c92d6`
- deployment: `1c5f16b2-5df2-4d40-89a5-aa248d52e9f5`
- migration 0009: **APPLIED**
- runtime assets: **CURRENT**

DEV:
- Worker: `cd641a3b-bd82-4694-93f0-f846a3acee41`
- rollback: `46aa8ef3-f07d-4ce8-bc3f-2ed43e7b7f23`
- source: `d70f5e3856bcc33982a23ca78d8ad0e7340910a9`
- D1/environment isolation: **DEV ONLY / REMOTE_DEV**

Agent:
- stable release: **0.3.7**
- governed surface: exactly five device tools
- arbitrary shell/filesystem access: **ABSENT BY CONTRACT**
- 0.3.7 polling/heartbeat remains the V1 homologation baseline
- Event V2 is the post-baseline scale/cost target and remains source-only/default-off until V1 E2E is terminal

## 2. What this front closed

### Identity / OIDC / session hardening
Closed and regression-covered:
- Authorization Code + PKCE S256
- exact issuer/client/subject binding
- account selection / account switch
- open-redirect denial
- OIDC transaction cleanup and terminal cookie cleanup
- malformed session-cookie fail-closed behavior
- `azp`, `nbf`, `iat`, audience and subject shape validation
- HTTPS-only Discovery endpoint validation
- JWKS signing-key metadata constraints
- explicit `AUTH_CLIENT_AUTH=BASIC|NONE`
- credential-bearing Token/UserInfo redirect denial
- same-origin mutation guard with missing-Origin fail-closed
- alternate PROD Worker/version surface disabled

The live DEV regression introduced by broad `redirect=error` handling was bisected and corrected by #146 before the front was closed.

### Public surface minimization
- `/api/health` is intentionally minimal: `{"ok":true,"service":"hara-commander"}`
- `/api/portal/auth-config` exposes only `{"configured":true|false}`
- rich DEV diagnostics remain token-gated
- no environment/storage/auth fingerprint is intentionally exposed by the public health contract

### Product / UX
Canonical and live in PROD:
- one Commander brand in the top-left header
- no duplicated signed-in identity
- account + `Sair` top-right
- exactly one sun/moon theme toggle
- sidebar starts with navigation; `Suporte` lives there
- no center Product/H.A.R.A. Labs navigation
- single guided Linux/Windows pairing flow
- quota/status dashboard hierarchy
- Trial temporary-plan treatment
- selected / online / offline device states
- honest ChatGPT/Codex pre-E2E state; no fake activation CTA
- keyboard/focus accessibility
- mobile bottom navigation: Visão geral / Computadores / Conexões / Mais
- loading skeletons and honest empty states

Real-browser smoke found and closed two defects that static validation missed:
1. mobile-only `Mais` leaked into desktop;
2. primary mobile nav labels/icons could fail to render visibly.

PR #160 fixed both and the final desktop/mobile smoke passed.

## 3. Live proof at front closure

PROD:
- runtime assets: **CURRENT**
- public health minimal contract: **PASS**
- public auth-config minimal contract: **PASS**
- fail-closed read-only gates: **PASS**
- login redirect to HARA Identity: **PASS**
- PKCE method: **S256**
- D1 migration 0009: **APPLIED**
- UX Wave 2 markers: **PASS**
- desktop `Mais` hidden: **PASS**
- mobile primary navigation visible: **PASS**

DEV:
- config/D1/secrets/health readback: **PASS**
- login redirect: **PASS**
- PKCE S256: **PASS**
- transaction cookie: **PASS**
- account switch: **PASS**
- no PROD D1/route binding: **PASS**

Structural PROD state at handoff remains intentionally pre-pairing:
- real paired devices: **0**
- first real pairing: **NOT YET OPENED BY OPERATOR**

## 4. Test front — exact next scope

### Product data-plane law for all new testing

The test front must keep the internal H.A.R.A. path and customer product path separate.

```text
INTERNAL_HARA_MCP
OpenAI -> Cloudflare Tunnel -> Services -> H.A.R.A.
MONITORING=ALLOWED

CUSTOMER_PRODUCT
ChatGPT/Codex -> Commander edge -> DeviceChannel -> outbound Agent
HARA_SERVICES_INLINE=FALSE
CONTENT_TELEMETRY=FALSE
OPERATIONAL_METADATA_ONLY=TRUE
```

Customer-local console/log output belongs to the customer machine. Tests may use
that local output as operator evidence, but normal product telemetry must not
export command/result/file/conversation content to Services.

The next front is **homologation/testing**, not another polish wave.

Run in this order:

1. private-browser human auth:
   - login
   - callback
   - authenticated header
   - logout
   - account switch
   - prove no DEV redirect and no stale-login loop

2. intentionally open first real device gate:
   - candidate: `nucleo-a`
   - Linux x86_64
   - Agent 0.3.7
   - do not create the pairing token before the operator begins this phase

3. real device lifecycle — V1 baseline:
   - pairing
   - current 0.3.7 heartbeat
   - online/offline
   - selected-device persistence
   - pairing expiry
   - pairing supersession
   - revoke behavior
   - observe local Agent/console execution output and prove no secrets are leaked into published evidence

4. governed five-tool E2E:
   - stable selected device
   - exact tool/request/device correlation
   - negative authorization cases
   - no arbitrary shell/filesystem path

5. receipts:
   - real invoke receipt
   - exact result/stdout binding
   - `hara.receipts.get` correlation
   - no cross-request ambiguity

6. quota:
   - reserve
   - terminal execution proof
   - COMMIT only after valid receipt
   - failure/release path
   - no double-charge on retry

7. evidence audit:
   - zero pairing/device/product/OAuth token leakage
   - no session cookie/client secret in Git evidence
   - sanitize screenshots/logs/comments before publishing
   - distinguish customer-local console content from metadata eligible for NOC aggregation

8. Event V2 scale/cost canary — **only after V1 baseline is terminal**:
   - one HARA-owned device first
   - customer path must bypass HARA Services
   - outbound authenticated WebSocket to Commander/Cloudflare
   - idle HTTP polling = 0
   - 30-second HTTP heartbeat = 0 on the Event path
   - protocol keepalive target = 60s idle, not app-level telemetry spam
   - durable liveness checkpoint target = 6h, coalesced with meaningful state changes
   - reconnect = exponential + full jitter + bounded maximum
   - fixed 2-second fallback = denied
   - D1 durable truth survives dropped notification/reconnect
   - repeat lifecycle, five-tool, receipt and quota parity
   - rollback to V1 remains proven until V2 terminal acceptance

9. NOC evidence — source/test first:
   - Cloudflare native Worker/D1/DO aggregate metrics are primary
   - Services consumes aggregate capacity/cost/reliability signals asynchronously
   - customer content is not exported to Services
   - internal H.A.R.A. MCP monitoring remains unrestricted by this customer privacy boundary

## 5. Acceptance boundary

Commander can be called E2E-homologated only after:
- human auth PASS
- first real device PASS
- lifecycle PASS
- five governed tools PASS
- negative authorization tests PASS
- receipt binding / `receipts.get` PASS
- quota COMMIT/release semantics PASS
- zero secret leakage PASS

Only after that should ChatGPT/Codex activation move out of the current homologation state.

## 6. Non-blocking maturity items

Not blockers for the test campaign:
- independent bootstrap/package trust anchor
- independent Windows-host dynamic runtime proof
- Identity SMTP 465/587 maturity
- Login V2 upstream/system-locale `pt` warning

Do not turn these into reasons to postpone the real-device campaign.

## 7. Guardrails for the test front

Do not:
- redeploy PROD merely to reproduce existing evidence
- reapply migration 0009 while state is APPLIED
- regenerate or publish tokens in Git evidence
- reintroduce fake ChatGPT/Codex activation
- enable arbitrary shell/filesystem access
- weaken pairing supersession, receipt binding or quota terminal semantics
- treat DEV behavior as proof of PROD behavior
- mix unrelated feature work into the V1 test campaign unless a test exposes a concrete defect
- route customer command traffic through HARA Services
- collect customer content for routine telemetry or model training
- treat local customer console output as permission to export that content
- reintroduce fixed 2-second polling as Event V2 fallback

## 8. Read order

1. `docs/handoffs/HARA_COMMANDER_CURRENT_KIT_20260924.md`
2. this closure/test handoff
3. `docs/handoffs/HARA_COMMANDER_SUCCESSOR_HANDOFF_20260923.md`
4. issue #65 current body + newest comments
5. current `main`

Issue #65 remains the canonical coordination ledger and is repurposed for the PROD homologation / first-device E2E campaign.
