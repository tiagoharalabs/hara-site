# H.A.R.A. Commander — handoff canônico e completo para o próximo chat
**Checkpoint de 10/10/2026 (America/Sao_Paulo) | Produto comercial, Event V2, Cloudflare, segurança, assinatura, billing e governança Git**

> **COMECE POR AQUI.** Este documento é a verdade mais recente do produto neste checkpoint. As linhas antigas nos handoffs de 08 e 09/10 mostram a evolução histórica, **não** devem ser lidas como o estado atual quando contradizem este documento. Não iniciar outra frente de produto; continuar exclusivamente em `local/commander-product-current`.

## 1. Identidade, produto e objetivo
- Produto: **H.A.R.A. Commander** da H.A.R.A. Labs, aplicativo/MCP comercial para ChatGPT, com autenticação, computadores pareados, execução local governada, histórico/recibos e controle de plano. O Founder usa sua própria conta como canário real.
- Repositório: `tiagoharalabs/hara-site`. Worktree no Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`. **Única frente canônica:** `local/commander-product-current`.
- Plugin comercial correto: ferramentas `mcp__H_A_R_A__Commander__*`. Não confundir com `mcp__H_A_R_A__Commander_Baseline__` (admin/Services), nem com o conector `Remote_Desktop_Commander` usado como via de suporte/inspeção. Provas E2E do produto exigem ferramenta **do plugin comercial**.
- MCP público: `https://commander.haralabs.com.br/api/mcp?profile=simple`; autenticação HARA Identity/OAuth; tráfego de comando passa no Worker/relay comercial da Cloudflare. **Não existe um túnel privado OpenAI direto em produção**. Site: `https://commander.haralabs.com.br/`.
- Objetivos: assinatura SaaS, execução local do cliente, segurança/autorização por tenant e máquina, redução de requisições ociosas de infraestrutura, billing confiável e onboarding simples. **Não confundir transação mostrada no site, operação de quota comercial e requisição HTTP da Cloudflare.**

## 2. ESTADO OPERACIONAL VERIFICADO — 10/10/2026
| Componente | Verdade neste checkpoint | Prova |
|---|---|---|
| ChatGPT MCP comercial → Núcleo A | **PASS** | `ping`, `get_device_info`, `read_file`, `list_processes`; resultados/recibos SHA-256 |
| Núcleo A: Agent | **0.3.44, EVENT_V2, HARA_COMMANDER_AGENT** | Cliente assinado e D1 PROD; máquina `nucleo-a` |
| Núcleo A: user systemd | **v2 ativo+habilitado; v1 inativo+desabilitado; 0 reinicializações inesperadas** | `systemctl --user show` |
| WebSocket | **Conectado; Durable Object hibernável, sem polling HTTP ocioso contínuo deste Agent** | `event-v2-status.json`; canal Event V2 e fonte |
| Watchdog/failback | **Timer habilitado/ativo; `HEALTHY`, strikes=0** | Guard local ~120 s; falha sustentada provoca retorno ao v1 |
| Outros dispositivos comerciais | **Ainda em OUTBOUND_RELAY / 0.3.41**, não migrados | Listagem comercial/PROD |
| Worker Cloudflare PROD | `215ab34e-78ad-4002-a4d6-7e26e3a71f94` (100%) | `wrangler deployments list --json` |
| `DeviceChannel` PROD | Migração DO `v3`, `DEVICE_EVENT_V2_ENABLED=true`; **allowlist exclusiva Núcleo A** | Configuração Worker e D1 |
| Transient RPC sem D1 payload | **Somente DEV**; não habilitado no Worker PROD | `DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED` ausente em PROD |
| Quota Free | `TRIAL`: **10.000 operações governadas/mês**, período `CALENDAR_MONTH` | PROD D1 e preflight |
| Pro | `STANDARD`: **ilimitado**, preço de catálogo aprovado R$ 80/mês | PROD D1; preço não prova Stripe ativo |
| Founder | `FOUNDER_INTERNAL`: ilimitado, `UNMETERED` | Plugin `get_usage_stats` |
| Stripe PROD | **Checkout pago NÃO PRONTO** | Faltam `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` |
| Cold reboot Núcleo / failover forçado real | **NÃO REALIZADOS** | Evitar interrupção de cargas GPU/H.A.R.A. sem janela de manutenção |
| CI workflow novo | **Adição de dois comandos de teste NÃO PUBLICADA no GitHub** | Credencial GH sem `workflow` scope |
| Divergência Storage | **PENDENTE de reconciliação autorizada** | Ref protegida, detalhes na seção 8 |

