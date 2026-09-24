# H.A.R.A. Commander — successor guide — 2026-09-23

Status: **PROD PROMOTED / RUNTIME CONVERGED / HUMAN HOMOLOGATION PENDING / DEVICE E2E NOT YET OPEN**

This is the canonical successor guide for the Commander front, created on 2026-09-23 and updated through 2026-09-24 after Login V2 convergence and the full deterministic pre-PROD hardening sweep.

## 1. Product boundary

H.A.R.A. Commander is a simple customer connectivity product:

1. customer creates or enters a HARA account;
2. installs HARA Commander Agent on Linux or Windows;
3. pairs the computer with a short-lived one-time code;
4. the Agent keeps an outbound-only authenticated connection;
5. ChatGPT, Codex or another supported MCP client is authorized;
6. governed MCP calls are routed to the selected computer;
7. sanitized results and receipts are returned.

Commander is **not**:
- Paradox;
- a fleet NOC;
- a generic SSH/shell/file browser;
- a per-customer Cloudflare Tunnel product.

Keep arbitrary shell and generic filesystem access absent.

## 2. Production endpoints

- Commander PROD: `https://commander.haralabs.com.br`
- HARA Identity: `https://auth.haralabs.com.br`
- public MCP target: `https://mcp.haralabs.com.br/mcp`

The deterministic hardening is promoted to PROD. The next blocking gate is the operator browser homologation before first real device pairing.

## 3. Login / Identity state — CLOSED technically, browser retest pending

The HARA Identity Login Policy fallback redirect was corrected through the supported ZITADEL Admin API:

```text
HARA_IDENTITY_LOGIN_POLICY_READ=PASS
HARA_IDENTITY_DEFAULT_REDIRECT_PREVIOUS=https://hara-commander-dev-v2.tiago-sartori.workers.dev/
HARA_IDENTITY_DEFAULT_REDIRECT_CURRENT=https://commander.haralabs.com.br/
HARA_IDENTITY_DEFAULT_REDIRECT_ALIGN=PASS
```

Independent backend validation:

```text
IDENTITY_LOGIN_DEFAULT_REDIRECT=PASS
IDENTITY_RUNTIME_HEALTH=PASS
IDENTITY_LOGIN_IMAGE_VARIANT=PASS_HARA_8
```

The Login V2 container was restarted through the authorized operator path:

```text
hara-identity-zitadel-login-1
health=healthy
```

Fresh public runtime proof after the restart:
- Cloudflare response is dynamic, not stale cache;
- rendered Login V2 payload contains `defaultRedirectUri=https://commander.haralabs.com.br/`;
- Settings API instance context returns PROD redirect;
- Settings API default-organization context returns PROD redirect.

The public validator initially produced a false negative because the Next.js server-component payload escapes quotes. The validator was fixed to normalize that escaping before checking the rendered value.

Canonical proof from `main`:

```text
HARA_IDENTITY_PUBLIC_ASSETS=PASS
HARA_IDENTITY_MANIFEST=PASS
HARA_IDENTITY_VISIBLE_BRANDING=PASS
HARA_IDENTITY_VISIBLE_VENDOR_LEAK=FALSE
COMMANDER_OIDC_REDIRECT=PASS
COMMANDER_OIDC_PKCE=PASS
COMMANDER_ACCOUNT_SELECTION=PASS
HARA_IDENTITY_LOGIN_DEFAULT_REDIRECT_RUNTIME=PASS
HARA_IDENTITY_RECOVERY_PAGE_HTTP=PASS
HARA_IDENTITY_RECOVERY_COPY_PT=PASS
HARA_IDENTITY_RECOVERY_FALSE_SUCCESS_COPY=ABSENT
```

Regular login uses `prompt=select_account`.
`Usar outra conta` uses `prompt=select_account&max_age=0`.

PR #64 was merged by squash into `main` as:

```text
54e7da7b9b92ecd66b9c071a1f43b1731c717ab3
fix(identity): prove Login V2 runtime convergence (#64)
```

Do **not** reapply the backend redirect policy unless backend readback proves drift.
Do **not** edit ZITADEL projections or event-store rows directly.

## 4. Current pre-test hardening — CLOSED IN SOURCE

