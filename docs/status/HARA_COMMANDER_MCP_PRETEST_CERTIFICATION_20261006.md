# H.A.R.A. Commander — MCP pre-test certification readiness

Date: 2026-10-06
State: PREPARED_NOT_EXECUTED

## What was advanced without client testing

Prepared:
- public/internal compatibility manifests;
- four-client target matrix;
- 22-case common certification matrix;
- evidence privacy schema;
- certificate schema;
- multi-client rollup policy;
- deterministic scratch/process fixture policy;
- VS Code portable/native templates;
- Cursor template;
- Claude Code certification card;
- MCP Inspector certification card;
- evidence preparation/reconciliation utility.

No client was launched.
No local MCP client test was run.
No certification evidence was fabricated.
No PASS claim is made for VS Code, Cursor, Claude Code or Inspector.

## Existing live prerequisites inherited from canonical state

Already closed before this slice:
- Simple MCP 1.1 source/preprod conformance;
- 24 public tools;
- MCP 2025-06-18 / 2025-11-25 / 2026-07-28 synthetic conformance;
- RFC 8414 PROD;
- guarded DCR PROD;
- strict generic-auto OAuth discovery PASS;
- disposable DCR register/read/delete lifecycle PASS.

## Prepared client expectations

VS Code:
- HTTP remote MCP;
- portable `.mcp.json` preferred for new configuration;
- native `.vscode/mcp.json` compatibility template retained;
- primary certification uses generic auth, not static client ID.

Cursor:
- project/global `mcp.json`;
- current desktop and web/cloud OAuth redirects captured in expectations;
- primary certification uses guarded generic OAuth.

Claude Code:
- remote Streamable HTTP target;
- native host OAuth expected;
- no pre-seeded bearer in primary certification.

MCP Inspector:
- Streamable HTTP;
- Quick OAuth Flow;
- reference manual/wire client.

## Not deployed in this slice

`apps/commander/public/mcp/compatibility-v1.json` is prepared as a future
public machine-readable compatibility document. It is NOT claimed live because
no Commander Worker release was performed in this slice.

## Next actual execution

The next operation that materially increases client confidence is no longer
architecture work. It is running the frozen certification workflow against the
four real hosts and recording evidence.

MCP_PRETEST_ARCHITECTURE=READY
MCP_CERTIFICATION_MATRIX=FROZEN_V1_CANDIDATE
MCP_EVIDENCE_SCHEMA=PREPARED
MCP_CLIENT_CERTIFICATE_SCHEMA=PREPARED
MCP_MULTICLIENT_ROLLUP=PREPARED
MCP_PUBLIC_COMPATIBILITY_MANIFEST=PREPARED_NOT_DEPLOYED
MCP_REAL_CLIENT_TESTS=NOT_RUN
MCP_LOCAL_CLIENT_TESTS=NOT_RUN

Certification bundle commit:
- `c4e2a50e81c1d7487116c35b551924862f21018c`

The frozen artifact hashes in `apps/commander/mcp/certification-freeze.v1.json` refer to that bundle.
