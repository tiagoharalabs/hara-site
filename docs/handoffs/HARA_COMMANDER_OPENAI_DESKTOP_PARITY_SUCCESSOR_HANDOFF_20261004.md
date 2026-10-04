# H.A.R.A. Commander — OpenAI / Desktop-Parity Successor Handoff

Date: 2026-10-04
Status: LIVE_PROVEN_0_3_25_READ_ONLY_CONTEXT + PROCESS_RUN_SCHEMA_REFRESH_PENDING
Scope: ChatGPT/OpenAI customer MCP → H.A.R.A. Identity → Commander edge → outbound Agent → governed Linux execution

## Executive state

This front proved the customer-facing path without using the laboratory-local MCP as the execution plane:

`ChatGPT/OpenAI -> OAuth H.A.R.A. Identity -> https://commander.haralabs.com.br/api/mcp -> H.A.R.A. Commander Worker -> outbound Agent -> target computer`

The product path is distinct from the internal/local H.A.R.A. MCP. Desktop Commander was used only as an administrative bootstrap/development channel while evolving the product. Final read-only proofs were executed through H.A.R.A. Commander itself.

Current production Worker version after this front:

- `054c00d0-cba1-47e5-b782-981f062362ed`

Immediately prior live versions from this continuation:

- `a9ea8d76-4da6-4c3d-9b33-f40e04d3f2c7` — bounded file search + persistent recent-call audit
- `f16d60f2-06fb-4d63-ab3f-c0f46288538f` — preserve purpose-specific tool identity + discovery/ping/file-info
- `cd2e7d5d-4f28-4aaf-b5e1-c5d3ae8ff442` — purpose-specific read-only computer tools
- `6029c2cf-3180-4491-b0b0-a4c454f81273` — explicit multi-device routing / remove selected-device authority

Pre-front rollback reference preserved in the working record:

- `77c5a8ff-b53a-4174-9650-bc51fd29cf2f`

## Agent release

Linux canary advanced from 0.3.14 through 0.3.15/0.3.16/0.3.17 to:

- Stable manifest version: `0.3.18`
- Live Linux proof host: `nucleo-a`
- Transport: `OUTBOUND_RELAY`
- Local operator session gate: required
- Arbitrary shell: denied

The daemon may remain enabled/active, but it is execution-inert without a local operator session.

Universal Linux user commands:

```bash
hara-commander start
hara-commander status
hara-commander stop
```

`Ctrl+C` in the session terminal revokes access immediately.

Important: do not advertise `hara commander start` as the universal product command. On H.A.R.A. lab nodes, `/usr/local/bin/hara` is the canonical administration CLI and does not yet delegate `commander:*`. A later integration may add that convenience without changing the public product CLI.

## Local operator terminal UX

When `hara-commander start` is open, the user can observe sanitized events in real time:

- `AGENT_ONLINE`
- `RECEIVED`
- `EXECUTING`
- `PASS` / `DENIED`
- public `tool_id`
- governed function identity
- state
- shortened request/receipt identifiers

Tokens, secrets, raw sensitive arguments and secret material are not printed.

## MCP surface at closeout

The public MCP now exposes purpose-specific tools rather than forcing the model to think primarily in terms of generic invoke.

1. `hara.devices.list`
2. `hara.health`
3. `hara.ping`
4. `hara.device.info`
5. `hara.system.uptime`
6. `hara.processes.list`
7. `hara.files.info`
8. `hara.files.search`
9. `hara.files.list`
10. `hara.files.read`
11. `hara.files.read_many`
12. `hara.functions.list`
13. `hara.functions.describe`
14. `hara.functions.invoke`
15. `hara.receipts.get`
16. `hara.calls.recent`

`hara.functions.invoke` remains as governed compatibility/escape surface; purpose-specific tools are the preferred product interface.

## Tool identity preservation

A key architecture correction landed in this front: purpose-specific tools preserve their public identity all the way through the Agent and receipt.

Example:

`ChatGPT -> hara.processes.list -> Worker -> Agent -> receipt`

