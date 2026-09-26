# Commander Windows Event V2 RC contract

Owner: #163

Windows remains on the proven public Agent 0.3.7 / POLL_V1 path until an
independent Event V2 transport, five-tool parity, rollback proof and live Windows
canary are all complete.

## Current law

```text
WINDOWS_STABLE_PUBLIC_AGENT=0.3.7
WINDOWS_PUBLIC_TRANSPORT=POLL_V1
WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1
WINDOWS_EVENT_V2=SOURCE_CONTRACT_ONLY
WINDOWS_EVENT_V2_LIVE_PARITY=FALSE
WINDOWS_PUBLIC_CUTOVER=DENY
CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=FALSE
```

The source-only RC selector is:

`apps/commander/candidate/windows_agent_rc.ps1`

It fails closed if `EVENT_V2` is selected before a Windows Event V2 transport
implementation exists.

## Transport design

The target implementation uses the .NET
`System.Net.WebSockets.ClientWebSocket` API available to PowerShell/.NET rather
than adding a third-party WebSocket runtime.

Target connection:

```text
Commander HTTPS origin
  -> wss://.../api/device/channel
  -> Authorization: Bearer <device credential>
  -> DeviceChannel Durable Object
```

Requirements:

- WSS/TLS only;
- device bearer only on the upgrade request;
- no redirect following to a different origin;
- no credential logging;
- no customer command/result/file telemetry;
- WebSocket protocol keepalive, not HTTP heartbeat;
- no fixed 2-second polling in steady state;
- CALL_AVAILABLE is a wake hint only;
- D1 remains durable call truth;
- reconnect performs bounded durable reconciliation;
- full-jitter reconnect remains bounded;
- exactly five governed tools;
- arbitrary shell/filesystem remains denied.

Microsoft's documented ClientWebSocket surface provides asynchronous connect,
send, receive and close operations plus request-header configuration and
keepalive options. Exact keepalive behavior must be validated against the
PowerShell/.NET version used by the Windows package before live promotion.

## Identity and token handling

The Windows public baseline currently stores the device credential using the
Windows-protected SecureString/DPAPI representation in `device.json`.

The RC must reuse that enrolled identity.

```text
WINDOWS_RC_REPAIRING=FALSE
WINDOWS_RC_NEW_DEVICE_ID=FALSE
WINDOWS_RC_TOKEN_EXPORT=FALSE
WINDOWS_RC_TOKEN_LOGGING=FALSE
```

No second device enrollment is allowed merely to change transport.

## Promotion gates

Before `EVENT_V2` may become runnable in the Windows RC:

1. Event V2 Windows transport source exists.
2. Bearer handshake is fail-closed and secret-safe.
3. Connect/disconnect status is locally recorded without customer content.
4. Idle HTTP polling is absent.
5. HTTP 30-second heartbeat is absent on Event V2.
6. Durable reconnect reconciliation is bounded.
7. Five-tool / receipt parity is proven.
8. Update/install rollback preserves the existing encrypted device identity.
9. Scheduled Task transition never permits two agents using the same credential.
10. Live Windows canary passes.
11. Public installer/manifest still remain V1 until an explicit later release gate.

## Current non-claim

```text
WINDOWS_EVENT_V2_TRANSPORT_SOURCE=READY_UNPROVEN
WINDOWS_EVENT_V2_AGENT_ADAPTER_IMPLEMENTED=FALSE
WINDOWS_EVENT_V2_RUNTIME_PROVEN=FALSE
WINDOWS_EVENT_V2_FIVE_TOOL_PARITY=FALSE
CROSS_PLATFORM_EVENT_V2_PARITY=FALSE
```

This document intentionally prevents the Linux proof from being generalized to
Windows before Windows-specific evidence exists.


## Transport source checkpoint

Source-only transport now exists at:

`apps/commander/experimental/event_v2_windows_transport.ps1`

It uses the .NET `ClientWebSocket` surface and establishes the following
fail-closed source contract:

```text
WINDOWS_EVENT_V2_WSS_ONLY=TRUE
WINDOWS_EVENT_V2_BEARER_UPGRADE_ONLY=TRUE
WINDOWS_EVENT_V2_KEEPALIVE_TARGET=60s
WINDOWS_EVENT_V2_MAX_EVENT_BYTES=4096
WINDOWS_EVENT_V2_FRAGMENTED_WAKE=DENY
WINDOWS_EVENT_V2_NON_TEXT_WAKE=DENY
WINDOWS_EVENT_V2_CONTENT_BEARING_WAKE=DENY
WINDOWS_EVENT_V2_THIRD_PARTY_WEBSOCKET_RUNTIME=FALSE
```

This does **not** make Windows Event V2 runnable yet. The missing layer is the
Windows Event V2 agent adapter that binds wake/reconciliation to the existing
five governed tools, receipts, runtime status and Scheduled Task rollback.