**Regra de interpretação:** o produto já funciona comercialmente **para o Founder, na máquina dele**, mas **não** houve homologação da cobrança paga, de múltiplos tenants externos, da franquia Free na borda sob esgotamento nem distribuição pública do Event V2.

## 3. Caminho E2E REAL e segurança
```text
ChatGPT / H_A_R_A__Commander (plugin comercial)
  → OAuth HARA Identity → https://commander.haralabs.com.br/api/mcp?profile=simple
  → Cloudflare Worker (grant/tenant/seleção de computador/quota)
  → Durable Object DeviceChannel (WebSocket autenticado e hibernável)
  → Agent 0.3.44 no nucleo-a (autorização local e executor completo)
  → execução / recibo SHA-256 → Cloudflare D1 → resultado no ChatGPT
```
- O Upgrade WebSocket sem token válido é negado; sem Upgrade, a rota responde 426; com Upgrade e bearer inválido, 401. A fonte do Worker nega acesso não-Founder `DEVICE_EVENT_V2_CANARY_DENIED` (403) após autenticar a máquina. **Prova ao vivo de outro cliente autenticado negado está PENDENTE**, pois o acesso remoto bloqueou a tentativa.
- Os resultados comerciais `ping`, `get_device_info`, `read_file(/etc/os-release)` e `list_processes` retornaram **PASS** com `operational_authority=HARA_COMMANDER`; recibos SHA256 locais foram correlacionados 1:1 aos `HARA-CUSTOMER-MCP-...` de D1 PROD `COMPLETED` (inclusive 3/3 após reinício do serviço v2).
- Em 0.3.41 o campo `operational_authority=HARA_SERVICES` pode aparecer como **rótulo legado do Agent**, não necessariamente como rota administrativa. Em 0.3.44 Event V2 o valor correto é `HARA_COMMANDER`.
- Política: operações do cliente são governadas por tenant, grants, sessão/aprovação local e quota; não ampliar arbitrariamente superfície de comandos nem registrar tokens, argumentos, conteúdo de arquivos ou payloads em telemetria.
- A conta Founder é ilimitada; **seu sucesso não comprova** bloqueio real da franquia Free. `TenantQuota` tem contrato de `reserve/commit/release`, mas o teste externo de último crédito/negativa simultânea e isolamento multi-tenant permanece obrigatório.

## 4. Assinatura de release e rollback
- **v1 pública e estável:** Agent **0.3.41**, manifest assinado com `commander-release-v1` e chave pública pinada nos instaladores Linux/Windows antigos. Instalações existentes **não** podem confiar em v2 automaticamente.
- **v2 separada (Founder Linux):** Agent **0.3.44**, RSA-3072/RS256, `kid=commander-release-v2`, fingerprint público SHA256:
  `93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`.
- A chave **privada v2 existe somente no Services**, sob custódia `~/.config/hara-commander-release/v2/release-signing-private.jwk` (0600). **NUNCA copiar para Núcleo/cliente, GitHub ou logs.** Apenas a pública pode ser distribuída.
- Pacote Founder 0.3.44 isolado no Services: `/tmp_hara/commander-event-v2-0.3.44-founder-signed-v2`; no Núcleo: `~/.local/share/hara-commander/releases/0.3.44-founder-event-v2`. Manifest SHA256 `178795df2b8cf4739d285c50c65370265ef5cceca0e5bfd08271243cb3523a49`. 6 artefatos conferidos; tamper do código/assinatura negado.
- Antes de iniciar v2, `ExecStartPre` verifica public fingerprint, manifest RS256 e 6 hashes: `verify_release_v2.py`. Versão pública v1 não foi sobrescrita.
- Unidade v2: `hara-commander-agent-v2.service` ativa e habilitada; `Conflicts=hara-commander-agent.service`, opt-in explícito e `Linger=yes`. Unidade antiga `hara-commander-agent.service` instalada mas desabilitada.
- Watchdog local: `hara-commander-v2-guard.timer` / `.service`; a cada ~120s, grace 105s, exigência de 2 falhas consecutivas para fallback. Observa systemd, arquivo local e socket TCP `ESTAB`; **não envia polling à Cloudflare**.
- Corrigido falso positivo `EVENT_V2_TCP_CONNECTION_MISSING`: **o serviço do watchdog NÃO deve usar `PrivateTmp=yes`**, pois oculta atribuição PID em `ss -tnp`. Conservou `NoNewPrivileges=yes`; testes e execução posterior deram `HEALTHY`, strikes 0.
- **Rollback manual no próprio Núcleo (somente se necessário, após diagnosticar):**
  `python3 ~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py --rollback`.
  A rotina desativa/para v2, confirma que ele não está ativo, só então habilita/inicia v1 e desarma o timer. Não subir dois Agents com o mesmo device token; não restaurar backup de D1.
