# H.A.R.A. Commander — OpenAI / Desktop-Parity Reconciliation

Date: 2026-10-06  
State: CLOSED_PASS_RECONCILED  
Canonical branch: `local/commander-openai-desktop-parity-20261004`  
Preimage HEAD: `81e559772dddb3a159af2c6acbf6d300d8a3160d`  
GitHub preimage: exact match at reconciliation start

## Purpose

Reconcile the live ChatGPT/OpenAI-to-`nucleo-a` product proofs from the 0.3.15–0.3.18 canary sequence with the newer Commander lineage that has since advanced to Agent 0.3.40.

This record exists so successor fronts do not replay old work or accidentally overwrite later product hardening.

## Product path proven by the predecessor canary

The tested customer execution plane was:

`ChatGPT/OpenAI -> OAuth H.A.R.A. Identity -> commander.haralabs.com.br/api/mcp -> Commander Worker -> outbound H.A.R.A. Commander Agent -> nucleo-a`

The laboratory-local MCP was not the execution plane for those proofs.

Desktop Commander was used only as an administrative/bootstrap/development channel while evolving the product. Final product proofs were executed through H.A.R.A. Commander itself.

## Historical live proof absorbed from 0.3.15–0.3.18

The predecessor canary proved on `nucleo-a`:

- OAuth account/tenant routing through the normal Tiago customer identity
- explicit/same-tenant computer routing
- local operator terminal session gate
- background daemon inert without local authorization at that stage
- purpose-specific public tools
- tool identity preservation through Agent and receipt
- bounded process/file inspection
- bounded file search without generic shell
- bounded multi-file read
- receipt lookup
- cross-tenant denial
- arbitrary `shell.run` denial
- Online/Offline/Revoked fleet semantics instead of selected-device authority

Historical Worker sequence:

- `6029c2cf-3180-4491-b0b0-a4c454f81273` — explicit multi-device routing / selected-device authority removed from public MCP
- `cd2e7d5d-4f28-4aaf-b5e1-c5d3ae8ff442` — purpose-specific read-only tools
- `f16d60f2-06fb-4d63-ab3f-c0f46288538f` — public tool identity preserved through Agent/receipt
- `a9ea8d76-4da6-4c3d-9b33-f40e04d3f2c7` — bounded search + recent-call audit
- `054c00d0-cba1-47e5-b782-981f062362ed` — recursive listing + bounded read-many closeout

Key receipts:

- baseline `device.info`: `3bae76bc3bd9446f57a6f1559537a60400206462317493c8e73aa1c8a8114641`
- public `hara.processes.list`: `38ef59b1e851105ded18b3587a1b6182df7da099685c0c59da4b06734b701e0a`
- governed file search: `4a30fb4b51bebca5a2304eca47c808b9960460e59f6be216d6a11f646f0c1cda`
- bounded read-many: `bee4d9d70303855c2a227fa2c1bab0aab3bef6754a2efdb58edab8cf81eb90e6`

These proofs remain historical evidence. Do not redeploy the old 0.3.18 source over the current lineage.

## Current superseding source state

The same canonical branch has since advanced to Agent 0.3.40 and now contains a materially broader governed product:

- full H.A.R.A. customer MCP surface: 37 tools
- vendor-neutral Simple MCP surface: 24 tools
- capabilities / usage / activity
- system resources and workspace inspection
- file info/hash/diff/search/list/read/read-many
- reversible file mutation with preimages and rollback
- governed process run/start/output/interact/kill/sessions
- purpose-specific receipts
- local activity store / budget / signed lease hardening
- release trust and dual-origin Linux bootstrap validation
- SLO/support plane maturity
- MCP multi-version conformance
- guarded Identity DCR compatibility source

The old handoff sections that recommend implementing mutation/process P0/P1/P2 are historical and superseded by the current source.

## Current production truth

Agent/Worker 0.3.40 failure-semantics promotion is CLOSED_PASS in PROD.

