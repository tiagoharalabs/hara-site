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
- migrations 0029 and 0030 applied successfully to remote DEV and PROD D1; post-migration schema/readback PASS;
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

The release gate remains intentionally red at signed-release SHA drift until the updated Agent 0.3.43 is packaged and signed canonically. The remote migrations 0029/0030 are already applied; no Worker/Agent promotion was performed.

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
- Storage collector installed on real Storage; SQLite and self-tests PASS. Hourly timer disabled pending scoped Cloudflare D1 Read token and live readback. No customer-content relay or PROD Worker cutover claimed.
- Linux and Worker unit/regression tests PASS locally; real tunnel/Cloudflare integration remains pending.
- Signed release still 0.3.41; source Agent 0.3.43 remains unreleased with SHA drift.

## 2026-10-08 productive Gateway + Storage preparation

- Cloudflare PROD D1 migrations `0029` and `0030` **applied**, same on DEV;
  remote D1 lists no pending migrations; PROD foreign-key integrity clean.
- Worker PROD baseline **unchanged** at
  `afffe718-fe41-49e5-8728-c07c45382866` (100%). Its HTTP health
  response was 200; unauthenticated MCP gateway returned 401 as expected.
- Updated Worker PROD bundle `wrangler versions upload --dry-run` PASS
  with existing binding to `PRODUCT_DB`; no version deployed or promoted.
- Release-signing operation via remote tool was blocked by security policy.
  Do not bypass it, and do not advertise unsigned Agent 0.3.43 as live.
  Published signed Agent remains 0.3.41; the existing release SHA drift is
  an intentional fail-closed gate.
- Storage host collector installed:
  `/home/sartorius/.local/bin/hara-commander-storage-collector.py`.
  Local SQLite and read-only collector self-tests PASS; checksum byte-for-byte
  matches the canonical product script. User systemd service and hourly timer
  installed; **timer disabled** because scoped `D1 Read` API token has not
  been provisioned into its mode-0600 config.
- Secure, private runtime operation note on Services:
  `/home/sartorius/.local/state/hara-commander-prod-ops/commander_prod_prep_20261008.txt`,
  mode 0600, with pre-migration D1 bookmark and exact Worker rollback ID.
  Never publish database recovery bookmark in Git.
- To close the remaining gate: canonical signer approval and
  manifest verification; real scoped D1 read-token on Storage; one-shot
  Storage collection, then enable the hourly timer; Worker PROD version
  promotion with secret-carrying target/readback and rollback evidence;
  finally real OpenAI LOCAL_TUNNEL customer MCP E2E on a test Agent.
