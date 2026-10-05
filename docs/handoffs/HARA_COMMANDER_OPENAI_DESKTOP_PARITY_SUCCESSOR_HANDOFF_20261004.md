# H.A.R.A. Commander — OpenAI / Desktop-Parity Successor Handoff

Date: 2026-10-04
Status: LIVE_PROVEN_0_3_26_SESSION_TRUSTED + SUCCESSOR_CANDIDATE_0_3_27_APPROVAL_SYNC
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

A live process.start canary immediately after the Agent update was denied with LOCAL_OPERATOR_SESSION_UPGRADE_REQUIRED. This is expected fail-closed behavior: the local operator session was opened under Agent 0.3.23, while 0.3.25 requires the authorizing session's recorded agent_version to match the currently executing Agent. Read-only authority remains available, but mutation/process approval cannot inherit authority across an Agent upgrade.

Required operator action before mutating/process live acceptance:

1. close the old local console session with Ctrl+C
2. run ~/.local/bin/hara-commander start again
3. confirm the banner reports Agent 0.3.25
4. retry the harmless process canary and approve it locally

Do not bypass this gate by rewriting the session file; the version-bound local-human approval boundary is intentional.

The fresh 0.3.25 local operator session subsequently closed the governed process-execution live gate through H.A.R.A. Commander itself.

Live accepted call:

- tool: hara.process.start
- command summary: printf HARA_G10_PTY_READY
- approval: APPROVAL_GRANTED
- execution: PASS
- receipt: e120cb137aa0eb3d57fca81755dc3e0a61b24e46c65925be0abefb26b3d2d787
- receipt mutation_class: PROCESS_EXECUTION_V1
- human_approval_required: true
- human_approval_state: APPROVED
- transport: OUTBOUND_RELAY
- execution authority: HARA_COMMANDER_AGENT
- payload_values_persisted: false

Therefore the 0.3.25 process start/output authority is LIVE_PROVEN on nucleo-a. The earlier approval timeouts were operator-response timeouts, not a broken approval channel; a concurrent accepted canary proved the same approval path end to end.

The prior 0.3.18 designation is superseded for the Linux nucleo-a live path by this 0.3.25 canary. The newly named hara.process.run tool still needs a ChatGPT MCP schema refresh for a named client-side acceptance call, but its Agent/Worker contract and full branch regression are already PASS.

## Successor 0.3.26 — configurable local authorization

The successor candidate 0.3.26 changes the approval UX from a hard-coded per-action prompt to an explicit device policy selected at onboarding.

Supported modes:

- SESSION_TRUSTED — recommended/default for new installs. Opening hara-commander start is the human authorization boundary for the governed toolset. Filesystem mutations and process execution run without additional y/N prompts while that exact local session remains active. Ctrl+C/stop revokes authority and managed processes are cleaned up.
- ASK_EVERY_ACTION — conservative mode. Each filesystem mutation/process action continues to require an explicit local terminal decision.

The policy does not expose unrestricted shell.run, does not bypass grants/tool allowlists, does not bypass preimages/rollback, and does not make the background daemon authoritative without a local session.

Product integration:

- portal onboarding exposes both modes before the installer command is copied
- portal defaults new installs to SESSION_TRUSTED
- Linux and Windows installer commands carry HARA_COMMANDER_APPROVAL_MODE
- enrollment stores approval_mode on the device
- migration 0017_device_approval_mode.sql adds the device field with legacy-safe default ASK_EVERY_ACTION
- Agent heartbeat keeps server state synchronized when the local mode changes
- hara.capabilities v2 projects device approval_mode, per-tool local_approval_required, and local_session_authorization_sufficient
- Linux CLI supports hara-commander approval-mode ask|session; changing an active device requires a session restart before the new policy becomes authoritative
- receipts distinguish per-action prompts from session authorization using local_authorization_mode and authorization_source
- legacy devices that do not yet have a persisted mode fail toward ASK_EVERY_ACTION

0.3.26 remains source/regression ready until migration + Worker/assets + Agent canary are promoted. The current live-proven Linux state remains 0.3.25.

## 0.3.26 configurable authorization — production/live closeout

The configurable-authorization cut was promoted to PROD and closed LIVE_PROVEN on nucleo-a.

