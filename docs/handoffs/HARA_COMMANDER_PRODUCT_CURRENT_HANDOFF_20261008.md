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

## 2026-10-09 — Direct UX / segurança (fonte candidata, ainda não publicada)

- Contrato de transporte exclusivo: OpenAI/ChatGPT -> Secure MCP Tunnel -> `tunnel-client` no cliente -> `hara-commander mcp` via STDIO. O HARA Services não encaminha essas chamadas. A Cloud HARA mantém pareamento, licenças e metadados mínimos.
- Na fonte Linux Agent **0.3.43**, o comando preferido agora é `hara-commander tunnel connect` (`tunnel configure` continua como alias). Mostra páginas oficiais para obter `tunnel_id` e chave de runtime. Chave guardada somente em arquivo local `0600`, nunca em argv, Git ou HARA Cloud.
- O `tunnel-client init` cria perfil de dados privados `0600`; `doctor` deve retornar sucesso ANTES de considerar a configuração válida. Falha limpa o perfil e o env, sem alterar o Agent. Configuração existente não é sobrescrita.
- **Fail-closed de autorização:** `tunnel start` e `tunnel autostart on` não iniciam conexão sem licença local `LOCAL_TUNNEL` válida (janela de 6 horas) E OpenAI doctor PASS. Seleção de autostart no instalador fica pendente até `hara-commander authorize`; com autorização válida, inicia automaticamente, se essa foi a escolha do cliente.
- O portal, na fonte candidata, descreve explicitamente que OpenAI Secure MCP Tunnel é privado por workspace, não é distribuição pública de plugin.
- Helper temporário `hara-commander-openai-bridge` no Núcleo recebeu validação que exige `hara-commander doctor` sinalizar licença `LOCAL_TUNNEL`, `HARA_COMMANDER_LOCAL_AUTHORIZATION=PASS` e `HARA_COMMANDER_TOOL_DATA_PLANE=LOCAL_DIRECT` antes de iniciar ou habilitar o túnel; SHA-256 do helper: `ece13b6fbad4ad93441b951d0dac87bda8e40ed05dd348e46a1fe62cd595523d`. Isso mantém o Agent assinado 0.3.41 fora da conexão direta, até release autorizado.
- Testes offline: `validate_linux_tunnel_start_modes.py` PASS, `validate_local_tunnel_control_plane.py` PASS, `validate_local_openai_bridge_bootstrap.py` PASS, `validate_local_tunnel_unit_economics.py` PASS, Agent self-test PASS, Python/Bash syntax PASS. Incluem negação antes da autorização, não vazamento de chave, rollback de configuração inválida e não sobrescrita.
- **Não é E2E com a OpenAI real**. Pendências externas: tunnel_id legítimo, chave OpenAI de runtime e associação ao workspace/permissões, e inclusão da conexão do tipo Tunnel no ChatGPT. Não criar credenciais fictícias.
- **Não é release público**. A fonte 0.3.43 continua sem assinatura válida pela cadeia do release (mismatch JWK privada/pública reportado anteriormente). Não promover o código ou trocar chave de assinatura fora do processo de custódia autorizado. O PROD permanece com Agent assinado 0.3.41.
- Documentação pública consultada em 2026-10-09: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels — Secure MCP Tunnel suporta conexões privadas, NÃO submissão/distribuição de plugin público; esse limite não pode ser removido pelo instalador HARA.

## 2026-10-09 — decisão de lançamento Cloud-first (modelo Desktop Commander)

O usuário aprovou explicitamente a distribuição via MCP HTTPS comercial da H.A.R.A., com Agent executando localmente e **o tráfego de cada chamada do plugin passando pelo Gateway Cloudflare**. Não utilizar o MCP administrativo HARA Services como proxy. OpenAI Secure MCP Tunnel privado permanece opcional e não bloqueia beta público.

