# H.A.R.A. Commander — Auth-config transient false-state recovery

Date: 2026-10-07 / 2026-10-08 UTC

## Incident

The Commander login UI could show:

`O HARA Identity ainda não está disponível para autenticação.`

while H.A.R.A. Identity itself was healthy.

Observed backend state during the incident:
- public H.A.R.A. Identity login: HTTP 200
- OIDC discovery: HTTP 200
- OAuth authorization-server metadata: HTTP 200
- Identity containers: healthy
- Identity container restart counts: 0
- recent Identity proxy 429/5xx: none observed
- Commander `/api/portal/auth-config`: HTTP 200 with `{"configured":true}`

## Root cause

`authProviderConfigured` is initialized false in the browser.

A transient failure or timing window around the initial
`/api/portal/auth-config` fetch could leave that advisory browser flag false.
`startRemoteAuth()` then blocked navigation locally and showed the unavailable
toast without allowing the authoritative server-side `/auth/login` route to
decide.

This created a false-negative login state even when OIDC was configured and
healthy.

## Fix

`startRemoteAuth()` is now asynchronous.

If the advisory browser state is false it re-runs `configureAuthUi()`, but it
does not use that cached/advisory state as a hard login gate.

The server-side `/auth/login` route remains the authority and continues to
fail closed if OIDC is actually not configured.

Permanent static gate:

`COMMANDER_PROD_AUTH_CONFIG_TRANSIENT_FAILURE_DOES_NOT_BLOCK_LOGIN=PASS`

## DEV proof

Only `app.js` changed.

DEV Version:
`114739fd-31a3-4156-bd23-b41ac6962299`

Live DEV:
- hotfix marker: PASS
- stale blocking toast: absent
- `/api/portal/auth-config`: configured=true
- login path reached H.A.R.A. Identity

## PROD promotion

Source commit:
`5de744e31edc661644d0c712f8ddb3ea2825027a`

PROD Version:
`512554c5-4102-4d55-84a9-6922152f682e`

Deployment:
`e73e8b3d-4e72-4dde-b40a-43b43c4592ce`

Traffic:
100%

Rollback Version:
`91a870b7-e84a-4f70-95df-d3be1367f190`

Promotion guards:
- preflight PASS
- required secrets PASS
- Worker PASS
- triggers PASS
- exact readback PASS
- runtime assets PASS

## PROD live readback

- hotfix marker: PASS
- stale blocking toast: ABSENT
- `/api/portal/auth-config`: `{"configured":true}`
- GET `/auth/login?return_to=/#devices`: HTTP 302
- redirect target: H.A.R.A. Identity OAuth authorize endpoint
- PKCE method: S256

## Identity boundary

No H.A.R.A. Identity container, ZITADEL database, DCR mode or Identity runtime
configuration was modified by this hotfix.

DCR remains intentionally closed and is unrelated to normal Commander OIDC
login.

State:

`COMMANDER_AUTH_CONFIG_FALSE_STATE_RECOVERY=CLOSED_PASS`
