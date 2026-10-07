# H.A.R.A. Commander — MCP PROD-compatible runtime candidate

Date: 2026-10-06
Base: `6dc6d28f9cf6e609df469b3700468b1f2027c274`
Branch: `local/commander-mcp-prod-compatible-20261006`

## Why this branch exists

The current PROD Worker declares source `6dc6d28` and carries the aggregate
usage-history/bootstrap product fix. The broader MCP development line diverged
from that PROD source and also contains unrelated migration/bootstrap assets.

This branch starts from the actual PROD source and ports only the MCP runtime
corrections required by the current live gap.

## Runtime delta

Preserved:
- simple MCP surface remains exactly 24 tools;
- product transaction history remains `AGGREGATE_ONLY`;
- product aggregate history does not include tool IDs, payloads or results;
- public portal activity/SLO diagnostics remain outside the product;
- no migration, public asset, bootstrap or Wrangler config change.

Changed:
- `hara.activity` uses the existing privacy-safe activity implementation;
- `hara.calls.recent` uses the existing metadata-only recent-call implementation;
- only `DEVICE_OFFLINE` is normalized from MCP error to structured
  `state=UNAVAILABLE`, category `DEVICE_AVAILABILITY`, `retryable=true`;
- permission/schema/policy/selection errors remain MCP errors.

## Current PROD gap proven live

Before promotion:
- offline `HARA_WIN11` through PROD `hara.health` -> connector `INVALID_ARGUMENT`
  with underlying `DEVICE_OFFLINE`;
- PROD `hara.calls.recent` -> connector `INVALID_ARGUMENT` with underlying
  `LOCAL_DIAGNOSTICS_REQUIRE_SIGNED_AGENT_UPDATE`.

## Source validation

PASS:
- `COMMANDER_SIMPLE_MCP_TOOL_COUNT=24`
- Simple MCP adapter regression
- full customer MCP edge regression
- aggregate history independent of diagnostics
- recent-call projection metadata-only
- full/simple `DEVICE_OFFLINE` operational-state contract
- public runtime boundary
- complete source preprod readiness for the `6dc6d28` line.

## Promotion boundary

No PROD version upload or traffic change has been performed.

Next safe step is to deploy this exact committed branch to DEV, read back the
exact DEV Worker version, and run the same source/runtime checks. A PROD version
candidate may only be uploaded after that DEV proof, and traffic promotion
remains a separate explicit gate.
