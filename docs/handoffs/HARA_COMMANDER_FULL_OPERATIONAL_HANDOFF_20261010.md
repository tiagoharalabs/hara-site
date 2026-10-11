# H.A.R.A. Commander — handoff operacional completo para a próxima conversa

## Atualização autoritativa — capacidade, 11/10/2026

Visual de Plano e cobrança aprovado pelo proprietário. Capacidade: auditoria e melhorias publicadas, **sem certificação de 1.000–10.000 clientes simultâneos**. Suíte final **63/63 PASS**; testes de fonte/SQLite com 10.000 contas, 20.000 dispositivos e 210.000 sessões; plano da nova consulta confirmado no D1 DEV real. Limpeza indexada em lotes limitados, observação agregada sem dados de clientes e empacotamento comercial assinado testável.

**PROD `9f7526c5-98a9-415a-b756-25200eee0627`**, 100%, 12/12 assets exatos, saúde/autenticação/assinatura PASS. **DEV `96e67af5-9a67-41f0-8322-763fcd3bb237`**. Rollback íntegro **`b500dd23-c33b-4247-ac3e-04c24c8af15a`**. A candidata `97f050a3-ab1c-4175-94f1-fdd9e4614740` foi revertida por divergência de assets e não deve ser usada como rollback.

**Separar LOCAL_TUNNEL de OUTBOUND_RELAY:** túnel local já desliga polling de fila; a projeção de tráfego elevado é do relay. Telemetria horária não equivale à carga total do túnel. Event V2 Founder não comprova escala de clientes públicos. Sem migração D1, mudança de preços, liberação de Stripe LIVE ou reconfiguração da frota.

Relatório: `docs/operations/HARA_COMMANDER_CAPACITY_1K_10K_20261011.md`. Evidências: `docs/evidence/commander-capacity-20261011/`. Fonte runtime `29067c2`; validação final `b486501`. Publicar assets com `stage_signed_commercial_assets.py` + `wrangler --assets`, nunca com `public/` bruto. Storage segue HOLD.

---


**Corte de evidências:** 10/10/2026, noite, horário de São Paulo (11/10 UTC).
**Owner:** H.A.R.A. Labs. **Frente única:** `local/commander-product-current`.
**Estado dominante:** `PUBLIC_UI_DEPLOYED_VERIFIED` · `PRICING_FULL_FRAME_CENTERING_CLOSED_TECHNICALLY` · `VISUAL_HUMAN_ACCEPTANCE_PENDING` · `STRIPE_LIVE_OFF`.
**Este documento é a porta de entrada para uma nova conversa** e complementa `docs/handoffs/HARA_COMMANDER_CURRENT.md`; fatos anteriores marcados como históricos não sobrescrevem o estado aqui confirmado.

## 1. Última solicitação e conclusão real

A última solicitação do proprietário foi corrigir a tela **Plano e cobrança**, porque os cartões Free e Pro estavam simetricamente alinhados na horizontal, mas o grupo permanecia grudado no topo, com muito espaço vazio abaixo. Foi corrigido o **frame pai**, não apenas o tamanho dos cards.

- O `workspace-main` da rota `plans` agora usa `display:flex`, `flex-direction:column`, `align-items:center`, `justify-content:center` e `min-height:calc(100dvh - 74px)`, fallback de `100vh`.
- **Conjunto inteiro** centralizado como uma unidade: dois cartões Free/Pro, badges de prontidão da cobrança, mensagem de status e botão de gerenciamento quando exibido.
- Largura máxima de **1.080 px**, grid Free/Pro com duas colunas iguais e espaçamento de 18 px. Cards compactos e tipografia legível, paleta Navy/Blue/Gold preservada.
- Abaixo de 1.050 px ou em viewport baixa, o layout volta ao fluxo superior e mantém scroll para não cortar ações. No celular, cartões empilhados.
- Novo cache key `styles.css?v=20261010-centered-plans-vertical1`. **Somente HTML/CSS da interface foram alterados**; nenhum Agent, serviço, key, D1 ou API foi alterado.
- **Evidência técnica fechada:** `test_plan_cards_centered_ui.mjs` cobre centralização vertical/responsiva; gate offline completo **57/57 PASS**; DEV/PROD publicados e readback público **11/11 SHA exatos**, Worker auth/health PASS. **Ainda não há aprovação visual do proprietário após visualizar a versão verticalizada**; não presumir que ele viu o resultado. Próxima conversa deve reconhecer que o código está publicado e, quando pertinente, colher apenas a avaliação visual.