- Cold reboot e failover deliberado em PROD **não testados**; não afirmar o contrário.

## 5. Eficiência real Cloudflare — medição auditável, com limites
- API Cloudflare GraphQL read-only; `workersInvocationsAdaptive` por Worker e `httpRequestsAdaptiveGroups` da zona filtrado exatamente em `/api/device/calls/next`, `avg.sampleInterval=1`; D1 PROD `SELECT COUNT(*)` na mesma janela.
- Janelas equivalentes de 40 min, **4 chamadas comerciais em cada**, datas UTC:
  - Antes: 2026-10-10 00:20–01:00Z (09/10 21:20–22:00 BRT): **1.756 polls** de fila, **2.066 Worker requests**, **0 erros**.
  - Depois: 2026-10-10 02:05–02:45Z (09/10 23:05–23:45 BRT): **1.392 polls** de fila, **1.658 Worker requests**, **0 erros**.
  - Diferença observada na frota: **−364 polls (−20,73%)** e **−408 Worker requests (−19,75%)**.
- São **contadores agregados de toda a zona/Worker**, não economia causal isolada por máquina. Número igual de operações não garante perfil idêntico; outro comparativo com 37 vs 4 operações foi descartado como confundido.
- **NÃO** converter isso em redução de fatura: não foram verificados valores da invoice, custo por DO hibernado, métricas de duração do Durable Object ou janela 24h controlada. Protocol PING WebSocket não é o antigo polling ocioso HTTP.
- Reprodutibilidade no Services, com janelas UTC explícitas:
```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
python3 apps/commander/scripts/commander_prod_cf_efficiency_probe.py --check
python3 apps/commander/scripts/commander_prod_cf_efficiency_probe.py \
  --before-start 2026-10-10T00:20:00Z \
  --after-start 2026-10-10T02:05:00Z --minutes 40
```
- Evidência sanitizada: `docs/status/HARA_COMMANDER_CF_EVENT_V2_MATCHED_ACTIVITY_MEASUREMENT_20261009.json`.
- Documento analítico: `docs/operations/HARA_COMMANDER_EVENT_V2_CLOUDFLARE_MEASURED_TRAFFIC_20261009.md`. Probe obtém credencial Wrangler transitoriamente em memória e somente usa consultas de leitura.

