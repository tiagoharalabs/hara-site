# HARA Commander Product V1 — canonical mission — 2026-09-22

## Product definition

HARA Commander V1 is a simple customer connectivity product.

The customer flow is:

1. create/login to a HARA account;
2. install HARA Commander Agent on the customer's Linux or Windows computer;
3. pair that computer to the customer's tenant using a short-lived one-time token;
4. the Agent maintains an outbound-only authenticated connection;
5. the customer authorizes ChatGPT, Codex or another supported MCP client;
6. the MCP call is routed to the selected connected computer through the HARA-owned relay;
7. the local Agent invokes only the governed HARA tool surface and returns a sanitized result/receipt.

## Explicit non-goals for V1

Commander is not:
- a HARA fleet NOC;
- a Paradox observability dashboard;
- a server-health/degraded-state console;
- a generic shell/SSH/file browser;
- a per-customer Cloudflare Tunnel deployment.

Customer-facing state should be simple:
- account;
- plan/quota;
- computers;
- connected/offline/revoked;
- ChatGPT/Codex authorization;
- sessions/security.

Do not expose internal HARA infrastructure health states such as `Degradado` in the normal customer dashboard.

## Current implementation

PASS:
- HARA Identity login;
- tenant/plan/entitlement/quota;
- device pairing token, one-time and short-lived;
- Linux enrollment bootstrap;
- Windows enrollment bootstrap;
- device credential;
- heartbeat/presence;
- device revocation;
- Linux user systemd persistence;
- Windows Scheduled Task persistence;
- Windows DPAPI token protection + ACL hardening;
- portal device list;
- public installer delivery.

Current DEV:
`https://hara-commander-dev-v2.tiago-sartori.workers.dev/`

Current Worker:
`e6303c51-135c-4f83-bd56-c3a6fdcb772f`

Functional relay baseline:
`abc1768f39c29bacb52396c10494d0ba1f931b4c`

Repository HEAD before the latest succession reconciliation:
`3f6c921e81e09c98f2d385f87079101a43746fad`

The commits after `abc1768` are documentation/design/succession updates; they do not supersede the relay functional baseline.

Validation:
- `DEVICE_PAIRING_VALIDATION=PASS`
- `LINUX_DEVICE_INSTALLER_STATIC=PASS`
- `WINDOWS_DEVICE_INSTALLER_STATIC=PASS`
- `PORTAL_DEVICE_INSTALLERS=PASS`
- `PER_DEVICE_CLOUDFLARED_DEPENDENCY=FALSE`
- `OUTBOUND_CALL_CHANNEL_HEALTH_ONLY=PASS`
- `DEVICE_RELAY_ATOMIC_CLAIM=PASS`
- `DEVICE_RELAY_RESULT_ROUNDTRIP=PASS`
- `DEVICE_RELAY_IDEMPOTENCY=PASS`
- `DEVICE_RELAY_ARBITRARY_TOOL=DENIED`
- `CUSTOMER_DEGRADED_LANGUAGE=ABSENT`

## Current transport proof

`OUTBOUND_CALL_CHANNEL_HEALTH_ONLY=PASS`

The installed Linux and Windows Agents now have a real outbound call channel. The current proven canary is intentionally limited to `hara.health`:

- durable relay call state;
- outbound device polling;
- atomic `PENDING -> EXECUTING` claim;
- `COMPLETED/FAILED` result return;
- request/call/device correlation;
- result roundtrip;
- idempotent enqueue;
- arbitrary/unknown tool denied fail-closed.

The next functional blocker is not transport. It is the portable local governed tool bridge plus public MCP routing to the selected customer device.

Next implementation gate:
- expose the exact governed five-tool local contract through the Agent;
- keep arbitrary shell/filesystem/SSH absent;
- bind public MCP identity/tenant to a selected online device;
- route `hara.health`, list, describe, read-only invoke and receipt through that device;
- run a real ChatGPT/Codex read-only canary.

The canonical relay architecture remains:
`hara-platform/docs/architecture/HARA_REMOTE_MCP_RELAY_V1.md`.

Do not call heartbeat/presence a completed tunnel, and do not call the health-only outbound channel a completed five-tool product bridge.


## Visual baseline

Dark mode is the current approved visual reference.

The light theme refinement is named `Clarus` and is specified at:

`docs/design/HARA_COMMANDER_CLARUS_V1_20260922.md`

Clarus must preserve the same product hierarchy while reducing the current pale-blue wash. The sidebar remains dark; the workspace moves to a neutral cold off-white canvas with stronger white-card separation.

Visual work is subordinate to the V1 functional mission and must not reintroduce fleet/NOC/observability concepts.


## Cross-repository canonical anchors

HARA Platform Commander reconciliation:
- prior mission reconciliation PR: `#1019`
- prior documentation merge: `6a81f37f4d2975da3b86014c4b6f03ed457d769e`
- Ponto 0 closure PR: `#1022`
- Ponto 0 merge commit: `8823d179c25840add5f51028d45d25724097ae00`
- HARA Site Ponto 0 closure commit: `53d407765f7bfa32a8c71d13e0cc44b6515603a1`
- Issue #747 reconciliation comment id: `5783791551`

Canonical HARA Platform handoff:
`docs/handoffs/HARA_COMMANDER_DEVICE_CONNECT_SUCCESSOR_HANDOFF_20260922T203602Z.md`

This hara-site mission document and the HARA Platform handoff must be treated as the same product authority. If they diverge, reconcile before implementation.
