# H.A.R.A. Commander — P0 Windows Current Canary

Date: 2026-10-05
Source branch during reconciliation: `local/commander-windows-starter-20261005`

## Source candidate

The Windows starter workstream was rebased cleanly on the current Commander canonical branch.

Candidate commits after rebase:
- `536d544` — Windows starter toolset;
- `2930ec8` — preserve Windows starter validator mode;
- `94d5176` — make Windows starter self-test live-safe.

Source candidate Agent version:
- `0.3.32`

Windows starter surface includes:
- device info / ping / process listing;
- filesystem info/search/list/read/read-many;
- create directory / write;
- governed one-shot process execution;
- fail-closed approval behavior where unsupported;
- encoded PowerShell process command handling;
- installer integrity, manifest/version binding and self-test.

## Regression after reconciliation

PASS:
- device installers;
- device tool contract;
- Event V2 productization;
- PROD static surface;
- privacy/NOC;
- Simple MCP profile;
- release manifest integrity.

Marker:
`COMMANDER_WINDOWS_STARTER_REBASED_REGRESSION=PASS`

The Worker contract recognizes:
`COMMANDER_DEVICE_TOOL_CONTRACT_WORKER_WINDOWS_STARTER_0_3_32=PASS`

## Current live Windows inventory

PROD D1 currently contains one non-revoked Windows enrollment:

- device: `HARA_WIN11`
- Agent: `0.3.14`
- state: `ACTIVE`
- approval mode: `ASK_EVERY_ACTION`
- last heartbeat: `2026-10-03T23:02:28.763Z`

Older Windows enrollments for the same name are REVOKED.

Desktop Commander inventory at this continuation contains only:
- nucleo-a;
- sentinela-d;
- sentinela-c;
- services.

No Windows host is currently online/reachable through the available administrative channel.

## Current P0 state

`WINDOWS_CURRENT_SOURCE_REGRESSION=PASS`

`WINDOWS_CURRENT_LIVE_CANARY=BLOCKED_HOST_UNAVAILABLE`

This is not a source failure. The remaining live gate requires an accessible Windows host.

## Required live canary

When a Windows host becomes reachable:

1. preserve existing enrollment or pair a fresh Windows device;
2. update/install the current canonical Windows Agent;
3. require integrity + self-test + startup attestation PASS;
4. verify current Agent version and capabilities;
5. through Simple MCP prove:
   - read file;
   - write file;
   - filesystem metadata/list/search;
   - one-shot process command;
   - receipt/audit metadata;
6. verify no secret/token output;
7. verify fail-closed behavior for unsupported approval/tool paths;
8. record rollback state.

Only then mark Windows public-beta parity PASS.
