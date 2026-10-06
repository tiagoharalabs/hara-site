# H.A.R.A. Commander — MCP DCR Guard

Date: 2026-10-06
State: SOURCE/PREPROD CLOSED_PASS; PROD CLOSED GUARD PENDING DEPLOY

## Purpose

Provide a compatibility boundary for MCP clients that still use OAuth Dynamic
Client Registration without exposing ZITADEL's raw registration endpoint.

ZITADEL live preimage before this slice:
- dynamicClientRegistration.enabled = false
- dynamicClientRegistration.allowUnauthenticated = false

No backend DCR setting is changed by the source/preprod slice.

## Design

Dedicated image:
- `hara-identity-dcr-gateway:v0.1.0`

Public route when deployed:
- `/oauth/v2/register` and registration-management descendants
- Traefik priority 800, above the ZITADEL API catch-all

Default runtime mode:
- `closed`

Closed mode:
- health endpoint remains available internally;
- registration and management paths return 404;
- upstream ZITADEL is never contacted.

Guarded mode is a later explicit promotion and validates/sanitizes requests
before proxying to internal `zitadel-api:8080`.

## Admission policy

Public-client only:
- token_endpoint_auth_method = none
- response_type = code
- grant_types = authorization_code (+ optional refresh_token)

Redirect classes:
- HTTPS web callback: accepted
- HTTP localhost/127.0.0.1/::1 loopback: accepted
- native custom URI scheme: accepted for native apps
- remote HTTP: rejected
- data/file/javascript/vbscript/blob: rejected

Limits:
- request body <= 64 KiB
- <= 16 redirect URIs
- redirect URI <= 2048 chars
- duplicate redirects rejected
- new registrations rate limited per source address

Management:
- GET/DELETE require registration bearer token
- PUT replacement metadata is revalidated
- registration access token is relayed but never logged by the gateway

## Synthetic compatibility proof

Source tests model:
- VS Code redirects: PASS
- Cursor HTTPS + localhost + custom scheme set: PASS
- MCP Inspector loopback: PASS
- closed-mode upstream isolation: PASS
- guarded registration proxy: PASS
- metadata sanitization: PASS
- registration management bearer: PASS
- rate limiting: PASS

## Promotion order

1. Deploy gateway in `closed` mode.
2. Confirm public /oauth/v2/register still behaves as unavailable.
3. Confirm ZITADEL DCR remains disabled.
4. Run an internal synthetic DCR lifecycle behind the closed public guard.
5. Restore/confirm backend DCR disabled.
6. Only at a later compatibility decision, enable guarded public DCR and
   advertise registration_endpoint.
7. Run actual client smoke matrix.

DCR_BACKEND_ENABLED=FALSE
DCR_PUBLIC_OPEN=FALSE
DCR_GATEWAY_SOURCE=CLOSED_PASS
DCR_GATEWAY_DEFAULT=CLOSED
DCR_GATEWAY_PROD=PENDING_DEPLOY
