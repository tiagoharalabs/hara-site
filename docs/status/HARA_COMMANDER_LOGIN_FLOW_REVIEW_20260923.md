# H.A.R.A. Commander — login flow review — 2026-09-23

State: **COMMANDER CODE FIXED / IDENTITY DEFAULT REDIRECT LIVE ALIGNED / BROWSER CALLBACK RETEST NEXT**

## Symptoms reviewed

The production login appeared inconsistent: Commander could start an OIDC transaction, but multiple recent attempts did not return to `/auth/callback`. The previous Commander session had already expired.

## Proven findings

### Identity fallback redirect drift

Production ZITADEL projection readback:

```text
projections.login_policies5.default_redirect_uri
=https://hara-commander-dev-v2.tiago-sartori.workers.dev/
```

This is incorrect for production. The canonical target is:

`https://commander.haralabs.com.br/`

The OIDC application still emits the correct explicit production callback when Commander starts a normal auth request. The wrong instance default becomes relevant when Login V2 loses request context or enters a direct/recovery flow.

### Commander session readback bug

The old readback counted every non-revoked DB session as active even after expiry. The corrected query now uses `julianday(expires_at_utc)` and reports the current production state as:

`active_sessions=0`

Expired but non-revoked history is now reported as session hygiene, not structural corruption.

### OIDC transaction accumulation

DEV proof before cleanup:

`OIDC_EXPIRED_TX_BEFORE=86`

After a new login initiation with the corrected code:

`OIDC_EXPIRED_TX_AFTER=0`

Expired OIDC transactions are now deleted before a new browser login transaction is created.

### Account-switch semantics

`Usar outra conta` previously sent `prompt=login`, which reauthenticated the current identity instead of explicitly selecting another account.

Corrected DEV proof:

```text
REGULAR_PROMPT=select_account
OTHER_PROMPT=select_account
OTHER_MAX_AGE=0
COMMANDER_DEV_ACCOUNT_SWITCH=PASS
```

## Canonical Identity correction

New script:

`apps/identity-login/scripts/align_login_default_redirect.py`

The script uses the supported ZITADEL Admin API, preserves the current Login Policy fields and changes only `defaultRedirectUri`, then performs API readback. It never prints the PAT.

`validate_identity_backend.py` now requires the production default redirect to equal `https://commander.haralabs.com.br/`.

## Live policy alignment — PASS

The supported ZITADEL Admin API alignment was executed from the authorized operator path using the secure owner PAT without exposing the PAT value. Readback:

```text
HARA_IDENTITY_LOGIN_POLICY_READ=PASS
HARA_IDENTITY_DEFAULT_REDIRECT_PREVIOUS=https://hara-commander-dev-v2.tiago-sartori.workers.dev/
HARA_IDENTITY_DEFAULT_REDIRECT_CURRENT=https://commander.haralabs.com.br/
HARA_IDENTITY_DEFAULT_REDIRECT_ALIGN=PASS
```

Independent backend validator after the mutation:

```text
IDENTITY_LOGIN_DEFAULT_REDIRECT=PASS
IDENTITY_RUNTIME_HEALTH=PASS
IDENTITY_LOGIN_IMAGE_VARIANT=PASS_HARA_8
```

Do not edit ZITADEL projections or event-store rows directly. The canonical path remains the supported Admin API helper.

## Completion target

```text
HARA_IDENTITY_DEFAULT_REDIRECT_ALIGN=PASS
IDENTITY_LOGIN_DEFAULT_REDIRECT=PASS
COMMANDER_PROD_ACCOUNT_SWITCH=PASS
COMMANDER_PROD_OIDC_TX_RETENTION=PASS
COMMANDER_LOGIN_CALLBACK_E2E=PENDING_BROWSER_RETEST
```
