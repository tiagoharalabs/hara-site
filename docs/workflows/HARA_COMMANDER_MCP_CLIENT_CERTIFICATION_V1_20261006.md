# H.A.R.A. Commander — MCP Multi-Client Certification V1

Date: 2026-10-06
State: PREPARED_NOT_EXECUTED

## Objective

Certify one unchanged H.A.R.A. Commander Simple MCP surface against multiple
independent MCP hosts without creating vendor-specific tool contracts.

Canonical endpoint:

`https://commander.haralabs.com.br/api/mcp?profile=simple`

Public contract:

- Simple MCP 1.1.0
- 24 vendor-neutral tools
- Streamable HTTP
- HARA Identity OAuth
- RFC 8414 live
- PKCE S256
- guarded DCR live
- public OAuth clients only
- no client secret
- CIMD prepared but not advertised

## Freeze before testing

Before the first real client is opened, freeze:

1. `client-compatibility-profile.v1.json`
2. `client-adapter-expectations.v1.json`
3. `client-certification-matrix.v1.json`
4. `certification-fixture-policy.v1.json`
5. `client-certification-evidence.schema.json`
6. exact canonical source commit
7. exact PROD Worker version
8. exact Identity DCR/metadata image versions

Changing any of the first four files after a client run starts creates a new
certification revision. Never edit the acceptance criteria retroactively to
make a client pass.

## Recommended certification order

1. MCP Inspector — manual/wire reference
2. VS Code — standards-heavy desktop + Agent Host
3. Cursor — desktop OAuth plus optional CLI/cloud surfaces
4. Claude Code — independent remote-MCP/OAuth implementation

The order is diagnostic only. A PASS from an earlier host cannot waive a case
for a later host.

## Standard evidence sequence

Every host runs the same phases:

1. Discovery
2. OAuth authorization-server discovery
3. client registration
4. human Authorization Code + PKCE
5. reconnect / registration reuse
6. tool catalog discovery
7. schema/annotation inspection
8. read-only device/filesystem calls
9. deterministic invalid-input error
10. governed file mutation
11. bounded process execution
12. audit/receipt correlation
13. optional interactive lifecycle
14. cleanup

The authoritative case list is machine-readable in
`client-certification-matrix.v1.json`.

## Certification fixture

All filesystem/process test effects are confined to:

`/tmp/hara-mcp-cert/{run_id}`

Forbidden during certification:
- package install;
- service control;
- privilege escalation;
- reboot/power operation;
- writes outside scratch;
- network side effects from certification commands.

Cleanup is a REQUIRED case.

## Evidence privacy

Never persist:
- access token;
- refresh token;
- registration access token;
- client secret;
- browser cookie;
- raw command text;
- raw file/result content.

Allowed evidence:
- client/version/surface;
- case id;
- HTTP status;
- MCP error code;
- tool name;
- request id;
- bridge receipt SHA-256;
- latency;
- concise PASS/FAIL note.

## Certificate

A client becomes `CERTIFIED` only when:
- every REQUIRED case passes;
- optional N/A cases have a reason;
- evidence privacy booleans remain false;
- the evidence file hashes to the certificate;
- the certificate references the frozen matrix hash and source commit.

Four certificates are required for:

`MULTI_CLIENT_CERTIFIED`

Targets:
- MCP Inspector
- VS Code
- Cursor
- Claude Code

## Failure classification before code changes

Every failure must be classified into exactly one category:

- HARA_PROTOCOL_OR_AUTH_DEFECT
- HARA_PRODUCT_UX_DEFECT
- CLIENT_LIMITATION_OR_BUG
- OPTIONAL_OR_UNSUPPORTED_MCP_CAPABILITY
- TEST_ENVIRONMENT_DEFECT

Do not add aliases, weaken OAuth, bypass approvals or inject static bearer tokens
just to convert a client-specific failure into PASS.

## Current boundary

This workflow is prepared only. No real client, local client harness, Inspector,
VS Code, Cursor or Claude Code certification was executed in this slice.

PRETEST_CERTIFICATION_ARTIFACTS=PREPARED
CLIENT_TEST_EXECUTION=FALSE
LOCAL_CLIENT_TEST_EXECUTION=FALSE
