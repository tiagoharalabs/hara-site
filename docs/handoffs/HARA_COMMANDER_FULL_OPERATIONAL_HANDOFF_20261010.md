# H.A.R.A. Commander — handoff operacional completo para a próxima conversa

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
