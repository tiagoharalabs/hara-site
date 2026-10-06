# H.A.R.A. Commander — MCP client configuration templates

State: PREPARED_NOT_CLIENT_TESTED
Date: 2026-10-06

Canonical endpoint:

`https://commander.haralabs.com.br/api/mcp?profile=simple`

These templates intentionally contain no API key, bearer token, client secret or
pre-registered client ID. The certification path must exercise the standards-
based HARA Identity OAuth discovery/registration flow rather than bypass it.

## VS Code

Preferred new portable workspace/user format:
- template: `vscode.portable.mcp.json`
- workspace destination: `.mcp.json`
- user portable destination: `~/.copilot/mcp-config.json`

VS Code-native compatibility format:
- template: `vscode.native.mcp.json`
- destination: `.vscode/mcp.json` or the VS Code user MCP configuration

Do not add `oauth.clientId` during the primary certification run. VS Code
supports explicitly configured client IDs, but the H.A.R.A. certification goal
is to prove generic discovery/registration first.

## Cursor

Template:
- `cursor.mcp.json`

Destinations:
- project: `.cursor/mcp.json`
- global: `~/.cursor/mcp.json`

The guarded HARA DCR policy already admits the current Cursor OAuth redirect
classes:
- Desktop: `http://localhost:8787/callback`
- Web/Cloud Agents: `https://www.cursor.com/agents/mcp/oauth/callback`

Primary certification must omit static `auth.CLIENT_ID` so the generic OAuth
path is exercised. Static OAuth remains a supported fallback mode for customer
environments that require pre-registration, but it is not the certification
path.

## Claude Code

Certification target: Claude Code remote MCP using the canonical Streamable
HTTP URL and its native OAuth flow.

Do not pre-seed a bearer token for the primary Claude Code certification.
The goal is to observe HARA Identity discovery/registration/login as the host
performs it.

Important distinction: the Anthropic Messages API MCP connector accepts a
pre-obtained `authorization_token`; that API connector is a separate
integration surface and is not a substitute for the Claude Code native-OAuth
certification.

## MCP Inspector

Transport:
- Streamable HTTP

Server URL:
- canonical Simple MCP endpoint above

Authentication:
- use the Inspector Quick OAuth Flow
- do not paste a manually generated bearer token for the primary certification

The Inspector is the reference manual/wire-validation client in the matrix.

## Client-test freeze rule

Before a real host test starts, record:
- exact client version;
- exact surface (desktop/CLI/cloud/agent-host);
- operating system;
- config template used;
- certification matrix version.

Do not alter the server contract to make a single host pass until the failure
is classified as one of:
1. HARA protocol/auth defect;
2. HARA product UX defect;
3. client-specific limitation/bug;
4. unsupported/optional MCP capability.

Any client-specific workaround must remain outside the 24-tool public contract
unless at least two independent MCP clients require the same protocol-level
change.
