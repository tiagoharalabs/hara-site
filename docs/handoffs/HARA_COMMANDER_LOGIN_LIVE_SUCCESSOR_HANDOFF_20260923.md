# H.A.R.A. Commander — login live successor handoff — 2026-09-23

State: **BACKEND DEFAULT REDIRECT ALIGNED / LOGIN V2 RUNTIME CONVERGED / HUMAN BROWSER RETEST NEXT**

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

## Do not repeat

Do not reapply the default redirect unless backend readback proves drift. Do not edit ZITADEL projections/event-store rows. Do not repeat HARA Identity recovery hara.8 promotion, PKCE/account-switch fixes, OIDC transaction cleanup, Cloudflare AUD lookup, or product-token provisioning.

## Exact next gate

1. open `https://commander.haralabs.com.br` in a fresh human browser session;
2. complete HARA Identity login;
3. prove return to Commander production origin and authenticated session/UI;
4. test `Sair`;
5. test `Usar outra conta`;
6. confirm no redirect to DEV, no stale-login loop and no unauthenticated UI flash.

Keep the ZITADEL API and Postgres untouched. Only after this login gate passes should the first real production device pairing begin.
