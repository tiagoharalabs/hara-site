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

## 2026-10-09 — Public signed beta checkpoint

- Signed public Agent/installer **0.3.41 LIVE**, Worker deployment
  `51348588-5b38-4622-bed9-da99ab9a3ef9` at 100%.
- Previous Worker rollback `afffe718-fe41-49e5-8728-c07c45382866`
  recorded and preserved. Secrets/readback/assets/triggers PASS.
- Official web installer `update` on Nucleo A PASS, systemd active,
  version 0.3.41 and `doctor=PASS`; local MCP **33/33 PASS**.
- Latest candidate source and installers aligned 0.3.43. Release signature
  BLOCKED by private/public JWK modulus mismatch; unsigned candidate
  was NOT promoted. Canonical published signature/manifest stays 0.3.41.
- Cloudflare Gateway route and identity exist; direct OpenAI Secure
  MCP Tunnel remains unconfigured; HARA_SERVICES is not product direct
  authority. Stripe billing PROD activation still FALSE.
- Details: `docs/operations/HARA_COMMANDER_SIGNED_BETA_0_3_41_20261009.md`.

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
