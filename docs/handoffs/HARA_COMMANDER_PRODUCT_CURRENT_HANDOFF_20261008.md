# H.A.R.A. Commander — Product Current Handoff

Date: 2026-10-08
Authoritative branch: `local/commander-product-current`
Authoritative base: `9df6c8aa72c2f6b18f63123b0aef25ffabcfec98`

## Product law

H.A.R.A. Commander is one product line.

Customer execution path:

```text
OpenAI / ChatGPT / Codex
        |
OpenAI Secure MCP Tunnel
        |
hara-commander mcp
        |
customer machine
```

H.A.R.A. Cloud is the control plane only:

- Identity/login;
- device pairing/registry;
- plan/billing/entitlement;
- revoke/update/release;
- one-time device authorization;
- signed product lease;
- aggregate usage/metering persistence.

A LOCAL_TUNNEL device must not silently fall back to cloud relay.

The legacy remote/V1 relay is migration fallback only.

## Authorization

- device authorization code: one-time, device/tenant bound, server stores only SHA-256;
- authorization-code TTL: 10 minutes;
- product lease: RS256, device-bound, valid for 6 hours;
- local MCP fails closed without a valid LOCAL_TUNNEL lease;
- tunnel transport may remain connected while H.A.R.A. execution authority is expired;
- expired authority returns structured AUTHORIZATION_EXPIRED with Commander reauthorization URL.

## Metering and billing

The customer Agent service now performs minimal, authenticated telemetry on START, every 60 minutes while running, and on normal STOP. This is independent of tool calls and does not use cloud relay.

Metering is event-driven:

- MCP_START: sync aggregate usage only if the previous successful sync is at least 1 hour old;
- MCP_STOP: sync only if the session lasted at least 1 hour and the previous successful sync is at least 1 hour old;
- MCP session-based metering remains separately START/STOP only; the Agent service emits its own hourly presence/aggregate events;
- lease authorization also carries aggregate usage and counts as a successful sync when accepted.

Server and Agent both enforce the 1-hour minimum interval.

Cloud metering stores only aggregate/minimal metadata:

- device/tenant/subject;
- random MCP session id;
- START/STOP;
- timestamps and bounded session duration;
- Agent version/transport;
- cumulative local governed-execution count and recent daily buckets.

No command, path, file content, stdout, tool result or raw customer payload is sent.

Portal product usage is:

`remote governed calls + synchronized local governed execution aggregates`.

It is separate from Cloudflare infrastructure request count.

## Trial / Free enforcement

LOCAL_TUNNEL must not return to cloud for every tool or every 100 tools.

For metered plans, the 6-hour authorization can allocate the remaining period entitlement into the signed local budget. The Agent debits locally and fails closed at zero.

Reauthorization reconciles usage before another authorization/lease cycle.

Unlimited plans keep aggregate product history but do not enforce a quantity ceiling.

## Canonical functions

Current Linux/local canonical-function hardening is part of this branch.

Key guarantees:

- symlink leaf mutations denied; move preserves the symlink object;
- lstat semantics for symlink info;
- O_NOFOLLOW where applicable;
- optional expected_sha256 preconditions for write/edit/delete;
- preimage TOCTOU revalidation using device/inode/size/mtime metadata;
- path control-character/length guards;
- safe continuation metadata for read/list/search;
- deterministic list/search pagination;
- truthful LOCAL_MCP authority/transport receipts;
- functions.describe exposes canonical contract details;
- operational errors are structured instead of opaque failures.

Local MCP functional canary on nucleo-a:

`COMMANDER_LOCAL_MCP_FULL_CANARY_33_OF_33=PASS`.

Simple MCP remains exactly 24 tools.

## Current source/release boundary

Source Agent candidate: **0.3.43**.

Published signed release manifest: **0.3.41**.

Full readiness intentionally stops fail-closed at:

`RELEASE_SHA256_DRIFT:agent/linux.py`.

This is correct until 0.3.43 is built and signed through the canonical release-signing process.

## Migration

