# H.A.R.A. Commander — Generic MCP client onboarding

Date: 2026-10-06

## Canonical endpoint

`https://commander.haralabs.com.br/api/mcp?profile=simple`

The Simple profile is the recommended customer-facing MCP surface.

## Host templates

These are transport templates, not a claim that automatic OAuth registration is
already complete for every host.

### VS Code / Cursor-style HTTP server entry

```json
{
  "servers": {
    "hara-commander": {
      "type": "http",
      "url": "https://commander.haralabs.com.br/api/mcp?profile=simple"
    }
  }
}
```

### Claude Code-style remote HTTP registration

```bash
claude mcp add --transport http hara-commander \
  'https://commander.haralabs.com.br/api/mcp?profile=simple'
```

### MCP Inspector

Use the same Streamable HTTP URL:

`https://commander.haralabs.com.br/api/mcp?profile=simple`

## Authentication note

The Commander resource server already returns standards-based 401 +
resource_metadata and publishes Protected Resource Metadata.

HARA Identity currently exposes valid OIDC discovery and PKCE S256 but does not
yet publish RFC 8414 Authorization Server Metadata, CIMD support, or a DCR
registration_endpoint in its public metadata.

Until that Identity slice closes, hosts that require automatic client
registration may need an explicitly provisioned/static OAuth client path.

Do not weaken HARA Identity or permanently enable unauthenticated DCR merely to
make a host connect. Upgrade Identity metadata/CIMD instead.

## Verification

Protocol/source:
`node apps/commander/scripts/test_customer_mcp_conformance.mjs`

Live auth discovery:
`python3 apps/commander/scripts/commander_mcp_auth_discovery_probe.py`

Future strict auth gate:
`python3 apps/commander/scripts/commander_mcp_auth_discovery_probe.py --require-generic-auto`