The deterministic pre-PROD hardening sweep is consolidated in canonical `main`.

Key merged closures:
- #68 runtime reliability: OIDC failure-cookie cleanup, best-effort/coalesced session touch,
  Agent diagnostics, no idle-poll presence writes, Linux/Windows secret/error hardening;
- #69 device-call TTL bounded to 50s;
- #70 OIDC return-target open redirect blocked;
- #71 REVIEWER least privilege;
- #72 invalid client input mapped to 400 and alternate Worker surfaces explicitly disabled;
- #73 pairing-token supersession + migration `0009_pairing_supersession.sql`;
- #75 governed portal-session retention;
- #76 device lifecycle race/idempotency hardening;
- #77 canonical PROD portal schema + retryable pairing-create error;
- #78 same-origin guard for portal mutations;
- #79 latest Astra UI snapshot reconciled onto hardened `main`;
- #81 revoked-device claim TOCTOU blocked;
- #82 concurrent invite identity claim serialized.

PR #66 is **CLOSED / SUPERSEDED**. Its UI work was preserved by #79, while its stale backend
was intentionally not merged.

Current production gate:
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
COMMANDER_PROD_SESSION_OLDEST_EXPIRED_AGE_DAYS=1.28
COMMANDER_PROD_RUNTIME_ASSETS=CURRENT
COMMANDER_PROD_WORKER_DEPLOYMENT=PROVEN
COMMANDER_PROD_WORKER_VERSION=daf0cc4b-9372-4165-8c94-c2decefa221f
COMMANDER_HUMAN_HOMOLOGATION=PENDING_OPERATOR_GATE
COMMANDER_FIRST_DEVICE_E2E=PENDING_HOMOLOGATION
```

The original production promotion used canonical `main` commit `da28e0404df689b9e9943fa4377f51789c9b5dfd`. The current deployed runtime has since advanced through reviewed hardening to source `021b32476074c2b7655337a5d902ff19a3ffa855` (PR #113 Agent 0.3.6 redirect fail-closed release). PRs #110–#112 are operator-tooling/preflight/token-custody hardening; #113 required and received an explicit DEV/PROD asset promotion.
Future source merges still do **not** implicitly publish Commander; later deployments remain explicit.

## 5. Live product/data facts confirmed

Current PROD D1 facts recorded in issue #65:
- exactly one active plan row: `TRIAL`;
- Trial unit limit: `100`;
- period: `CALENDAR_MONTH`;
- current entitlement: `TRIAL / ACTIVE`;
- current Trial grants:
  - `COMMANDER_DISCOVERY`
  - `COMMANDER_READ_ONLY_INVOKE`
  - `COMMANDER_RECEIPT_READ`

Therefore old visible claims such as Trial 1,000, Standard 10,000 and active Standard/Scale were incorrect and must not return.

Latest structural PROD readback during the hardening:
- devices = 0;
- selections = 0;
- calls = 0;
- active portal sessions = 0;
- foreign-key/integrity defects = 0;
- expired/unrevoked portal sessions = 1;
- retention-eligible terminal sessions under the 30-day policy = **0**;
- oldest expired/unrevoked session age observed on 2026-09-24 = **1.28 days**, so preservation is expected rather than a cleanup defect.

No real production device has been paired yet.

Production promotion receipt (2026-09-24 UTC):
- pre-migration D1 export: `/tmp/hara-commander-product-prod-before-0009-20260924T043420Z.sql`;
- export SHA-256: `e3f91038f431b69289d41344ec7c48e74b71fd50fb3b412521ba670279d63b2f`;
- migration `0009_pairing_supersession.sql`: **APPLIED**;
- promoted deployable source: `da28e0404df689b9e9943fa4377f51789c9b5dfd`;
- Cloudflare deployment id: `6ea63b52-875d-4d4c-a7b4-adadd45d518c`;
- Worker version at 100%: `ae7c9d6c-1d2a-401b-abf0-489f5d09b869`;
- rollback Worker version: `fe4abe4e-1ce3-484d-aa11-b9535dd8610d`;
- deployed at: `2026-09-24T04:35:17.783098Z`;
- public health/auth: **PASS**;
- public fail-closed smoke: **PASS**;
- 10 critical public assets (UI, installers, Agents, release manifest/checksums and brand asset): **CURRENT** against canonical deployable source.

Subsequent UX-only deployment (2026-09-24 UTC):
- source `main`: `f5d0b13cc4e1f2250b3d9ae71fee636f2d3f6e71`;
- removed six duplicated internal `user-chip` identity cards; global top-header identity remains canonical;
- PROD Worker version: `6d018e75-6c43-4efe-bf29-c277a49d4f2c`;
- PROD rollback version: `ae7c9d6c-1d2a-401b-abf0-489f5d09b869`;
- DEV Worker `hara-commander-dev-v2`: `8022e192-dc12-4fa7-9416-0404b76873cf`;
- DEV rollback version: `964936c0-c921-4b43-82ac-aff9b54ed491`;
- DEV D1 migration 0009: **APPLIED** after backup; DEV health remains `DEV / REMOTE_DEV`;
- PROD and DEV rendered `user-chip` count: **0**.

Agent 0.3.4 / technical hardening deployment (2026-09-24 UTC):
- Agent/supply-chain source first promoted through PRs #91-#94; public Agent release is **0.3.4**;
- canonical source after the latest Worker hardening: `c0669a1db1a3ac75b86c1f196f9aef0f67bd8e01`;
- PR #94 pins the privileged E2E harness to the exact canonical PROD origin and disables token-bearing redirects;
- PR #95 validates the five device-tool payload contracts server-side and denies unsupported function IDs before quota reservation;
- that rollout's PROD deployment id: `8fb3f5b5-41b6-4cb5-901e-778b7681087b`;
- that rollout's PROD Worker version at 100%: `f96d5690-7681-4976-b86b-94fe66ea842c`;
- that rollout's rollback Worker version: `0f1028a0-797a-470e-a825-68d3e607cf67`;
- #95 deployment uploaded **no changed asset files**; it changed Worker trust-boundary logic only;
- 10/10 critical public assets: **CURRENT**;
- public fail-closed smoke: **PASS**;
- `validate_bootstrap_supply_chain.py`: **PASS**;
- server-side five-tool payload contract: **PASS**;
- initial bootstrap trust remains `WEB_ORIGIN`; independent trust anchor remains **PENDING_MATURITY**;
- no PowerShell runtime was already available on the reviewed Linux infrastructure, so this front did not claim an independent Windows runtime execution proof; the 0.3.4 Windows installer itself requires its dynamic Agent self-test fail-closed during install/update.


Agent 0.3.5 startup-attestation deployment (2026-09-24 UTC):
- source `main`: `85ec98591842c0e82fc67873fda1937c1fc8eee7`;
- PR #97 hardened the operator E2E harness to reconcile ambiguous quota commit/release outcomes through idempotent request-state readback;
- PR #98 released Agent **0.3.5**;
- both Agents now persist `started_at_utc` only after required local configuration is successfully loaded; Windows additionally proves its encrypted device token can be decrypted;
- Linux and Windows installers/updates require a fresh startup marker for the expected Agent version before declaring success;
- failed startup attestation preserves existing revoke/rollback behavior;
- dynamic Linux startup proof passes even with an intentionally unreachable network endpoint, proving startup attestation is local rather than network-coupled;
- PROD Worker version: `5fce4f09-8db4-44a0-a5d6-b237c5288e75`;
- rollback Worker version: `532bb762-c2b2-443d-8527-ada001bbce39`;
- deployment id: `e22da847-4641-413d-a6e0-f5dd547b072f`;
- 10/10 public runtime assets: **CURRENT**;
- fail-closed live smoke: **PASS**;
- full live-readonly gate: **PASS**.

Agent 0.3.6 redirect fail-closed deployment (2026-09-24 UTC):
- source `main`: `021b32476074c2b7655337a5d902ff19a3ffa855`;
- PR #110 hardened local MCP product-token custody with owner/mode/no-follow checks and Wrangler 4.137.0 alignment;
- PR #111 requires byte-exact public/local installer + release-manifest parity before the first-device candidate may report READY;
- PR #112 closed a symlink-bypass regression in the E2E token path and redacts raw Wrangler failure output;
- PR #113 released Agent **0.3.6** and makes sensitive Agent/installer transport fail closed on HTTP redirects on Linux and Windows;
- Linux redirect canary proves the redirect destination receives **0 requests** and **0 bearer credentials**;
- Windows Agent/installer calls use `-MaximumRedirection 0`; Linux urllib bearer helpers use explicit no-redirect openers;
- Windows pairing plaintext payload is cleared immediately after enrollment response handling;
- PROD deployment id: `03f57aee-7194-484c-a42e-314482f5e6c6`;
- PROD Worker version: `daf0cc4b-9372-4165-8c94-c2decefa221f`;
- PROD rollback Worker version: `cb80f974-cb21-4ae7-9d5d-fc2271eacd8e`;
- PROD deployed at: `2026-09-24T19:42:20.099217Z`;
- DEV deployment id: `7050005c-cada-4900-be76-3e1986259481`;
- DEV Worker version: `5b2efcc0-607e-445b-a06e-7275b91bd5f3`;
- DEV rollback Worker version: `f7970197-d3dc-4122-afc2-f61c972cfd25`;
- DEV deployed at: `2026-09-24T19:41:05.035211Z`;
- six release assets were the only pre-deploy drift; all ten critical PROD assets are now **CURRENT**;
- full live-readonly gate and fail-closed smoke: **PASS**;
- `nucleo-a` first-device candidate is **READY** on Linux x86_64 with public installer/manifest byte parity and Agent **0.3.6**.

## 6. Device pairing / credential review

The reviewed pairing model is structurally sound:
- pairing token is generated randomly;
- only its SHA-256 hash is stored in D1;
- pairing is one-time;
- a new pairing token supersedes any prior current token for the same tenant/subject;
- expiry and supersession are checked;
- device credential is random and only its hash is stored in D1;
- device selection is tenant-bound;
- revocation marks the device REVOKED;
- revocation removes device selection;
- revocation cancels matching PENDING/EXECUTING calls;
- Linux config uses `umask 077` and file mode 0600;
- Windows config protects the token through the user credential mechanism and explicit ACLs.

Do not weaken these properties.

## 7. Closed architecture / security gates

Canonical coordination remains GitHub issue #65.

Closed:
- PROD portal schema: `hara.commander-portal-dashboard.v1` via #77;
- OIDC callback terminal failure cleanup via #68;
- valid-session telemetry no longer gates auth via #68;
- silent Agent outer-loop failures removed / support diagnostics added via #68;
- idle call polling no longer mutates presence via #68;
- REVIEWER tenant-wide destructive authority removed via #71;
- pairing-token supersession enforced via #73;
- portal-session retention defined and bounded via #75;
- selection/revoke/enqueue/complete lifecycle races closed via #76;
- cross-origin browser portal mutations denied via #78;
- Astra pre-test UI hardening reconciled via #79;
- post-auth device claim cannot race past revocation via #81;
- concurrent invite claim cannot overwrite the winning identity via #82;
- post-deploy public fail-closed checks deny unauthenticated portal/device/internal MCP access and disable PROD dev routes;
- runtime drift proof covers all 10 critical public customer assets, not only the UI shell;
- signed-in identity is rendered once in the global top header; duplicated internal workspace user chips were removed via #89.

Do not reopen these as unresolved unless a current runtime/source readback proves regression.

## 8. Remaining gates after PROD promotion

The deterministic source and runtime promotion gates are closed. Remaining work now requires homologation or later product maturity:

1. **Human auth homologation**
   - fresh private browser;
   - login / callback;
   - authenticated header;
   - logout;
   - account switch;
   - no DEV redirect / stale loop.

2. **First real device E2E**
   - run the non-mutating first-device candidate preflight on the intended Linux host;
   - first PROD pairing;
   - Agent heartbeat;
   - selected-device online/offline behavior;
   - governed five-tool call path;
   - revoke and expiry behavior.
   - current candidate evidence: `nucleo-a` is **READY** on Linux x86_64 with no prior Commander enrollment/residue, systemd-user persistence ready, public installer/manifest byte parity and public Agent 0.3.6 reachable; custom XDG roots are inspected correctly and relative XDG roots fail closed.

3. **Quota runtime proof**
   - hara-platform PR #1158 closed the source compensation gap;
   - live PROD reserve -> release -> terminal replay denial is now proven with `commander_e2e_harness.py quota-roundtrip`, with net usage zero;
   - real COMMIT remains pending until a real `hara.functions.invoke` finishes on a paired device and returns a receipt SHA-256.

4. **Final client activation contract**
   - keep ChatGPT/Codex actions disabled / `Em homologação` until ordinary E2E passes;
   - then define the final OAuth/configuration customer flow.

5. **Installer bootstrap supply chain**
   - release manifest + SHA256SUMS cover both installers and both Agents;
   - Linux enforces Agent SHA-256, release version and dynamic self-test before acceptance;
   - Agent 0.3.5 added the same fail-closed functional self-test requirement to Windows install and update, after SHA/version/syntax validation;
   - Agent 0.3.5 additionally requires fresh local startup attestation for the expected version before install/update success on both Linux and Windows;
   - Agent 0.3.6 additionally denies HTTP redirects for credential-bearing Agent/installer transport on both platforms;
   - the public runtime drift gate covers installers, Agents, manifest and checksums byte-for-byte;
   - the customer-visible Linux bootstrap now requires HTTPS/TLS 1.2+, fails on any redirect and pins `HARA_COMMANDER_URL` to the canonical PROD origin before piping to `bash`;
   - the customer-visible Windows bootstrap now sets `-MaximumRedirection 0`, pins `HARA_COMMANDER_URL` to canonical PROD during execution and restores the caller's previous environment value afterward;
   - the initial bootstrap still trusts the Commander HTTPS origin and has no independent trust anchor yet;
   - independent package/signature trust remains a later product-maturity target and must not be represented as already solved.

6. **Offline-selection semantics**
   - current contract intentionally preserves selection of an ACTIVE but offline device;
   - UI renders it as Offline and invocation refuses an offline device;
   - revisit only if product semantics change.

## 9. Production promotion — CLOSED

The promotion was executed in the required order:

```text
1. pre-migration live gate: migration=PENDING, assets=STALE
2. D1 export backup + SHA-256 receipt
3. apply 0009_pairing_supersession.sql
4. readback: migration=APPLIED
5. deploy canonical source commit da28e040...
6. verify Cloudflare Worker version at 100%
7. verify public health/auth
8. verify assets=CURRENT
```

Current deployment:
- deployable source: `fecd6e79cd9d4d997c4e93ca2143b879153bb197`;
- Worker version: `afbba7d5-5219-4abc-be06-7df48d218505`;
- rollback version: `cd1d27b8-a574-46ff-83f9-f05f8cdef5bb`;
- deployed after PR #118 canonical bootstrap-origin pinning;
- migration 0009: **APPLIED**;
- runtime assets: **CURRENT**;
- public health/auth: **PASS**;
- public fail-closed smoke: **PASS**;
- OIDC transaction hygiene: **PASS**, 10-minute window, expired=0 in latest readback;
- pairing/session retention eligibility: **0** in latest readback;
- Agent release: **0.3.6**;
- Agent startup attestation on install/update: **READY**;
- customer-visible Linux/Windows bootstrap commands deny redirects and pin enrollment to canonical PROD even when a stale `HARA_COMMANDER_URL` is inherited.

Current DEV runtime:
- Worker `hara-commander-dev-v2`: `27de9c54-2dda-4462-82d9-a13772ce0d95`;
- rollback DEV Worker: `0e466497-0ccf-4cbc-bc1c-83de0d82243f`;
- health: **DEV / REMOTE_DEV / HARA Identity configured**;
- bootstrap command assets: byte-equal to canonical source after propagation readback.

The HTML runtime validator permits only one known Cloudflare Browser Insights beacon injection when comparing `/`; after removing that single known injected script, the HTML must match source exactly. The other nine critical assets (JS/CSS, installers, Agents, release files and brand asset) remain byte-exact checks.

Do not reapply migration 0009 while readback reports `APPLIED`.
Do not redeploy solely to reproduce this promotion receipt; future deployment should happen only for a reviewed source change.

## 10. Known non-blocking operational items

These are non-blocking operational follow-ups and are not current Commander source blockers:
- Identity SMTP 587/STARTTLS remains a **non-blocking fallback/maturity item**. Supported Admin REST read was previously authority-blocked (HTTP 403), and the current automation environment will not expose/manipulate the PAT to bypass that safely. The existing read-only backend validator currently reports `IDENTITY_SMTP_BRANDING=PASS`, TLS enabled on the provider, and `IDENTITY_SMTP_TLS_ALIGNMENT=PENDING_587_STARTTLS_FALLBACK`. The observed `ZITADEL_TLS_ENABLED=false` is only the internal ZITADEL listener behind the TLS proxy, not SMTP evidence. A supported Admin-API helper exists to align to port 465, but it was **not** executed because password-preservation semantics on the deprecated full-config endpoint are not explicit enough for a safe blind mutation;
- Login V2 custom-translation warning previously recurred as `Error fetching custom translations: Error: fetch() returned undefined`. The running v4.16 bundle shows this warning comes from `getHostedLoginTranslation()`, after which bundled locale JSON remains the fallback. A fresh one-hour log window on 2026-09-24 showed **0 occurrences** while the container remained healthy. Treat this as upstream/transient unless current logs and user-visible behavior prove regression; do not patch around it blindly;
- device count remains zero until first production pairing.

## 11. Do not repeat

Do not:
- reapply the Login Policy redirect while backend readback is PASS;
- edit ZITADEL projections or event-store rows directly;
- redo the HARA Identity `hara.8` recovery promotion;
- redo PKCE/account-switch changes already merged;
- redo OIDC expired-transaction cleanup already merged;
- expose device tokens, PATs or D1 export download URLs in Git evidence;
- enable arbitrary shell or generic filesystem access;
- publish fake ChatGPT/Codex actions;
- publish Standard/Scale as active plans before their backend contracts exist;
- reapply migration `0009_pairing_supersession.sql` while PROD readback says `APPLIED`;
- redeploy the already-promoted Worker only to reproduce evidence;
- deploy future source implicitly when merging;
- overwrite Astra's original local dirty UI worktree;
- merge or revive PR #66 backend; it is superseded by #79.

## 12. Exact next gates

Order of execution from the current promoted state:

1. Run the consolidated live-readonly gate and require:
   - migration 0009 = `APPLIED`;
   - public assets = `CURRENT`;
   - Worker version = `daf0cc4b-9372-4165-8c94-c2decefa221f`.
2. Perform the human browser homologation:
   - fresh private browser;
   - login / callback;
   - authenticated header;
   - logout;
   - account switch;
   - no DEV redirect or stale-login loop.
3. Pair the first real PROD device.
4. Prove heartbeat, selected-device online/offline behavior, revoke and call expiry.
5. Run the canonical `commander_e2e_harness.py five-tool` proof against the paired/selected online device.
6. Require the invoke leg to COMMIT quota with the Agent-generated receipt and the receipts.get leg to retrieve that receipt; release is already proven live independently.
7. Only then enable/finalize ChatGPT/Codex customer activation.
8. Advance billing/commerce only after ordinary auth + device + MCP E2E is stable.

## 13. Validation commands

Consolidated pre-PROD gate:

```bash
python3 apps/commander/scripts/validate_preprod_readiness.py
```

Current canonical live-readonly gate after promotion:

```bash
python3 apps/commander/scripts/validate_preprod_readiness.py \
  --live-readonly \
  --expect-prod-migration applied \
  --expect-prod-assets current \
  --expect-prod-worker-version afbba7d5-5219-4abc-be06-7df48d218505
