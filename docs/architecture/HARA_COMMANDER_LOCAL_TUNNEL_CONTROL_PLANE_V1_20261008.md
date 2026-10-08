# H.A.R.A. Commander — Local Tunnel Control Plane V1

Date: 2026-10-08
State: **CANONICAL TARGET / SOURCE CANDIDATE**
Branch: `local/commander-local-tunnel-control-plane-20261008`

## Product law

For customer machines, the H.A.R.A. Cloud is the **control plane**, not the
per-tool data plane.

Default target topology:

```text
H.A.R.A. Cloud
  Identity / device registry / plan / billing / revoke
  one-time authorization code
  signed product lease
          |
          | occasional control traffic
          v
Customer machine
  H.A.R.A. Commander Agent
  hara-commander mcp
          ^
          |
  OpenAI Secure MCP Tunnel
          ^
          |
ChatGPT / Codex / OpenAI
```

A tool call must not traverse the H.A.R.A. Worker when LOCAL_TUNNEL is active.

## Customer onboarding

1. User logs into H.A.R.A. Commander through H.A.R.A. Identity.
2. User pairs/enrolls a computer.
3. Commander installs the Agent and the pinned official OpenAI tunnel-client.
4. User configures an OpenAI tunnel with:
   `hara-commander tunnel configure`.
5. The site generates a one-time, device-bound H.A.R.A. authorization code.
6. On the computer, the user runs:
   `hara-commander authorize`.
7. The Agent exchanges the code for a signed six-hour H.A.R.A. product lease.
8. OpenAI tool traffic flows through the OpenAI tunnel directly to
   `hara-commander mcp`.

## Authorization

- authorization-code lifetime: 10 minutes;
- authorization code is stored server-side only as SHA-256;
- one pending code per device; a new code supersedes the previous one;
- code is device and tenant bound;
- lease lifetime: 6 hours;
- lease is RS256 signed by H.A.R.A.;
- Agent contains only the public verification material;
- local MCP fails closed without a valid LOCAL_TUNNEL lease;
- expiration returns structured `AUTHORIZATION_EXPIRED` with the Commander
  reauthorization URL;
- OpenAI tunnel may remain connected while H.A.R.A. execution authority is
  expired.

This separates transport availability from H.A.R.A. execution authority.

## Cloud request law

In LOCAL_TUNNEL mode the background Agent performs:

- zero `/api/device/calls/next` polling;
- zero periodic timer-based H.A.R.A. heartbeat;
- zero per-tool H.A.R.A. relay;
- zero H.A.R.A. cloud quota transaction per local tool.

H.A.R.A. persistence is event-driven instead of periodic:

- `MCP_START`: aggregate metering sync only when the previous successful sync is
  at least one hour old;
- `MCP_STOP`: aggregate metering sync only when the MCP session itself lasted at
  least one hour **and** the previous successful sync is at least one hour old;
- no metering request runs in the middle of an open MCP session;
- authorization/lease exchange also carries the same aggregate usage report, so
  an MCP start immediately after authorization does not create a duplicate sync.

The server independently enforces the same one-hour minimum interval. Duplicate
`device + session + event` reports are idempotent.

The six-hour manual authorization flow adds:

- one portal code request;
- one device lease exchange.

At most four six-hour authorization cycles/day means eight authorization-control
requests/day. Event-driven metering is additionally capped by the one-hour
minimum to at most 24 accepted metering syncs/day in an intentionally pathological
start/stop pattern. Therefore the absolute core control-plane ceiling modeled for
one continuously active device is 32 requests/day, while a normal long-running
MCP session is substantially below that ceiling.

## Usage accounting

Product usage and infrastructure traffic are separate metrics.

Local MCP execution history remains in the device SQLite store.

At authorization time and eligible MCP start/stop events, the Agent sends
metadata-only cumulative aggregates:

