# H.A.R.A. Commander — CIMD migration decision

Date: 2026-10-06
State: ARCHITECTURE_PREPARED / NOT ACTIVATED

## Context

MCP 2026-07-28 formally moves client registration toward Client ID Metadata
Documents (CIMD) and deprecates Dynamic Client Registration (DCR).

H.A.R.A. Identity currently has:
- RFC 8414 live;
- guarded DCR live;
- generic auto OAuth discovery PASS;
- CIMD URL admission policy prepared;
- CIMD fetch SSRF controls prepared;
- `client_id_metadata_document_supported=false`.

This is sufficient for current generic client homologation because DCR remains a
compatibility path.

## Decision

Do not build an ad-hoc authorization/token translation broker solely to claim
CIMD before the Identity engine can support URL client IDs cleanly.

Preferred migration order:

1. Track native CIMD support in the Identity engine / ZITADEL.
2. If native support becomes available, validate it behind the existing HARA
   metadata service and only then advertise
   `client_id_metadata_document_supported=true`.
3. If native support does not arrive and CIMD becomes mandatory for a target
   client, design a dedicated stateful HARA authorization bridge as a separate
   security workstream with:
   - URL client_id fetch/validation;
   - exact redirect binding;
   - issuer binding;
   - PKCE S256;
   - no client secret;
   - mapping lifecycle/retention;
   - replay/mix-up protections;
   - rate limiting;
   - rollback and migration from DCR.
4. Keep guarded DCR available during the compatibility window.
5. Never advertise CIMD before the authorization path actually accepts a CIMD
   client_id URL end-to-end.

## Why

A premature translation broker would add:
- client-id mapping state;
- authorization/token rewrite complexity;
- additional replay/mix-up attack surface;
- cleanup/retention obligations;
- another availability dependency.

The current guarded DCR implementation is smaller, bounded and already live.

## Certification policy

The V1 multi-client certification may use guarded DCR.

A future V2 CIMD certification must add cases for:
- client_id HTTPS metadata URL;
- server-side secure CIMD fetch;
- exact metadata client_id match;
- exact redirect URI binding;
- no DCR request;
- no client secret;
- issuer validation;
- reconnect without registration state on HARA Identity.

CIMD_POLICY_READY=TRUE
CIMD_FETCH_GUARD_READY=TRUE
CIMD_ADVERTISED=FALSE
DCR_GUARDED_COMPATIBILITY=LIVE
CIMD_ACTIVATION_BLOCKER=IDENTITY_AUTHORIZATION_INTEGRATION
