# H.A.R.A. Commander — MCP DCR Hardening V0.2

Date: 2026-10-06
State: SOURCE/PREPROD CLOSED_PASS; PROD CLOSED ROLLOUT PENDING

## Purpose

Make generic OAuth/DCR onboarding promotion-ready before running real VS Code,
Claude Code, Cursor or MCP Inspector smoke tests.

This slice does not open public registration.

## DCR gateway V0.2

Image target:
- `hara-identity-dcr-gateway:v0.2.0`

Default mode remains:
- `closed`

Hardening added:
- `CF-Connecting-IP` is the trusted client rate key by default;
- `X-Forwarded-For` is ignored unless explicitly enabled;
- forwarding/client-IP headers are removed before the ZITADEL hop;
- per-client fixed-window registration limiter: 10/hour default;
- global fixed-window registration limiter: 200/hour default;
- independent Traefik edge rate limiter keyed by `CF-Connecting-IP`;
- health readback exposes mode/rate/trust configuration, not secrets.

The existing admission policy remains:
- public OAuth clients only;
- Authorization Code + PKCE-compatible redirect classes;
- optional Refresh Token;
- HTTPS, loopback HTTP and guarded native scheme redirects;
- remote HTTP and dangerous schemes denied;
- bounded payload/redirect counts;
- management bearer required.

## RFC 8414 adapter V1.1

Image target:
- `hara-identity-oauth-metadata:v1.1.0`

Default remains fail closed:
- `HARA_CIMD_ADVERTISED=false`
- `HARA_DCR_REGISTRATION_ADVERTISED=false`

The adapter can now conditionally publish:
- `client_id_metadata_document_supported=true` only when explicitly enabled;
- `registration_endpoint=https://auth.haralabs.com.br/oauth/v2/register`
  only when DCR is explicitly promoted.

This prevents discovery from advertising a capability before the guarded runtime
is ready.

## Transactional promotion lane

New script:
- `apps/identity-login/scripts/promote_mcp_dcr_guarded.py`

Preconditions:
- compose state exactly CLOSED;
- backend ZITADEL DCR disabled;
- RFC 8414 does not advertise registration_endpoint;
- hardened v0.2/v1.1 images selected.

Promotion order:
1. capture exact compose + security-policy preimage;
2. enable ZITADEL DCR while the public guard remains closed;
3. atomically switch compose to guarded + advertise registration_endpoint;
4. recreate only DCR gateway + metadata adapter;
5. require public metadata readback;
6. require invalid registration to be rejected by the public guard.

Failure path:
1. restore closed/no-advertise compose;
2. recreate only the two isolated services;
3. restore exact DCR security-policy state;
4. require public closed readback.

Dry-run is default. `--execute` is mandatory for mutation.

## Gates

- HARA_IDENTITY_DCR_GATEWAY_SOURCE=PASS
- HARA_IDENTITY_DCR_GATEWAY_GLOBAL_RATE_LIMIT=PASS
- HARA_IDENTITY_DCR_GATEWAY_CF_IP_TRUST=PASS
- HARA_IDENTITY_RFC8414_DCR_CONDITIONAL_ADVERTISEMENT=PASS
- HARA_MCP_DCR_PROMOTION_SOURCE=PASS
- COMMANDER_PREPROD_MCP_DCR_PROMOTION=PASS
- COMMANDER_SOURCE_PREPROD_READY=PASS

## Boundary

This closes source/preprod hardening and promotion mechanics.

Public DCR remains CLOSED until a later explicit promotion. Real client smokes
should happen after the closed hardened images are live and, if chosen, after
the guarded DCR promotion passes its own strict readback.

DCR_GATEWAY_V02_SOURCE=CLOSED_PASS
DCR_EDGE_RATE_LIMIT=CLOSED_PASS
DCR_CF_CLIENT_IP_TRUST=CLOSED_PASS
DCR_GLOBAL_RATE_LIMIT=CLOSED_PASS
DCR_METADATA_CONDITIONAL_ADVERTISEMENT=CLOSED_PASS
DCR_PROMOTION_TRANSACTION=CLOSED_PASS
DCR_PUBLIC_OPEN=FALSE
DCR_PROD_HARDENED_CLOSED=PENDING