- Fonte candidata do Linux installer: default de nova instalação `OUTBOUND_RELAY`; Direct somente opt-in; Cloud não precisa de OpenAI Platform key; update evita baixar tunnel-client em máquinas Cloud.
- Front-end candidato: Cloud como opção padrão, Direct avançado somente Linux, instruções de OAuth HARA Identity e declaração explícita de transporte.
- Pacote de submissão rascunho com logo da capivara: `apps/commander/plugin-submission/` (`plugin.json`, `mcp.json`, ícones, 5 roteiros positivos + 3 negativos). **Não está publicado na OpenAI.**
- Privacidade verificada: D1 fallback de chamada contém `payload_json`/`result_json` até TTL nominal de 50 s; redação por manutenção periódica pode ocorrer depois do TTL (cron minuto 17 a cada hora). Depois persistem hash markers e metadados. Não anunciar 'nunca armazena' nem 'nenhum tráfego pela HARA'.
- Evidência de testes: `validate_cloud_launch_contract.py` PASS; `validate_prod_static.py` PASS; `validate_linux_tunnel_start_modes.py` PASS; `validate_local_tunnel_control_plane.py` PASS; `validate_customer_privacy_noc_contract.py` PASS; `test_customer_mcp_simple_profile.mjs` PASS; `test_customer_mcp_edge.mjs` PASS; `node --check` e `bash -n` PASS.
- Versão assinada pública em PROD continua 0.3.41. Fonte 0.3.43 não assinada, JWK mismatch não solucionado. Preparado staging isolado `/tmp/hara-commander-prod-cloud-ui-20261009` com assets binários assinados 0.3.41 intactos; a validação final de deploy não pôde ser concluída e **nenhuma promoção de produção foi realizada** nesta rodada. Evitar alegar que o portal live já exibe as alterações candidatas.
- Próximo gate: homologação **real** do ChatGPT conectado ao MCP comercial via OAuth, sem Services Baseline, com cliente DEMO, e aprovação de submissão à OpenAI. Video, challenge de domínio e credenciais de reviewer ainda pendentes.
- Runbook: `docs/operations/HARA_COMMANDER_CLOUD_FIRST_PUBLIC_PLUGIN_20261009.md`.

## 2026-10-09 — frota 7/7 Agent assinado 0.3.41 online

- Atualizadas pela distribuição oficial assinada 0.3.41 as máquinas `services`, `sentinela-a`, `sentinela-b`, `sentinela-c`, `sentinela-d`, `ninja-blue`. `nucleo-a` já usava 0.3.41.
- Ponto causal anterior: nas Sentinelas A/B/C/D e Ninja, o Agent 0.3.40 já existia com cadastro preservado, mas o systemd user estava `inactive/disabled`. Agora todos os sete `active/enabled`, e `Linger=yes` verificado; aplicado `loginctl enable-linger` às Sentinelas A e D.
- Config do dispositivo preservado byte idêntico em cada atualização; binário 0.3.41 confere com release público, `doctor` e Remote Health PASS.
- PROD Cloudflare D1: sete dispositivos ativos, 0.3.41, modo `OUTBOUND_RELAY`, presença recente. `hara_ping` pelo Baseline: **7/7 PASS** com recibos.
- Não confundir: esses pings foram via `HARA_SERVICES`, não a homologação E2E do ChatGPT com o MCP comercial Cloudflare.
- Detalhes e evidências: `docs/operations/HARA_COMMANDER_FLEET_SIGNED_AGENT_0_3_41_20261009.md`.
- Nenhum release 0.3.43 não assinado, instalação de serviço D GPU ou mudança na fila de jogo; nenhum host reiniciado.

## 2026-10-09 — live OAuth/DCR blocker isolated to Identity gate (not token generator)