Production rollout:
- migration ledger: 0015, 0016 and 0017 applied; no pending migrations after rollout
- pre-migration D1 export SHA-256: e165ff69ca819fa85d801c60e183cd219403132db558df4e159b6f22b625213d
- Worker version: f9826390-ab41-419e-8f24-efe51d314266
- deployment ID: 6563b9b2-2328-4f5f-bf91-976ef16402ee
- rollback Worker: 297a40ca-5391-43a2-9a61-2343455cd5e4
- runtime assets: CURRENT
- public fail-closed smoke: PASS
- PROD D1 readback/integrity: PASS

nucleo-a was upgraded to Agent 0.3.26 and configured explicitly with SESSION_TRUSTED. The old 0.3.25 session was revoked and a fresh 0.3.26 operator session opened with the banner:

- Approval: automatic for this session
- governed filesystem mutations: session-authorized
- governed process execution: session-authorized

Live hara.capabilities after device synchronization reports:
- approval_mode = SESSION_TRUSTED
- mutation_requires_local_approval = false
- process_execution_requires_local_approval = false
- local_session_authorizes_governed_mutations = true
- per mutable/process tool: local_approval_required=false and local_session_authorization_sufficient=true

No-prompt live mutation proof:
- hara.files.write PASS
- receipt: 2ba7c667592a98e29e1a162f332bf02bd704562f152098587fd8771113fe8fc7
- human_approval_required=false
- human_approval_state=APPROVED
- console sequence: RECEIVED -> APPROVAL_GRANTED -> EXECUTING -> PASS
- no APPROVAL_REQUIRED event and no y/N prompt

No-prompt live process proof:
- hara.process.start PASS
- receipt: ca94c3b45bb697b0d6625bbadef5fe1a759870ac0b9e57966bdf45c8a9eedae8
- mutation_class=PROCESS_EXECUTION_V1
- human_approval_required=false
- human_approval_state=APPROVED
- console sequence: RECEIVED -> APPROVAL_GRANTED -> EXECUTING -> PASS
- no APPROVAL_REQUIRED event and no y/N prompt

This is the intended end-user model: the human authorizes the governed capability set by opening the local session in SESSION_TRUSTED mode; individual operations remain constrained by grants, schemas, bounded payloads, receipts, preimages/rollback and session revocation, but do not interrupt the user for repeated confirmations.

## Successor 0.3.27 — effective approval-mode synchronization

A follow-up source candidate 0.3.27 hardens mode changes after installation:
- Agent heartbeat reports the effective approval mode of the currently active operator session, not a stale daemon-startup copy
- offline metadata reloads the latest persisted device config
- device.info reports the effective mode
- public result/receipt projection exposes local_authorization_mode and authorization_source
- switching ask/session can therefore converge in hara.capabilities after the required local-session restart without requiring an additional daemon restart
- release-coherent Linux/Windows metadata was bumped to 0.3.27

The complete branch regression suite passed for this patch. 0.3.27 is source/regression ready but was not promoted in this continuation; 0.3.26 remains the LIVE_PROVEN version.

## Operational Activity P0 — production/live rollout

The portal observability gap was closed on the canonical Commander branch in commit 078861d81f095c4e2771b181d55b33f54d790b24 (feat(commander): add operational activity dashboard).

Production rollout:
- Worker version: 841b50c9-6a03-4062-9302-4ae28ba1ec22
- deployment ID: dbf0c531-d0ae-4ff6-aca8-7c69e442b840
- rollback Worker: f9826390-ab41-419e-8f24-efe51d314266
- D1 readback/integrity: PASS
- pending migrations: none
- runtime assets: CURRENT
- public fail-closed smoke: PASS
- unauthenticated /api/portal/activity: 401 AUTH_REQUIRED
- live HTML contains the Activity KPI surface
- live app.js contains loadUsageActivity

Activity API:
- GET /api/portal/activity?limit=50
- schema: hara.commander-portal-activity.v1
- OWNER/ADMIN scope: TENANT
- other member scope: SUBJECT
- maximum 100 recent transactions
- no payload_json/result_json selected by the Activity query
- request_id not exposed
- privacy markers: payload_values_exposed=false, result_values_exposed=false, request_id_exposed=false

Operational summary includes:
- total/completed/failed/pending/executing/expired/cancelled
- success rate
- percent of completed calls under three seconds
- average queue, Agent execution and total latency
- distinct device count
- transport modes