Migration 0029 contains:

- local authorization expiry on commander_devices;
- one-time authorization codes;
- aggregate local usage totals/daily buckets;
- last metering/start/stop timestamps;
- minimal MCP lifecycle metering events.

Migration chain 0001..0029 passes locally. New migration 0030 (Agent lifecycle telemetry) also passes SQLite schema/integrity tests.

Migrations 0029 and 0030 were successfully applied to remote DEV and PROD D1 on 2026-10-08. PROD post-migration foreign-key check returned no violations; the Agent telemetry table exists. This prepares storage schema only; it is NOT an Agent/Worker release.

## Platform status

Linux:
- LOCAL_TUNNEL source-qualified;
- canonical function hardening PASS;
- zero cloud polling in LOCAL_TUNNEL; one minimal service heartbeat per hour;
- zero per-tool H.A.R.A. relay;
- real local MCP 33/33 PASS.

Windows:
- source Agent version aligned;
- customer path remains legacy relay;
- LOCAL_TUNNEL authorization action remains withheld until Windows local-MCP/canonical parity closes.

## Current live boundary

No LOCAL_TUNNEL product cutover to PROD has been claimed.

Current live blockers:

1. sign/package Agent 0.3.43 with canonical release trust;
2. DONE: migrations 0029 and 0030 applied to DEV and PROD in order;
3. deploy DEV and run real OpenAI Secure MCP Tunnel canary using an actual tunnel_id/runtime key;
4. validate usage/metering readback;
5. promote with exact-version rollback evidence;
6. finish Windows local-tunnel/canonical parity before enabling it to customers.

## Branch policy

Continue Commander development only from:

`local/commander-product-current`

Historical Commander branches are evidence/archive only. They are not independent product strategies and must not be used as continuation bases unless this handoff explicitly reopens one.

The following lines have been absorbed into Product Current:

- command robustness;
- process-run recovery;
- Agent request efficiency/backoff;
- LOCAL_TUNNEL control plane;
- usage-meter wording/semantics;
- canonical-function hardening.

Identity/DCR remains a separate infrastructure concern. Do not merge it into the Commander product branch merely to repair Identity.


### Repository continuation policy

Storage may retain historical `local/commander-*` names because the Git Gateway denies branch deletion. Absorbed recent refs are aligned to the canonical line where fast-forward is valid. This does not create separate product strategies.

The GitHub continuation branch is only:

`local/commander-product-current`

Do not publish historical internal workstream branches to GitHub merely for archival convenience.

## Canonical next attacks

1. release/sign 0.3.43;
2. DONE: DEV/PROD migrations 0029 + 0030; existing Worker endpoint awaits eligible signed release and deployment;
3. real OpenAI tunnel E2E;
4. Windows parity;
5. canonical process contract hardening and move-rollback semantics;
6. remove legacy relay from default customer onboarding after local-tunnel live proof.

State:

`COMMANDER_PRODUCT_CURRENT=SINGLE_ACTIVE_LINE`

`COMMANDER_PRODUCT_DATA_PLANE=LOCAL_TUNNEL`

`COMMANDER_PRODUCT_CLOUD_ROLE=CONTROL_PLANE`

`COMMANDER_PRODUCT_METERING=MCP_START_STOP_AND_AGENT_HOURLY`

`COMMANDER_PRODUCT_SOURCE_AGENT=0.3.43`

`COMMANDER_PRODUCT_SIGNED_RELEASE=0.3.41`

`COMMANDER_PRODUCT_PROD_LOCAL_TUNNEL=PENDING`

## 2026-10-08 approved Agent telemetry delta — source-only

The user approved precisely three service events through the **existing**
`POST /api/device/metering-sync` endpoint: `AGENT_START` immediately when the
local Agent service starts; `AGENT_HEARTBEAT` every 3600 seconds during
operation; and `AGENT_STOP` before a normal SIGTERM/exit. No new MCP
endpoint, no per-tool Cloudflare call, no customer-data relay or customer
command payload is created. The OpenAI Secure MCP Tunnel remains the tool
transport; the Cloudflare Worker/D1 is the existing product control plane.

