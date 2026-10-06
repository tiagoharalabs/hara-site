# H.A.R.A. Commander — MCP test-window safety preparation

Date: 2026-10-06
State: PREPARED_NOT_EXECUTED

Added without launching or emulating any MCP client:

- static/live-readonly certification preflight script;
- secret-free environment snapshot script;
- fail-closed DCR emergency-close script;
- test-window safety/incident runbook.

## Preflight

`apps/commander/scripts/commander_mcp_certification_preflight.py`

Checks the frozen bundle, 22-case matrix, four-client set, scratch safety,
template secret hygiene and required certification utilities.

Optional future `--live-readonly` adds HARA metadata/DCR/PKCE checks without
launching an MCP client.

Not executed in this preparation slice.

## Snapshot

`apps/commander/scripts/commander_mcp_certification_snapshot.py`

Can capture:
- exact Git state;
- frozen artifact hashes;
- expected PROD Worker version;
- public RFC8414 / Protected Resource Metadata state;
- Identity container image/status readback;
- guarded DCR/CIMD compose flags.

It explicitly records no credential material.

Not executed in this preparation slice.

## Emergency closure

`apps/identity-login/scripts/close_mcp_dcr_guarded.py`

Prepared as a dry-run-by-default, explicit-execute emergency closure lane.

Safety invariant:
PUBLIC_DCR_CLOSE -> PUBLIC_READBACK_404 -> BACKEND_DCR_DISABLE.

Failure to disable backend must leave the public guard closed.

Not executed in this preparation slice.

MCP_TEST_WINDOW_PREFLIGHT=PREPARED
MCP_TEST_WINDOW_SNAPSHOT=PREPARED
MCP_DCR_EMERGENCY_CLOSE=PREPARED
MCP_REAL_CLIENT_TESTS=NOT_RUN
MCP_LOCAL_CLIENT_TESTS=NOT_RUN

## Frozen safety contract

Machine-readable test-window policy:
- `apps/commander/mcp/test-window-policy.v1.json`

Campaign skeleton:
- `apps/commander/mcp/certification-campaign.v1.json`

The campaign remains `PREPARED_NOT_STARTED`; all four clients remain `NOT_STARTED`.

## First client attempt / recovery

- MCP Inspector 2.9.0 DISC-01: PASS (`auth_required` with isolated empty OAuth store).
- DCR registration and Authorization Code + PKCE flow started.
- User-visible login regression reported during the OAuth attempt.
- Test stopped before certification completion.
- Public DCR rollback: CLOSED / registration endpoint hidden / register route 404.
- Normal Commander login + HARA Identity validation after rollback: PASS.

CAMPAIGN_STATE=PAUSED_RECOVERY
