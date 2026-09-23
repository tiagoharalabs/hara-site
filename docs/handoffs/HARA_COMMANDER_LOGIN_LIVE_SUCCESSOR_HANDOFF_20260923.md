# H.A.R.A. Commander — login live successor handoff — 2026-09-23

State: **DEFAULT REDIRECT LIVE ALIGNED / CODE HARDENING LIVE / HUMAN BROWSER RETEST NEXT**

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

## Do not repeat

Do not reapply the default redirect unless readback proves drift. Do not edit ZITADEL projections/event-store rows. Do not repeat HARA Identity recovery hara.8 promotion, PKCE/account-switch fixes, OIDC transaction cleanup, Cloudflare AUD lookup, or product-token provisioning.

## Exact next gate

Human browser retest in production:

1. open `https://commander.haralabs.com.br`;
2. sign out if an old session exists;
3. click `Entrar`;
4. complete HARA Identity login;
5. prove return to Commander production origin and authenticated session/UI;
6. test `Sair`;
7. test `Usar outra conta`;
8. confirm no redirect to DEV and no stale-login loop.

Only after this login gate passes should the first real production device pairing begin.
