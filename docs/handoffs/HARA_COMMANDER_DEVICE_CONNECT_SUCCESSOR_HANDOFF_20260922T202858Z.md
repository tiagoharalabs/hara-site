# HARA Commander — device-connect successor handoff — 2026-09-22 20:28:58Z

## Canonical mission

HARA Commander V1 is a simple customer connectivity product:

`Account -> Device -> Commander Agent -> outbound HARA relay -> ChatGPT/Codex -> governed five-tool bridge`.

It is not a fleet NOC, Paradox dashboard, degraded-state console, generic shell, SSH browser or per-customer Cloudflare Tunnel product.

## Current DEV

- portal: `https://hara-commander-dev-v2.tiago-sartori.workers.dev/`
- HARA Identity: `https://auth.haralabs.com.br/`
- public MCP: `https://mcp.haralabs.com.br/mcp`
- Worker version: `e6303c51-135c-4f83-bd56-c3a6fdcb772f`
- hara-site branch: `issue29-commander-dev-v3-auth`
- latest mission commit before this handoff: `c194a721492ced23d462eb6e584e77e74844f0bd`
- hara-platform main: `77904a2ac5c895e3634d53458b0021fe25d24c79`

## Proven product pieces

PASS:
- HARA Identity login;
- tenant/plan/entitlement/quota;
- one-time short-lived device pairing;
- Linux installer;
- Windows installer;
- Linux user-systemd persistence;
- Windows Scheduled Task persistence;
- Windows DPAPI token protection and ACL hardening;
- device credential;
- heartbeat/presence;
- device list;
- revocation;
- public installer delivery;
- outbound relay call state;
- atomic `PENDING -> EXECUTING` claim;
- result roundtrip;
- enqueue idempotency;
- arbitrary/unknown tool denied fail-closed;
- customer-facing `Degradado` language removed.

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

## Important maturity boundary

Do not overstate the transport.

The installed Linux and Windows Agents have a real outbound call channel proven with `hara.health`, but the product is not yet a complete five-tool bridge.

Still pending:
1. portable local governed tool bridge;
2. exact five-tool local contract:
   - `hara.health`
   - `hara.functions.list`
   - `hara.functions.describe`
   - `hara.functions.invoke`
   - `hara.receipts.get`
3. bind public MCP identity/tenant to a selected online device;
4. route those calls through the relay to the selected device;
5. execute against the local governed HARA surface;
6. return sanitized result/receipt;
7. real ChatGPT/Codex read-only canary.

Arbitrary shell/filesystem/SSH must remain absent.

## Visual state

Dark mode is approved as the current reference.

Light mode needs refinement but not redesign.

Canonical light-theme direction:
`docs/design/HARA_COMMANDER_CLARUS_V1_20260922.md`

Clarus direction:
- keep dark navy sidebar;
- replace pale-blue workspace wash with neutral cold off-white;
- white cards with stronger structural borders;
- navy text hierarchy;
- restrained shadow;
- gold only for HARA emphasis / primary CTA;
- sky blue only for links/focus/secondary state;
- green only for real success/connected state.

Do not reintroduce monitoring/telemetry concepts while refining the light theme.

## Immediate continuation order

1. preserve the current dark-mode baseline;
2. implement Clarus without changing layout semantics;
3. runtime-test Windows installer on a real Windows host;
4. finish portable five-tool local bridge;
5. bind selected online device to public MCP session;
6. run real ChatGPT/Codex read-only canary;
7. only after this, continue OpenAI publication review flow;
8. billing remains deferred until the product bridge is real.

## Operator note

Tiago intends to log out and log in again for a final ordinary portal session check.

That UI/session check is useful but is not the main engineering blocker. The main blocker is the five-tool device bridge.