**Fonte de implementação:** `docs/operations/HARA_COMMANDER_PRICING_FULL_FRAME_CENTERING_20261010.md`.

## 2. Verdade atual — repositório, Cloudflare e rollback

| Componente | Verdade confirmada |
| --- | --- |
| Host operacional | `services` via Desktop Commander Remote, ID de conexão **não** necessário no chat |
| Worktree canônico | `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current` |
| Branch | `local/commander-product-current` |
| HEAD-base antes deste handoff | `3d4709cd43f78c38fb53ea42d4cd8f4796e09dcc` |
| GitHub branch | `tiagoharalabs/hara-site`, `local/commander-product-current`; remote SHA exato igual à base no início do handoff |
| Worker PROD | `hara-commander`, **`b500dd23-c33b-4247-ac3e-04c24c8af15a`**, 100% |
| Worker DEV | `hara-commander-dev-v2`, **`39b8e74a-5e5f-40a5-988b-7b0906a59cb0`**, 100% |
| Rollback imediato PROD | **`0fd13813-9c0a-45c1-9102-8ab5db7c3d26`** |
| Portal | `https://commander.haralabs.com.br` |
| Integridade | 11/11 arquivos públicos (index.html, app.js, styles.css, installers, Agents e assinatura) exatos; `/api/health`, `/api/portal/auth-config` HTTP 200 e runtime drift `CURRENT` |
| Quotas reais D1 PROD | `TRIAL`/Free **10.000 chamadas governadas/mês**; `STANDARD`/Pro `unit_limit=NULL` (ilimitado) |
| Pro de catálogo | **R$ 80/mês**, mas checkout automático de produção ainda **desativado** |

**Git/storage:** GitHub online é atualizado pela branch canônica com `git push https://github.com/tiagoharalabs/hara-site.git HEAD:refs/heads/local/commander-product-current` e leitura `git ls-remote`. O remote `origin` aponta ao espelho Git no Storage, que segue sob **HOLD/proteção**; não forçar `push`, `reset`, exclusão de branches nem reconciliar divergências sem governança. Depois de registrar este handoff, usar o novo SHA publicado como checkpoint; o SHA-base acima é apenas a referência imediatamente anterior.

## 3. Decisões de UX que NÃO devem regredir

- Quatro áreas no menu lateral: **Computadores, Uso, Plano e cobrança, Configurações**. **Não repetir** o título da área dentro da própria página. Todas preservam `aria-label`.
- Computadores tem abas **Dispositivos**, **Conectar novo** e **Comandos e integrações**; o topo é compacto, sem título duplicado e sem divisórias internas excessivas. Cores da marca, capivara, tema claro/escuro preservados.
- Em Dispositivos, linhas legíveis e compactas com estado real; `⋯` agora é botão funcional que expande **detalhes inline abaixo da máquina** (não pop-up absoluto). Mostra versão Agent, OS, arquitetura, transporte, última presença, política, autorização por 6 h Linux e revogação com confirmação. Abrir não executa ação remota.
- Conectar novo: **(1) sistema Linux/Windows → (2) token one-time gerado no portal autenticado, válido até 10 min → (3) comando de download/instalação assinado por HTTPS e prompt de pareamento no terminal**. Nunca imprimir token na linha de comando ou no chat.
- Comandos e integrações: card externo único, cards internos simétricos **Linux/Windows** e **MCP** na largura total. Botões Copiar com comandos reais, fontes amplas, sem título repetido e sem caixas/linhas internas desnecessárias. Linux: `hara-commander start|status|stop|doctor|mcp`; Windows: `start|status|stop` via script PowerShell instalado; MCP local STDIO é Linux; clientes compatíveis usam MCP remoto com OAuth.
- Sincronização de presença é automática enquanto o Agent está conectado; **não existe `hara-commander sync`**.
- Free 10.000 chamadas/mês, **não 15.000 e não 100.000**. Pro R$ 80/mês sem cobrança live. Mudanças anteriores de limite foram encerradas pela migração canônica `0032_free_10000_revert_20261010.sql`.

**Documentação UI:** `docs/operations/HARA_COMMANDER_DEVICE_DETAILS_MENU_FIX_20261010.md`, `HARA_COMMANDER_PORTAL_NAVIGATION_NO_DUPLICATE_20261010.md`, `HARA_COMMANDER_CUSTOMER_INSTALL_GUIDE_UX_20261010.md`, `HARA_COMMANDER_PLAN_CARDS_CENTERED_20261010.md`.

## 4. Distribuição comercial e cautelas da frota