Live receipt proof:

- receipt SHA-256: `38ef59b1e851105ded18b3587a1b6182df7da099685c0c59da4b06734b701e0a`
- `tool_id = hara.processes.list`
- `function_id_if_any = process.list`
- state `PASS`
- mutation class `READ_ONLY_OR_NONE_V1`

This replaces the earlier user-visible mismatch where a purpose-specific MCP call was translated to `hara.functions.invoke` before reaching the device.

## Multi-device routing

The public MCP no longer depends on the legacy global selected-device row.

Rules:

- explicit `computer` name: exact case-insensitive same-tenant resolution
- duplicate name: fail closed with `COMPUTER_NAME_AMBIGUOUS`
- no explicit target + exactly one online computer: auto-resolve
- no explicit target + multiple online computers: `COMPUTER_REQUIRED`
- cross-tenant target: denied
- revoked/inactive target: denied
- selected-device DB/endpoint may remain for compatibility/rollback but is not MCP authority

Portal UX was changed to fleet state semantics (Online / Offline / Revoked) instead of `Usar` / `Em uso` routing authority.

## Read-only capability details

### Processes

`hara.processes.list`

- bounded result count
- process name, PID, state, RSS
- command lines not exposed
- environment not exposed

Live proof on `nucleo-a` returned real processes including `qemu-system-x86`, `llama-server`, Firefox/Codium processes.

### Files

`hara.files.info`

- metadata only
- type, size, mode, modified time

`hara.files.list`

- bounded entry count
- recursive depth bounded to 1..5
- no file-content read

`hara.files.read`

- bounded line read
- text only
- binary denied
- large file denied
- output capped

`hara.files.read_many`

- up to 10 text files
- common bounded offset/length
- individual file failure does not abort the entire batch

Live read-many proof:

- `/etc/os-release`
- `/etc/hostname`
- receipt: `bee4d9d70303855c2a227fa2c1bab0aab3bef6754a2efdb58edab8cf81eb90e6`

### Search

`hara.files.search`

- `search_type = files | content`
- no shell subprocess
- bounded to <=100 results
- scan cap 5000 files
- approximately 3 second device-side deadline
- optional hidden-file inclusion
- optional case-insensitive behavior
- optional filename glob
- binary/oversize text content skipped

Live proof via governed engine on `nucleo-a` searched `/etc` for `os-release`:

- 3793 files scanned
- 5 matches
- `truncated=false`
- receipt: `4a30fb4b51bebca5a2304eca47c808b9960460e59f6be216d6a11f646f0c1cda`

## Other live E2E proofs

Initial baseline E2E:

- `hara.health` PASS
- `hara.functions.list` PASS
- `hara.functions.describe(device.info)` PASS
- `hara.functions.invoke(device.info)` PASS
- `hara.receipts.get` PASS
- initial device.info receipt: `3bae76bc3bd9446f57a6f1559537a60400206462317493c8e73aa1c8a8114641`

Read-only expansion proofs:

- `process.list` PASS
- `system.uptime` PASS
- `filesystem.list` PASS
- `filesystem.read` PASS
- arbitrary `shell.run` -> `POLICY_DENIED`

## Discovery and audit surfaces

`hara.devices.list`

- tenant-scoped fleet list
- returns computer name, device ID, platform, architecture, Agent version, Online/Offline/Revoked, last seen

`hara.ping`

- end-to-end Agent connectivity check

`hara.calls.recent`

- server-side persistent call metadata
- tenant + subject scoped
- optional computer/tool filter
- no payload values
- no raw result bodies
- materially stronger audit continuity than session-memory-only history

## Security/governance properties retained

- OAuth H.A.R.A. Identity
- tenant isolation
- explicit computer routing
- entitlement/grant checks
- quota reserve/commit/release for governed function work
- idempotency binding includes target device + payload
- local operator session required
- background daemon execution authority remains inert
- arbitrary function/shell denied
- bounded file/search outputs
- receipt stdout binding for governed execution
- secrets/tokens not printed in terminal
- raw customer content not promoted into NOC/learning telemetry