The device sends authenticated metadata-only `hara.commander-agent-telemetry.v1`
with client-generated event/session IDs, timestamps, bounded uptime and
`hara.commander-local-usage-report.v1` (cumulative count and bounded daily
counts). Worker verifies device credentials and LOCAL_TUNNEL, enforces a
one-hour separation of heartbeats within each Agent session, and persists
to D1 table `commander_device_agent_telemetry` introduced by migration
`0030_agent_lifecycle_telemetry.sql`. START and STOP are not suppressed
for sessions under one hour. Duplicate event IDs are idempotent; session
START/STOP has a unique partial index. The previous MCP_START/MCP_STOP
events/migration 0029 remain backward-compatible.

The Agent uses a durable SQLite `agent_telemetry_outbox`, flushing a bounded
batch at START, HEARTBEAT and STOP. Outages do not block the local tool
data plane, and unsent events survive Agent restarts. SIGKILL/power loss
cannot guarantee STOP; the last heartbeat and next START provide recovery
evidence. No background high-frequency polling is introduced.

The Storage collector has now been written and staged on the real Storage host. It queries Cloudflare D1 metadata directly using a narrowly scoped `D1 Read` API token and the cursor `(received_at_utc,event_id)`; upserts are idempotent by event ID. It is installed as a user systemd oneshot and hourly timer, with a mode-0600 config and SQLite local database. The timer remains **disabled** until the scoped token is provisioned and a live one-shot D1 read succeeds. No customer MCP tool requests pass through Storage.

Offline regressions:
`python3 apps/commander/scripts/validate_agent_hourly_telemetry.py`
`node apps/commander/scripts/validate_agent_cloudflare_telemetry.mjs`.
These validate SQLite replay, three-event Agent lifecycle, Cloudflare
handler authorization/privacy/idempotency/hourly throttle and migration.
The release signer/manifest drift gate is **still intentionally red**;
source 0.3.43 is not a signed/public 0.3.43 release.

Request-efficiency reference (one continuous Agent session per 24h, not a restart
worst case): 8 authorization requests + up to 24 MCP metering requests +
24 service heartbeats + 2 service lifecycle events = 58 control-plane
requests/day, or 1,740 per 30 days. Tool requests still produce no
per-tool control-plane traffic. This is infrastructure cost, not a billed
Commander transaction count.

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

## Local customer test readiness

Read-only client check on nucleo-a (without using HARA Services as customer
MCP): the installed `hara-commander` reports **0.3.41**, and the
`hara-commander tunnel status` subcommand is not available there.
Consequently, tomorrow's true OpenAI Secure MCP Tunnel customer-path test
requires canonical signed 0.3.43 installation and actual tunnel authorization.
The current H.A.R.A. Services administrative MCP must not be accepted as
substitute evidence.

No automatic Agent update, tunnel activation, lease issuance, or production
customer cutover was attempted during this preparation.

## 2026-10-09 — Desktop Commander installation and local MCP canary

User approved customer-client installation and testing through the **Desktop
Commander bootstrap channel**. This is separate from the product MCP E2E.

Nucleo A, observed from the client machine:

- Already installed: `hara-commander` Agent **0.3.41**, active
  `hara-commander-agent.service`, doctor PASS and remote health PASS.
- Agent executable SHA-256 matches the tracked signed 0.3.41 manifest entry
  (`e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730`).
- Existing local STDIO MCP accepts initialize and tools/list; exactly
  **24 Simple MCP tools**. In a bounded throwaway `/tmp` fixture, the
  canonical local MCP full canary returned `33/33 PASS` and `0 FAIL`.
  It covered readonly functions, temporary file mutations, process one-shot,
  PTY interaction, kill/cleanup, receipts and structured conflicts.
  Agent remained active/healthy after testing; temporary fixture removed.
