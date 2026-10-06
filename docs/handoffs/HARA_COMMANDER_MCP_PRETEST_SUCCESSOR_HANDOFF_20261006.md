# H.A.R.A. Commander — MCP pre-test successor handoff

Date: 2026-10-06
State: PRETEST_PREPARATION_COMPLETE / CLIENT_TESTS_NOT_RUN

## Canonical starting point

Base canonical at preparation start:
`ccdb642e643174484a57a34115f7b24c964e8c20`

Do not claim any client as certified from this handoff alone.

## Live prerequisites already closed

- Simple MCP 1.1 source/preprod conformance
- 24 vendor-neutral public tools
- RFC 8414 PROD
- guarded DCR PROD
- generic auto OAuth discovery PASS
- disposable DCR register/read/delete lifecycle PASS
- Worker PROD remains `5f6f29aa-e333-4898-a11b-e7cc29c77f12`

## Pre-test artifacts prepared

Machine-readable:
- `apps/commander/mcp/client-compatibility-profile.v1.json`
- `apps/commander/mcp/client-adapter-expectations.v1.json`
- `apps/commander/mcp/client-certification-matrix.v1.json`
- `apps/commander/mcp/certification-fixture-policy.v1.json`
- `apps/commander/mcp/certification-rollup-policy.v1.json`
- `apps/commander/mcp/schemas/client-certification-evidence.schema.json`
- `apps/commander/mcp/schemas/client-certification-certificate.schema.json`

Utilities:
- `apps/commander/scripts/commander_mcp_client_certification.py`
- `apps/commander/scripts/commander_mcp_client_certificate.py`
- `apps/commander/scripts/commander_mcp_certification_rollup.py`

Templates:
- VS Code portable
- VS Code native
- Cursor
- Claude Code certification card
- MCP Inspector certification card

Workflow:
- `docs/workflows/HARA_COMMANDER_MCP_CLIENT_CERTIFICATION_V1_20261006.md`

## Explicitly not executed

- no VS Code MCP connection;
- no Cursor MCP connection;
- no Claude Code MCP connection;
- no MCP Inspector connection;
- no local MCP client harness execution;
- no client certification evidence;
- no client certificate;
- no multi-client rollup.

## Frozen certification invariant

A client PASS requires all REQUIRED cases from matrix V1.

The public 24-tool contract may not be modified merely to make one vendor pass.

Failure classification is mandatory before any server change.

## Suggested actual test order later

1. MCP Inspector
2. VS Code
3. Cursor
4. Claude Code

## Future track

CIMD remains a separate migration track. Guarded DCR is the V1 compatibility
registration mechanism. See:
`docs/status/HARA_COMMANDER_MCP_CIMD_MIGRATION_DECISION_20261006.md`.

## Frozen certification bundle

Bundle commit:
`c4e2a50e81c1d7487116c35b551924862f21018c`

Do not alter matrix/evidence/fixture artifacts after the first client run without creating a new certification revision.


## Test-window safety controls

Prepared after the certification bundle freeze:

- `apps/commander/scripts/commander_mcp_certification_preflight.py`
- `apps/commander/scripts/commander_mcp_certification_snapshot.py`
- `apps/identity-login/scripts/close_mcp_dcr_guarded.py`
- `apps/commander/mcp/test-window-policy.v1.json`
- `apps/commander/mcp/certification-campaign.v1.json`
- `docs/workflows/HARA_COMMANDER_MCP_TEST_WINDOW_SAFETY_20261006.md`
- `docs/status/HARA_COMMANDER_MCP_TEST_WINDOW_SAFETY_20261006.md`

These controls were prepared but NOT executed in this slice.

The future test window must be one client at a time. Emergency DCR closure is
public-first/backend-second and dry-run by default.

Campaign state remains:
- MCP Inspector: NOT_STARTED
- VS Code: NOT_STARTED
- Cursor: NOT_STARTED
- Claude Code: NOT_STARTED
- MULTI_CLIENT_CERTIFIED: FALSE