- Live ZITADEL/HARA Identity OIDC issuer, PKCE S256, endpoints and customer-MCP protected resource metadata: **PASS**.
- OIDC discovery advertises `registration_endpoint`, but RFC 8414 OAuth authorization server metadata **does not** advertise it; `client_id_metadata_document_supported=false`.
- Identity Storage `hara-identity-zitadel-dcr-gateway-1` is HEALTHY but **mode=closed**, compose `HARA_DCR_GATEWAY_MODE: closed`, `HARA_DCR_REGISTRATION_ADVERTISED: "false"`. A controlled invalid `POST /oauth/v2/register` is rejected HTTP **404**, consistent with closed guard.
- Existing Identity worktree `local/identity-dcr-refresh-20261008` already contains guarded DCR promotion + atomic rollback and synthetic security tests (PASS); activation requires authorized ZITADEL owner PAT via private local file and production promotion from the Identity host. **Not executed**; no PAT accessed or exposed.
- New customer-side preflight: `apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect closed` PASS; `--expect guarded --require-ready` fails closed as expected.
- Active blocker for ChatGPT consumer OAuth: **DCR not promoted**. Once governed promotion passes, configure custom MCP connection in ChatGPT with normal HARA Identity consent/PKCE and execute actual commercial tool through Cloudflare (not Services Baseline). No new token generator needed.
- Evidence/runbook: `docs/operations/HARA_COMMANDER_ZITADEL_DCR_GATE_20261009.md`. Signed 0.3.41 fleet and Cloudflare endpoint remain unchanged.

## 2026-10-09 — DCR GUARDED ativado, registro OAuth real homologado

**CURRENT GATE: `HARA_DCR_EDGE_RECONCILIATION=PASS`.** O usuário leu no Storage, com a própria credencial de proprietário, os flags reais do ZITADEL `dynamicClientRegistration.enabled=True` e `allowUnauthenticated=True`. Não recriar PAT, não reverter flags para `False/False` e não executar novamente o antigo `promote_mcp_dcr_guarded.py` que exige backend fechado.

- Nova rotina canônica `apps/identity-login/scripts/reconcile_mcp_dcr_existing_backend.py` (branch Identity `local/identity-dcr-refresh-20261008`) reconcilia **somente o Gateway público e o anúncio RFC 8414**, mantendo ZITADEL/backend intocados. Aplicada pelo Storage com root e testes de backup, rollback, fail-closed e idempotência PASS.
- Configuração PROD Storage: `HARA_DCR_GATEWAY_MODE: guarded`; `HARA_DCR_REGISTRATION_ADVERTISED: "true"`. DCR positivo: cliente OAuth temporário registrado HTTP 201, consultado HTTP 200, excluído HTTP 204; limpeza PASS. DCR negativo: `400 invalid_client_metadata`. Health do ZITADEL/login e dos dois serviços de borda PASS.
- HARA Commander público: `python3 apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect guarded --require-ready` PASS. `/api/mcp?profile=simple` sem token ainda 401. Os nomes das três configurações de audiência e introspecção aparecem no catálogo de segredos do Worker PROD (não foram revelados valores).
- Rotina atual em Storage: `/srv/hara/identity/operations/reconcile_mcp_dcr_existing_backend.py --backend-already-enabled`, que verifica `HARA_DCR_EDGE_ALREADY_GUARDED=PASS` e retorna `HARA_DCR_EDGE_EXECUTE=NO_CHANGE` sem modificar serviços.
- Candidato do plugin `apps/commander/plugin-submission/mcp.json` permanece apontando para o MCP comercial com DCR da Identity; **não é necessário Secure MCP Tunnel OpenAI por cliente**.
- **ÚNICO GATE COMERCIAL ainda pendente:** ChatGPT concluir consentimento OAuth/PKCE e entregar token de usuário aceito pelo Worker, depois ChatGPT invocar ferramenta no Agent pelo MCP **COMERCIAL** (não pelo Baseline administrativo), isolamento/permissões e revisão/publicação na OpenAI. Não afirmar que a sessão ChatGPT foi homologada, que o app está publicado nem que o Worker valida todo token real antes da prova E2E.
- Evidência autoritativa da frente de Identity: `docs/status/HARA_COMMANDER_MCP_DCR_GUARDED_LIVE_20261009.md`.

## 2026-10-09 — E2E real pelo plugin comercial do ChatGPT CONFIRMADO (Núcleo A)

