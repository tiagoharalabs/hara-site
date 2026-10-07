# H.A.R.A. Commander — Fleet Agent Rollout

Date: 2026-10-07
Branch: `local/commander-mcp-prod-compatible-20261006`

## Objective

Close the operational gap between the H.A.R.A. Commander MCP control plane and
the actual local fleet.

The desired topology is:

`MCP client -> H.A.R.A. Commander MCP -> named local Agent -> local host`

Every Linux fleet host must therefore have its own enrolled local Agent while
the Commander remains the centralized governed MCP/router.

## Gap found

Before this rollout, only:

- `nucleo-a`
- `sentinela-d`

were enrolled in the Commander tenant.

The following hosts were reachable through other management channels but had no
Commander Agent enrollment:

- `sentinela-a`
- `sentinela-b`
- `sentinela-c`
- `ninja-blue`
- `services`

This was an incomplete Agent rollout, not an MCP architecture limitation.

## Preflight

The official PROD installer was run in `preflight` mode on all five missing
hosts.

All five returned:

- Commander health reachable
- release manifest valid
- release signature valid
- systemd-user persistence ready
- stable Agent version `0.3.40`
- mutation_performed=false

## Enrollment method

Enrollment used the production pairing contract:

- one-time pairing token
- 10-minute TTL
- one current token per tenant/subject
- each newly issued token supersedes any prior unconsumed token
- tokens consumed sequentially, one host at a time
- no pairing token printed to logs
- Agent configured as `PERSISTENT_TRUSTED`

A PTY runner was used because the official installer intentionally reads the
pairing token from `/dev/tty`. The runner waits for the pairing prompt and
injects the token without terminal echo; output is additionally redacted against
the token value.

## Enrollment result

Sequential enrollment:

- `sentinela-a`: PASS
- `sentinela-b`: PASS
- `sentinela-c`: PASS
- `ninja-blue`: PASS
- `services`: PASS

Every newly enrolled host passed:

- Agent startup attestation
- enrollment transaction
- service active
- service enabled
- Agent version 0.3.40
- approval mode PERSISTENT_TRUSTED
- device token not exposed
- server-side consumed-pairing/device readback

## Núcleo reconciliation

`nucleo-a` was upgraded from Agent 0.3.39 to 0.3.40 while preserving its
existing enrollment.

A stale orphan cloud-Agent process from the prior 0.3.39 runtime was found
running concurrently with the systemd-managed Agent. It caused the control plane
to continue observing 0.3.39 even after the file on disk had been upgraded.

The orphan cloud-Agent was terminated. The managed Agent was preserved and the
existing local `hara-commander-agent mcp` process was explicitly left intact.

After one heartbeat cycle the control plane converged to 0.3.40.

## Final MCP proof

The H.A.R.A. Commander MCP now reports all seven Linux control/execution hosts as
ONLINE at Agent 0.3.40:

- `nucleo-a`
- `sentinela-a`
- `sentinela-b`
- `sentinela-c`
- `sentinela-d`
- `ninja-blue`
- `services`

Real `hara.health` calls routed by `computer` returned PASS on all seven.

Every host reported:

- Agent 0.3.40
- 13 registered functions
- 13 executable functions

This proves the fleet is not merely present in inventory; it is executable
end-to-end through the Commander MCP by host name.

## Pairing / D1 hygiene

Post-rollout production readback:

- total device records: 13
- consumed pairing tokens: 13
- consumed pairings with device provenance: 13
- consumed pairing without device: 0
- current valid pairing tokens: 0
- PROD D1 readback: PASS

No live one-time pairing token was left outstanding.

## Boundary

The legacy/offline `HARA_WIN11` test enrollment remains outside this Linux
fleet rollout. It is not used as evidence for the seven-host Linux fleet state.

## State

`COMMANDER_MCP_LOCAL_FLEET_ENROLLMENT=CLOSED_PASS`

`COMMANDER_LINUX_FLEET_ONLINE_7_OF_7=PASS`

`COMMANDER_LINUX_FLEET_AGENT_0_3_40_7_OF_7=PASS`

`COMMANDER_LINUX_FLEET_HEALTH_13_OF_13_7_OF_7=PASS`
