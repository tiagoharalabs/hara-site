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
`a80aff45-4f33-42ee-af45-9f7ca7c710d2`

Current code:
`34ebd1425061036b6e3ef96567a20024510e895f`

Validation:
- `DEVICE_PAIRING_VALIDATION=PASS`
- `LINUX_DEVICE_INSTALLER_STATIC=PASS`
- `WINDOWS_DEVICE_INSTALLER_STATIC=PASS`
- `PORTAL_DEVICE_INSTALLERS=PASS`
- `PER_DEVICE_CLOUDFLARED_DEPENDENCY=FALSE`
- `CUSTOMER_DEGRADED_LANGUAGE=ABSENT`

## Remaining functional blocker

`OUTBOUND_CALL_CHANNEL_IMPLEMENTED=FALSE`

The installed Agents currently prove identity, pairing, presence and revocation. They do not yet transport MCP tool calls.

Next implementation gate:
- durable relay call state;
- outbound device event/poll channel;
- atomic `PENDING -> EXECUTING` claim;
- local governed MCP execution;
- `COMPLETED/FAILED` result return;
- request/call/device correlation;
- ChatGPT/Codex real read-only canary.

The canonical relay architecture remains:
`hara-platform/docs/architecture/HARA_REMOTE_MCP_RELAY_V1.md`.

Do not call heartbeat/presence a completed tunnel.