## 6. Billing e qualificação comercial
- Preflight `python3 apps/commander/scripts/billing_prod_activation_preflight.py --live` leu secret **names** e catálogo D1 PROD sem mutações; catálogo PASS: TRIAL Free 10.000/mês, Standard Pro ilimitado, SCALE não ativo, Founder ilimitado.
- A rotina foi endurecida para usar Wrangler instalado, retry limitado, `SELECT` remoto e `secret list` somente, sem imprimir segredos; testes de bloqueio de operações inseguras PASS.
- **Faltam Stripe PROD**: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` (e opcional SCALE). `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`; último preflight viu 0 billing connections e 0 eventos webhook.
- Implementação source de checkout/webhook/portal e ponte de entitlement existe, mas **não declarar venda, cobrança ou assinatura ativa** antes de criar o produto/Price ID real, configurar secrets em Cloudflare, verificar webhook Stripe assinado/idempotente e efetuar checkout real autorizado.
- Preço aprovado em documento: R$ 80/mês para Standard; preço efetivamente cobrado depende do Stripe configurado. Vender ou anunciar `SCALE` antes de ativar é proibido.
- Ainda falta canário externo para Free: último crédito aceito, próxima operação `QUOTA_EXCEEDED`, replay idempotente, concorrência, refund em falha, isolamento cross-tenant. Não simular via conta Founder ilimitada.

## 7. Frota e rollout
- Pelo plugin comercial a frota tinha **13 registros**, incluindo máquinas ativas, Windows histórico/revogado e duplicatas históricas. Apareciam online: `services`, `ninja-blue`, `sentinela-a/b/c/d` e `nucleo-a`; somente `nucleo-a` no Event V2. Consultar estado vivo a cada nova sessão; não presumir Sentinela D disponível via conector Remote Desktop só pelo heartbeat comercial.
- Repositório só contém pacote **Founder-only**, com device ID hardcoded e allowlist de Worker para o Núcleo. **NÃO copiar a release Founder para sentinelas ou clientes**. Exigir per-device signing/allowlist, Windows compatível e rollback antes de ampliar.
- O primeiro rollout ocorreu após teste real DEV, assinatura separada v2 e corte humano controlado no Núcleo. O próximo cliente deve receber sua própria identidade, não reutilizar token de máquina existente.
- Não fazer reboot do Núcleo A sem verificar jobs H.A.R.A. ativos e janela de manutenção; existem cargas GPU/ML não relacionadas ao Commander.

## 8. Governança Git — divergência que não pode ser escondida
**Atenção à atualização dos hashes: preencher no novo chat usando `git rev-parse HEAD` e `git ls-remote`.**
- Branch canônica: `local/commander-product-current`. Remote `origin` do worktree aponta ao bare Storage `ssh://storage/srv/hara/archive/github-mirrors/working/hara-site.git`; GitHub real `https://github.com/tiagoharalabs/hara-site.git`.
- Pré-handoff (verificado nesta rodada), **Git local e GitHub = `e764b13e6437a7e210dd45763a7827ad05b653c3`**; **Storage bare = `092f35afc52827d6c5584f0401e9f60eaeb3d985`**.
- Causa: commit `092f35a` no Storage incluiu também alteração de `.github/workflows/hara-commander-scale-v2-validation.yml`, rejeitada pelo GitHub por credencial OAuth sem `workflow` scope. Foi produzido histórico GitHub limpo `225c60e` com os 7 arquivos sem alteração de workflow, depois `e764b13` documentou o incidente. Atualização não-fast-forward do Storage via `--force-with-lease` foi **recusada** pelo receive hook.
- Backup local preservado: `refs/backup/commander-workflow-rejected-20261009` → `092f35a`. **Não** fazer `git push --force`, `git update-ref` diretamente no Storage, contornar o hook, reenviar o commit com workflow pelo token atual ou apagar evidências.
- Publicar alterações futuras por **fast-forward no GitHub**, com readback exato. **Se Storage continuar divergente, reportar explicitamente `STORAGE_RECONCILIATION=HOLD`; não escrever “GitHub/Storage iguais”.** Reconciliação do Storage exige fluxo administrativo aprovado e autorizado, ou estratégia de merge que preserve proteções e não publique alteração de workflow não autorizada. A simples autorização de handoff não revoga as políticas Git.
- Este arquivo é o handoff mais recente e deve ser priorizado sobre as linhas históricas do documento grande `HARA_COMMANDER_PRODUCT_CURRENT_HANDOFF_20261008.md`. O índice raiz `HARA_COMMANDER_CURRENT.md` aponta para esta referência.

## 9. Próximos gates, em ordem de menor risco
1. **P0 Git/continuidade:** verificar GitHub atual, commit publicado do handoff, worktree limpa, registrar Storage HOLD e preparar reconciliação com owner/administrador sem quebrar proteções; não ampliar frente paralela.
2. **P0 Qualificação cliente externo:** testar identidade OAuth/tenant distintos, pairing e negativa cross-tenant em DEV; teste Free real (fim de franquia) e segurança de revogação. Não usar token de dispositivo de outro cliente via comandos improvisados.
3. **P0 Billing Stripe:** criação/configuração oficial de produto e preço em BRL, Worker secrets via canal autorizado e webhook; preflight; checkout pequeno supervisionado com entitlement/replay/cancelamento; evitar cobrar antes de passar.
4. **P1 Operação Event V2:** mais janelas de 1–24h com carga normalizada, coletar DO duration, Worker requests, D1 reads/writes, SLO e reconexões; confirmar custos em fatura/planos Cloudflare. Medir antes de abrir frota.
5. **P1 Cold boot e failover:** teste de reboot do Núcleo **somente em janela de manutenção autorizada**; validar `Linger`, `EVENT_V2`, watchdog e prova comercial pós-boot. Testar fallback real seguro quando puder interromper o canário.
6. **P1 Rollout por máquina:** disponibilizar pacote Linux per-device com assinatura v2 sem compartilhar chave privada; homologar Windows equivalente, considerar canais estáveis de atualização, habilitar 1 dispositivo por vez no Worker e preservar rollback.
7. **P2 CI workflow:** testes `validate_event_v2_persistent_guard.py` e `commander_prod_cf_efficiency_probe.py --check` devem entrar na validação GitHub quando o token tiver escopo `workflow` por via autorizada; não gerar outro commit rejeitado.

