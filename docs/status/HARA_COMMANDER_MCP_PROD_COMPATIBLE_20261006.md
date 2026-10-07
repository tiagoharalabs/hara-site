# H.A.R.A. Commander — MCP PROD-compatible runtime candidate

Date: 2026-10-06
Base: `6dc6d28f9cf6e609df469b3700468b1f2027c274`
Branch: `local/commander-mcp-prod-compatible-20261006`

## Why this branch exists

The current PROD Worker declares source `6dc6d28` and carries the aggregate
usage-history/bootstrap product fix. The broader MCP development line diverged
from that PROD source and also contains unrelated migration/bootstrap assets.

This branch starts from the actual PROD source and ports only the MCP runtime
corrections required by the current live gap.

## Runtime delta

Preserved:
- simple MCP surface remains exactly 24 tools;
- product transaction history remains `AGGREGATE_ONLY`;
- product aggregate history does not include tool IDs, payloads or results;
- public portal activity/SLO diagnostics remain outside the product;
- no migration, public asset, bootstrap or Wrangler config change.

Changed:
- `hara.activity` uses the existing privacy-safe activity implementation;
- `hara.calls.recent` uses the existing metadata-only recent-call implementation;
- only `DEVICE_OFFLINE` is normalized from MCP error to structured
  `state=UNAVAILABLE`, category `DEVICE_AVAILABILITY`, `retryable=true`;
- permission/schema/policy/selection errors remain MCP errors.

## Current PROD gap proven live

Before promotion:
- offline `HARA_WIN11` through PROD `hara.health` -> connector `INVALID_ARGUMENT`
  with underlying `DEVICE_OFFLINE`;
- PROD `hara.calls.recent` -> connector `INVALID_ARGUMENT` with underlying
  `LOCAL_DIAGNOSTICS_REQUIRE_SIGNED_AGENT_UPDATE`.

## Source validation

PASS:
- `COMMANDER_SIMPLE_MCP_TOOL_COUNT=24`
- Simple MCP adapter regression
- full customer MCP edge regression
- aggregate history independent of diagnostics
- recent-call projection metadata-only
- full/simple `DEVICE_OFFLINE` operational-state contract
- public runtime boundary
- complete source preprod readiness for the `6dc6d28` line.

## Promotion boundary

No PROD version upload or traffic change has been performed.

Next safe step is to deploy this exact committed branch to DEV, read back the
exact DEV Worker version, and run the same source/runtime checks. A PROD version
candidate may only be uploaded after that DEV proof, and traffic promotion
remains a separate explicit gate.

## DEV qualification of exact PROD-compatible source

Committed runtime candidate:

- source commit: `10d48fabd7f1502d77e6fe81d024db4323599975`
- Storage branch readback: exact same SHA
- base remains PROD source `6dc6d28...`

DEV deployment of this exact line:

- DEV Worker: `1d369eab-c226-4d86-b2b2-1538a5aab804`
- rollback: `4ae18bc2-26f5-491c-bec6-59feed4edf12`
- DEV exact-version deployment readback: PASS
- DEV config / D1 / secrets / DeviceChannel / health: PASS
- DEV login redirect / PKCE / transaction cookie / account switch: PASS

No DEV config or package dependency drift exists between the PROD source line and
the broader MCP development line.

## PROD packaging proof without upload

Wrangler 4.137.0 `versions upload --dry-run --strict` against
`apps/commander/wrangler.jsonc` completed successfully.

- bundle upload size: 1581.28 KiB
- gzip: 279.59 KiB
- bundled worker SHA-256:
  `d2401454f1f5effec53f9e98d472208ac3d29056f48ae95f007814f660a760e5`

Compared with the current PROD source `6dc6d28...`:

- Wrangler PROD config diff: NONE
- Wrangler DEV config diff: NONE
- migrations diff: NONE
- public assets diff: NONE
- runtime source changes are limited to:
  - `apps/commander/src/customer-mcp-simple.mjs`
  - `apps/commander/src/customer-mcp.mjs`
  - `apps/commander/src/worker.js`

## Live-readonly compatibility against current PROD

Using this candidate source, consolidated live-readonly validation against the
current PROD deployment completed with exit code 0.

PASS:

- source readiness
- Identity live readback
- PROD D1 readback
- PROD runtime/assets current
- updated fail-closed contract
- PROD Worker exact-version readback

Current PROD remains:

- Worker `fa4217f6-cc99-4395-8fe3-e0abb4e67950`
- rollback `0046cabd-cd2c-4522-941c-0a86db850837`

Current PROD still exhibits the two symptoms this candidate fixes:

- offline device state reaches the connector as generic `INVALID_ARGUMENT`;
- `hara.calls.recent` remains blocked by
  `LOCAL_DIAGNOSTICS_REQUIRE_SIGNED_AGENT_UPDATE`.

## Remaining explicit PROD gate

No PROD version was uploaded and no PROD traffic was changed.

The next action is a PROD `versions upload` of this exact candidate source. That
operation creates a remote candidate Version but does not route traffic to it.
After upload, the canonical versioned-promotion helper must first be run without
`--execute` to verify:

1. target Version ID shape;
2. current 100% rollback Version is still the expected current PROD version;
3. required secrets are present on the target version;
4. trigger synchronization will be required if/when promotion is executed.

Actual traffic promotion remains a separate explicit gate.

## PROD candidate version upload — authorized first write

Authorized on 2026-10-07.

A PROD Worker Version was uploaded with no traffic promotion:

- Version ID: `91a870b7-e84a-4f70-95df-d3be1367f190`
- tag: `mcp-runtime-prod-compatible-20261007`
- message: `MCP runtime fixes on PROD source 6dc6d28; runtime 10d48fa; qualified db6b738`
- upload source: version_upload
- compatibility date: 2026-09-21

Candidate Version bindings/readback:

- PROD D1 binding preserved
- TenantQuota / SecurityRateLimit bindings preserved
- PROD environment and public MCP resource vars preserved
- required secrets present
- candidate carries the same expected six secret bindings as current PROD

Canonical versioned-promotion preflight, **without** `--execute`:

- `COMMANDER_VERSIONED_PROMOTE_PREFLIGHT=PASS`
- target = `91a870b7-e84a-4f70-95df-d3be1367f190`
- rollback = `fa4217f6-cc99-4395-8fe3-e0abb4e67950`
- required secrets = PASS
- trigger sync = REQUIRED if promotion is later executed
- `COMMANDER_VERSIONED_PROMOTE_EXECUTE=NO`

Traffic readback after upload:

- deployment remains `f596f36e-74fb-467d-95a8-53d1d8691731`
- `fa4217f6-cc99-4395-8fe3-e0abb4e67950` remains at **100%**
- candidate receives **0%** traffic
- routes/triggers were not changed

Therefore the first PROD write is complete and bounded. The next gate is the
separate `commander_versioned_prod_promote.py --execute` operation, which would
move traffic to the candidate and synchronize triggers.
