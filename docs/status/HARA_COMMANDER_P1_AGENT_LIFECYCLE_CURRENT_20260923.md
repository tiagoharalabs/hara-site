# H.A.R.A. Commander — P1 Agent lifecycle current — 2026-09-23

## Scope

This package hardens the post-P0 customer Agent lifecycle without broadening the Commander execution surface.

Invariants preserved:

- outbound-only Agent transport;
- no arbitrary shell;
- no SSH surface;
- no generic filesystem surface;
- exact five governed tool surface;
- HARA Services remains operational authority;
- device credentials are not printed by lifecycle commands.

## Delivered

### Device self-revocation

New authenticated endpoint:

`POST /api/device/revoke-self`

The endpoint authenticates with the existing device bearer credential and atomically:

- marks the device `REVOKED`;
- records `revoked_at_utc`;
- removes current device selection rows;
- cancels pending/executing device calls with `DEVICE_REVOKED`.

The endpoint is fail-closed without a valid device credential.

### Linux lifecycle

Supported installer actions:

- `install`
- `status`
- `doctor`
- `update`
- `uninstall`

`doctor` verifies:

- enrollment/config exists;
- Agent binary exists;
- user systemd unit exists;
- service is enabled;
- service is active;
- Agent self-test passes;
- authenticated remote heartbeat succeeds.

`update`:

- downloads to a temporary file;
- runs Agent self-test before replacement;
- preserves the prior Agent as a rollback candidate;
- restarts the service;
- automatically restores the prior Agent when the new version fails to become active.

`uninstall`:

- attempts authenticated server-side self-revocation before deleting the local credential;
- continues local uninstall if the network is unavailable;
- reports `SERVER_DEVICE_REVOKE=PENDING` when server revocation could not be confirmed;
- never prints the device token.

### Windows lifecycle

The Windows installer exposes the same product lifecycle contract:

- `install`
- `status`
- `doctor`
- `update`
- `uninstall`

The device token remains DPAPI-protected in the local config. `doctor` and self-revoke decrypt it only in memory for the authenticated request. Update keeps a rollback copy and restores it if the scheduled task does not return to `Running`.

A live Windows host was not available during this package homologation; Windows validation is static/parser-oriented in this gate and must receive a real-host canary before claiming Windows terminal lifecycle proof.

## Homologation evidence

Linux / Worker local E2E:

- `P1_DEVICE_SELF_REVOKE_HTTP=PASS`
- device state after revoke: `REVOKED`
- selection count after revoke: `0`
- pending call after revoke: `CANCELLED`
- `HARA_COMMANDER_AGENT_DOCTOR=PASS`
- `COMMANDER_REMOTE_HEARTBEAT=PASS`
- `HARA_COMMANDER_AGENT_UNINSTALL=PASS`
- `SERVER_DEVICE_REVOKE=PASS`
- `P1_LINUX_UPDATE_FAILURE_ROLLBACK=PASS`
- `P1_LINUX_UPDATE_SUCCESS=PASS`

DEV Cloudflare readback:

- `DEV_AGENT_DOCTOR_ASSET=PASS`
- `DEV_SELF_REVOKE_INSTALLER=PASS`
- `DEV_AGENT_032=PASS`
- `DEV_SELF_REVOKE_AUTH_GATE=PASS`

Static security/regression gates:

- `COMMANDER_EXACT_FIVE_TOOL_AGENT=PASS`
- `ARBITRARY_SHELL_EXPOSED=FALSE`
- `PER_DEVICE_CLOUDFLARED_DEPENDENCY=FALSE`
- `OUTBOUND_CALL_CHANNEL_FIVE_TOOL_READY=PASS`
- `AGENT_REMOTE_SELF_REVOKE=PASS`
- `AGENT_DOCTOR_REMOTE_HEARTBEAT=PASS`
- `AGENT_UPDATE_ROLLBACK_SAFE=PASS`

## Agent version

Current lifecycle package Agent version:

`0.3.2`

## Remaining product gates

The lifecycle package does not close these later product gates:

1. full clean-machine customer journey through real ChatGPT/Codex;
2. live Windows lifecycle canary;
3. MCP distribution/draft and final OpenAI review path;
4. billing/checkout and commercial activation;
5. customer-facing support/diagnostic workflow beyond CLI lifecycle commands.