```

This command is the current production convergence proof. If a future reviewed deployment changes the Worker version, update the expected version only after that deployment is intentionally promoted.

Public Identity / Commander login runtime:

```bash
python3 apps/identity-login/scripts/validate_live_white_label.py
```

Commander static contract:

```bash
python3 apps/commander/scripts/validate_prod_static.py
```

Device installers:

```bash
python3 apps/commander/scripts/validate_device_installers.py
```

First Linux device candidate preflight (non-mutating; run on the intended host before generating/using a pairing token):

```bash
python3 apps/commander/scripts/commander_first_device_preflight.py --json
```

Expected terminal marker: `COMMANDER_FIRST_DEVICE_CANDIDATE=READY`.

Bootstrap / release supply-chain posture:

```bash
python3 apps/commander/scripts/validate_bootstrap_supply_chain.py
```

Expected posture markers include:
- `COMMANDER_AGENT_POST_BOOTSTRAP_INTEGRITY=PASS`
- `COMMANDER_RELEASE_RUNTIME_ATTESTATION=READY`
- `COMMANDER_BOOTSTRAP_INITIAL_TRUST=WEB_ORIGIN`
- `COMMANDER_BOOTSTRAP_INDEPENDENT_TRUST_ANCHOR=PENDING_MATURITY`

Pairing supersession:

```bash
python3 apps/commander/scripts/validate_pairing_supersession.py
```

Production D1 readback:

```bash
python3 apps/commander/scripts/commander_prod_readback.py --attempts 3
```

Explicit migration-state readback:

```bash
python3 apps/commander/scripts/commander_prod_readback.py \
  --attempts 3 \
  --expect-migration-0009 applied
