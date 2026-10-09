# H.A.R.A. Commander — Product Current

Date: 2026-10-08
Branch: `local/commander-product-current`
State: **SOLE ACTIVE PRODUCT CONTINUATION**

Current source HEAD starts from:

`9df6c8aa72c2f6b18f63123b0aef25ffabcfec98`

This branch consolidates the current H.A.R.A. Commander product strategy:

- LOCAL_TUNNEL as customer data plane;
- H.A.R.A. Cloud as control plane;
- 6-hour signed authorization lease;
- one-time authorization code;
- MCP START/STOP aggregate metering with 1-hour minimum interval;
- Agent service START/STOP telemetry and hourly aggregate heartbeat in LOCAL_TUNNEL (source implemented, release pending);
- no per-tool cloud relay in LOCAL_TUNNEL;
- Trial/Free local signed budget enforcement;
- corrected product usage versus infrastructure-request semantics;
- Linux canonical-function safety/continuation hardening;
- Simple MCP surface fixed at 24 tools.

## Proof carried into this branch

PASS:

- local MCP 33/33 on nucleo-a;
- historical zero-idle-outbound baseline superseded by the explicitly authorized hourly Agent heartbeat;
- migration chain through 0029, plus new migration 0030 validated locally;
- signed product lease validation;
- local budget and replay guards;
- aggregate usage sync privacy/idempotency;
- START sync;
- STOP under 1h skipped;
- STOP after 1h synced;
- symlink mutation hardening;
- SHA preconditions;
- TOCTOU revalidation;
- deterministic continuation/pagination;
- truthful local authority/receipts;
- Full/Simple MCP regressions.


## Repository sanitation

Repository continuation has been normalized around this branch.

- `local/commander-product-current` is the only authoritative product continuation.
- Recent absorbed internal branches were fast-forwarded in Storage to the same canonical product-current SHA where ancestry allowed it.
- Redundant recent worktrees were removed locally after clean-status verification.
- Divergent historical branches remain evidence only; they are not continuation bases.
- The Git Gateway forbids deleting `local/*` remote branches, so sanitation uses canonical alignment rather than bypassing branch-protection hooks.
- GitHub publication is intentionally limited to `local/commander-product-current`; internal historical workstream branches are not part of the public continuation surface.

## Release truth

Source Agent: 0.3.43.

Published signed Agent: 0.3.41.

The release gate remains intentionally red at signed-release SHA drift until the updated 0.3.43 source and migration 0030 are packaged, deployed and signed canonically.

No PROD LOCAL_TUNNEL cutover is claimed.

## Continuation rule

All new H.A.R.A. Commander product work must branch from
`local/commander-product-current`.

Other `local/commander-*` refs are historical evidence or superseded work
unless explicitly reopened from the Product Current handoff.

Canonical handoff:

`docs/handoffs/HARA_COMMANDER_PRODUCT_CURRENT_HANDOFF_20261008.md`.

`COMMANDER_PRODUCT_CURRENT=SINGLE_ACTIVE_LINE`

## Agent lifecycle telemetry — approved 2026-10-08

- New source-only `AGENT_START`, `AGENT_HEARTBEAT` (3600 s), `AGENT_STOP` via existing authenticated `/api/device/metering-sync`.
- D1 migration 0030; no new MCP endpoint and no change to 24 Simple MCP tools.
- Durable SQLite outbox, bounded replay and graceful SIGTERM upload.
- Detailed customer command history is local; Cloudflare stores aggregated event metadata only.
- Storage/Citadel collector remains a follow-up; no collector or PROD cutover claimed.
- Linux and Worker unit/regression tests PASS locally; real tunnel/Cloudflare integration remains pending.
- Signed release still 0.3.41; source Agent 0.3.43 remains unreleased with SHA drift.
