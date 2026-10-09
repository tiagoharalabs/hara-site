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

## 2026-10-09 Desktop Commander canary

- Nucleo-A Agent 0.3.41 already installed; systemd active; doctor PASS.
- Local STDIO MCP 24 tools, bounded functional canary **33/33 PASS**.
- Local ping metadata still `HARA_SERVICES` / `runtime_authority_from_chatgpt=false`.
  **Not** the commercial OpenAI Secure MCP Tunnel E2E.
- Official checksum-pinned tunnel-client 0.0.15 installed, not configured.
- Public signed manifest serves 0.3.40; repo signed manifest remains 0.3.41;
  source is 0.3.43 with SHA drift. No agent upgrade or tunnel cutover.
- Agent health after canary PASS; all canary scratch files cleaned.
- Next: legitimate signed 0.3.43 and correct public manifest, real tunnel
  credentials and ChatGPT customer MCP readback; do not use HARA_SERVICES
  tools as substitute.

## 2026-10-09 12:58 BRT — authorized Desktop Commander dual-host product readiness

The user explicitly authorized service changes and installation on **nucleo-a**
and **services**, provided that the end goal stays ChatGPT -> OpenAI Secure
MCP Tunnel -> *customer* hara-commander mcp -> local machines, **not** the
Services administrative MCP.

Actual observations and changes made through Remote Desktop Commander:

- Both pre-existing `hara-commander-agent.service` processes were already
  active: nucleo-a on **0.3.41**, services on **0.3.40**. Neither was stopped,
  replaced or restarted to avoid accepting a non-signed production release.
- The current canonical source on `local/commander-product-current` is
  Agent **0.3.43**, source SHA-256
  `5fbff972ce00dcfd73d3e6510563d13cf304040fe2e8911d4d5e6e635dc804b0`.
  The 0.3.43 source is staged and checksum verified on both hosts as
  `~/.local/share/hara-commander/candidates/hara-commander-agent-0.3.43`,
  executable 0700, **not active as the customer Agent service**.
- The canonical Linux installer is staged on both hosts as
  `~/.local/share/hara-commander/candidates/install-0.3.43.sh`,
  with source SHA-256
  `0401097e72cfecaca994870e82641760b974468a907e6ac4673b1213fa1ccb96`.
  `bash -n` passed, but it was **not executed**; existing published release
  fails matching signed version/manifest precondition.
- The official OpenAI tunnel-client **0.0.15** is installed on each host,
  validated against the existing pinned official ZIP SHA-256
  `8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1`.
  No tunnel service was enabled; `openai-tunnel.env` and profile are absent.
- On both hosts, the **isolated** 0.3.43 self-tests passed and an ephemeral
  STDIO protocol session reported `initialize=PASS`, `24 Simple MCP tools`,
  and expected fail-closed `AUTHORIZATION_EXPIRED` with
  `PRODUCT_LEASE_REQUIRED` when running without a verified lease
  (`mutation_performed=false`). No live customer execution claimed.
- Public production `/release/agent-manifest.json` still advertises
  **0.3.40** (curl readback); canonical tracked manifest advertises
  **0.3.41**, and `build_release_manifest.py --check` reports **STALE**
  versus 0.3.43 source. This **does not substantiate a published/signed
  0.3.43**, despite the user's expectation.
- Cloudflare PROD Worker deployment remains the previous
  `afffe718-fe41-49e5-8728-c07c45382866` version; D1 migrations
  0029/0030 have no pending entries. Do not equate DB readiness with
  signed Agent readiness.
- ChatGPT's connected H.A.R.A. Commander Baseline MCP returned
  `operational_authority=HARA_SERVICES`,
  `execution_authority=HARA_SERVICES`,
  `runtime_authority_from_chatgpt=false` for both named links. **Do not**
  use this as the proof of product customer tunnel execution.

The remaining HUMAN/PRODUCT activation gate is: canonical signing and
publication of the updated 0.3.43 Agent and manifest, official signed
installer/update with rollback, OpenAI Secure MCP Tunnel ID + runtime API key
configured separately on the authorized customer machines, one-time
product authorization and 6h signed lease, then a ChatGPT-connected
**product MCP** instance showing truthful runtime/customer authority.
No private keys/tokens need be pasted in ChatGPT.

Do not repeat signature attempts blocked by security controls, substitute
a locally staged unsigned candidate as a signed release, create a Services
MCP relay, or issue unverified customer mutation commands.

## 2026-10-09 — Linux tunnel manual / auto startup implementation

- Site Linux onboarding has an opt-in autostart checkbox; generated official
  installer command passes the mode, which is persisted locally.
- Source Agent adds `tunnel start|stop|status|autostart on|off`; ON enables
  systemd user startup and OFF defaults to manual launch.
- Existing installations use a local command; a site checkbox alone does
  not remotely execute host operations.
- User service startup and local signed 6h lease are separate safety gates.
- Simulator and static tests PASS; no privileged live user-service
  changes or real tunnel credential creation claimed.
- Updated candidate source and installer staged on nucleo-a and services.
  Live versions remain 0.3.41/0.3.40, and published release remains gated.
- Reference: `docs/operations/HARA_COMMANDER_LINUX_TUNNEL_STARTUP_V1_20261009.md`.

## 2026-10-09 — Nucleo A 0.3.43 isolated execution, signed-release gate

Desktop Commander inspection of real customer test host `nucleo-a`:

- Live signed Agent `hara-commander` **0.3.41**, systemd user service ACTIVE.
- Side-by-side `~/.local/share/hara-commander/candidates/hara-commander-agent-0.3.43`
  matches source candidate checksum
  `1bb1875ee7483d4518b46cf9ef8d31f3231f5c4b3d3d7f54b9b74de964bcc129`.
- Real local STDIO MCP functional canary against candidate `0.3.43`:
  **33/33 PASS**, zero failures. It covered initialize, 24-tool list,
  governed filesystem operations in throwaway `/tmp`, process sessions,
  structured operational errors and activity metadata. Scratch fixture
  cleaned. This is **local functional evidence**, NOT ChatGPT product tunnel.
- On Nucleo A, candidate isolated manual/auto CLI regression:
  default manual OFF, autostart ON pending configuration, manual start denied
  when no profile exists, status NOT_CONFIGURED, OFF toggle, malformed
  preference denial and mode-0600 local test configuration: **7/7 PASS**.
- After tests, installed live Agent remained **0.3.41**, running and healthy.
- Public site `/release/agent-manifest.json` still reported **0.3.40**,
  public `agent/linux.py` SHA matched its own 0.3.40 manifest; repo
  tracked signed manifest remains **0.3.41**, `build_release_manifest.py
  --check` reports STALE for source 0.3.43. No canonical signed 0.3.43
  release or actual tunnel credentials/profile was found on Nucleo.
- `openai-tunnel.env`, `~/.config/tunnel-client/hara-commander.yaml`
  and `hara-commander-openai-tunnel.service` are absent: the product
  direct ChatGPT -> tunnel -> local Agent E2E remains PENDING. Existing
  Services Cloudflare edge cannot count as this product E2E.

**Do not switch the active service to the locally staged unsigned
candidate and do not run the official public installer while it serves
0.3.40**, since it could downgrade 0.3.41. The legitimate continuation
is a canonical signed 0.3.43 release / exact public artifact readback
followed by the checked update-with-rollback and authorized OpenAI tunnel
configuration on the customer's machine.
