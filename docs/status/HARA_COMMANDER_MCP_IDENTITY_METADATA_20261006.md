# H.A.R.A. Commander — MCP Identity Metadata / CIMD Readiness

Date: 2026-10-06
State: RFC8414 SOURCE/PREPROD/PROD CLOSED_PASS
CIMD: ADMISSION/FETCH POLICY READY; NOT ADVERTISED

## Runtime discovery

Live Identity runtime inspected on `storage`:

- ZITADEL API: `ghcr.io/zitadel/zitadel:v4.17.3`;
- Login overlay: `hara-identity-login:v4.16.0-hara.8`;
- Traefik: `v3.7.7`;
- Postgres: `17.10-alpine`.

The older handoff still described API 4.16.0; live runtime is ahead of that
handoff and is authoritative for this slice.

Current public OIDC metadata already exposes:

- issuer `https://auth.haralabs.com.br`;
- authorization endpoint;
- token endpoint;
- introspection endpoint;
- revocation endpoint;
- JWKS URI;
- Authorization Code;
- Refresh Token;
- PKCE S256.

The missing generic MCP discovery endpoint is currently
`/.well-known/oauth-authorization-server`.

## RFC 8414 adapter

A dedicated image was added:

`hara-identity-oauth-metadata:v1.0.0`

It serves only the exact RFC 8414 well-known path and has its own healthcheck.
The Traefik route has priority 700, above the ZITADEL API catch-all.

No existing Identity service needs to be rebuilt or restarted.

The metadata is deliberately conservative:

- response_types_supported = [code]
- grant_types_supported = [authorization_code, refresh_token]
- code_challenge_methods_supported = [S256]
- client_id_metadata_document_supported = false
- registration_endpoint = absent

This means RFC 8414 can be enabled independently without weakening client
registration policy.

## CIMD next-stage preparation

Source contains a non-routed CIMD policy and fetcher.

Admission controls:
- HTTPS/non-root client_id URL;
- no userinfo/query/fragment;
- localhost, .local, literal private/reserved IPs denied;
- redirect URIs HTTPS or loopback-IP HTTP only;
- Authorization Code required;
- token endpoint auth method must be none;
- client_id in document must equal metadata URL exactly.

Fetcher controls:
- DNS resolution before request;
- private/reserved DNS answers denied;
- validated address pinned into TLS request lookup;
- SNI/hostname certificate validation retained;
- redirects denied;
- application/json required;
- 64 KiB document cap;
- bounded timeout.

The fetcher is packaged but not externally routed and the RFC metadata keeps
CIMD disabled. This is intentional.

## Gates

Source:
- `validate_mcp_oauth_metadata.py`
- `test_mcp_oauth_metadata.mjs`
- permanent Commander preprod gate:
  `COMMANDER_PREPROD_MCP_IDENTITY_METADATA=PASS`

Future live:
- `validate_mcp_oauth_metadata_live.py --expect-cimd disabled`
- after CIMD implementation:
  `validate_mcp_oauth_metadata_live.py --expect-cimd enabled`
- generic client gate:
  `commander_mcp_auth_discovery_probe.py --require-generic-auto`

## PROD proof

Deployed 2026-10-06 as a sixth isolated Identity service on `storage`:

- service: `hara-identity-zitadel-oauth-metadata-1`;
- image: `hara-identity-oauth-metadata:v1.0.0`;
- image ID: `sha256:f7e5984ad00f85f74f93dd66f14c711e9f9da0a0450472e7cd56a8826bdc05c4`;
- live compose backup:
  `/srv/hara/identity/compose/compose.yml.pre-mcp-rfc8414-20261006T151956Z`.

Deployment used `docker compose up -d --no-deps zitadel-oauth-metadata`.
The pre-existing proxy, ZITADEL API, login, assets and Postgres containers kept
the same container IDs and uptime across the change.

Public live validation:
- RFC 8414 HTTP: PASS;
- issuer and auth/token/introspection/revocation/JWKS exact-match OIDC: PASS;
- Authorization Code: PASS;
- PKCE S256: PASS;
- CIMD disabled: PASS;
- DCR not advertised: PASS;
- existing HARA Identity white-label: PASS.

Commander full live-readonly regression after deployment:
- source/preprod readiness: PASS;
- D1: PASS/APPLIED;
- runtime assets: CURRENT;
- fail-closed: PASS;
- exact Worker deployment: PROVEN;
- Worker remains `5f6f29aa-e333-4898-a11b-e7cc29c77f12`.

Rollback of this Identity-only slice is to remove/stop
`zitadel-oauth-metadata` and restore the timestamped compose backup. No Worker,
ZITADEL API, Login or database rollback is required.

RFC8414_SOURCE=CLOSED_PASS
RFC8414_LIVE=CLOSED_PASS
CIMD_ADMISSION_POLICY=CLOSED_PASS
CIMD_FETCH_SSRF_GUARD=CLOSED_PASS
CIMD_ADVERTISED=FALSE
PUBLIC_DCR_ADVERTISED=FALSE
GENERIC_AUTO_OAUTH=PENDING_CIMD_AUTHORIZATION_INTEGRATION