```

Current canonical expectation is `applied`. Do not reapply migration 0009 while this passes.

Public runtime asset drift readback:

```bash
python3 apps/commander/scripts/validate_prod_runtime_drift.py --expect-assets current
```

Current canonical expectation is `current`. During an intentional partial asset rollout, `mixed` is a valid temporary expected state and may be requested explicitly with `--expect-assets mixed`; it must return to `current` after deployment. The validator allows only the known Cloudflare Browser Insights beacon injection on HTML before normalized comparison; the other nine critical assets remain byte-exact.

Public fail-closed smoke:

```bash
python3 apps/commander/scripts/validate_prod_fail_closed.py
```

This must deny unauthenticated portal reads/mutations, Agent calls without a device credential, internal MCP calls without the product token, cross-origin portal mutation and PROD dev endpoints.

Worker deployment readback:

```bash
python3 apps/commander/scripts/commander_prod_deployment_readback.py \
  --expect-version afbba7d5-5219-4abc-be06-7df48d218505
```

E2E harness source contract:

```bash
python3 apps/commander/scripts/validate_e2e_harness.py
```

Server-side five-tool payload contract:

```bash
node apps/commander/scripts/validate_device_tool_contract.mjs
```

The Worker must reject non-canonical payloads before queueing and must deny any invoke function other than `device.info` before quota reservation.

Reversible live quota proof (requires the local 0600 MCP product-token file and the OIDC identity passed at runtime; never commit either value):

```bash
python3 apps/commander/scripts/commander_e2e_harness.py quota-roundtrip \
  --token-file /path/to/local/mcp-product-token \
  --issuer https://auth.haralabs.com.br/ \
  --subject '<oidc-subject>'
