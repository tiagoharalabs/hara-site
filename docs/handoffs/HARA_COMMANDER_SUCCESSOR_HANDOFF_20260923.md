# H.A.R.A. Commander — successor guide — 2026-09-23

Status: **LOGIN RUNTIME CONVERGED / PRE-TEST HARDENING IN PROGRESS / HUMAN RETEST DEFERRED / DEVICE E2E NOT YET OPEN**

This is the canonical successor guide for the Commander front as of 2026-09-23 after the Login V2 runtime convergence work and the pre-test usability/security sweep.

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

## 4. Current pre-test hardening

Active PR:

- PR #66 — `fix(commander): harden pretest usability and safety`
- branch: `fix/commander-ux-pretest-20260923`
- published head observed during this sweep: `9f53eb0dabf44a8ad3a290b1a0093eb97c1f314f`
- GitHub Actions `HARA Site Main Provenance Guard`: **SUCCESS** for that published head.

The Astra front is actively working on this branch. During the sweep, local uncommitted work was observed in:
- `apps/commander/public/app.js`
- `apps/commander/public/index.html`
- `apps/commander/public/styles.css`
- `apps/commander/scripts/validate_prod_static.py`

Do not overwrite or reset those files while Astra is active.

PR #66 already covers or is actively covering:
- authenticated-session gating for protected app routes;
- PROD `?api=` override blocked outside localhost;
- QA `?scenario=` override blocked outside localhost;
- auth-error URL/view/banner alignment;
- honest logout failure behavior;
- removal of fake/demo production actions;
- Trial visible quota aligned to live PROD D1: **100 executions/month**;
- Standard/Scale no longer represented as active commercial PROD plans;
- selected-device UX: none / online / offline;
- pairing UX converted to explicit 1 -> 2 -> 3 flow;
- visible pairing expiry and retry UX;
- confirmation before device revocation;
- portal revoke aligned with Agent self-revoke by cancelling pending/executing calls;
- same-origin enforcement on portal mutation routes;
- mobile Support access;
- keyboard focus treatment;
- customer-facing Portuguese role labels and page titles;
- removal of dead Google Font dependency blocked by CSP;
- activity/history no longer falsely represented as available when current portal API exposes aggregate usage only;
- legal links and revocation-confirmation UX were being refined locally during the latest sweep.

Source merge alone does **not** publish the Commander Worker. Deployment must remain explicit.

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
- expiry is checked;
- device credential is random and only its hash is stored in D1;
- device selection is tenant-bound;
- revocation marks the device REVOKED;
- revocation removes device selection;
- revocation cancels matching PENDING/EXECUTING calls;
- Linux config uses `umask 077` and file mode 0600;
- Windows config protects the token through the user credential mechanism and explicit ACLs.

Do not weaken these properties.

## 7. Astra coordination authority

Canonical coordination issue:

- GitHub issue #65 — `[ASTRA REVIEW][COMMANDER] Pre-test UX/runtime decisions before browser homologation`

Use #65 for architecture/contract decisions that should not be silently made by a parallel front.

### Already recorded decisions/questions before this sweep

#### A. PROD dashboard schema still says dev

`/api/portal/dashboard` currently exposes:

```text
hara.commander-portal-dashboard-dev.v1
```

Decision required:
- rename to `hara.commander-portal-dashboard.v1`; or
- carry an explicit compatibility/version transition.

Do not silently mutate a versioned public contract.

#### B. Installer bootstrap supply-chain posture

Current bootstrap remains trust-on-first-web-response:

Linux:
```text
curl -fsSL https://commander.haralabs.com.br/install/linux.sh | bash
```

Windows:
```text
irm https://commander.haralabs.com.br/install/windows.ps1 | iex
```

The downloaded Agent itself is later verified through release manifest + SHA256, but the bootstrap script is trusted directly from the origin.

Product-maturity decision still needed:
- signed bootstrap;
- pinned release artifact/hash;
- packaged installer;
- or another canonical mechanism.

#### C. Persistent offline selected-device semantics

Current backend permits an ACTIVE device to remain selected while offline.

Current UX direction:
- no selection -> Aguardando;
- selected online -> Pronto;
- selected offline -> Offline.

Astra should confirm whether persistent offline selection is canonical.

## 8. New findings from this parallel sweep

The following were added to issue #65 for Astra.

### D. OIDC callback failure leaves transaction cookie residue — LOW/MEDIUM

On provider cancel/error and several callback-validation failures, `finishLogin()` throws and the global callback handler redirects to `/?auth_error=...#login`.

The transaction cookie `hara_commander_oidc_tx` is not cleared on those terminal failure paths and can remain for up to 10 minutes.

Recommended fix:
- clear the OIDC transaction cookie on every terminal callback failure;
- preserve sanitized auth-error redirect;
- preserve replay/state validation.

Issue comment: `5805482038`.

### E. Valid portal session depends on non-essential D1 write — MEDIUM

`resolvePortalSession()` correctly validates:
- session exists;
- not revoked;
- not expired;
- user ACTIVE;
- tenant ACTIVE.

After that, every successful session resolution synchronously executes:

```sql
UPDATE portal_sessions SET last_seen_at_utc = ? WHERE session_hash = ?
```

A transient D1 write failure can therefore convert a valid authenticated read into HTTP 500 even though `last_seen_at_utc` is not an authorization predicate.

Recommended direction:
- make the touch bounded/coalesced;
- or make it best-effort after successful authorization;
- keep all expiry/revocation/account checks fail-closed.

