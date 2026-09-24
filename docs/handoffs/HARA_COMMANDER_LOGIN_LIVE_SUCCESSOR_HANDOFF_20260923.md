# H.A.R.A. Commander — login live successor handoff — 2026-09-23

State: **BACKEND DEFAULT REDIRECT ALIGNED / LOGIN V2 RUNTIME CONVERGED / PRE-TEST HARDENING READY FOR REVIEW / HUMAN RETEST DEFERRED BY OPERATOR**

## What is already live

- Commander PROD auth config: `configured=true`, provider `HARA Identity`, client auth `BASIC`.
- `/auth/login` returns HTTP 302 to `https://auth.haralabs.com.br/oauth/v2/authorize`.
- explicit callback remains `https://commander.haralabs.com.br/auth/callback`.
- PKCE S256 remains active.
- regular login and `Usar outra conta` use `prompt=select_account`; account switch adds `max_age=0`.
- expired OIDC transactions are pruned before a new login transaction is created.
- production session readback distinguishes expired sessions from explicit revocation.
- HARA Identity recovery UX is live on `hara.8` and anti-enumeration safe.

## Live identity redirect fix

Operator-applied supported Admin API alignment:

```text
HARA_IDENTITY_LOGIN_POLICY_READ=PASS
HARA_IDENTITY_DEFAULT_REDIRECT_PREVIOUS=https://hara-commander-dev-v2.tiago-sartori.workers.dev/
HARA_IDENTITY_DEFAULT_REDIRECT_CURRENT=https://commander.haralabs.com.br/
HARA_IDENTITY_DEFAULT_REDIRECT_ALIGN=PASS
```

Independent backend validator:

```text
IDENTITY_LOGIN_DEFAULT_REDIRECT=PASS
IDENTITY_RUNTIME_HEALTH=PASS
IDENTITY_LOGIN_IMAGE_VARIANT=PASS_HARA_8
```

## Runtime convergence finding — PASS

The operator restarted only `hara-identity-zitadel-login-1`; the container returned `healthy`. A fresh public Commander PROD login is served with `cf-cache-status: DYNAMIC` and the server-rendered Login V2 payload now contains:

```text
defaultRedirectUri=https://commander.haralabs.com.br/
```

The public validator was corrected to normalize Next.js escaped quotes before checking the rendered setting. Post-restart validation now reports:

```text
HARA_IDENTITY_LOGIN_DEFAULT_REDIRECT_RUNTIME=PASS
COMMANDER_OIDC_REDIRECT=PASS
COMMANDER_OIDC_PKCE=PASS
COMMANDER_ACCOUNT_SELECTION=PASS
```

Live `Usar outra conta` proof also returns `prompt=select_account&max_age=0`. Do not reapply the backend policy.

## Pre-test hardening — source ready for review

The operator explicitly deferred the human browser retest while Commander receives a deeper usability/security pass.

Source branch: `fix/commander-ux-pretest-20260923`.

Validated hardening includes:

- protected workspace routes require a hydrated authenticated session;
- PROD `?api=` and QA `?scenario=` overrides are localhost-only;
- auth-error routing now keeps URL, rendered view and visible banner aligned;
- logout fails honestly instead of pretending the session closed;
- portal mutation routes enforce same-origin browser semantics;
- fake/demo production actions were replaced by honest disabled homologation/roadmap states;
- pairing is presented as an explicit 1 → 2 → 3 flow, with visible expiry, focus/scroll and retry UX;
- device revoke requires confirmation and cancels pending/executing calls in the product DB;
- selected-device UX distinguishes no selection, selected-online and selected-offline states;
- Trial UI now matches live PROD D1: 100 executions/month; Standard and Scale are not represented as active catalog plans;
- per-execution history is labeled as in homologation because the current portal dashboard contract exposes aggregate usage, not activity rows;
- dead Google Font dependencies were removed without relaxing CSP;
- mobile keeps Support reachable while avoiding duplicate logout controls;
- customer-facing copy was simplified while canonical grant codes remain visible in Security.

Full static, installer, Identity and PROD D1 readback suites pass.

Astra coordination: GitHub issue **#65** contains architectural questions that this front will not decide silently: pairing-token supersession, quota release after CANCELLED/EXPIRED device calls, final ChatGPT/Codex activation semantics, versioned PROD dashboard schema naming, bootstrap installer supply-chain posture and persistent offline-device selection semantics.

This repository has no automatic Commander deployment workflow. Merging source does not by itself publish the Commander Worker.

## Do not repeat

Do not reapply the default redirect unless backend readback proves drift. Do not edit ZITADEL projections/event-store rows. Do not repeat HARA Identity recovery hara.8 promotion, PKCE/account-switch fixes, OIDC transaction cleanup, Cloudflare AUD lookup, or product-token provisioning.

## Exact next gate

1. integrate the pre-test hardening through PR/CI without publishing the Worker automatically;
2. incorporate any Astra #65 decision that materially affects the pre-test UX/runtime contract;
3. explicitly deploy the reviewed Commander Worker;
4. only then perform the fresh human browser login/callback, logout and `Usar outra conta` retest;
5. confirm no redirect to DEV, no stale-login loop, no unauthenticated UI flash and no fake/demo product action;
6. after the login gate passes, complete the first real production device pairing.

Keep the ZITADEL API and Postgres untouched. Do not start the human retest until the pre-test hardening/deploy gate is intentionally opened.
