# H.A.R.A. Commander — MCP certification test-window safety runbook

Date: 2026-10-06
State: PREPARED_NOT_EXECUTED

This runbook prepares the operational boundary around future real-client
certification. It does not itself authorize or execute a client test.

## Before opening any client

1. Confirm canonical Git local = GitHub.
2. Run the certification preflight:
   `commander_mcp_certification_preflight.py --live-readonly`
3. Capture the environment snapshot:
   `commander_mcp_certification_snapshot.py --live-readonly --prod-worker-version <exact> --out <evidence-path>`
4. Confirm:
   - guarded DCR is live;
   - RFC 8414 advertises registration_endpoint;
   - CIMD remains false;
   - Identity sidecars are healthy;
   - certification bundle hashes match freeze V1;
   - source tree used for testing is clean.
5. Create the client evidence plan only after the exact client version is known.

No test should start from an unclean/unfrozen tree.

## Test-window safety boundary

During a client test:
- one client/version/surface at a time;
- certification scratch only under `/tmp/hara-mcp-cert/{run_id}`;
- no package install;
- no service control;
- no privilege escalation;
- no reboot/power actions;
- no raw token/secret capture;
- no modification of the 24-tool public contract;
- no auth weakening to make a client pass.

## Immediate stop conditions

Stop the client test and close public DCR if any of these occur:

- registration storm / repeated unexpected clients;
- invalid redirect accepted;
- client secret issued to a certification public client;
- remote HTTP redirect accepted;
- dangerous/custom scheme admitted outside policy;
- management endpoint accessible without registration access token;
- registration rate controls appear bypassed;
- Identity metadata no longer matches HARA issuer;
- client causes uncontrolled tool invocation;
- evidence pipeline captures credential material.

## Emergency DCR close

Prepared script:

`apps/identity-login/scripts/close_mcp_dcr_guarded.py`

Dry-run is default.

Execution requires:
- Identity owner PAT file;
- live Identity compose path;
- explicit `--execute`.

Fail-closed order:
1. switch gateway to CLOSED;
2. hide registration_endpoint;
3. recreate only DCR gateway + OAuth metadata sidecars;
4. require public DCR route to return 404;
5. only then disable backend ZITADEL DCR;
6. verify backend disabled and public route still closed.

If backend disable fails after step 4, the script does not reopen public DCR.

Reopening after investigation uses the separately governed
`promote_mcp_dcr_guarded.py` lane and its preconditions.

## After every client run

Required:
- cleanup certification scratch;
- delete disposable client registration when the host/test path permits;
- record reconnect behavior before deletion when required by matrix;
- hash/finalize evidence;
- classify every failure before code changes;
- issue certificate only if all REQUIRED cases pass.

## No-test state for this preparation slice

CERTIFICATION_PREFLIGHT_PREPARED=TRUE
CERTIFICATION_SNAPSHOT_PREPARED=TRUE
DCR_EMERGENCY_CLOSE_PREPARED=TRUE
REAL_CLIENT_TEST_EXECUTION=FALSE
LOCAL_CLIENT_TEST_EXECUTION=FALSE