Recent transaction rows expose metadata only:
- timestamp
- purpose-specific tool
- source category (CUSTOMER_MCP / QA / E2E / MANUAL / OTHER)
- computer
- transport mode
- Agent version
- state / sanitized error code
- queue/execution/total latency
- shortened trace/call identifier

Portal Usage now renders four operational cards plus the 50 most recent transactions and a functional refresh action instead of the prior homologation placeholder. CSV and richer filters are intentionally deferred to the next cut.

Permanent validation:
- COMMANDER_PORTAL_ACTIVITY_CONTRACT=PASS
- Owner/Admin tenant scope PASS
- Member subject scope PASS
- cross-tenant isolation PASS
- content-not-selected PASS
- privacy markers PASS
- full Commander regression under Node v24.15.0 PASS
- COMMANDER_OBSERVABILITY_P0_FULL_REGRESSION=PASS

Measured pre-rollout PROD baseline used to validate the design:
- 85 technical calls
- 79 completed / 6 failed
- 71 CUSTOMER_MCP calls, 66 completed / 5 failed
- completed average total latency ~2.27 s
- 74/79 completed below 3 s
- all 85 then-current stored payload/result fields were redacted/hash markers

The Activity rollout did not require a new table or migration; it reuses existing commander_device_calls operational metadata. Billing/quota units remain a separate commercial metric from technical transaction count.

Release note: the deployed static release channel now advertises Agent 0.3.27 from the canonical branch, while nucleo-a remains on the compatible and LIVE_PROVEN 0.3.26 session. Agent 0.3.27 live canary remains a separate staged rollout and is not required for the Activity API/portal path.

## Operational Activity P0.1 — bounded/indexed production queries

The Activity surface was hardened for production scale in commit 57caafab797a3c0c00a0609fb86a659cdfde1d58 (perf(commander): bound and index activity queries).

Changes:
- Activity windows: 24h / 7d / 30d
- default operational window: 7d
- backend adds c.created_at_utc >= ? to both summary and recent-transaction queries
- client cache is isolated per activity window
- migration 0018_activity_indexes.sql adds:
  - idx_device_calls_activity_tenant_created (tenant_id, created_at_utc DESC)
  - idx_device_calls_activity_subject_created (tenant_id, subject_id, created_at_utc DESC)

Production proof:
- migration 0018 applied successfully
- no pending migrations after apply
- remote EXPLAIN QUERY PLAN used idx_device_calls_activity_tenant_created for tenant + created_at timeline query
- Worker version: 6d36008c-f55f-4d7b-a305-8c1010ead3c5
- deployment ID: 6ec43c48-d0f4-46a6-942d-c2a551ec6ba2
- rollback Worker: 841b50c9-6a03-4062-9302-4ae28ba1ec22
- runtime assets: CURRENT
- public fail-closed smoke: PASS
- live HTML contains all 24h / 7d / 30d controls
- live app.js contains setActivityWindow
- COMMANDER_ACTIVITY_WINDOWS_LIVE=PASS
- COMMANDER_ACTIVITY_P01_FULL_REGRESSION=PASS

This cut intentionally does not introduce automatic deletion/retention of commander_device_calls. Technical metadata retention also participates in audit/idempotency and requires an explicit product retention policy before destructive cleanup is added.

## MCP operational Activity — hara.activity

Operational telemetry is now also projected to the authenticated MCP surface in commit 9e4657296d0f8aca049bfe4ee1c58f958d58a70e (feat(commander): expose operational activity to MCP).

New purpose-specific tool:
- hara.activity

MCP surface count:
- 37 public tools

Input:
- window: 24h / 7d / 30d
- limit: 1..100

Security/privacy:
- grant: COMMANDER_RECEIPT_READ
- MCP activity is always forced to SUBJECT scope, including Owner/Admin sessions
- portal Owner/Admin tenant-wide activity remains a separate UI capability
- payload_json/result_json are not selected by the Activity engine
- request IDs are not exposed
- customer_services_relay=false
- metadata-only operational response

The response reuses the same production Activity engine, returning success/failure counts, latency stages, device/transport metadata and recent call metadata without customer payload/result content.

