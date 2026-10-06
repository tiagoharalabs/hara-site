# MCP Inspector certification card

State: PREPARED_NOT_EXECUTED

- Transport: Streamable HTTP
- URL: https://commander.haralabs.com.br/api/mcp?profile=simple
- Authentication: Quick OAuth Flow
- Expected authorization server: https://auth.haralabs.com.br
- Expected registration mode: guarded DCR
- Expected public tool count after authorization: 24
- Expected public tool prefix exposure: no `hara.*`

The primary run must not inject a bearer token manually.

Capture evidence into the common certification envelope:
`hara.commander.mcp-client-certification-evidence.v1`.

Do not record access_token, refresh_token, registration_access_token, cookies,
raw command content or raw result content.
