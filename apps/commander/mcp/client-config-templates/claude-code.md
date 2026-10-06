# Claude Code remote MCP certification card

State: PREPARED_NOT_EXECUTED

Canonical remote MCP URL:

`https://commander.haralabs.com.br/api/mcp?profile=simple`

Primary certification requirements:
- remote Streamable HTTP;
- Claude Code native OAuth path;
- no pre-seeded bearer token;
- no static customer API key;
- record exact Claude Code version and platform;
- require 24-tool discovery after authorization;
- require read-only call before governed mutation;
- capture HARA request/receipt correlation without raw content.

Do not confuse this target with the Anthropic Messages API MCP connector. The
Messages API connector can consume a pre-obtained authorization token and is a
separate certification surface.

No CLI command is frozen in this file before live homologation because the
Claude Code CLI surface may evolve independently of the MCP wire contract. The
canonical invariant is the server URL + native remote-MCP OAuth behavior.