O plugin nomeado **H.A.R.A. Commander** chamou `ping` e `get_device_info` via ferramentas próprias `mcp__H_A_R_A__Commander__*`, ambas PASS. Recibos SHA-256 locais do Agent 0.3.41 `nucleo-a` foram verificados e cada `request_id` foi localizado com exatidão como operação `HARA-CUSTOMER-MCP-` concluída na Cloudflare **PROD D1**, incluindo tool ID, dispositivo e horários compatíveis. Isto elimina a dúvida anterior sobre se a chamada teria realmente alcançado o caminho comercial.

ATENÇÃO: `operational_authority=HARA_SERVICES` é rótulo legado *hardcoded* pelo Agent 0.3.41 para **todos os transportes remotos** (qualquer `_transport != LOCAL_MCP`), inclusive `OUTBOUND_RELAY` comercial. `runtime_authority_from_chatgpt=false` também é fixo. Nenhum dos dois rótulos pode servir sozinho para provar o trajeto do pedido. Prova no recibo + D1 é a evidência autoritativa.

Relatório: `docs/operations/HARA_COMMANDER_COMMERCIAL_MCP_REAL_E2E_20261009.md`. Escopo: conta ChatGPT atual e Núcleo A; faltam testes com outro tenant, negações, aprovação/escrita e submissão pública. Manter Agent público assinado 0.3.41 e não declarar plugin publicado.

## 2026-10-09 — auditoria de tráfego e bloqueio comercial Cloud/Direct

**Não confundir AUTH ONCE com DATA PLANE DIRECT.** Em `OUTBOUND_RELAY` público cada chamada MCP passa por `commander.haralabs.com.br/api/mcp?profile=simple` e é encaminhada pela Cloudflare ao Agent; o Agent ainda faz polling ocioso a cada 10s, hot a cada 2s e heartbeat por minuto. O modelo de testes estima 10.086 HTTP/dia/Agent ocioso (70.602 com sete ligados) — **não são operações cobradas**.

**Cobrança separada da contagem de UI:** Free `TRIAL` 10.000 operações governadas/mês; REVIEW 100/mês; Founder/Pro ilimitados. `TenantQuota` reserva uma unidade antes, confirma com recibo no sucesso, libera em falha, e nega `QUOTA_EXCEEDED` ao esgotar. `ping` é gratuito, mas aparece no contador informativo 7d/total. A sincronização 1/h e os blocos locais são do **modo Direct**, não do Cloud público corrente.

Provas: os testes de quota, orçamento local, TTL, telemetria e eficiência passaram; leitura PROD D1 confirmou planos. A conta conectada é `FOUNDER_INTERNAL` `UNMETERED`, e nenhum entitlement Free ativo foi encontrado nesta leitura: **bloqueio real no limite Free ainda não foi exercitado em PROD**. Próxima prova adequada: tenant sintético DEV com limite reduzido, repetição/idempotência e excesso. Evitar alterar produção para simular esgotamento.

Documento: `docs/operations/HARA_COMMANDER_CLOUD_DIRECT_QUOTA_TRANSPORT_AUDIT_20261009.md`. Nenhuma mutação PROD foi realizada.

## 2026-10-09 — Event V2 WebSocket hibernável: E2E DEV no Núcleo A

**Hibernation-capable DeviceChannel DEV = PASS.** Agent Event V2 isolado registrado e conectado à Cloudflare DEV; `hara.health` enfileirado e acordado por WebSocket concluiu em 3829ms. SIGTERM/reconnect limpo, novo wake concluiu em 2499ms. Experimento tem XDG e token DEV separados; Agent comercial assinado 0.3.41 seguiu ativo e respondeu a `ping` após todos os testes. Sem idle HTTP polling no loop Event V2; PING de protocolo a cada 60s não interrompe hibernação segundo a API Cloudflare. Nenhuma economia real de billing medida ainda.

