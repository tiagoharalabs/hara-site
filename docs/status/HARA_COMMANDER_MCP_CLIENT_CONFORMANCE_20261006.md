# H.A.R.A. Commander — MCP Client Conformance V1

Date: 2026-10-06
State: SOURCE/PREPROD CLOSED_PASS — GENERIC AUTO-OAUTH PENDING IDENTITY METADATA

## Goal

Keep one client-neutral Simple MCP contract that works across OpenAI/ChatGPT,
Claude Code, VS Code, Cursor, MCP Inspector and other standards-compliant MCP
hosts without creating per-vendor forks.

## Public Simple MCP surface

Endpoint:
- https://commander.haralabs.com.br/api/mcp?profile=simple

Stable public tool count:
- 24

The public tool names remain vendor-neutral and no internal `hara.*` names are
exposed.

## Contract maturity added

Simple MCP server profile advanced from 1.0.0 to 1.1.0.

All 24 tools now publish:
- strict JSON Schema input contracts;
- explicit JSON Schema output contracts;
- title and description;
- readOnlyHint;
- destructiveHint;
- idempotentHint;
- openWorldHint;
- OAuth securitySchemes metadata.

The server now publishes neutral instructions covering:
- inspect-before-mutate behavior;
- optional computer selection;
- one-shot vs managed interactive processes;
- governed mutation/approval semantics;
- no assumption about model vendor/client.

Server implementation metadata now includes:
- title: H.A.R.A. Commander;
- website URL;
- product description;
- Commander icon.

## Protocol conformance

Automated in-process host simulation proves the same endpoint across:

- MCP 2025-06-18 handshake era: PASS
- MCP 2025-11-25 handshake era: PASS
- MCP 2026-07-28 stateless era: PASS

Modern 2026 proof includes:
- server/discover;
- tools/list;
- tools/call;
- mandatory MCP-Protocol-Version;
- mandatory Mcp-Method;
- Mcp-Name cross-check on named calls;
- resultType=complete;
- structuredContent;
- outputSchema;
- fail-closed rejection when required standard headers are absent.

Permanent gate:
- apps/commander/scripts/test_customer_mcp_conformance.mjs
- COMMANDER_PREPROD_MCP_CLIENT_CONFORMANCE=PASS

## Authentication discovery live proof

Current PROD resource server:

- unauthenticated MCP -> HTTP 401: PASS
- WWW-Authenticate resource_metadata: PASS
- Protected Resource Metadata: PASS
- authorization server binding -> HARA Identity: PASS
- OIDC discovery fallback: PASS
- PKCE S256: PASS

Current HARA Identity metadata gaps for zero-config generic MCP onboarding:

- RFC 8414 /.well-known/oauth-authorization-server: PENDING (currently 404)
- client_id_metadata_document_supported: PENDING
- registration_endpoint advertised in metadata: PENDING

Therefore:

- MCP protocol/tool interoperability: CLOSED_PASS
- bearer/resource OAuth boundary: CLOSED_PASS
- generic automatic OAuth client onboarding: PENDING_IDENTITY_METADATA

The latest MCP direction prefers Client ID Metadata Documents (CIMD). DCR can
remain a compatibility fallback, but should not be opened permanently merely
to make a client demo pass.

Live probe:
- apps/commander/scripts/commander_mcp_auth_discovery_probe.py

It supports:
- normal diagnostic mode (records pending metadata without hiding it);
- --require-generic-auto for the future release gate once Identity is upgraded.

## Client readiness matrix

| Client / host | Protocol surface | Tool contract | OAuth resource discovery | Zero-config OAuth registration | Current state |
| --- | --- | --- | --- | --- | --- |
| ChatGPT / OpenAI | PASS | PASS | PASS | Existing configured integration path | READY on existing integration |
| Claude Code | PASS by MCP conformance | PASS | PASS | PENDING Identity metadata | PROTOCOL_READY |
| VS Code | PASS by MCP conformance | PASS | PASS | PENDING Identity metadata | PROTOCOL_READY |
| Cursor | PASS by MCP conformance | PASS | PASS | PENDING Identity metadata | PROTOCOL_READY |
| MCP Inspector | PASS by MCP conformance | PASS | PASS | PENDING Identity metadata | PROTOCOL_READY |
| Generic MCP 2025 host | PASS | PASS | PASS | Depends on client registration method | PROTOCOL_READY |
| Generic MCP 2026 host | PASS | PASS | PASS | PENDING Identity CIMD/RFC8414 | PROTOCOL_READY |

Client-specific live smoke tests remain useful after automatic OAuth onboarding
is closed, but are no longer required to prove the correctness of the core
tool/protocol contract.

## Next identity slice

Preferred:
1. publish RFC 8414 Authorization Server Metadata at
   /.well-known/oauth-authorization-server;
2. advertise client_id_metadata_document_supported=true;
3. implement/finalize CIMD validation with HTTPS client_id URLs;
4. retain DCR only as controlled compatibility fallback where needed;
5. rerun commander_mcp_auth_discovery_probe.py --require-generic-auto;
6. then run actual VS Code / Claude Code / Cursor / Inspector live smoke matrix.

MCP_SIMPLE_PROFILE_VERSION=1.1.0
MCP_TOOL_COUNT=24
MCP_2025_06_18_CONFORMANCE=CLOSED_PASS
MCP_2025_11_25_CONFORMANCE=CLOSED_PASS
MCP_2026_07_28_CONFORMANCE=CLOSED_PASS
MCP_OUTPUT_SCHEMA=CLOSED_PASS
MCP_SERVER_INSTRUCTIONS=CLOSED_PASS
MCP_SERVER_METADATA=CLOSED_PASS
MCP_PROTOCOL_CLIENT_NEUTRALITY=CLOSED_PASS
MCP_OAUTH_RESOURCE_DISCOVERY=CLOSED_PASS
MCP_GENERIC_AUTO_OAUTH=PENDING_IDENTITY_METADATA

## Full live read-only regression

The Commander-wide live read-only gate was rerun with Node 24 after the MCP
conformance changes.

PASS:
- Commander source/preprod readiness;
- HARA Identity live white-label;
- MCP auth discovery live probe;
- PROD D1 readback;
- PROD runtime assets CURRENT;
- PROD fail-closed suite;
- exact PROD Worker deployment readback.

Observed live boundary:
- `COMMANDER_MCP_GENERIC_AUTO_OAUTH_ONBOARDING=PENDING_IDENTITY_METADATA`
- `COMMANDER_PROD_WORKER_VERSION=5f6f29aa-e333-4898-a11b-e7cc29c77f12`

The MCP 1.1 contract is intentionally not promoted to PROD in this slice. The
current canonical source also contains external SLO alert-delivery source work
that remains deliberately unpromoted until an explicit destination is chosen.
A future MCP production promotion must therefore use an isolated release lineage
or a separately approved combined rollout.

MCP_CONFORMANCE_FULL_LIVE_READONLY=PASS
MCP_CONFORMANCE_PROD_PROMOTION=NOT_PERFORMED
