# H.A.R.A. Commander — Local Tunnel Control Plane source qualification

Date: 2026-10-08
Branch: `local/commander-local-tunnel-control-plane-20261008`
Agent source candidate: **0.3.43**
Source implementation commit: `2a971fe1c207f59860058f69ffd0a55501e30d1a`

## Problem reproduced

Cloudflare Workers account usage showed the production `hara-commander` Worker
above the 100,000 requests/day Free-plan threshold.

The installed relay Agent architecture still performed periodic H.A.R.A.
`/api/device/calls/next` polling even when the customer machine had no useful
work.

The product's governed-execution counter and Cloudflare request count are
different metrics; the UI has been corrected to say so.

## Architecture change

The customer product is now source-implemented as local-first:

`OpenAI Secure MCP Tunnel -> hara-commander mcp -> customer machine`

H.A.R.A. Cloud handles identity, device registration, billing/entitlement,
revocation, release/update, authorization codes and signed leases.

Per-tool relay through H.A.R.A. Cloud is not part of LOCAL_TUNNEL.

## Proofs

PASS:
- migration chain 0001..0029;
- 10-minute one-time device authorization code;
- six-hour signed product lease;
- invalid/replayed code fail-closed;
- authorization validation occurs before budget mutation;
- signed lease required for all local tool calls in LOCAL_TUNNEL;
- zero H.A.R.A. polling and zero periodic timer-based heartbeat branch;
- event-driven MCP_START/MCP_STOP metering sync with one-hour minimum interval;
- MCP_STOP sync additionally requires a session duration of at least one hour;
- Trial/Free LOCAL_TUNNEL budget can carry the remaining period entitlement locally;
- strace runtime proof: zero AF_INET/AF_INET6 outbound connect while idle;
- official OpenAI tunnel-client v0.0.15 CLI/flags validated;
- OpenAI profile persists env reference, not runtime API key;
- pinned Linux amd64/arm64 archive hashes;
- tunnel key 0600 and absent from argv/unit/log output;
- remote MCP returns DIRECT_PATH_REQUIRED after migration;
- local usage sync metadata-only and idempotent;
- re-enrollment usage baseline prevents double attribution;
- signed product lease gate;
- local budget/replay gates;
- customer privacy/NOC gates;
- full and Simple MCP regressions;
- Agent 0.3.43 local MCP functional canary: 33/33 PASS;
- LOCAL_TUNNEL unit economics: zero H.A.R.A. relay per tool.

## Quantitative control-plane model

With six-hour authorization and event-driven metering:
- max authorization cycles/day: 4;
- authorization requests/cycle: 2;
- authorization-control requests/day: 8;
- metering sync: start/stop only, minimum one hour between accepted syncs;
- worst-case accepted metering syncs/day: 24;
- absolute modeled core-control ceiling/day: 32;
- absolute modeled core-control ceiling/30 days: 960.

For a Free 10,000-governed-execution month, even that pathological ceiling is a
9.6% control-request ratio versus one cloud request per execution, a 90.4%
reduction before counting the much larger elimination of idle polling. Normal
long-running tunnel sessions are materially below this ceiling.

## Current blockers to live cutover

- Agent 0.3.43 is source candidate only; signed release packaging is pending the
  canonical signing context. The full readiness suite stops fail-closed at
  `RELEASE_SHA256_DRIFT:agent/linux.py` because the published signed manifest
  remains 0.3.41.
- migration 0029 is not applied live.
- Cloudflare Worker is currently over its daily Free request allocation, so DEV
  and PROD live readback are unavailable.
- a real OpenAI tunnel_id/runtime API key has not yet been used for the final
  end-to-end tunnel canary.
- Windows local-tunnel parity remains pending.

No PROD mutation for this architecture was performed.

`COMMANDER_LOCAL_TUNNEL_SOURCE_QUALIFICATION=CLOSED_PASS`

`COMMANDER_LOCAL_TUNNEL_LIVE_CUTOVER=PENDING`