## Test gates run after the final 0.3.18 source cut

All closed PASS / exit code 0:

- `node scripts/test_customer_mcp_edge.mjs`
- `node scripts/validate_device_tool_contract.mjs`
- `python3 scripts/validate_device_installers.py`
- `python3 scripts/validate_event_v2_productization.py`
- `python3 scripts/validate_e2e_harness.py`
- `python3 scripts/validate_prod_static.py`
- `python3 scripts/validate_customer_privacy_noc_contract.py`
- `node scripts/test_customer_mcp_device_routing.mjs`
- `python3 scripts/build_release_manifest.py --check`

Notable negative gates:

- arbitrary shell exposed: FALSE / DENIED
- cross-tenant target: DENIED
- background daemon execution authority: INERT
- console secret exposure: FALSE

## OpenAI custom MCP continuation notes

The customer MCP endpoint is:

`https://commander.haralabs.com.br/api/mcp`

The test used a normal founder/customer account for the real `nucleo-a` tenant. A separate reviewer account remains intentionally isolated for later reviewer acceptance testing.

ChatGPT caches MCP tool schemas per connection/conversation. After adding tools, use the plugin's `Atualizar ferramentas` action; a fresh chat may also be required for a newly added tool to become callable by name.

Do not store or document OAuth tokens, link IDs, device tokens, or other secret material.


## Concurrent successor candidate captured during handoff

While this handoff was being assembled, the shared Commander sandbox advanced from the live-proven 0.3.18 cut to an Agent 0.3.23 successor candidate. That candidate is preserved on this handoff branch so successor fronts do not lose the newer work, but it MUST NOT be confused with the live proof recorded above.

Candidate 0.3.23 adds/contains additional product surfaces beyond the 0.3.18 live gate, including:

- capability and usage surfaces (`hara.capabilities`, `hara.usage`)
- file hash/diff
- reversible/mutating filesystem operations: create-directory, write, edit, move, copy, delete, preimage list and rollback
- governed process lifecycle: sessions, start, output, interact and kill
- founder grants introduced by migrations `0015_founder_mutation_grant.sql` and `0016_founder_process_execution_grant.sql`
- local mutation approval and local process execution approval gates
- reversible file mutation/preimage handling
- mutation/process metering and Agent-version guards

The 0.3.23 candidate must receive a fresh live canary before production promotion. The authoritative live proof from this front remains 0.3.18 on `nucleo-a`.


### Candidate 0.3.23 validation snapshot

The reconciled 0.3.23 predecessor candidate advertises **33 MCP tools** and passed the full branch-local regression suite with exit code 0 on 2026-10-04. This is source/test readiness only; it is not a substitute for a live canary gate.

## Successor continuation — candidate 0.3.24 GPT-native context surface

The successor branch advanced one additional source/test checkpoint to **Agent 0.3.24** while preserving 0.3.18 as the last live-proven state.

0.3.24 adds two purpose-specific read-only tools and raises the public MCP surface from 33 to **35 tools**:

- hara.system.resources
- hara.workspace.inspect

hara.system.resources returns bounded local CPU, load average, memory, swap and root-filesystem capacity without invoking a shell or external process.

hara.workspace.inspect reduces multi-call project discovery by returning bounded workspace metadata:

- resolved requested path and detected workspace/project root
- project markers/manifests such as package.json, pyproject.toml, Cargo.toml, go.mod, CMakeLists.txt and Makefile
- bounded top-level entry metadata
- Git presence, branch and HEAD OID by reading Git metadata directly
- support for normal clones and Git worktrees through .git indirection plus commondir
- explicit dirty_state = UNKNOWN_NOT_EVALUATED; it does not invent a working-tree cleanliness claim

Security properties retained by design:

- no shell.run
- no subprocess dependency in the Linux Agent
- no external Git command invocation
- workspace scan bounded to 2000 discovered entries and at most 200 returned entries
- public purpose-tool identity remains receipt-bound
- Agent capability exposure is version-gated at 0.3.24