Regressões antigas do pacote Event V2 foram reconciliadas ao Worker autoritativo atual sem relaxar isolamento por tenant nem controles de quota; `validate_event_v2_wiring.py`, `validate_device_channel_source.py`, `validate_event_v2_transient_rpc.py` e `validate_event_v2_productization.py` PASS. O teste de quota DEV via tenant com plano ilimitado não atende precondição de reserva: não tratá-lo como homologação de bloqueio Free.

**PROD EVENT V2 permanece OFF.** Worker PROD sem binding `DEVICE_CHANNEL`; Agent assinado 0.3.41 sem transport Event V2; fonte 0.3.43 requer chave privada legítima que corresponda ao JWK público, sem atalho. Próximo gate: assinatura de release, binding/migração PROD behind flag, opt-in Founder e confirmação de redução efetiva de requests. Detalhes e rollback em `docs/operations/HARA_COMMANDER_EVENT_V2_HIBERNATION_DEV_PROOF_20261009.md`. Token de canário interna foi renovado exclusivamente no Worker DEV, não em PROD.

## 2026-10-09 — Event V2 PROD server canary: deployed and authenticated MCP regression PASS

**New Worker PROD 100%:** `215ab34e-78ad-4002-a4d6-7e26e3a71f94` (prior `51348588-5b38-4622-bed9-da99ab9a3ef9`). Added guarded `DEVICE_CHANNEL` Durable Object SQLite migration **v3** plus `DEVICE_EVENT_V2_ENABLED=true`, **single explicit Founder nucleo-a device allowlist**. Non-canary bearer connections rejected by source guard. **Transiente Event V2 RPC remains DEV-only**.

**Source/asset safety:** Isolated signed-stage builder `apps/commander/scripts/build_prod_signed_event_v2_stage.py` obtained all 4 signed 0.3.41 agent/installer payloads byte-exactly from historical `08500d5`, verified manifest RS256 and SHA-256, and deployed them alongside current Worker with no change to the signed public release. Six PROD secret names preserved. Stage + emergency flag OFF config available at `/tmp_hara/commander-eventv2-prod-stage-20261009-cf-v3/apps/commander` (Services).

**Live proof after deploy:** OAuth protected-resource metadata 200; anonymous customer MCP 401; anonymous channel GET 426 and bad-token WebSocket Upgrade 401; site assets 200; all four signed files exactly match expected SHA. Via **commercial ChatGPT H.A.R.A. Commander**, `ping`, `get_device_info` and `get_usage_stats` PASS; one post-deploy ping's local signed receipt was correlated 1:1 with completed `HARA-CUSTOMER-MCP` call in production D1. PROD device remains Agent 0.3.41 **OUTBOUND_RELAY** active; no device switched and no change in idle polling/cost can yet be claimed. Static regression, privacy, local quota and product lease tests PASS.

**Caution:** New deploy also refreshed `index.html`, `app.js` and `styles.css` from current Git source; HTTP smoke PASS, but not claimed byte-identical to previous deployed site. **DO migration is atomic:** to disable Event V2 use the prepared stage `wrangler.event-v2-disabled.jsonc` (only changes `DEVICE_EVENT_V2_ENABLED=false`), not a D1 backup restoration. Kill-switch dry run PASS.

**Remaining gate:** signed updated EventV2-enabled Agent (signing private JWK trust-anchor mismatch for 0.3.43 still unresolved); Founder-only client opt-in and tested rollback. No unsigned public Agent, no silent key rotation, no public rollout. Production's Event V2 server is ready but hasn't reduced HTTP polling because the signed installed Agent remains 0.3.41.

Authoritative report: `docs/operations/HARA_COMMANDER_EVENT_V2_PROD_SERVER_FOUNDER_CANARY_20261009.md`.

**Final operational closeout:** The post-deploy commercial plugin ping was correlated by Agent SHA-256 receipt to exactly one completed production D1 `HARA-CUSTOMER-MCP` call. The isolated DEV Event V2 canary process was then stopped cleanly; the production signed 0.3.41 service remains active. Feature-disable config was dry-run compiled without changing v3 migration or signed assets. PROD WebSocket server capability is live, but no production device has transitioned off 0.3.41 polling.

