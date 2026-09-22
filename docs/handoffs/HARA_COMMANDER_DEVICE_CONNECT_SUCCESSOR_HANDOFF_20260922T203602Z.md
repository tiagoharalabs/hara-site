# HARA Commander — device-connect successor handoff — 2026-09-22 20:36:02Z

## Canonical mission

HARA Commander V1 is a simple customer connectivity product.

Customer flow:

`HARA account -> Linux/Windows computer -> Commander Agent -> outbound HARA relay -> ChatGPT/Codex -> exact governed five-tool bridge`

V1 is explicitly **not**:
- a fleet NOC;
- a Paradox/observability dashboard;
- a degraded-health console;
- a generic shell/SSH/filesystem browser;
- a per-customer Cloudflare Tunnel product.

Normal customer states must remain simple: signed in, computer connected/offline/revoked, waiting for AI client, ready.

Do not expose internal infrastructure words such as `Degradado` in the customer dashboard.

## Current runtime

- portal: `https://hara-commander-dev-v2.tiago-sartori.workers.dev/`
- HARA Identity: `https://auth.haralabs.com.br/`
- public MCP: `https://mcp.haralabs.com.br/mcp`
- Worker: `e6303c51-135c-4f83-bd56-c3a6fdcb772f`
- hara-site branch: `issue29-commander-dev-v3-auth`
- functional relay baseline: `abc1768f39c29bacb52396c10494d0ba1f931b4c`
- pre-handoff repository HEAD: `3f6c921e81e09c98f2d385f87079101a43746fad`

## Proven product pieces

PASS:
- HARA Identity login and tenant resolution;
- plan/entitlement/quota primitives;
- dedicated reviewer tenant/account;
- one-time short-lived device pairing;
- Linux installer;
- Windows installer;
- Linux user-systemd persistence;
- Windows per-user Scheduled Task persistence;
- Windows DPAPI token storage;
- Windows ACL hardening;
- device credential;
- heartbeat/presence;
- device list;
- device revocation;
- public installer delivery;
- no per-device cloudflared dependency;
- durable outbound device-call state;
- outbound Agent polling;
- atomic `PENDING -> EXECUTING` claim;
- duplicate claim denied;
- `COMPLETED/FAILED` result return;
- request/call/device correlation;
- result roundtrip;
- enqueue idempotency;
- arbitrary/unknown tool denied fail-closed;
- customer-facing degraded language removed.

Fresh validation on 2026-09-22:
- `DEVICE_RELAY_ENROLLMENT=PASS`
- `DEVICE_RELAY_ONLINE=PASS`
- `DEVICE_RELAY_ENQUEUE=PASS`
- `DEVICE_RELAY_ATOMIC_CLAIM=PASS`
- `DEVICE_RELAY_DUPLICATE_CLAIM=DENIED`
- `DEVICE_RELAY_COMPLETE=PASS`
- `DEVICE_RELAY_RESULT_ROUNDTRIP=PASS`
- `DEVICE_RELAY_IDEMPOTENCY=PASS`
- `DEVICE_RELAY_ARBITRARY_TOOL=DENIED`
- `DEVICE_RELAY_SECRET_EXPOSED=FALSE`
- `DEVICE_RELAY_HEALTH_E2E=PASS`
- `DEVICE_RELAY_CANARY_CLEANUP=PASS`
- `LINUX_DEVICE_INSTALLER_STATIC=PASS`
- `WINDOWS_DEVICE_INSTALLER_STATIC=PASS`
- `PORTAL_DEVICE_INSTALLERS=PASS`
- `PER_DEVICE_CLOUDFLARED_DEPENDENCY=FALSE`
- `OUTBOUND_CALL_CHANNEL_HEALTH_ONLY=PASS`
- `ARBITRARY_SHELL_EXPOSED=FALSE`
- `CUSTOMER_DEGRADED_LANGUAGE=ABSENT`

## Important maturity boundary

The outbound transport is real, but currently proven only with `hara.health`.

Do **not** describe the current state as a complete five-tool customer bridge.

Still pending:
1. portable local governed implementation for the exact five tools:
   - `hara.health`
   - `hara.functions.list`
   - `hara.functions.describe`
   - `hara.functions.invoke`
   - `hara.receipts.get`
2. bind public MCP identity/tenant to one selected online customer device;
3. route all five governed calls through the outbound relay;
4. execute against the bounded local bridge without arbitrary shell/filesystem/SSH;
5. return sanitized result + receipt;
6. test Windows installer/runtime on a real Windows host;
7. run ordinary ChatGPT/Codex read-only canary without Desktop Commander.

## Architecture decision

Canonical relay architecture:
`hara-platform/docs/architecture/HARA_REMOTE_MCP_RELAY_V1.md`

The customer Agent opens an authenticated outbound channel to HARA. The customer does not install or administer a Cloudflare Tunnel.

Cloudflare remains infrastructure for HARA-owned public ingress only.

Do not create a second relay architecture or use runtime HARA domain tables as a transport queue.

## UI/design decision

Dark mode is the currently accepted visual reference.

Light theme refinement is `Clarus`:
`docs/design/HARA_COMMANDER_CLARUS_V1_20260922.md`

Clarus may refine canvas/cards/borders/light-theme contrast, but must not change the simple device-connect information architecture.

Functional product closure has priority over cosmetic work.

## Publication and billing boundary

OpenAI submission assets/reviewer infrastructure already exist, but publication is downstream of a real ordinary-client canary.

Order:
1. five-tool device bridge;
2. real Windows runtime test;
3. public MCP -> selected device routing;
4. ordinary ChatGPT/Codex read-only canary;
5. OpenAI portal tool scan/submission;
6. billing/payment-provider activation.

Billing primitives already exist internally; payment integration is intentionally deferred.

## Immediate continuation order

1. preserve simple device-connect scope;
2. finish exact five-tool portable local bridge;
3. bind selected online device to public MCP session;
4. run Linux device five-tool canary;
5. run Windows installer/runtime test;
6. run ordinary ChatGPT/Codex canary;
7. only then continue OpenAI publication and billing.

No successor should reintroduce fleet/NOC/Paradox/degraded-state concepts into Commander V1.