The real branch worktree itself was used as an additional smoke proof for worktree Git metadata:

- branch resolved: local/commander-openai-desktop-parity-20261004
- HEAD OID resolved through worktree commondir
- external_command_invoked = false

The full branch regression suite passed again after the 0.3.24 cut, including:

- test_customer_mcp_edge
- validate_device_tool_contract
- validate_device_installers
- validate_event_v2_productization
- validate_e2e_harness
- validate_prod_static
- validate_customer_privacy_noc_contract
- test_customer_mcp_device_routing
- build_release_manifest --check

The server-side capability projection was also enriched without changing the Agent protocol version. hara.capabilities now keeps the existing tools array for compatibility and adds per-tool metadata with:

- risk_class
- local_approval_required
- required_grant
- preferred_interface

This lets GPT plan around local approval and risk before attempting a call, while still steering it away from the generic hara.functions.invoke compatibility surface when a purpose-specific tool exists.

## Desktop Commander retirement P0 — candidate 0.3.25

The successor advanced again to **Agent 0.3.25** with a retirement-focused usability cut.

New purpose-specific tool: hara.process.run.

hara.process.run provides one-shot governed command execution for short tasks that previously required a multi-call start -> output lifecycle. It:

- uses the existing COMMANDER_PROCESS_EXECUTION grant
- requires local human approval before execution
- caps command payload, timeout and returned lines
- supports an optional governed working directory
- force-terminates the child if the one-shot deadline is exceeded
- does not retain a process session after completion or timeout
- keeps command payload hot-path redaction and receipt binding
- remains PROCESS_EXECUTION_V1; this is not unrestricted background shell authority

The public MCP candidate surface is now **36 tools**.

Capability negotiation was also corrected. The 0.3.23+ Agent already contains hara.files.hash, hara.files.diff, hara.files.copy and hara.files.delete, but the previous hara.capabilities projection omitted them. The corrected projection now:

- advertises hash/diff only from the conservatively proven 0.3.23 gate
- advertises copy/delete from 0.3.23 only when the mutation grant exists
- refuses to claim those tools for earlier Agent versions
- advertises hara.process.run only from 0.3.25 with the process-execution grant

This closes an important retirement gap: the model can trust hara.capabilities as the source of truth instead of discovering supported operations by failed calls.

The full branch regression suite passed with exit code 0 after the 0.3.25 cut, including the Agent self-test, customer MCP surface, device contract, installer/release integrity, Event V2 productization, E2E harness, prod static, privacy/NOC and multi-device routing.

This remains **SUCCESSOR_CANDIDATE** only. Promotion still requires a fresh live canary. The authoritative live-proven version remains **0.3.18**.

## 0.3.25 production rollout and live canary

Production Worker/assets were promoted from the 0.3.25 handoff branch after dry-run and regression gates.

Deployment receipt:

- Worker version: 297a40ca-5391-43a2-9a61-2343455cd5e4
- deployment ID: 4ff2f77b-4833-4c93-aa8c-f9cbe09ecce0
- rollback Worker: a4317351-8962-4500-b714-72cb173b4361
- public runtime assets: CURRENT
- public fail-closed smoke: PASS
- PROD D1 readback: PASS
- Agent public release: 0.3.25

The nucleo-a canary was updated using the published Linux updater. Update gates closed:

- HARA_COMMANDER_AGENT_INTEGRITY=PASS
- HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS
- HARA_COMMANDER_AGENT_UPDATE=PASS
- rollback-ready=TRUE
- local operator session remained ACTIVE
- secret material exposed=FALSE

Live proof through the customer H.A.R.A. Commander MCP, not Desktop Commander:

- hara.health -> PASS, Agent 0.3.25, 13/13 functions
- hara.capabilities -> PASS and advertises process.run, system.resources, workspace.inspect plus the corrected hash/diff/copy/delete surface
- capability tool_details -> risk class, local approval requirement, required grant and preferred-interface metadata live
- system.resources -> PASS through governed function path, receipt a20ec92faa4361218353c91abe7191e97a02d8599fd563ac2ad3129e6e0a14c4
- workspace.inspect -> PASS through governed function path, receipt 5c7c90b509749a1047e8b46b1c30c2774458c5394b1a21065ca766c8565c55b2
- nucleo-a workspace Git metadata resolved without shell/external command

The current ChatGPT conversation loaded the MCP tool schema before the 0.3.25 deployment, so the newly named hara.process.run tool is not yet present in this conversation's callable-tool snapshot even though the live hara.capabilities response advertises it. A ChatGPT tool refresh or fresh conversation is required for a named live call of process.run. Existing process.start/output remains live and usable meanwhile.

The prior 0.3.18 designation is superseded for the read-only/context live path by this 0.3.25 canary. Process-run named-tool acceptance remains pending only on client schema refresh, not Agent/Worker source readiness.

## Current known limitations

1. Windows purpose-specific parity is not yet proven. Windows version metadata was kept release-coherent, but the new Linux-first purpose-specific filesystem/search behavior must not be declared accepted on Windows without a separate canary.
2. No generic `shell.run` / arbitrary command execution is exposed.
3. Mutable filesystem tools exist in successor candidate 0.3.23 but were not part of the 0.3.18 live proof; live promotion requires a separate gate.
4. Process lifecycle tools exist in successor candidate 0.3.23 but were not part of the 0.3.18 live proof; live promotion requires a separate gate.
5. `hara commander start|status|stop` is not yet integrated into the canonical H.A.R.A. admin CLI; public product command remains `hara-commander ...`.
6. Search is intentionally bounded and synchronous; there is no progressive search session API yet.
7. Legacy selected-device route/table still exists for compatibility but is not MCP routing authority.

## Recommended successor order

### P0 — mutation authority model

Define explicit grants/risk classes before exposing mutation:

- `COMMANDER_FILE_WRITE`
- `COMMANDER_PROCESS_EXECUTE`
- optional stronger `COMMANDER_PROCESS_TERMINATE`

Specify per-tool approval semantics, mutation receipt schema, quota semantics and local-terminal visibility before implementation.

### P1 — filesystem mutations

Add purpose-specific tools in this order:

1. `hara.files.mkdir`
2. `hara.files.write` with bounded UTF-8 content and rewrite/append modes
3. `hara.files.move`
4. `hara.files.edit` using exact old/new block semantics

Each must preserve public tool identity in Agent + receipt and declare mutation performed.

### P2 — governed process lifecycle

Do not jump directly to a generic shell tool. Prefer a process family with explicit schemas:

1. `hara.processes.start`
2. `hara.processes.output`
3. `hara.processes.input`
4. `hara.processes.kill`
5. `hara.processes.sessions`

Define command admission/policy explicitly. Interactive process state should be per-device, bounded and revocable when the operator session closes.

### P3 — search UX parity

If needed, evolve bounded synchronous search into:

- `hara.search.start`
- `hara.search.more`
- `hara.search.stop`
- `hara.search.list`

Keep current bounded synchronous `hara.files.search` as simple fast path.

### P4 — canonical H.A.R.A. CLI convenience

On lab-managed machines only, add delegation from canonical `/usr/local/bin/hara`:

- `hara commander start`
- `hara commander status`
- `hara commander stop`

It must delegate to the installed product binary and must not weaken anti-drift authority rules.

### P5 — Windows parity gate

Repeat Agent acceptance on a Windows canary after Linux mutation/process contracts stabilize.

## Continuation invariant

Prefer Desktop Commander-style ergonomics (clear purpose-specific tools, obvious schemas, device targeting) while retaining the stronger H.A.R.A. properties:

- identity + tenant isolation
- local human session gate
- fail-closed policy
- receipt per action
- quota/idempotency
- minimized telemetry
- explicit mutation authority

Do not regain ergonomics by collapsing back to unrestricted shell as the primary product surface.