## 2026-10-09 ~23:00 BRT — Commercial Founder Event V2 LIVE PASS

**NEW AUTHORITATIVE CURRENT:** Núcleo A now executes the **signed Event V2 v0.3.44** Agent via production Cloudflare hibernating WebSocket; actual ChatGPT commercial MCP `ping`, `get_device_info`, `read_file`, `list_processes` all **PASS**. Agent SHA-256 receipts from commercial calls were read and validated on the local device, request IDs correlated to exact PROD D1 `COMPLETED` rows. DEV-only transient RPC still disabled in PROD; OAuth and signed v1 trust anchor unchanged.

User-manager: `hara-commander-agent-v2.service=active` (0 restarts), `hara-commander-agent.service=inactive/enabled`, temporary 15-minute fallback timer **cancelled** after proof. Boot still defaults to signed 0.3.41 legacy; do not claim persistent v2 after reboot. PROD D1 Founder device metadata conditionally synchronized to `agent_version=0.3.44`, `tunnel_mode=EVENT_V2`, `state=ACTIVE` after signed proof. All other devices untouched.

**Transport efficiency:** fixed 10-second idle HTTP polling has been removed from the running Event V2 Agent loop; socket keepalive is RFC6455 PING. Real-world Cloudflare billing/request count reduction must still be measured across representative idle windows before asserting cost savings.

Report (append-terminal-truth): `docs/operations/HARA_COMMANDER_V2_SIGNED_FOUNDER_CANARY_PROOF_20261009.md`. Remaining gates: soak, reboot-safe failover/enablement, Cloudflare request metrics, tenant/Free billing canary, Windows signed parity, expand per-device allowlist sequentially only after verification.

## 2026-10-09 23h+ BRT — Persistent Event V2 Founder + local failover (one machine)

**Núcleo A Event V2 0.3.44 is now enabled for boot**, signed 0.3.41 legacy disabled at boot but installed byte-perfect for rollback; `loginctl Linger=yes`. User service has `Conflicts=hara-commander-agent.service` preventing a dual-Agent token race, plus bounded systemd start restarts. New local-only `hara-commander-v2-guard.timer` enabled, checks every ~120s with startup grace and two-strike failover; no Cloudflare polling/token access. The watchdog stops v2 and verifies inactive before enabling/starting v1; mock failure/recovery tests PASS. Guard file and units permissions verified; v2 private signing key ABSENT from Nucleo.

**Live proof:** controlled v2 service restart PASS; commercial ChatGPT plugin `ping`, `get_device_info`, `read_file` returned PASS; exact local receipts correlated to 3 PROD D1 `COMPLETED` calls; local v2 WebSocket reconnected, old remained inactive. Guard real timer trigger and later `HEALTHY` result PASS. Git evidence: `docs/operations/HARA_COMMANDER_EVENT_V2_PERSISTENT_BOOT_GUARD_PROOF_20261009.md`.

**Limits:** no full OS reboot (other H.A.R.A. jobs preserved), no intentional live failover, no measured Cloudflare billing reduction yet. No other device migrated. Signed 0.3.44 Founder artifact is not a general-distribution release. Next: actual CF/D1 cost metrics, longer soak, maintenance-window reboot, Free quota isolation canary, Windows/platform release signing, then sequential per-device rollout. Rollback: local `python3 ~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py --rollback` on nucleo-a.

**Guard hardening correction, same session:** A first periodic service-mode probe recorded one false `EVENT_V2_TCP_CONNECTION_MISSING` because the guard unit had `PrivateTmp=yes`: read-only systemd sandbox tests isolated this exactly, while `NoNewPrivileges=yes` alone preserved PID/socket visibility. Timer was temporarily stopped **before** the two-strike rollback; the signed Event V2 commercial Agent stayed active. Guard unit now omits `PrivateTmp=yes` but retains `NoNewPrivileges=yes`. Exact SHA source-deployment readback PASS, real guard oneshot reset the false strike to `HEALTHY`/0, timer rearmed and live `--check` PASS. PROD D1 remains `0.3.44 / EVENT_V2 / ACTIVE`. All event payloads and tokens remain untouched. Tests now assert that the incompatible PrivateTmp setting cannot return undetected.