Validation:
- customer MCP protocol PASS
- 37-tool list PASS
- hara.activity schema/call dispatch PASS
- MCP activity grant PASS
- forced subject scope PASS
- service-side/no-quota activity branch PASS
- COMMANDER_HARA_ACTIVITY_FULL_REGRESSION=PASS

Production Worker:
- version: 69e17b37-be68-4bfc-a397-900adafd8117
- deployment ID: ebb7f54d-d84c-4425-ab47-4e63ba91e8f4
- rollback Worker: 6d36008c-f55f-4d7b-a305-8c1010ead3c5
- assets: CURRENT
- fail-closed smoke: PASS
- COMMANDER_HARA_ACTIVITY_POST_DEPLOY=PASS

The current ChatGPT conversation may retain the pre-deploy MCP tool snapshot, so a tool refresh/fresh chat can be required before hara.activity is callable by name from this exact client session. This is a client schema-refresh issue, not a server deployment blocker.

## Activity P0.2 — privacy-safe diagnostics and export LIVE

Canonical commits:
- `5df8507ae174cc0cb66ba5e3c33915577400c655` — privacy-safe activity diagnostics
- `6f9e76ffb1daaf8d3664ebabf664c04983f393cd` — restore executable validator mode

Production:
- Worker version: `691093ce-404e-4b9e-9096-a7f8aa04ba9c`
- deployment ID: `b4641ea3-bc3e-4dde-a3f5-77a3337bd08c`
- rollback Worker: `69e17b37-be68-4bfc-a397-900adafd8117`
- runtime assets: CURRENT
- fail-closed: PASS
- Activity P0.2 live asset smoke: PASS
- pending migrations after rollout: none

New operational surfaces:
- top tools by count for the selected Activity window
- top sanitized failure codes by count
- CSV export of operational metadata only
- CSV columns: UTC timestamp, tool, computer, state, total/queue/execution latency, transport, Agent version, sanitized error, trace id
- command text, argument values, payload values, result values and request ids are not CSV columns

Privacy contract is now explicit:
- `command_text_exposed=false`
- `argument_values_exposed=false`
- `payload_values_exposed=false`
- `result_values_exposed=false`
- `request_id_exposed=false`
- `historical_command_text_persisted=false`
- `payload_hot_path_transient=true`
- `metadata_only=true`

The cloud transport still necessarily carries a bounded command/payload while a call is PENDING so the Agent can claim it. On Agent claim, `payload_json` is immediately replaced by `HARA_REDACTED_SHA256:<sha256>`. This is transport state, not a customer command-history feature.

Production persistence proof after P0.2 rollout:
- process calls: 287
- process payloads redacted: 287
- terminal process calls: 287
- terminal process payloads redacted: 287
- pending process calls: 0

A prior point-in-time query caught two raw PENDING process payloads while they were still in transit; both were subsequently claimed, after which the repeat query showed 287/287 redacted and zero pending. No payload values were read during this verification.

Local Agent receipt contract is also metadata-only:
- `payload_values_persisted=false`
- no `command_preview`, raw `command` or `payload_json` persisted by `write_receipt()`
- no raw stdout persisted; only `result_stdout_sha256`
- receipt files remain local, mode 0600
- release validator marker: `COMMANDER_LOCAL_RECEIPT_CONTENT_HISTORY=METADATA_ONLY`

Regression:
- `COMMANDER_ACTIVITY_P02_FULL_REGRESSION=PASS`
- Activity privacy markers PASS
- top tools diagnostics PASS
- top error diagnostics PASS
- metadata-only CSV gate PASS
- local receipt metadata-only gate PASS
- customer MCP / device contract / installers / E2E / prod static / privacy-NOC / routing / manifest all PASS

## Current known limitations

1. Windows purpose-specific parity is not yet proven. Windows version metadata was kept release-coherent, but the new Linux-first purpose-specific filesystem/search behavior must not be declared accepted on Windows without a separate canary.
2. No generic `shell.run` / arbitrary command execution is exposed.
3. Mutable filesystem write/edit/rollback and governed process execution are LIVE_PROVEN on nucleo-a under 0.3.25; the new 0.3.26 approval-mode policy still requires its own migration/deploy/canary gate.
4. The newly named hara.process.run surface is source/regression ready but still depends on client MCP schema refresh for named-tool acceptance.
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