- Crucially, the local ping response identified
  `operational_authority=HARA_SERVICES` and
  `runtime_authority_from_chatgpt=false`. This is NOT valid evidence for
  the intended ChatGPT -> Secure MCP Tunnel -> product Agent path.
- Official `tunnel-client` v0.0.15 for linux-amd64 installed separately in
  `~/.local/share/hara-commander/tunnel-client`, mode 0700, after exact
  verification of the canonical pinned official archive SHA-256
  `8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1`.
  Only its version was checked; **no tunnel profile, credentials or
  systemd tunnel service** was created/enabled.
- Public `/release/agent-manifest.json` currently advertises **0.3.40**
  (Cloudflare cache HIT), despite local signed repository manifest 0.3.41,
  installed binary 0.3.41, and product source 0.3.43.
  Do not re-run public installer to downgrade the active Agent.
- Source release remains blocked by `RELEASE_SHA256_DRIFT:agent/linux.py`;
  `build_release_manifest.py --check` reports STALE. Signing the updated
  candidate via remote tool was blocked by security controls in the prior
  preparation; do not bypass signing, publish unsigned binaries, or claim PROD.
- Existing ChatGPT-connected Baseline interface is HARA_SERVICES, not a
  genuine product-runtime authority. Product E2E remains unproven.

Next legitimate gate: complete canonical human-approved signature and
release of Agent 0.3.43, align public signed manifest, install it through
the verified official updater with rollback, authorize the 6h local lease,
configure the actual OpenAI Secure MCP Tunnel under a real customer identity,
and verify end-to-end tool/receipt authority `LOCAL_MCP` with no Services
execution fallback.

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

## 2026-10-09 — Linux tunnel startup choice completed in source

A new customer-facing, Linux-only checkbox on **Conectar ao Commander**
selects `HARA_COMMANDER_TUNNEL_AUTOSTART=ON|OFF`. It is reflected in the
copied official installer command and persisted in mode-0600 local config.
The site selection does not issue a remote host mutation.

Agent 0.3.43 source now supports:
`hara-commander tunnel configure`, `tunnel start`, `tunnel stop`,
`tunnel status` and `tunnel autostart on|off`. Default is OFF.
The existing bare `hara-commander start` still opens an operator
session, not the network tunnel. Auto ON uses `systemctl --user enable
--now`, manual configure `disable --now`, manual start only `start`.
Turning autostart OFF does not unexpectedly stop a current session.
Systemd user boot behavior requires linger for pre-login operation.

Every tool remains gated by signed local product lease, and starting the
tunnel without a valid lease does not grant execution authorization.
Site and Agent display separate tunnel and authorization statuses.
No new HARA Cloud endpoint or Services relay was introduced.

A dedicated regression at
`apps/commander/scripts/validate_linux_tunnel_start_modes.py` exercises
installer shell, portal checkbox and command propagation, both user-systemd
start modes, existing-machine toggles, failure-closed behavior and secret
hygiene. It is added to preprod readiness gates.
See `docs/operations/HARA_COMMANDER_LINUX_TUNNEL_STARTUP_V1_20261009.md`.

Updated unsigned 0.3.43 source and installer are byte-verified in
`~/.local/share/hara-commander/candidates/` on nucleo-a and services,
while the live signed Agents remain 0.3.41 and 0.3.40 respectively.
Neither OpenAI Secure MCP Tunnel profile nor runtime credentials have
been provisioned. Do **not** claim live tunnel or PROD deployment: the
canonical release signature and public manifest remain outstanding.

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

## 2026-10-09 — Signed public beta is now LIVE (0.3.41)

The production public site **actually serves** the verified signed 0.3.41
Agent/installer package, upgraded from public 0.3.40 by a versioned
Cloudflare rollout. PROD Worker version at 100%:
`51348588-5b38-4622-bed9-da99ab9a3ef9`.
Rollback version:
`afffe718-fe41-49e5-8728-c07c45382866`.
All six required Worker secrets inherited; triggers, deployment readback,
source-based release signature verification and all live asset SHA-256
readbacks PASS.