## 2026-10-09 — first Cloudflare PROD measured Event V2 request comparison (read-only)

Confirmed via account-scoped Cloudflare GraphQL `workersInvocationsAdaptive`, zone-scoped **exact** `/api/device/calls/next` `httpRequestsAdaptiveGroups` (sampleInterval **1** in both windows) and same-window read-only PROD D1 `commander_device_calls` counts. Primary **matched quiet windows 40min each, 4 commercial calls per window**:

- Before (2026-10-10T00:20–01:00Z): `calls/next=1756`, `Worker requests=2066`, Worker errors 0.
- After (2026-10-10T02:05–02:45Z): `calls/next=1392`, `Worker requests=1658`, Worker errors 0.
- **Observed fleet-wide queue-path change −364 (−20.73%)**, Worker requests **−408 (−19.75%)**. Numbers cover the shared Cloudflare Worker/zone, not one device; exact causal attribution and billed DO-duration savings remain unverified. No private user payload or authentication token was exposed.
- A misleading high-workload baseline (37 vs 4 calls) was explicitly excluded from the principal comparison.

Reproducible read-only probe `apps/commander/scripts/commander_prod_cf_efficiency_probe.py`, sanitized evidence `docs/status/HARA_COMMANDER_CF_EVENT_V2_MATCHED_ACTIVITY_MEASUREMENT_20261009.json`, report `docs/operations/HARA_COMMANDER_EVENT_V2_CLOUDFLARE_MEASURED_TRAFFIC_20261009.md`.

**Next:** longer idle/cost windows and Durable Objects billed duration, live Free-plan quota/cross-tenant canary, per-device signed rollout gates. No production device or Worker code mutations in this audit.

## 2026-10-09 — commercial checkout read-only gate and preflight hardening

`billing_prod_activation_preflight.py --live` now returned **PASS** against actual PROD catalog: `TRIAL Free` 10,000 governed/month, `STANDARD Pro` unlimited, approved price BRL 80/month. `SCALE` is inactive. **Stripe PROD not provisioned:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and `STRIPE_PRICE_STANDARD` pending, billing_connections/webhook_events 0; `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`. Do not claim public paid checkout is live.

Hardened read-only preflight to pinned local Wrangler, bounded retry after transient D1 CLI failure, and fail-closed `secret list` or remote `SELECT` command allowlist; runtime testing explicitly denied unsafe commands, no PROD mutation. Exact report: `docs/operations/HARA_COMMANDER_COMMERCIAL_READINESS_GATE_20261009.md`. Continue to distinguish Founder-operational commercial MCP from ready-to-charge Stripe subscriptions.

## 2026-10-09 — publishing scope / Storage mirror reconciliation hold

**Clean content commit `225c60e70c1458f7bddf74ed1b94951efc67797a` published on GitHub and present in local history** (Cloudflare matched workload efficiency + billing read-only preflight). **Storage mirror separately holds `092f35afc52827d6c5584f0401e9f60eaeb3d985`**, a rejected draft that includes a CI workflow edit. GitHub OAuth lacked `workflow` scope; therefore the published commit was surgically prepared without workflow changes and accepted by normal GitHub fast-forward. Storage denied the guarded non-fast-forward reconciliation and **this repository control was not bypassed**. See `docs/operations/HARA_COMMANDER_PUBLISH_SCOPE_AND_STORAGE_RECONCILIATION_20261009.md`. Do not falsely claim local/Storage/GitHub equal; administrative Storage ref reconciliation is required. CI wiring of two new source-only tests is DEFERRED, but manual tests PASS. **No live PROD change** from this publishing issue.