- local lifetime governed execution count;
- recent daily buckets;
- random MCP session id;
- MCP start/stop timestamp and, for stop, bounded session duration;
- Agent version and transport mode.

It does not send commands, paths, file contents, stdout or results. The cloud
stores only the aggregate counters plus a minimal metering event record.

Server aggregation is monotonic/idempotent with MAX/upsert semantics. A retry
does not double count.

Re-enrollment creates a new per-device baseline so old local history is not
reattributed to the new device identity.


### Trial / Free enforcement without per-tool cloud calls

For metered plans in `LOCAL_TUNNEL`, the six-hour authorization can allocate the
remaining entitlement balance to the signed local budget instead of the legacy
100-unit relay block. The Agent debits that budget locally and fails closed at
zero. Reauthorization reconciles the cumulative usage before another lease is
issued. The legacy relay path keeps the smaller block behavior.

The portal's governed-execution counter is:

`remote governed calls + synchronized local governed execution aggregates`.

It is not the Cloudflare request counter.

## OpenAI tunnel distribution

Linux installer pins OpenAI tunnel-client v0.0.15.

Supported packages:

- Linux amd64 SHA-256:
  `8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1`
- Linux arm64 SHA-256:
  `c51bfd883fc22e3445494a03c0179875176564bde470661b308fd83af5d01abb`

Origin:
`https://persistent.oaistatic.com/tunnel-client/v0.0.15`

The archive is verified before extraction. The binary is installed inside the
private H.A.R.A. Commander data directory rather than replacing a user-managed
global tunnel-client.

The OpenAI runtime API key is stored in a 0600 environment file and referenced
by the tunnel profile. It is not placed in argv, systemd unit text, Git or
Commander logs.

The local tunnel health listener uses an ephemeral loopback port.

## Doctor semantics

For LOCAL_TUNNEL:

- valid signed LOCAL_TUNNEL lease = H.A.R.A. execution authority;
- healthy OpenAI tunnel = data-plane transport authority;
- H.A.R.A. Cloud health = control-plane health and is optional while the lease
  remains valid.

Therefore a temporary H.A.R.A. Cloud outage does not stop active local tool
execution.

## Remote MCP fallback

The Commander Remote MCP/V1 relay remains available during migration for
non-migrated devices.

Once a device is marked LOCAL_TUNNEL, the remote relay refuses to enqueue work
and returns structured `DIRECT_PATH_REQUIRED`.

There is no silent fallback from LOCAL_TUNNEL to cloud relay.

## Platform status

Linux:
- LOCAL_TUNNEL source candidate implemented;
- local MCP full canary: 33/33 PASS;
- zero outbound H.A.R.A. IP-connect idle proof: PASS.

Windows:
- current customer path remains legacy relay;
- portal does not offer the six-hour LOCAL_TUNNEL authorization action;
- Windows local MCP/tunnel parity remains a separate release gate.

## Release boundary

This architecture is source-qualified but not yet deployed to PROD.

Before live promotion:

1. build/sign the new Agent release with canonical release-signing context;
2. apply D1 migration 0029;
3. deploy DEV Worker/UI;
4. run real OpenAI Secure MCP Tunnel canary with an actual tunnel_id/runtime key;
5. promote only after readback and rollback evidence.

State markers:

`COMMANDER_LOCAL_TUNNEL_ARCHITECTURE=CANONICAL_TARGET`

`COMMANDER_LOCAL_TUNNEL_ZERO_HARA_TOOL_RELAY=PASS`

`COMMANDER_LOCAL_TUNNEL_ZERO_IDLE_HARA_POLL=PASS`

`COMMANDER_LOCAL_TUNNEL_LEASE_6H=PASS`

`COMMANDER_LOCAL_TUNNEL_LOCAL_MCP_33_OF_33=PASS`

`COMMANDER_LOCAL_TUNNEL_PROD=PENDING_RELEASE_AND_LIVE_CANARY`