```

After the first real device is paired, selected and online, run the same harness in full mode:

```bash
python3 apps/commander/scripts/commander_e2e_harness.py five-tool \
  --token-file /path/to/local/mcp-product-token \
  --issuer https://auth.haralabs.com.br/ \
  --subject '<oidc-subject>'
```

The harness never prints the product token. Its invoke leg reserves quota, releases on failure, and commits only after a completed Agent call returns a 64-hex receipt SHA-256. If a commit/release response is lost after server processing, it reconciles the same request_id through the existing idempotent authorize readback; COMMITTED is accepted only with the exact receipt SHA-256 and RELEASED only from the terminal RELEASED state. The five-tool proof also requires one stable selected device for the entire run, exact call/request/device/tool correlation, Agent version parity with the public release manifest, semantic tool-result validation, and receipt provenance bound to the invoke device_id + request_id + OUTBOUND_RELAY + canonical receipt SHA-256.

JavaScript syntax:

```bash
node --check apps/commander/public/app.js
node --check apps/commander/src/worker.js
node --check apps/commander/src/auth.js
```

Repository hygiene:

```bash
git diff --check
```

## 14. Current coordination references

- PR #64 — Login V2 runtime redirect convergence — **MERGED**
- PR #66 — old pre-test UX/backend branch — **CLOSED / SUPERSEDED**
- PR #68 — runtime reliability / Agent hardening — **MERGED**
- PR #69 — bounded device-call lifecycle — **MERGED**
- PR #70 — unsafe auth return-target fix — **MERGED**
- PR #71 — REVIEWER least privilege — **MERGED**
- PR #72 — PROD surface / input status hardening — **MERGED**
- PR #73 — pairing-token supersession — **MERGED**
- PR #75 — portal-session retention — **MERGED**
- PR #76 — device lifecycle races — **MERGED**
- PR #77 — production contract cleanup — **MERGED**
- PR #78 — portal mutation same-origin guard — **MERGED**
- PR #79 — reconciled Astra UI snapshot — **MERGED**
- PR #81 — revoked-device claim TOCTOU hardening — **MERGED**
- PR #82 — invite identity-claim serialization — **MERGED**
- PR #83 — latest race proofs added to consolidated readiness — **MERGED**
- PR #84 — migration 0009 state-aware PROD readback — **MERGED**
- PR #85 — public runtime drift gate — **MERGED**
- PR #86 — PROD promotion receipt / Worker deployment proof — **MERGED**
- PR #87 — post-deploy fail-closed + 10-asset runtime gates — **MERGED**
- PR #89 — single signed-in identity in workspace UI — **MERGED**
- PR #91 — dead internal user-chip CSS cleanup — **MERGED**
- PR #92 — canonical E2E/quota harness — **MERGED**
- PR #93 — Agent 0.3.4 supply-chain hardening — **MERGED**
- PR #94 — E2E product-token origin / redirect hardening — **MERGED**
- PR #95 — server-side five-tool payload contract — **MERGED**
- PR #96 — Agent 0.3.4 runtime rollout receipt — **MERGED**
- PR #97 — ambiguous E2E quota-state reconciliation — **MERGED**
- PR #98 — Agent 0.3.5 startup attestation — **MERGED + PROMOTED**
- PR #99 — Agent 0.3.5 runtime rollout receipt — **MERGED**
- PR #100 — non-mutating first-device candidate preflight — **MERGED**
- PR #101 — session-retention readback clarification — **MERGED**
- PR #102 — retention state surfaced in readiness — **MERGED**
- PR #103 — terminal pairing retention — **MERGED + PROMOTED**
- PR #104 — bounded OIDC transaction hygiene — **MERGED + PROMOTED**
- PR #105 — five-tool semantic result validation — **MERGED**
- PR #106 — custom-XDG residue correctness in first-device preflight — **MERGED**
- PR #107 — same-device / release-version / request / receipt correlation — **MERGED**
- PR #108 — relative XDG paths denied in first-device preflight — **MERGED**
- PR #110 — local MCP product-token custody hardening — **MERGED**
- PR #111 — first-device public/local installer + manifest parity — **MERGED**
- PR #112 — MCP token symlink-bypass closure / failure-output redaction — **MERGED**
- PR #113 — Agent 0.3.6 redirect fail-closed release — **MERGED + PROMOTED**
- PR #114 — Agent 0.3.6 rollout authority / MIXED drift modeling — **MERGED**
- PR #115 — Windows device-token plaintext lifetime minimization — **MERGED + PROMOTED**
- PR #116 — customer bootstrap redirect denial / Linux TLS floor — **MERGED + PROMOTED**
- PR #117 — bootstrap redirect-hardening rollout authority — **MERGED**
- PR #118 — customer bootstrap canonical enrollment-origin pin — **MERGED + PROMOTED**
- hara-platform PR #1158 — quota finalization compensation source — **MERGED; real-device COMMIT E2E pending**
- issue #65 — Commander post-promotion coordination / residual homologation — **OPEN**

Canonical repository state at this checkpoint: `main` = `fecd6e79cd9d4d997c4e93ca2143b879153bb197`.
Current deployed Commander runtime source: `fecd6e79cd9d4d997c4e93ca2143b879153bb197`.
Current PROD Worker: `afbba7d5-5219-4abc-be06-7df48d218505`; rollback: `cd1d27b8-a574-46ff-83f9-f05f8cdef5bb`.
Current DEV Worker: `27de9c54-2dda-4462-82d9-a13772ce0d95`; rollback: `0e466497-0ccf-4cbc-bc1c-83de0d82243f`.
PRs #110–#112 are operator-tooling/preflight/token-custody hardening. PRs #113/#115/#116/#118 changed deployable/runtime customer assets or behavior and were explicitly promoted.

Continue from current `main`, this guide and the newest issue #65 comments. Do not use PR #66 as a backend source.