# HARA Identity / ZITADEL — DCR guarded edge live (2026-10-09)

## CURRENT TRUTH: GUARDED, NOT CLOSED

**DCR_PUBLIC_GATE=GUARDED_PASS**

The owner confirmed an authenticated read of ZITADEL `/v2/settings/security` on Storage before the operation:

- `dynamicClientRegistration.enabled = true`
- `dynamicClientRegistration.allowUnauthenticated = true`

The original canonical promoter (`promote_mcp_dcr_guarded.py`) was intentionally fail-closed: it required `false/false` as its preimage, so it refused the already-enabled backend with `DCR_PROMOTION_REQUIRES_BACKEND_DISABLED`. This is **not** a token generator defect, and the backend was **not** reset.

## Scoped reconciliation performed

Scope was limited to the two public-edge compose flags and Docker services. The new canonical helper is:

`apps/identity-login/scripts/reconcile_mcp_dcr_existing_backend.py`

- Receives **no PAT**, reads **no ZITADEL owner secret**, makes **no ZITADEL security policy PUT**.
- Requires owner-attested preexisting backend `true/true`, root-owned execution, exact hardened gateway/metadata images and CF-IP/rate-limit markers, closed compose preimage and public denied DCR readback.
- Takes timestamped chmod-0600 backup of compose; updates only `HARA_DCR_GATEWAY_MODE: guarded` and `HARA_DCR_REGISTRATION_ADVERTISED: "true"`, recreates only `zitadel-dcr-gateway` and `zitadel-oauth-metadata`.
- Runs public RFC 8414 readback and invalid registration negative test; rollback to original compose and closed gateway on failure.
- Source script now **idempotently detects already-guarded mode** and exits without rewriting or restarting services.

The script was staged at `/srv/hara/identity/operations/reconcile_mcp_dcr_existing_backend.py` with root ownership and permissions 0700 on Storage. Its current fingerprint is SHA-256:

`e8d7be38476285d3897ee2511235af88ec9ac3df20f20b1b9d622c8122390d7e`

Run date: 2026-10-09.
- Preflight: `HARA_DCR_EDGE_PREFLIGHT=CLOSED_PASS`
- Apply: `HARA_DCR_EDGE_RECONCILIATION=PASS`
- Backup: `/srv/hara/identity/compose/compose.yml.pre-dcr-edge-reconcile-20261009T223825Z`
- Backup SHA-256: `1230c50a9b8e6ac48bfe1fdd067c061b3126b1facd5a6b28c17c924321df8d52`
- Backend administrative policy mutations: `ZERO`
- Subsequent idempotent readback: `HARA_DCR_EDGE_ALREADY_GUARDED=PASS`, `HARA_DCR_EDGE_EXECUTE=NO_CHANGE`

## Public acceptance evidence

Read-only live verifier:
`python3 apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect guarded --require-ready`:

- OIDC/RFC 8414 issuer, authorization endpoint, token endpoint, PKCE S256: PASS.
- Protected resource metadata binds `https://commander.haralabs.com.br/api/mcp`: PASS.
- Unauthenticated MCP `401`: PASS.
- RFC 8414 DCR advertised and guarded malicious registration denied `400 invalid_client_metadata`: PASS.
- ZITADEL API/Login/Assets containers unchanged and healthy; two edge containers recreated and healthy.

**Live positive DCR lifecycle was independently executed** by an isolated temporary client (no human access token or login):
- POST OAuth DCR registration: **201**
- GET registration-management URI with its registration token: **200**, same client ID
- DELETE via management URI: **204**
- Automatic temporary client cleanup: **PASS**
- No registration token/client_id secrets written to logs or repo; no test client intentionally retained.

The PROD Commander Worker also lists the required secret **names** for audience and introspection as present:
`HARA_IDENTITY_MCP_DCR_PROJECT_AUD`,
`HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_ID`,
`HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_SECRET`.
Values were not read or exposed.

## Remaining OpenAI-specific gate

DCR issuance and management are now proven through the public URL, but **ChatGPT browser consent + PKCE exchange + the actual resulting user's access-token audience + MCP commercial tool invocation have not been tested**. These must occur via ChatGPT's customer MCP connection, not via the administrative `H_A_R_A__Commander_Baseline` / HARA Services relay. Do not claim OpenAI plugin installed, reviewed or published.

To recheck current live state without changes on the Identity host:

`sudo python3 /srv/hara/identity/operations/reconcile_mcp_dcr_existing_backend.py --backend-already-enabled`

Expected: `HARA_DCR_EDGE_ALREADY_GUARDED=PASS`, `HARA_DCR_EDGE_EXECUTE=NO_CHANGE`.

Do not rerun the original promoter (requires `false/false` backend preimage), reset the backend policy, regenerate owner PAT, or restart the ZITADEL API.