- Installer comercial público **0.3.43**, tag imutável `hara-commander-commercial-v0.3.43-signed-v2`, pacote `apps/commander/release-bundles/commercial-0.3.43-v2/`. Assinatura **RS256/RSA-3072** e `kid=commander-release-v2`; a chave privada não está no Git e não deve ser copiada para o chat.
- Novas instalações: iniciam uma vez para comprovar o pareamento, mas **não habilitam autostart** futuro. No Linux, próximos usos requerem `hara-commander start`, `stop` para encerrar; configuração de persistência é manual para técnicos. Políticas sensíveis seguem `ASK_EVERY_ACTION`. Direct/lease de 6 h é opcional.
- **Founder interno permanece separado e mais novo**, com Event V2 assinado / Agent 0.3.44. **Nunca reinstalar o pacote público 0.3.43 por cima da frota Founder 0.3.44** e nunca alterar serviços/timers Founder em uma frente de UI.
- Windows comercial ainda **beta**, sobretudo ações sensíveis/PowerShell real; não anunciar paridade Linux total até homologação.
- A versão anterior v0.3.41 continua em tag `hara-commander-signed-agent-v0.3.41` como recuperação, mas não deve ser misturada com a assinatura v2 atual.

## 5. Estado de conectividade — distinguir caminhos

**H.A.R.A. Commander comercial / produto:** chamada de leitura `list_devices` nesta retomada mostrou **13 registros** (5 `ONLINE`, 3 `OFFLINE`, 5 `REVOKED`) incluindo históricos Windows e uma Sentinela D revogada antiga. A listagem veio com `operational_authority=HARA_SERVICES` e `runtime_authority_from_chatgpt=false`; **é inventário, não uma prova isolada de sessão operacional end-to-end**, e alguns estados ONLINE podem ter `last_seen` antigo. Não exibir IDs internos ou tokens ao cliente.

**Pings pela ferramenta H_A_R_A__Commander:** `nucleo-a` e `sentinela-c` retornaram `PASS`, `operational_authority=HARA_COMMANDER`, `execution_authority=HARA_COMMANDER_AGENT`, Agent **0.3.44**, com recibos. O campo `runtime_authority_from_chatgpt=false` exige **não exagerar** sobre end-to-end da instância comercial no cliente. Se preciso, provar novamente o caminho autorizado OpenAI/ChatGPT → Secure MCP Tunnel → MCP instanciado pelo cliente → Agent, sem confundir com infraestrutura.

**Desktop Commander Remote (ferramenta administrativa distinta):** services, nucleo-a e sentinela-c estavam online; sentinela-d offline pela presença desse **outro serviço**. Isso não contradiz a conectividade informada pelo Commander comercial; são túneis e registros diferentes.

## 6. Financeiro/Stripe — pendências reais

- Preflight read-only de PROD: `TRIAL_CURRENT_PROD_UNITS=10000`, `TRIAL_LIVE_ALIGNED=TRUE`, `STANDARD_LIVE_UNLIMITED=TRUE`, `STANDARD_CATALOG_ACTIVE=TRUE`, mas `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`; **zero ligações de cobrança e zero webhooks observados**. Os segredos de checkout Stripe PROD ainda estão **PENDING**.
- Wizard TEST-only pronto: `apps/commander/scripts/stripe_test_activation_wizard.py`; runbook `docs/operations/HARA_COMMANDER_STRIPE_TEST_ONE_COMMAND_ACTIVATION_20261010.md`. Precisa de **chave `sk_test_` digitada privadamente pelo proprietário em terminal interativo**, nunca em chat/argumento CLI. O wizard atua somente no Cloudflare DEV.
- Depois do wizard, ainda falta provar Checkout TEST hospedado, webhook assinado, deduplicação, atualização da assinatura/entitlement, suspensão/recuperação/cancelamento e Portal do cliente; depois aprovação humana específica para qualquer ativação LIVE.
- **Não iniciar Stripe PROD, cobrar cartão ou afirmar assinatura paga funcionando.** Gate separado da UI.
- Outras pendências comerciais: autenticação e fluxo real do cliente Windows, soak multi-tenant, testes de estresse de produto e revisão/listagem pública do Plugin no diretório OpenAI. Installer público e Plugin público são coisas diferentes.

## 7. Próxima conversa — sequência sem retrabalho

