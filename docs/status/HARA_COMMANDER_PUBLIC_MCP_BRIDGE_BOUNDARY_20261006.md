# H.A.R.A. Commander — Public MCP bridge boundary

Date: 2026-10-06
State: SOURCE/PREPROD CLOSED_PASS

## Product boundary

Public H.A.R.A. Commander is the MCP bridge between a customer's local
Commander Agent and a compatible AI/MCP client.

The H.A.R.A. internal fleet/control plane is a separate workstream and must not
leak into the public product.

## Public product

Visible:
- customer computers;
- MCP connection/onboarding;
- plan and usage;
- account/billing;
- simple service/product state.

Not visible:
- internal SLO;
- p50/p95/p99;
- transport mode;
- internal incidents;
- top tools/errors;
- execution ledger;
- H.A.R.A. lab/fleet diagnostics.

## Privacy / storage

Detailed activity remains local-authoritative in the Agent SQLite store.

Public Cloudflare/D1 does not persist Agent activity snapshots from heartbeat.
Legacy Agents may still send the old field during transition; the Worker ignores
it.

Remote detailed-history MCP calls remain fail-closed until a signed Agent release
exposes the local-history bridge end-to-end.

## Heartbeat economics

Heartbeat requests may continue every 30 seconds for connectivity.

D1 presence writes are coalesced to at most once per 120 seconds unless relevant
device metadata changes. Non-Event-V2 online grace is 240 seconds.

## Auth recovery hardening

Generic D1/SQLite code 7500 is not sufficient to activate billing-only auth
recovery. Recovery requires explicit daily-row-write-limit error text.

## Signed Agent boundary

The currently signed PROD Agent remains 0.3.40 in this release.

Agent 0.3.41 source removes legacy activity snapshot transmission at the origin,
but must not be promoted until its governed release signature is valid.

PUBLIC_COMMANDER=MCP_BRIDGE
INTERNAL_CONTROL_PLANE=SEPARATE
PUBLIC_INTERNAL_DIAGNOSTICS=ABSENT
CLOUD_ACTIVITY_SNAPSHOT_PERSISTENCE=DISABLED
HEARTBEAT_PERSIST_SECONDS=120
ONLINE_GRACE_SECONDS=240
SIGNED_AGENT_CHANGED=FALSE


## PROD proof

Worker:
- `f864b2f0-3dde-4479-8e5c-fbfe17748dd9`

Rollback:
- `8968a5e8-95f9-4a1a-a9ed-34833047f918`

Live proof:
- public HTML does not contain internal diagnostic labels;
- Usage page contains the public privacy boundary copy;
- `/api/portal/activity` -> HTTP 404 `INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT`;
- `/api/portal/slo` -> HTTP 404 `INTERNAL_DIAGNOSTICS_NOT_IN_PRODUCT`;
- `/auth/login` -> HTTP 302 to HARA Identity with PKCE;
- runtime assets = CURRENT.

Legacy D1 cleanup remains intentionally pending while D1 writes are constrained.
The legacy rows are no longer read or updated by the public product path.

PUBLIC_MCP_BRIDGE_BOUNDARY_PROD=CLOSED_PASS
PROD_WORKER=f864b2f0-3dde-4479-8e5c-fbfe17748dd9
PROD_ROLLBACK=8968a5e8-95f9-4a1a-a9ed-34833047f918
LEGACY_D1_PURGE=PENDING_WRITE_PLANE_RECOVERY
