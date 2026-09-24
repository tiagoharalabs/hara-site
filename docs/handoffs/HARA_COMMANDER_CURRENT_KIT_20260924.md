# H.A.R.A. Commander — Current Kit — 2026-09-24

Status: **PROD PROMOTED / RUNTIME CONVERGED / AGENT 0.3.7 / FIRST DEVICE READY FOR OPERATOR / HUMAN HOMOLOGATION PENDING**

This file is the compact operational entrypoint for the current Commander state.

Full historical authority:
- `docs/handoffs/HARA_COMMANDER_SUCCESSOR_HANDOFF_20260923.md`
- GitHub issue #65

## 1. Current authority

Repository:
- source authority incorporated by this kit through PR #129: `7f1f24e2399666017c7a6e7cf2f09b5273121d95`
- latest source/config merge before this kit: PR #129 — versioned DEV runtime authority
- open Commander PRs observed at kit creation: **0**

PROD:
- origin: `https://commander.haralabs.com.br`
- deployed source: `84895dd17489e418b4b207bde405d7db9aa33469`
- Worker: `093ceec9-cacb-4f8b-ba23-bbfc85f7e1aa`
- rollback Worker: `382f4b7e-3094-43b9-a013-3b3f46f39fbf`
- deployment: `723af9a0-10f6-4e01-bdcf-b5701801309e`
- migration 0009: **APPLIED**
- critical public assets: **CURRENT**
- public fail-closed smoke: **PASS**
- Identity live-readonly: **PASS**

DEV:
- Worker `hara-commander-dev-v2`: `5a1185d7-98ac-4d47-87fd-84cf33bbc9da`
- rollback: `5a594804-0de5-4aa8-abf4-b669454f020f`
- deployed source: `7f1f24e2399666017c7a6e7cf2f09b5273121d95`
- health: **DEV / REMOTE_DEV / HARA Identity configured**
- bootstrap public assets: byte-equal to canonical source in latest readback
- versioned DEV config: `apps/commander/wrangler.dev.jsonc`
- DEV config explicitly binds `hara-commander-product-dev` / `REMOTE_DEV`, never PROD routes/D1
- DEV secrets remain external to Git
- static anti-cross-environment validation is mandatory in source readiness
- live DEV deployment/binding/health readback exists
- do not infer DEV bindings/config from PROD when promoting backend behavior

Agent release authority:
- stable Agent: **0.3.7**
- manifest: `apps/commander/public/release/agent-manifest.json`
- Linux/Windows Agent + installers are covered by release manifest and SHA256SUMS

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
- PROD alternate Worker/version URL surface disabled

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

### Agent / device security

Current release **0.3.7** includes:
- only governed five-tool surface
- arbitrary function/shell denied
- server-side payload contract before queueing/quota
- Linux config file mode / secret custody hardening
- Windows encrypted device token + ACLs
- bounded/rate-limited operator diagnostics
- explicit heartbeat as presence authority
- no idle poll presence writes
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
  --expect-prod-worker-version 093ceec9-cacb-4f8b-ba23-bbfc85f7e1aa
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
COMMANDER_PROD_WORKER_VERSION=093ceec9-cacb-4f8b-ba23-bbfc85f7e1aa
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

## 7. Recent delivery map — #91 to #128

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

For the earlier #64–#90 history, use the canonical successor guide.

## 8. Remaining work — by owner

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

After operator pairing:
- prove heartbeat and online/offline state
- prove selected-device behavior
- prove revoke + expiry behavior
- run canonical five-tool E2E
- prove real invoke receipt
- prove quota COMMIT
- prove `receipts.get` correlation
- preserve zero secret/token leakage in evidence

Can continue before pairing only on deterministic maturity items:
- independent bootstrap/package trust-anchor design
- Windows-host dynamic runtime evidence when a reviewed Windows host is available
- current Identity operational residue inspection

### Astra — preferred ownership

Astra should focus on UX/information architecture, not backend security:

1. Authenticated navigation de-duplication:
   - decide canonical desktop placement for `Sair`
   - rationalize repeated `Suporte`
   - preserve sensible mobile access

2. Pairing onboarding UX:
   - pairing token is OS-independent
   - prefer one clear flow: generate token -> choose Linux/Windows -> copy installer -> paste token
   - do not change one-current-token backend semantics

3. Connections / ChatGPT / Codex:
   - refine disabled/homologation states
   - improve explanatory copy and eventual activation flow
   - do not enable real CTA before real-device E2E

4. Offline selected-device presentation:
   - backend semantics remain persistent selection while ACTIVE/offline
   - invocation remains denied offline
   - Astra may improve wording/status hierarchy only

5. Responsive/workspace polish:
   - header/sidebar density
   - empty states
   - device onboarding hierarchy
   - mobile behavior
   - never reintroduce duplicate signed-in identity

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

## 11. Handoff order for the next front

Read in this order:
1. this kit
2. `docs/handoffs/HARA_COMMANDER_SUCCESSOR_HANDOFF_20260923.md`
3. newest issue #65 comments
4. current `main`
5. only then open a new branch

If Astra is activated, use the ownership split in section 8 and coordinate through issue #65 before editing overlapping UI files.