1. **Começar lendo este handoff e `docs/handoffs/HARA_COMMANDER_CURRENT.md`.** Conferir o HEAD/branch e o Worker PROD antes de qualquer edição. Não retomar o diagnóstico anterior como se a centralização estivesse pendente.
2. **Validação visual do cliente:** abrir `https://commander.haralabs.com.br/#plans`, atualizar sem cache (`Ctrl + Shift + R`) e verificar se Free/Pro + badges/status agora estão no **centro horizontal e vertical** da área útil. A implantação técnica está PASS; aprovação estética do proprietário permanece aberta. Se houver ajuste, tocar **só** a rota de planos.
3. Depois da aceitação visual, congelar esse baseline e priorizar gates de lançamento: Stripe TEST E2E, Windows real, cadeia comercial MCP ponta a ponta, teste de estresse/soak e cadastro/listagem do Plugin, conforme autorização do proprietário.
4. Rotinas read-only (no Services, em diretório canônico):
   ```bash
   git status --short && git rev-parse HEAD
   node apps/commander/scripts/test_plan_cards_centered_ui.mjs
   python3 -B apps/commander/scripts/commander_prod_deployment_readback.py --expect-version b500dd23-c33b-4247-ac3e-04c24c8af15a
   python3 -B apps/commander/scripts/validate_signed_commercial_v2_bundle.py --live
   python3 -B apps/commander/scripts/validate_prod_runtime_drift.py --expect-assets current
   python3 -B apps/commander/scripts/billing_prod_activation_preflight.py --live
   ```
5. **Se for publicar mais UI:** seguir DEV → gate de testes → confirmação da assinatura 0.3.43 intacta → Worker version upload PROD → confirmar nomes de secrets → deploy 100% com rollback → 11/11 SHA, `/api/health`, `/api/portal/auth-config`, D1 quota 10.000 → commit/push GitHub com `GITHUB_EXACT_READBACK=PASS`. Sem push forçado ao Storage.

## 8. Mensagem de retomada pronta para colar

> Continuar o H.A.R.A. Commander pelo documento `docs/handoffs/HARA_COMMANDER_FULL_OPERATIONAL_HANDOFF_20261010.md` no GitHub `tiagoharalabs/hara-site`, branch `local/commander-product-current`. O portal PROD está em `b500dd23-c33b-4247-ac3e-04c24c8af15a`, com a centralização total dos cards Free e Pro publicada e readback PASS; falta apenas eu validar visualmente a estética. Não repetir a implementação nem alterar Agents/Stripe sem autorização. Preservar Free 10.000/mês, Pro R$ 80, a frota Founder 0.3.44, os instaladores comerciais assinados 0.3.43 e o rollback. Ler o handoff completo e informar o próximo gate objetivo antes de executar.

---

**Regra de verdade:** separar sempre *código escrito*, *GitHub sincronizado*, *Worker efetivamente promovido*, *readback público comprovado* e *aceitação visual humana*. Não afirmar sucesso de uma etapa com evidência de outra.

## 9. Verificação visual adicional — 11/10/2026, manhã BRT

Após a retomada, confirmei novamente por leitura remota que a branch canônica e o GitHub estão no HEAD `3256f3dba2f1ad9382af55adc0f43b27dc4e6e68`, árvore limpa, Worker PROD `b500dd23-c33b-4247-ac3e-04c24c8af15a` em 100%, `commander_prod_deployment_readback.py` PASS e `validate_prod_runtime_drift.py --expect-assets current` PASS. Não foi necessário novo deploy ou alteração nos Agents.

Realizei inspeção visual técnica adicional com **Firefox headless no Núcleo A**, usando o HTML e o CSS baixados diretamente do domínio público (sem sessão autenticada nem dados de cliente). Visual de referência escuro foi reproduzido isoladamente com uma topbar/sidebar de teste e o trecho real da página de planos, nas resoluções **1710×960 (desktop)** e **420×880 (móvel)**. No desktop, Free e Pro ficaram alinhados em colunas iguais e o conjunto Free/Pro + badges + status ocupou o centro horizontal e vertical da área útil, sem o grande vazio inferior da versão antiga. Na visualização estreita, os cards ficaram empilhados e o conteúdo continuou acessível por scroll, sem corte de controles ou transbordamento horizontal observável. Esta é uma **QA visual reproduzida**, e não equivale a captura da sessão autenticada do proprietário nem à sua aprovação estética humana. As imagens temporárias ficam apenas no diretório de QA local do Núcleo A (`/tmp/hara-commander-pricing-visual-qa/`), não estão no Git.

**Estado pós-verificação:** `VISUAL_QA_DESKTOP_AND_MOBILE=PASS`; `PUBLIC_DEPLOYMENT_UNCHANGED`; `HUMAN_VISUAL_ACCEPTANCE=PENDING`. Próximo passo opcional: colher a percepção visual do proprietário na página já publicada; não reimplementar a centralização sem nova observação concreta.
