# H.A.R.A. Commander — successor guide — 2026-09-23

Status: **SOURCE PRE-PROD READY / PROD NOT PROMOTED / HUMAN HOMOLOGATION DEFERRED / DEVICE E2E NOT YET OPEN**

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

The human browser homologation test is intentionally deferred until pre-test hardening is reviewed and deliberately deployed.

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

Current source gate:
```text
COMMANDER_SOURCE_PREPROD_READY=PASS
COMMANDER_IDENTITY_LIVE_READONLY=PASS
COMMANDER_PROD_D1_LIVE_READONLY=PASS
COMMANDER_PROD_D1_MIGRATION_0009=PENDING_PROMOTION_GATE
COMMANDER_PROD_WORKER_DEPLOYMENT=PENDING_PROMOTION_GATE
COMMANDER_HUMAN_HOMOLOGATION=PENDING_OPERATOR_GATE
COMMANDER_FIRST_DEVICE_E2E=PENDING_HOMOLOGATION
```

Source merge alone does **not** publish the Commander Worker. Deployment remains explicit.

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

Latest structural PROD readback during the pre-test hardening:
- devices = 0;
- selections = 0;
- calls = 0;
- active portal sessions = 0;
- foreign-key/integrity defects = 0;
- one historical expired/unrevoked portal session remains as retention hygiene.

No real production device has been paired yet.

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
- concurrent invite claim cannot overwrite the winning identity via #82.

Do not reopen these as unresolved unless a current runtime/source readback proves regression.

## 8. Remaining pre-PROD gates

The remaining work is no longer basic source hardening:

1. **Promotion order / runtime convergence**
   - apply PROD D1 migration `0009_pairing_supersession.sql`;
   - only after migration success, deploy the current Commander Worker/assets;
   - verify the deployed runtime against the canonical source.

2. **Human auth homologation**
   - fresh private browser;
   - login / callback;
   - authenticated header;
   - logout;
   - account switch;
   - no DEV redirect / stale loop.

3. **First real device E2E**
   - first PROD pairing;
   - Agent heartbeat;
   - selected-device online/offline behavior;
   - governed five-tool call path;
   - revoke and expiry behavior.

4. **Quota runtime proof**
   - hara-platform PR #1158 closed the source compensation gap;
   - runtime promotion and real commit/release E2E still require proof.

5. **Final client activation contract**
   - keep ChatGPT/Codex actions disabled / `Em homologação` until ordinary E2E passes;
   - then define the final OAuth/configuration customer flow.

6. **Installer bootstrap supply chain**
   - downloaded Agent artifacts are hash-verified;
   - bootstrap scripts still trust the Commander origin and remain a future maturity hardening target.

7. **Offline-selection semantics**
   - current contract intentionally preserves selection of an ACTIVE but offline device;
   - UI renders it as Offline and invocation refuses an offline device;
   - revisit only if product semantics change.

## 9. Exact production promotion contract

Current source references `device_pairing_tokens.superseded_at_utc`.

Therefore deployment ordering is mandatory:

```text
1. PROD D1 migration 0009_pairing_supersession.sql
2. verify migration/readback
3. deploy current Commander Worker + assets
4. verify health/static/runtime contract
5. human browser homologation
6. first real device pairing
7. governed device-call + quota E2E
```

Never deploy the current Worker before migration 0009.
No PROD promotion has been performed by this hardening front.

## 10. Known non-blocking operational items

These are non-blocking operational follow-ups and are not current Commander source blockers:
- Identity SMTP TLS alignment still reports the historical 587/STARTTLS fallback pending state;
- Login V2 logs previously showed a custom-translation fetch warning; no user-visible blocker was proven from it;
- device count remains zero until first production pairing.

## 11. Do not repeat

Do not:
- reapply the Login Policy redirect while backend readback is PASS;
- edit ZITADEL projections or event-store rows directly;
- redo the HARA Identity `hara.8` recovery promotion;
- redo PKCE/account-switch changes already merged;
- redo OIDC expired-transaction cleanup already merged;
- expose device tokens or PATs in logs/evidence;
- enable arbitrary shell or generic filesystem access;
- publish fake ChatGPT/Codex actions;
- publish Standard/Scale as active plans before their backend contracts exist;
- start the human browser test while the operator has explicitly deferred it;
- deploy the Commander Worker implicitly when merging source;
- overwrite Astra's original local dirty UI worktree;
- merge or revive PR #66 backend; it is superseded by #79;
- deploy a Worker referencing `superseded_at_utc` before migration 0009.

## 12. Exact next gates

Order of execution:

1. Run the consolidated pre-PROD source gate.
2. If promotion is opened:
   - apply migration 0009 to PROD D1;
   - run PROD readback;
   - deploy current Worker/assets;
   - verify runtime health and public contract.
3. Open the human browser homologation gate only after runtime convergence.
4. Perform login/callback/logout/account-switch tests.
5. Pair the first real PROD device.
6. Prove heartbeat, selection, offline behavior, revoke and call expiry.
7. Prove governed MCP call E2E and quota commit/release.
8. Only then enable/finalize ChatGPT/Codex customer activation.
9. Advance billing/commerce only after ordinary auth + device + MCP E2E is stable.

## 13. Validation commands

Consolidated pre-PROD gate:

```bash
python3 apps/commander/scripts/validate_preprod_readiness.py
```

Include current public Identity and PROD D1 read-only checks:

```bash
python3 apps/commander/scripts/validate_preprod_readiness.py --live-readonly
```

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

Pairing supersession:

```bash
python3 apps/commander/scripts/validate_pairing_supersession.py
```

Production D1 readback:

```bash
python3 apps/commander/scripts/commander_prod_readback.py --attempts 3
```

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
- hara-platform PR #1158 — quota finalization compensation source — **MERGED; runtime E2E pending**
- issue #65 — Commander pre-PROD coordination / residual decisions — **OPEN**

Continue from current `main`, this guide and the newest issue #65 comments. Do not use PR #66 as a backend source.