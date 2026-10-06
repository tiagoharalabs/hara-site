# MCP client compatibility source references

Snapshot date: 2026-10-06

These are maintainer references used to prepare the H.A.R.A. Commander
pre-test certification bundle. They are not test evidence.

## VS Code

- https://code.visualstudio.com/docs/agents/reference/mcp-configuration
- https://code.visualstudio.com/docs/agent-customization/mcp-servers
- https://code.visualstudio.com/api/extension-guides/ai/mcp

Current preparation assumptions:
- remote HTTP MCP is supported;
- OAuth is supported;
- portable `.mcp.json` and VS Code-native `.vscode/mcp.json` exist;
- VS Code supports server instructions and tool annotations;
- VS Code has CIMD support, but HARA Identity currently advertises DCR rather
  than CIMD.

## Cursor

- https://prod.cursor.com/docs/mcp
- https://prod.cursor.com/docs/cli/mcp

Current preparation assumptions:
- Streamable HTTP and OAuth are supported;
- project/global `mcp.json` is supported;
- static OAuth is available but is not the HARA primary certification path;
- current documented redirects:
  - desktop: http://localhost:8787/callback
  - web/cloud: https://www.cursor.com/agents/mcp/oauth/callback

## Claude / Anthropic

- https://claude.com/blog/claude-code-remote-mcp
- https://platform.claude.com/docs/en/agents-and-tools/mcp-connector

Current preparation assumptions:
- Claude Code supports remote MCP and native OAuth;
- the Anthropic Messages API MCP connector is a separate surface and expects a
  pre-obtained authorization token.

## MCP Inspector / protocol

- https://modelcontextprotocol.io
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://php.sdk.modelcontextprotocol.io/get-started/inspector/

Current preparation assumptions:
- Inspector is suitable as the manual/wire reference host;
- MCP 2026-07-28 deprecates DCR in favor of CIMD while retaining DCR as
  compatibility behavior.

Do not convert these assumptions into PASS claims. The certification evidence
files are the only accepted client PASS proof.