The official public `install/linux.sh update` was executed on nucleo-a
using the published signed artifact; Agent startup/doctor PASS, service
ACTIVE, stable installed version 0.3.41. The same installed local MCP
subsequently completed 33/33 functional canaries. This is a real signed
web-installer smoke test, not a direct OpenAI tunnel E2E.

Candidate 0.3.43 remains **UNSIGNED**. The original public release
signature and `SHA256SUMS` are kept on 0.3.41, correctly matching the
trusted release public key, while candidate Linux and Windows source and
installers are now aligned to 0.3.43 for the next release.
Signing the candidate failed closed with
`RELEASE_SIGNING_KEY_MISMATCH`: available private RSA key's modulus
does not match the public JWK pinned by installed clients.
No bypass, trust-anchor rotation, or unsigned production upload was made.
The 0.3.43 signature/publication gate requires correct key custody or
explicitly authorized key rotation with backwards compatibility.
A dedicated operational receipt with public SHA hashes, exact Worker
versions, and what is/isn't tested is in:
`docs/operations/HARA_COMMANDER_SIGNED_BETA_0_3_41_20261009.md`.

The active ChatGPT baseline connector still resolves execution through
HARA_SERVICES; the final direct OpenAI Secure MCP Tunnel E2E is pending.
Stripe PROD credentials/Price ID remain pending, so do not claim paid
checkout is available.

## 2026-10-09 — customer-side OpenAI tunnel bridge bootstrap prepared on Nucleo A

The customer requested a **private, locally instantiated MCP process**:
ChatGPT/OpenAI -> OpenAI Secure MCP Tunnel -> outbound tunnel-client on
the customer's own machine -> signed `hara-commander mcp` over stdio,
**not** ChatGPT -> HARA_SERVICES Remote MCP.

On nucleo-a, signed Agent **0.3.41** local MCP initializes (24 tools).
Official `tunnel-client` 0.0.15 exists and network TLS to api.openai.com
succeeds. A new standalone, isolated bootstrap executable is installed
at `~/.local/bin/hara-commander-openai-bridge` and the associated
systemd --user unit `hara-commander-openai-tunnel.service` is
**loaded / disabled / inactive**. The unit runs the official tunnel-client
with profile `hara-commander`. Existing signed Agent and OUTBOUND_RELAY
background service remain untouched. No HARA Services tool-call relay
is placed in this new unit.

Source and offline test:
- `apps/commander/scripts/hara_commander_local_tunnel_bootstrap.py`
- `apps/commander/scripts/validate_local_openai_bridge_bootstrap.py`
- tests PASS: idempotent preparation, no auto-start, no raw credentials,
  no invented tunnel_id, secure systemd unit, fail-closed start.
- manual real-host test `hara-commander-openai-bridge start` returns
  `OPENAI_TUNNEL_ID_NOT_CONFIGURED` (exit 2) as expected.
- Full instructions and limitations in
  `docs/operations/HARA_COMMANDER_LOCAL_OPENAI_MCP_BRIDGE_20261009.md`.

BLOCKING external personal/platform credential gate: a real OpenAI-hosted
`tunnel_id` associated with the owner's Platform org + ChatGPT workspace
and a scoped OpenAI runtime API key (Tunnels Read + Use). The user must
create/authorize these in OpenAI Platform; HARA Identity OAuth cannot
issue them. `~/.config/tunnel-client/hara-commander.yaml` and
`~/.config/hara-commander/openai-tunnel.env` are absent as verified.
Do not paste runtime keys into chat or bypass OpenAI permissions.
Once provided locally, run the bootstrap's interactive `configure`,
then `doctor`, `start` or `autostart on`, and add a ChatGPT custom
plugin using connection type **Tunnel**, selecting the real ID.
Only then can a ChatGPT-originated product tool call be homologated.

The helper does NOT sign or distribute 0.3.43 and is NOT a standalone
proof of product E2E. The existing commercial HTTPS gateway and
Cloudflare tunnels remain unmodified.
