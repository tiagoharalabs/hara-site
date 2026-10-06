# H.A.R.A. Commander — MCP Identity Metadata / CIMD Readiness

Date: 2026-10-06
State: RFC8414 SOURCE/PREPROD CLOSED_PASS; LIVE PENDING DEPLOY
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

RFC8414_SOURCE=CLOSED_PASS
RFC8414_LIVE=PENDING_DEPLOY
CIMD_ADMISSION_POLICY=CLOSED_PASS
CIMD_FETCH_SSRF_GUARD=CLOSED_PASS
CIMD_ADVERTISED=FALSE
PUBLIC_DCR_ADVERTISED=FALSE
GENERIC_AUTO_OAUTH=PENDING_CIMD_AUTHORIZATION_INTEGRATION