## 10. Comandos seguros para o próximo chat
**Services — HEADs exatos e worktree (somente leitura):**
```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
git status -sb
git rev-parse HEAD
git ls-remote --heads origin local/commander-product-current
GIT_TERMINAL_PROMPT=0 git ls-remote --heads https://github.com/tiagoharalabs/hara-site.git local/commander-product-current
```
**Services → Núcleo — saúde (sem mutação):**
```bash
ssh -o BatchMode=yes nucleo-a 'systemctl --user is-active hara-commander-agent-v2.service; systemctl --user is-enabled hara-commander-agent-v2.service; systemctl --user is-active hara-commander-v2-guard.timer; python3 ~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py --check'
```
**PROVA comercial no ChatGPT:** invocar `H.A.R.A. Commander` `ping(computer="nucleo-a")`, `get_device_info(computer="nucleo-a")`, opcionalmente `get_usage_stats()`. Verificar `0.3.44`, `EVENT_V2`, `HARA_COMMANDER`, recibo SHA-256 e D1 `COMPLETED` quando fizer validação E2E. Não substituir por Baseline/admin.
**PROD billing read-only:** `python3 apps/commander/scripts/billing_prod_activation_preflight.py --live`.
**Scripts de regressão:** `validate_event_v2_wiring.py`, `validate_event_v2_persistent_guard.py`, `validate_event_v2_websocket_client.py`, `validate_release_signature.py`, `validate_multitenant_isolation.py`, `commander_prod_cf_efficiency_probe.py --check`.
**Nunca imprimir:** chave RSA privada, `device.env`, bearer de Cloudflare/Stripe/OAuth, token de dispositivo ou arquivos confidenciais.

## 11. Índice de fontes autoritativas
- Atualidade operacional, persistent boot e fallback: `docs/operations/HARA_COMMANDER_EVENT_V2_PERSISTENT_BOOT_GUARD_PROOF_20261009.md`.
- Prova E2E com plugin comercial, recibos, Cloud D1: `docs/operations/HARA_COMMANDER_V2_SIGNED_FOUNDER_CANARY_PROOF_20261009.md`; `docs/operations/HARA_COMMANDER_COMMERCIAL_MCP_REAL_E2E_20261009.md`.
- Medição real e limites da atribuição: `docs/operations/HARA_COMMANDER_EVENT_V2_CLOUDFLARE_MEASURED_TRAFFIC_20261009.md` e `docs/status/HARA_COMMANDER_CF_EVENT_V2_MATCHED_ACTIVITY_MEASUREMENT_20261009.json`.
- Billing: `docs/operations/HARA_COMMANDER_COMMERCIAL_READINESS_GATE_20261009.md`; `docs/operations/HARA_COMMANDER_BILLING_PROD_ACTIVATION_RUNBOOK.md`.
- Assinatura v2, v1 preservada: `docs/operations/HARA_COMMANDER_V2_SIGNED_FOUNDER_CANARY_PROOF_20261009.md`; `docs/operations/HARA_COMMANDER_SIGNING_KEY_ROTATION_AUTHORIZED_20261009.md`.
- WebSocket DEV e quotas: `docs/operations/HARA_COMMANDER_EVENT_V2_HIBERNATION_DEV_PROOF_20261009.md`; `docs/operations/HARA_COMMANDER_CLOUD_DIRECT_QUOTA_TRANSPORT_AUDIT_20261009.md`.
- Pendência Git: `docs/operations/HARA_COMMANDER_PUBLISH_SCOPE_AND_STORAGE_RECONCILIATION_20261009.md`.
- Histórico longo (pode conter estados anteriores já superados): `docs/handoffs/HARA_COMMANDER_PRODUCT_CURRENT_HANDOFF_20261008.md`.

## 12. Texto mínimo de continuidade (colar no próximo chat)
> Retome o H.A.R.A. Commander **somente** pela branch `local/commander-product-current`. Leia primeiro `docs/handoffs/HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md` e `docs/handoffs/HARA_COMMANDER_CURRENT.md`. Núcleo A tem Agent assinado 0.3.44 Event V2 funcionando via MCP comercial, v2 no boot e guard saudável. Cloudflare PROD Worker `215ab34e-...`, allowlist Founder. Métrica auditada 40m / quatro chamadas: polls 1756→1392 (−20,73%); Worker requests 2066→1658 (−19,75%); não é economia de fatura. Free 10k/mês; Pro ilimitado; Stripe checkout PENDENTE. Antes de alterar algo, verificar GitHub/local e divergência Storage (ref 092f35a), não forçar proteções. Priorizar próximos gates P0 (Free/tenant real, billing) e métricas 24h, com GitHub readback após publicação.