Issue comment: `5805482038`.

### F. Agent outer-loop errors are silently swallowed — HIGH usability/operability

Linux Agent:

```python
except Exception:
    pass
```

Windows Agent:

```powershell
catch {
}
```

DNS, TLS, token, API or configuration failures can leave the service/task apparently running with no operator-visible diagnosis.

Recommended pre-homologation minimum:
- bounded/rate-limited local error log;
- timestamp + sanitized error class/code only;
- no token or sensitive payload leakage;
- Support/Doctor surfaces latest runtime error;
- Support/Doctor exposes last successful heartbeat;
- avoid per-poll log spam.

Issue comment: `5805482038`.

### G. HIGH — call polling creates about 43,200 D1 presence writes/day/device

Both Agents currently poll `/api/device/calls/next` every 2 seconds.

There is already an explicit heartbeat every 30 seconds.

However `claimNextDeviceCall()` currently executes:

```sql
UPDATE commander_devices SET last_seen_at_utc = ?
```

on every poll, including the 204/no-call path.

Idle cost:
- ~30 polls/minute;
- ~43,200 presence writes/day/device;
- plus the actual heartbeat writes.

Recommended fix before broader customer testing:
1. remove presence mutation from empty call polling;
2. treat explicit heartbeat as canonical presence;
3. optionally refresh on actual call claim only;
4. consider bounded 5-10s polling with jitter until a proper long-poll/relay mechanism exists;
5. add a proof that no-call polling does not mutate presence.

Issue comment: `5805490671`.

### H. REVIEWER authorization requires explicit decision

`revokePortalDevice()` currently treats these as privileged:

```text
OWNER
ADMIN
REVIEWER
```

Those roles can revoke any ACTIVE device in the tenant.
`MEMBER` can only revoke a device it enrolled itself.

No role-capability matrix was found that establishes REVIEWER as an administrative destructive role.

Because the reviewer identity is currently used for homologation, Astra must confirm:
- REVIEWER intentionally admin-equivalent; or
- tenant-wide revocation should be limited to OWNER/ADMIN.

Issue comment: `5805495811`.

### I. Portal-session retention is undefined

OIDC transactions have bounded expired-row cleanup.
`portal_sessions` currently have no equivalent cleanup path.

PROD already contains one expired/unrevoked historical session row.

No deletion was executed by this front because retention must be governed.

Decision required:
- retention window for expired/revoked portal sessions;
- cleanup owner/mechanism:
  - bounded login-time hygiene;
  - scheduled maintenance;
  - or another governed retention job.

Issue comment: `5805502910`.

## 9. Other unresolved architecture gates already in #65

These remain open unless Astra records an explicit decision.

### Pairing-token supersession

Creating a new pairing token does not invalidate previous unconsumed tokens for the same tenant/subject.

Decision:
- allow multiple simultaneously valid one-time tokens; or
- enforce one active pairing token per tenant/subject.

If enforcing one active token, implement with a safe D1 transition and proof.

### Quota release after CANCELLED / EXPIRED device calls

Revocation now cancels PENDING/EXECUTING calls, but the end-to-end MCP caller/orchestrator still needs proof that terminal `CANCELLED` / `EXPIRED` states reliably cause `/api/internal/mcp/release` for previously RESERVED usage.

Do not assume quota is released until this is traced/proven.

### ChatGPT / Codex activation contract

Production UI should remain honest / disabled / `Em homologação` until first real production pairing and governed client E2E are proven.

Astra should define the final customer action:
- OAuth launch;
- client configuration instructions;
- or another canonical connection flow.

### Product claims

Before any customer-facing activation, revalidate:
- read-only V1 wording;
- Trial wording;
- future Standard/Scale wording;
- visible grant names;
- any entitlement/capacity claim.

## 10. Known non-blocking operational items

These should not be confused with the current login/runtime blocker:
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
- overwrite Astra's active dirty UI files.

## 12. Exact next gates

Order of execution:

1. Astra reviews/absorbs the high-priority #65 findings, especially:
   - G — D1 write amplification from 2s polling;
   - F — silent Agent runtime failures.
2. Resolve or explicitly defer architecture decisions that affect the browser/device homologation contract:
   - pairing-token supersession;
   - quota release for CANCELLED/EXPIRED;
   - REVIEWER privileges;
   - dashboard schema naming;
   - offline selection semantics;
   - final ChatGPT/Codex activation contract.
3. Complete PR #66 and CI.
4. Merge PR #66 without overwriting Astra's active work.
5. Explicitly deploy the reviewed Commander Worker.
6. Only then perform the human browser test:
   - fresh private browser;
   - login with HARA Identity;
   - return to Commander PROD;
   - authenticated user visible in header;
   - no stale unauthenticated flash;
   - logout;
   - `Usar outra conta`;
   - no DEV redirect;
   - no stale-login loop.
7. After login gate passes, perform first real production device pairing on `nucleo-a`.
8. Prove selected-device online/offline semantics.
9. Prove governed device-call E2E.
10. Prove quota commit/release behavior.
11. Only after ordinary auth + device + MCP E2E is stable should billing/commerce be advanced.

## 13. Validation commands

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
- PR #66 — Commander pre-test usability/safety hardening — **OPEN / ASTRA ACTIVE**
- issue #65 — Astra architectural review / pre-test decisions — **OPEN**
- this file — canonical successor guide for continuation after the 2026-09-23 sweep

When continuing this front, read this guide, then read the newest comments on issue #65 and the latest head/diff of PR #66 before changing Commander source.
