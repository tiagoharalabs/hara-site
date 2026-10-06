# H.A.R.A. Commander — P0 Windows 0.3.32 DEV canary

Date: 2026-10-05
Branch: `local/commander-windows-starter-20261005`
Environment: DEV only

## Stage A — reconcile Windows starter

The Windows starter branch originally contained two Windows-specific commits and was behind the canonical sellability branch.

The branch was reconciled with the current canonical branch without losing the Windows work.

A temporary rebase produced tree:
`78f2dea15700f75fb17d4f264cc9daf8cc37e3e5`

The local Git gateway correctly denied non-fast-forward force-push. The branch was therefore restored to its published history and canonical was merged normally.

The resulting merge tree was exactly:
`78f2dea15700f75fb17d4f264cc9daf8cc37e3e5`

Published reconciled Windows branch before the 0.3.32 fix:
`f0470d224c9b9b809b6e44ded76f188587a221ab`

Regression:
- device installer PASS;
- device tool contract PASS;
- Event V2 productization PASS;
- privacy/NOC PASS;
- Simple MCP PASS;
- routing / cross-tenant target PASS;
- release manifest PASS.

## Stage B — real Windows VM

Canary VM:
- libvirt domain: `commander-win11`;
- state: running;
- guest IP: `192.168.122.177`;
- QEMU Guest Agent: available;
- `guest-exec`: available;
- QGA execution identity: Windows SYSTEM;
- DEV health from inside guest: PASS.

Existing PROD isolation baseline:
- Scheduled Task `HARA Commander Agent`: present;
- SYSTEM-context PROD config: absent;
- therefore an isolated canary can use a separate SYSTEM `LOCALAPPDATA` without touching the existing PROD user enrollment/task.

QGA PowerShell canary:
`HARA_WINDOWS_QGA_CANARY=PASS`

Guest -> DEV:
`HARA_WINDOWS_DEV_HEALTH=PASS`

## Stage C — 0.3.31 real self-test found a release bug

DEV served Windows Agent 0.3.31 with manifest SHA:
`c5df56bc202b29e1dc32c7b216575dd10a00af508b823ae089ac95c0fa66f1d3`

SHA validation on the real Windows VM passed.

However, the real Windows self-test returned exit code 1.

Sanitized error:
`Get-ApprovalMode : ... CommandNotFoundException`

Root cause:
- `Invoke-AgentSelfTest` executes before the script reaches the original `Get-ApprovalMode` function declaration;
- the self-test calls `New-Receipt`;
- `New-Receipt` calls `Get-ApprovalMode`;
- static/source tests did not catch this PowerShell definition-order problem.

This is classified as a real Windows release bug, not an environment failure.

## Stage D — 0.3.32 fix

Fix:
- move `Get-ApprovalMode` before starter mutation / receipt code;
- remove the later duplicate declaration;
- bump release coherently from 0.3.31 to 0.3.32;
- update Windows capability admission/projection gate from patch 31 to patch 32;
- rebuild release manifest and SHA256SUMS.

Source regression:
- `COMMANDER_WINDOWS_0_3_32_SOURCE_REGRESSION=PASS`
- `COMMANDER_DEVICE_TOOL_CONTRACT_WORKER_WINDOWS_STARTER_0_3_32=PASS`
- `COMMANDER_STABLE_AGENT_VERSION=0.3.32`
- installer integrity PASS;
- release manifest PASS;
- Simple MCP / privacy / routing inherited from reconciled branch.

DEV Worker carrying 0.3.32:
`67e7ece3-46e3-40b6-9cdf-5fb6f430e828`

Published Windows Agent 0.3.32 SHA:
`e01bd2d8d7b57f0eb1de9970cd44039c67ead872e1c3b6c8613c36e186824ca3`

## Stage E — real Windows 0.3.32 self-test

On `commander-win11`:

- `WINDOWS_AGENT_SHA256_MATCH=True`
- `WINDOWS_SELFTEST_EXIT=0`
- `COMMANDER_WINDOWS_OPERATOR_SESSION_GATE=PASS`
- `COMMANDER_WINDOWS_CONSOLE_SANITIZATION=PASS`
- `COMMANDER_WINDOWS_STARTER_READ=PASS`
- `COMMANDER_WINDOWS_FIVE_TOOL_BRIDGE=PASS`
- `COMMANDER_WINDOWS_ARBITRARY_FUNCTION=DENIED`
- `COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS`

The self-test also validates receipt creation/readback and result SHA binding for the governed function bridge.

## Data-plane canary status

A fully isolated DEV enrollment was prepared:
- pairing token generated inside the guest;
- only its SHA-256/base64url hash left the guest;
- dedicated DEV tenant/user/identity/entitlement/pairing fixture created;
- fixture used `STANDARD`.

The administrative connector blocked the step that would automate enrollment/device-token handling inside the guest due OpenAI security settings.

No bypass was attempted.

Cleanup was completed:
- temporary guest canary root removed;
- DEV canary tenant count: 0;
- DEV canary device count: 0;
- DEV canary pairing count: 0;
- temporary host state removed.

Therefore:

- Windows 0.3.32 source/regression: PASS;
- real Windows Agent integrity: PASS;
- real Windows self-test: PASS;
- isolated enrollment/data-plane `files.write / files.read / process.run / receipts.get`: PENDING administrative enrollment channel.

This remaining gate is not classified as a Windows Agent failure.
