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

Desktop Commander inventory does not include a Windows connector, but the canary VM was recovered directly from libvirt on nucleo-a:

- libvirt domain: `commander-win11`;
- state: running;
- guest IP observed: `192.168.122.177`;
- QEMU Guest Agent: available;
- `guest-exec`: available;
- QGA execution identity: Windows SYSTEM;
- guest -> Commander DEV health: PASS.

Existing PROD isolation was preserved:
- Scheduled Task `HARA Commander Agent`: present;
- SYSTEM-context PROD config: absent.

Real Windows 0.3.32 proof:
- published Agent SHA matched the release manifest;
- `WINDOWS_SELFTEST_EXIT=0`;
- operator-session gate PASS;
- console sanitization PASS;
- starter read PASS;
- five-tool bridge PASS;
- arbitrary function DENIED;
- Agent self-test PASS.

The previous 0.3.31 candidate had a real PowerShell definition-order bug: `Get-ApprovalMode` was referenced by receipt code before its declaration during `--self-test`. That defect was fixed in 0.3.32 and is already canonical.

## Current P0 state

`WINDOWS_CURRENT_SOURCE_REGRESSION=PASS`

`WINDOWS_CURRENT_REAL_VM_SELFTEST=PASS`

`WINDOWS_CURRENT_DATA_PLANE_CANARY=PENDING_ALLOWED_ENROLLMENT_CHANNEL`

The remaining gate is isolated DEV enrollment and remote Simple MCP data-plane proof. An attempted fully automated guest enrollment was blocked by the administrative connector security policy around credential handling; no bypass was attempted and the temporary DEV fixture was cleaned completely.

## Required final live canary

1. use an allowed administrative/human channel to create or approve isolated DEV enrollment on `commander-win11`;
2. preserve the existing PROD task/config;
3. run current Agent 0.3.32 from the isolated canary root;
4. through Simple MCP prove:
   - read file;
   - write file;
   - filesystem metadata/list/search;
   - one-shot process command;
   - receipt/audit metadata;
5. verify no secret/token output;
6. verify fail-closed behavior for unsupported approval/tool paths;
7. clean the DEV fixture and record rollback state.

Only then mark Windows public-beta parity PASS.