Production Worker:

- `c8cfc1d1-592c-4d71-8788-d237e07828c6`

Rollback:

- `a62fde0b-9c7d-4500-a97e-f31d9bdf9eac`

Runtime assets: CURRENT  
PROD fail-closed: PASS  
Full live-readonly preprod validation: PASS

Current Linux rollout note:

- Sentinela D Agent 0.3.40: CLOSED_PASS
- Nucleo A Agent 0.3.40: PENDING_SAFE_CHILD_DRAIN in the current SLO rollout record; do not restart its Agent service while unrelated child work remains in the cgroup

## MCP interoperability truth

Simple MCP V1.1 is source/preprod CLOSED_PASS across:

- MCP 2025-06-18
- MCP 2025-11-25
- MCP 2026-07-28

ChatGPT/OpenAI existing configured integration path: READY.

Generic zero-config OAuth onboarding is still gated by Identity registration metadata/compatibility policy. The guarded DCR gateway is source/preprod CLOSED_PASS but its PROD public guard remains pending explicit deployment/promotion.

## Permanent product invariant

Desktop Commander remains a benchmark for ergonomics, not an authority boundary.

Preserve:

- purpose-specific tools
- clear computer targeting
- inspect-before-mutate ergonomics
- identity + tenant isolation
- grants and bounded schemas
- local authorization policy
- receipts
- preimages/rollback
- redaction
- quota/idempotency
- fail-closed behavior

Do not regain convenience by collapsing the public product back to unrestricted generic shell authority.

## Canonical validation at reconciliation preimage

Run on `81e559772dddb3a159af2c6acbf6d300d8a3160d`:

`python3 apps/commander/scripts/validate_preprod_readiness.py`

Result: exit 0.

Notable markers:

- `COMMANDER_PREPROD_MCP_CLIENT_CONFORMANCE=PASS`
- `COMMANDER_PREPROD_MCP_IDENTITY_METADATA=PASS`
- `COMMANDER_PREPROD_MCP_DCR_GATEWAY=PASS`
- `COMMANDER_PREPROD_DEVICE_TOOL_CONTRACT=PASS`
- `COMMANDER_PREPROD_AGENT=PASS`
- `COMMANDER_PREPROD_E2E_HARNESS=PASS`
- `COMMANDER_PREPROD_RELEASE_TRUST=PASS`
- `COMMANDER_PREPROD_SLO_FAILURE_SEMANTICS=PASS`
- `COMMANDER_SOURCE_PREPROD_READY=PASS`

## Remaining successor gates

1. Preserve 0.3.40 PROD and do not replay the 0.3.18 implementation.
2. Upgrade `nucleo-a` to 0.3.40 only after the current Agent cgroup child workload drains safely.
3. Finish Windows current live enrollment/data-plane canary before public-beta declaration.
4. Deploy/validate the guarded DCR compatibility boundary only under the explicit Identity promotion plan.
5. Complete real Stripe Standard runtime configuration and first checkout lifecycle before self-serve paid.
6. Select and validate an external SLO alert destination/signing secret before external alert delivery is declared live.
7. Continue client smoke testing from Simple MCP V1.1 rather than adding vendor-specific forks.

## Continuation references

- `docs/handoffs/HARA_COMMANDER_OPENAI_DESKTOP_PARITY_SUCCESSOR_HANDOFF_20261004.md`
- `docs/status/HARA_COMMANDER_SLO_FAILURE_SEMANTICS_20261006.md`
- `docs/status/HARA_COMMANDER_MCP_CLIENT_CONFORMANCE_20261006.md`
- `docs/status/HARA_COMMANDER_MCP_DCR_GATEWAY_20261006.md`
- `docs/status/HARA_COMMANDER_SELLABILITY_BACKLOG_20261005.md`

Successor rule: consult Git/GitHub first, then treat this reconciliation plus the newest dated status documents as authoritative over stale recommendations embedded in older handoff sections.
