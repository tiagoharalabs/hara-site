# H.A.R.A. Commander — localhost direct refresh DEV proof

Date: 2026-10-05
Branch: local/commander-localhost-refresh-20261005

## Architecture

Cloud remains authoritative for identity, tenant, entitlement, billing, grants,
revocation and authenticated portal access.

Operational Activity detail can now be read directly from the local Commander
Agent over loopback:

- host: 127.0.0.1 only
- default port: 32145
- source: local operations.sqlite3
- no cloud credential is sent to localhost
- cloud Activity remains the authenticated fleet summary/fallback

The browser never uses localhost to bypass cloud authentication.

## Browser permission UX

Current Chrome and Firefox releases gate public-site access to local/loopback
services behind Local Network Access permissions.

The portal therefore:
- does not trigger a localhost permission prompt automatically on page entry;
- uses the cloud/local-snapshot aggregate silently by default;
- attempts first direct localhost access only from an explicit Activity refresh;
- after permission is granted, subsequent refreshes may use localhost directly;
- falls back silently to cloud if permission is denied or the Agent is absent.

The request declares targetAddressSpace=loopback where supported.

## Agent 0.3.34

Linux:
- loopback HTTP server runs inside the existing Agent process;
- GET /v1/health
- GET /v1/activity
- OPTIONS/CORS/PNA support
- exact HARA_COMMANDER_URL origin allowlist
- foreign Origin -> HTTP 403 LOCAL_ORIGIN_DENIED
- no wildcard/LAN bind
- no device token in local API response

Windows:
- release version kept aligned at 0.3.34;
- no localhost/local-SQLite parity added in this slice;
- existing Windows behavior unchanged.

## Source/regression gates

PASS:
- Linux Agent self-test
- release manifest/SHA
- installer validators
- supply-chain validator
- Event V2 productization
- local Activity store validator
- localhost direct Activity validator
- PROD static security validator
- E2E harness
- full preprod readiness

## DEV Worker

First localhost build:
- 84e4370e-a08e-4e82-8dbf-e8d01ab92f3d

Final browser-permission build:
- 1de15192-db7d-4f10-ac3d-9dbd7d62ea67
- rollback: 84e4370e-a08e-4e82-8dbf-e8d01ab92f3d

DEV live:
- health/login/PKCE/cookie/account switch PASS
- cache key 20261005-localdirect1 PASS
- CSP exact loopback connect-src PASS
- loopback permission gate PASS
- targetAddressSpace=loopback PASS
- explicit-refresh prompt gate PASS
- cloud auth path preserved PASS
- local credentials omitted PASS

## Served Agent canary

The Linux Agent was downloaded from the live DEV Worker, not read from the
worktree.

PASS:
- manifest version 0.3.34
- served Agent version 0.3.34
- Agent SHA matches manifest
- served Agent self-test
- isolated loopback Activity returned HTTP 200
- source=LOCAL_SQLITE
- detail_location=LOCAL_DEVICE
- CORS exact DEV origin
- Access-Control-Allow-Private-Network=true
- evil origin denied with HTTP 403 / LOCAL_ORIGIN_DENIED

Windows VM canary from the live DEV Worker:
- manifest 0.3.34
- SHA match
- operator-session gate PASS
- console sanitization PASS
- starter read PASS
- five-tool bridge PASS
- arbitrary function DENIED
- self-test PASS / exit 0

## State

LOCALHOST_DIRECT_REFRESH_DEV=CLOSED_PASS
LOCALHOST_LOOPBACK_SECURITY_DEV=CLOSED_PASS
AGENT_0_3_34_DEV=CLOSED_PASS
WINDOWS_LOCAL_SQLITE_PARITY=PENDING_SEPARATE_SLICE
