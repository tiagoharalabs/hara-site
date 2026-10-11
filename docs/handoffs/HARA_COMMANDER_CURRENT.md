# H.A.R.A. Commander — CURRENT (10/10/2026, após rollout 7/7)

## CI hospedado e custo de referência (11/10/2026)

OpenAI review ZIP 0.2.0 validado; CI hospedado GitHub Actions run 38173368104 PASS no commit a4b0cca (79 suites offline). Auditoria read-only Cloudflare na janela 19:28-20:28 UTC observou subtotal variável de referência US$ 0.0033500826176; NÂO fatura, sem franquias nem mensalidade, sem capacidade 1k comprovada. Stripe produção ainda pendente de três configurações secretas, necessitando chave sk_test no wizard TEST em Services. Provas sanitizadas em docs/evidence/commander-golive-20261011/.

## Pacote OpenAI atualizado, gate 79/79 (11/10/2026)

Plugin submission ZIP 0.2.0 sob apps/commander/plugin-submission, com notas de release e dados técnicos compatíveis com 33 ferramentas. Validação offline de pacote PASS; gate ampliado 79/79 PASS no Services. Continua DRAFT não submetido, sem demo vídeo/credenciais de revisor/verificação empresarial. Evidências em docs/evidence/commander-golive-20261011/acceptance.json.

## Fechamento Founder 7/7 e entrada comercial (11/10/2026)

Sete Linux Founder online no Agent Event V2 0.3.45 via readback MCP comercial, com contratos/autorização preservados e pacote antigo de rollback por máquina. Provas comerciais Founder: write/edit com hash esperado, hash obsoleto negado, leitura, execução e REPL interativa, recibos do Agent. Novo smoke HTTP DEV 1.000 GET de health/50 concorrentes máximo, 0 erro (NAO representa 1.000 clientes OAuth/Agents). Validação de escopo/ZIP OpenAI 33 tools, 5 positivos/3 negativos: SOURCE_PACKAGE_PASS, nao submissão. Billing PROD catálogo STANDARD BRL80/mes e TRIAL 10k, mas tres segredos Stripe PENDING e zero eventos. Gate local 79/79 PASS, CI hospedado aguardando readback. Referência: docs/operations/HARA_COMMANDER_GO_LIVE_READINESS_20261011.md e docs/evidence/commander-golive-20261011/acceptance.json.


## Atualização efetiva da telemetria Event V2 — 11/10/2026

Runtime 93ebcf0 publicado em DEV/PROD com D1 0034, Workers DEV 15801b6f-6ec2-40e9-8508-2f1d578824df e PROD 3b926608-cff0-4dfb-947f-6ff3099cbe3f, ambos 100%; health/auth PASS. O Agent Founder 0.3.45 (RS256, sete arquivos) está instalado/ativo no services, com persistência local SQLite 0600 comprovada por reinício controlado; outros seis Founders permanecem 0.3.44, pacotes não instalados. LIVENESS cloud ~6h sem requisições HTTP adicionais; snapshots D1 ainda vazios no readback, e não significa falha antes do primeiro checkpoint. Gate local 77/77 PASS; GitHub Actions hospedado PASS no commit 1aec24c, run 38171345712, depois de corrigir limpeza do wrapper Linux no uninstall. Referência: docs/operations/HARA_COMMANDER_EVENT_V2_LOCAL_TELEMETRY_LOW_CHATTER_20261011.md.


## Event V2 telemetria local e menos leituras — 11/10/2026

O Agent candidato grava métricas agregadas em SQLite 0600 por sete dias, com flush em lotes e resumo piggyback no LIVENESS Event V2 existente (~6h com jitter). Sem novos POST/polling de telemetria. D1 salva último resumo por tenant/dispositivo com migração 0034, schema estrito e socket autenticado. MCP adiciona get_device_telemetry (perfil 33 ferramentas). Polling de chamadas adaptativo: modelo 45s 180 para 36 consultas, não medição cloud. Gate offline 77/77 PASS; assinatura Founder 0.3.45 (sete arquivos) verificada, canário Services preparado. Não inferir instalação do Agent nem registro de snapshot D1 antes do canário. Referência: docs/operations/HARA_COMMANDER_EVENT_V2_LOCAL_TELEMETRY_LOW_CHATTER_20261011.md.


## PROD administrativo oficial — 11/10/2026

Código funcional implantado: commit `605ffdad230e34c0f5acc09dd3bcc361a1c11618`. Perfil MCP simples: **32 ferramentas**, incluindo novas primitivas READ_ONLY de uptime, recursos, workspace, SHA-256 e diff; processos, sessões, arquivos, rollback, atividade e recibos continuam disponíveis e governados. Gate local **73/73 PASS**.

Cloudflare DEV: Worker `3ff8b6b0-28f0-4cbc-b8be-2f571bbdaf63` 100%, migração aditiva `0033_portal_read_indexes_20261011.sql` aplicada, health/auth HTTP 200. PROD: Worker `ecbd82d8-6780-4605-8eed-17d844ab3415` 100%, a mesma migração aplicada, health/auth PASS. Assets comerciais assinados 0.3.43-v2 preservados no stage; sem alteração de preços ou agentes assinados.

Frota Founder Linux após PROD e reconciliação por resultados canônicos do Agent: **7/7 ONLINE, Agent 0.3.44** (`nucleo-a`, `sentinela-a/b/c/d`, `ninja-blue`, `services`). Núcleo teve o Agent V2/guard reabilitados; v1 permanece disabled. Sentinela A recebeu wake pela rotina canônica e retornou; Ninja retornou e respondeu pelo produto embora não conste no wake-map canônico. Registros Windows legados permanecem offline/revogados e não integram esta homologação.

O conector já aberto nesta conversa pode manter o schema antigo de ferramentas em cache; novas sessões/conexões devem descobrir as 32 ferramentas do Worker publicado.


## Perfil administrativo ampliado — 11/10/2026

O perfil MCP simples passa de 27 para **32 ferramentas**, adicionando uptime, recursos, inspeção de workspace, hash e diff como primitivas READ_ONLY. Processos e mutações de arquivo já existiam e permanecem governados. Gate local **73/73 PASS**. Documento: `docs/operations/HARA_COMMANDER_ADMIN_PROFILE_20261011.md`.


## Regressão unificada — 11/10/2026; publicação pendente

Worker REAL corrigido: hash esperado e paginação preservados; teste padrão **38/38 PASS**, gate **72/72 PASS**. Candidatas em memória e bloqueios do patch citados abaixo são históricos. Não inferir deploy do commit. Referência: `docs/operations/HARA_COMMANDER_RELEASE_VALIDATION_20261011.md`.


## Consistência dos resultados MCP — 11/10/2026; fonte local, sem deploy

O perfil simples passou a sinalizar erros operacionais com `isError: true`, distinguir timeout de não execução, orientar reconciliação em vez de repetição automática, restringir mensagens públicas de exceção a códigos simbólicos e separar trecho de edição ausente de arquivo ausente. Teste novo contra o handler MCP real, executor simulado no Services: **38/38 PASS**; suíte anterior do perfil simples também PASS. Não confundir este teste com os 38 casos da cadeia de argumentos abaixo. A bateria geral não foi reexecutada e o Worker não foi alterado. Contrato de timeout com valores nulos exige homologação do cliente antes de promoção. Documento: `docs/operations/HARA_COMMANDER_MCP_RESULT_CONSISTENCY_20261011.md`.


## Revisão local de contratos — 11/10/2026; NÃO é novo deploy

A fonte local contém as melhorias de leitura do checkpoint `aa4a90b` e correções posteriores de concorrência da atividade, verificadas no Services contra o arquivo integral: **25/25 PASS**. O novo teste `test_customer_argument_pipeline.mjs` detectou perda de `expected_sha256` em escrita/edição/exclusão e de `offset` em busca/listagem no adaptador do Worker: **fonte atual 16/38 PASS; candidata apenas em memória 38/38 PASS**. **O patch desse Worker não foi aplicado**, pois a tentativa de gravação foi bloqueada. O modo candidato não substitui a aprovação do código do produto.

Não houve deploy, migração, coleta nova de custos, atualização de agentes nem comprovação de escala nesta revisão. A bateria geral anterior de 68 validadores não foi reexecutada. Leituras históricas de Cloudflare abaixo continuam históricas; não promovê-las a verificação desta rodada. Referências: `docs/operations/HARA_COMMANDER_ARGUMENT_PIPELINE_REVIEW_20261011.md` e `docs/operations/HARA_COMMANDER_ACTIVITY_SESSION_CONCURRENCY_20261011.md`.


## Atualização autoritativa — capacidade, 11/10/2026

Visual de Plano e cobrança aprovado pelo proprietário. Capacidade: auditoria e melhorias publicadas, **sem certificação de 1.000–10.000 clientes simultâneos**. Suíte final **63/63 PASS**; testes de fonte/SQLite com 10.000 contas, 20.000 dispositivos e 210.000 sessões; plano da nova consulta confirmado no D1 DEV real. Limpeza indexada em lotes limitados, observação agregada sem dados de clientes e empacotamento comercial assinado testável.

**PROD `9f7526c5-98a9-415a-b756-25200eee0627`**, 100%, 12/12 assets exatos, saúde/autenticação/assinatura PASS. **DEV `96e67af5-9a67-41f0-8322-763fcd3bb237`**. Rollback íntegro **`b500dd23-c33b-4247-ac3e-04c24c8af15a`**. A candidata `97f050a3-ab1c-4175-94f1-fdd9e4614740` foi revertida por divergência de assets e não deve ser usada como rollback.

**Separar LOCAL_TUNNEL de OUTBOUND_RELAY:** túnel local já desliga polling de fila; a projeção de tráfego elevado é do relay. Telemetria horária não equivale à carga total do túnel. Event V2 Founder não comprova escala de clientes públicos. Sem migração D1, mudança de preços, liberação de Stripe LIVE ou reconfiguração da frota.

Relatório: `docs/operations/HARA_COMMANDER_CAPACITY_1K_10K_20261011.md`. Evidências: `docs/evidence/commander-capacity-20261011/`. Fonte runtime `29067c2`; validação final `b486501`. Publicar assets com `stage_signed_commercial_assets.py` + `wrangler --assets`, nunca com `public/` bruto. Storage segue HOLD.

---


**HANDOFF PARA A PRÓXIMA CONVERSA — LEITURA OBRIGATÓRIA:** `docs/handoffs/HARA_COMMANDER_FULL_OPERATIONAL_HANDOFF_20261010.md`. Estado técnico comprovado: PROD `b500dd23-c33b-4247-ac3e-04c24c8af15a` 100%, DEV `39b8e74a-5e5f-40a5-988b-7b0906a59cb0`, centralização horizontal+vertical dos cartões Free/Pro encerrada no código e publicada. **Não confundir implantação com aceitação visual humana: falta verificação estética do proprietário na tela atualizada.** Free 10.000/mês, Pro R$ 80/mês (Stripe checkout LIVE OFF); 57/57 testes offline e 11/11 readback público PASS. O novo handoff reúne as decisões de UX, Fleet Founder 0.3.44 versus instaladores comerciais 0.3.43, limites de autoridade dos conectores, gates Stripe/Windows/Plugin e próximos comandos. Esta linha prevalece sobre as entradas históricas abaixo.


**PROD ATUAL — PLANO E COBRANÇA CENTRALIZADO VERTICALMENTE, 10/10/2026:** Worker Cloudflare `hara-commander` versão **`b500dd23-c33b-4247-ac3e-04c24c8af15a` em 100%**, rollback `0fd13813-9c0a-45c1-9102-8ab5db7c3d26`. A grade Free/Pro já era centralizada na horizontal; agora o `workspace-main` alinha e centraliza verticalmente **o conjunto inteiro** (cards, readiness, status e gerenciamento), com min-height relativo à área abaixo da topbar. Em telas baixas ou estreitas, rolagem normal preservada. DEV `39b8e74a-5e5f-40a5-988b-7b0906a59cb0`, DEV/PROD 11/11 assets SHA exatos, health/auth PASS, cache HTML e CSS convergidos; D1 Free 10.000 e Pro ilimitado, teste offline 57/57 PASS. Nenhuma mudança em API, Agent assinado, Founder, billing, Stripe ou autenticação. Handoff: `docs/operations/HARA_COMMANDER_PRICING_FULL_FRAME_CENTERING_20261010.md`.


**HISTÓRICO — CARDS COMPACTOS ANTES DO ALINHAMENTO VERTICAL DO CONJUNTO:** Worker Cloudflare `hara-commander` versão **`0fd13813-9c0a-45c1-9102-8ab5db7c3d26` 100%**, rollback `f16f8458-d595-4904-87d6-b9ff31bf5a58`. Tela Plano e cobrança: Free/Pro juntos com máximo de 1.080px, colunas simétricas centradas, padding reduzido e responsivo (1 coluna até 1050px). Os outros menus continuam sem headings repetidos; cores H.A.R.A., preço R$80 Pro, Free 10.000/mês e CTA beta preservados. DEV `4219f824-659f-4780-98e7-b85b39c0c980`; DEV/PROD 11/11 arquivos SHA exato e health/auth PASS, `/` e `/index.html` convergidos, D1 Free=10.000, Pro ilimitado. Gate offline **57/57 PASS**. Somente CSS e sua cache key HTML; nenhum Agent, instalador assinado, Worker API, Stripe, serviço Founder, OAuth ou D1 alterado. Documentação: `docs/operations/HARA_COMMANDER_PLAN_CARDS_CENTERED_20261010.md`.


**HISTÓRICO — MENU SEM TÍTULOS REPETIDOS, ANTES DOS CARDS COMPACTOS:** Cloudflare Worker `hara-commander` versão **`f16f8458-d595-4904-87d6-b9ff31bf5a58` em 100%**, rollback imediato **`48c04065-7de8-41f7-8e3e-48c289bcaa5b`**. Menu lateral continua com Computadores, Uso, Plano e cobrança e Configurações; nenhuma dessas rotas repete seu nome como heading na área central. Todas usam `aria-label` acessível. Conteúdo útil sobe para o topo; cartões Free/Pro usam largura total. Textos de Comandos e integrações e Conectar novo ficaram curtos e sem os antigos limites de 920/1000 px; desktop ampla largura mantém uma linha, telas menores quebram naturalmente. DEV `d42f7f55-490d-4bab-8959-23c499b96b33`, PROD e DEV **11/11 assets SHA exato**, rotas `/` e `/index.html` conferidas, health/auth PASS. D1 Free 10.000 chamadas/mês, Pro ilimitado. Gate offline **56/56 PASS**, incluindo teste novo das quatro abas. Nenhum Agent, pacote comercial 0.3.43, MCP, token, serviço Founder ou cobrança alterado. Documento: `docs/operations/HARA_COMMANDER_PORTAL_NAVIGATION_NO_DUPLICATE_20261010.md`.


**HISTÓRICO — correção dos três pontinhos na versão anterior:** Worker `hara-commander` versão `48c04065-7de8-41f7-8e3e-48c289bcaa5b` 100%; rollback `66958dc2-2951-423d-9699-6396e78d2890`. Menu ⋯ agora abre painel inline com detalhes e ações secundárias, sem executar comando só de abrir; botão acessível com `aria-expanded`. Removido título repetido Comandos e integrações dentro da aba. DEV `b9ecf6c0-dd0d-4020-83ef-0746db2eadc7`. SHA público 11/11 PASS, health/auth PASS, Free 10.000 e Pro ilimitado, pings comerciais Services/Núcleo A/Sentinela C/D Agent 0.3.44 PASS. Gate 55/55 PASS, sem mudanças nos Agents ou serviços. Relatório `docs/operations/HARA_COMMANDER_DEVICE_DETAILS_MENU_FIX_20261010.md`.


**HISTÓRICO — COMPUTADORES SEM TÍTULO DUPLICADO E SEM DIVISÓRIAS INTERNAS, antes do conserto dos três pontinhos:** Worker Cloudflare `hara-commander` versão **`66958dc2-2951-423d-9699-6396e78d2890` a 100%**; rollback imediato `4946ed70-bbf0-4605-98a8-063d0af0a8cb`. Removido o `<h1>` redundante no conteúdo, mantendo `aria-label="Computadores"` para acessibilidade; abas subiram. Dispositivos, Conectar novo e Comandos e integrações têm fontes maiores, linhas internas removidas e espaçamento reduzido; bordas externas, cores H.A.R.A., cards e ações preservadas. DEV `e27c8338-b45e-484f-a0b5-5b82705deaad`. DEV/PROD com readback **11/11 SHA** e health PASS; `/` e `/index.html` atualizados, auth PASS; MCP comercial Núcleo A/Sentinela D Agent 0.3.44 PASS. Free=10.000/mês, Pro ilimitado, testes offline **55/55 PASS**. Somente HTML/CSS modificados, sem tocar no Agent/instalador assinado, frota, Worker API, billing ou D1. Documento: `docs/operations/HARA_COMMANDER_DEVICES_COMPACT_BORDERLESS_20261010.md`.


**HISTÓRICO — ESTADO ANTERIOR DA MOLDURA DE COMANDOS, JÁ SUBSTITUÍDO:** Cloudflare Worker `hara-commander` versão **`4946ed70-bbf0-4605-98a8-063d0af0a8cb` a 100%**. Aba Comandos e integrações sem etiqueta REFERÊNCIA RÁPIDA, com uma caixa externa envolvente de largura total e cards simétricos internos Linux, Windows e MCP, preservando a paleta, os comandos e as fontes ampliadas. DEV `7438d28f-266f-46c4-9063-8bb00f2c7eb3`. SHA público 11/11 PASS, `/` e `/index.html` convergidos, health/auth PASS, regressão 55/55 PASS. Rollback PROD imediato `d305c678-7715-4594-b8b9-f1e697112702`. Somente index.html/styles.css publicados; nenhuma mutação D1, Agent, MCP, billing, serviço Founder ou pacote assinado. Ver `docs/operations/HARA_COMMANDER_DEVICES_SYMMETRIC_LAYOUT_20261010.md`.


**HISTÓRICO — etapa anterior de simetria, posteriormente refinada com caixa externa:** Worker `hara-commander` versão **`d305c678-7715-4594-b8b9-f1e697112702`**, 100%. Título Computadores compacto/alto, sem subtítulo; fontes maiores, cards Linux/Windows iguais ocupando toda a largura útil, MCP em largura total, comandos em linhas sem bordas internas. Identidade Navy/Blue/Gold e controles preservados. DEV `d122db6f-7ef4-410a-9656-d50c615d0a07`. DEV e PROD com SHA exato **11/11 assets**, health/auth PASS e `/`/`index.html` atualizados; D1 Free 10.000 e Pro ilimitado, pings comerciais Núcleo A e Sentinela D Agent 0.3.44 PASS. Rollback Worker anterior **`9943523c-a573-40bc-bc86-2f45b2156643`**. Documento de implementação: `docs/operations/HARA_COMMANDER_DEVICES_SYMMETRIC_LAYOUT_20261010.md`. Gate offline 55/55 PASS; nenhum Agent, instalador assinado, segredo, billing ou serviço Founder alterado.

**HISTÓRICO — UX GUIADA PUBLICADA ANTES DO REFINAMENTO ATUAL:** Worker Cloudflare `hara-commander` versão `9943523c-a573-40bc-bc86-2f45b2156643` **100%**, com três abas em Computadores (Dispositivos / Conectar novo / Comandos e integrações). Instalação via token one-time gerado no portal, instalador assinado Linux/Windows e comandos copiáveis. DEV versão `b160e263-fab5-4918-9d11-0ae128e413b4`. Readbacks independentes: Worker, health, auth e assets atuais PASS, **11/11 SHA**; Free 10.000, Pro ilimitado e pings do MCP comercial para Núcleo A e Sentinela D Agent 0.3.44 PASS. Rollback Worker anterior `228fdb6d-fbde-4a1c-91b0-57ac73f5d193`; não houve mudança em D1, Agent ou assinatura. Fonte/execução: `docs/operations/HARA_COMMANDER_CUSTOMER_INSTALL_GUIDE_UX_20261010.md`. Gate offline **55/55 PASS**. Windows ainda beta para operações sensíveis.

**HISTÓRICO — refinamento da lista:** Worker `228fdb6d-fbde-4a1c-91b0-57ac73f5d193` introduziu a lista minimalista com as cores preservadas. Essa versão foi o rollback da publicação guiada anterior; atualmente o rollback imediato é o Worker informado no topo deste handoff. Ver `docs/operations/HARA_COMMANDER_DEVICES_MINIMALIST_UI_20261010.md`. **Sem alteração de D1, quotas, autenticação ou Agents.**

**DECISÃO MAIS RECENTE DE PREÇO/QUOTA — FREE=10.000 chamadas governadas/mês.** O dono revogou a autorização temporária de 15.000. D1 DEV e PROD estão em 10.000 via migração `0032_free_10000_revert_20261010.sql`. Pro permanece ilimitado. A versão **histórica do deploy da quota** foi `43421f6f-5bee-4fe6-9bc4-982a3e10d019`, com readback de 10/10 assets assinados e portal JS/HTML 10.000 PASS; o **Worker atual é o informado no topo deste handoff**, sem alteração do limite. O conteúdo histórico abaixo sobre 15.000 está SUPERADO. Ver `docs/operations/HARA_COMMANDER_FREE_10K_REVERSION_20261010.md`.

**Antes de qualquer mutação ou decisão: ler primeiro**
`docs/handoffs/HARA_COMMANDER_FLEET_EVENT_V2_HANDOFF_20261010.md`.
**Para billing/Stripe:** `docs/operations/HARA_COMMANDER_STRIPE_TEST_ONE_COMMAND_ACTIVATION_20261010.md`.

**Única branch autoritativa de produto:** `local/commander-product-current`.
Worktree Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`.
Repo GitHub: `tiagoharalabs/hara-site`.

## Estado atual comprovado
- **Frota Linux Founder 7/7** em Agent **0.3.44 assinado per-device** e **EVENT_V2 WebSocket**, com `H_A_R_A__Commander.get_device_info` e `ping` comerciais PASS: `nucleo-a`, `sentinela-a`, `sentinela-b`, `sentinela-c`, `sentinela-d`, `ninja-blue`, `services`.
- V2 `active+enabled`, v1 0.3.41 `inactive+disabled` mas preservada para rollback; watchdog/timer ativo em todos. Nenhum reboot nem failover forçado foi realizado. Windows permanece offline/revogado/não homologado em Event V2.
- Worker PROD Cloudflare `hara-commander` versão `29e556f3-86af-476d-ba01-a764c3acb6a0` (100%) no último readback. Allowlist original Núcleo mais seis Founder configurados em **secret** `DEVICE_EVENT_V2_ADDITIONAL_DEVICE_IDS`; sem wildcard, sem liberar outros tenants.
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` ainda PENDING em PROD. **Checkout pago NÃO ATIVO.** Catálogo Free = 15.000 chamadas governadas/mês (migração PROD 0031 confirmada em 10/10); Standard Pro = R$80/mês (ilimitado no catálogo), não comprovadamente faturado.
- **Stripe TEST automation preparada:** `stripe_test_activation_wizard.py --check/--apply` (a segunda exige chave `sk_test_` introduzida privadamente no Services). Cria/reutiliza produto/Price BRL80, webhook assinado, Portal e configura quatro DEV Worker secrets; o assistente não recebeu/instalou nenhuma chave Stripe. Teste integrado SQLite e teste offline do wizard PASS. **Worker DEV publicado** na versão `490c38bf-5ef0-4b55-a33a-2dc6d0c6ad6c` 100%, DEV health 200, sem segredos Stripe; PROD mantido na versão anterior. Restam test Checkout real e live rollout governado.
- **Correção SSH Stripe 10/10:** erro `CLOUDFLARE_DEV_SECRET_LIST_UNAVAILABLE` foi causado por Wrangler sem Node no PATH em SSH non-login (`/usr/bin/env: node: No such file or directory`). O wizard agora resolve Node instalado via NVM sem carregar perfis nem tocar no PATH global. `--check` validado com SSH normal e `ssh -tt` Núcleo→Services e com PATH limitado, sem chaves, pagamentos ou alterações de Cloudflare. O operador, já em Services, deve executar o `--apply` manualmente e digitar `sk_test_` apenas no terminal.
- Métrica anterior Cloudflare de canário Núcleo −20,7% polling, −19,7% requisições Worker entre duas janelas equivalentes; **não transferir esse percentual à frota 7/7 nem à economia de fatura sem nova medição**.
- **Storage diverge de GitHub/local**: `092f35afc52827d6c5584f0401e9f60eaeb3d985`; `STORAGE_RECONCILIATION=HOLD`. Não forçar refs ou burlar hooks.
- O handoff anterior `HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md` e o arquivo de preparação `HARA_COMMANDER_EVENT_V2_FOUNDER_FLEET_STAGE_20261010.md` são **históricos**, não a verdade atual de deploy.

**Nova auditoria de produto e stress em 10/10:** ler também `docs/operations/HARA_COMMANDER_PRELAUNCH_SECURITY_STRESS_AUDIT_20261010.md`. As **31 funções do Agent são suficientes como primitivas do MVP**, mas o perfil simples ChatGPT tinha 24 métodos; **27 métodos estão preparados somente em código-fonte candidato** (inclui preimages, rollback e recibos), sem deploy público. A suíte offline de pré-lançamento **47/47 PASS** executou até **1.000 tentativas concorrentes / 24 threads** por cenário contra SQL exato do Worker em SQLite isolado: fila 16, idempotência 1, cross-tenant 0 e claim 16 únicos. Correções candidatas: limite RAM/sessões, quota de backups 256 MiB/4.096 entradas, `ASK_EVERY_ACTION` como padrão para novos instaladores, risco destrutivo honesto em MCP, `list_directory.offset` corrigido, regressões OIDC e integridade de v1. **Nenhuma dessas correções de agente foi implantada em release assinada**, e os 3 métodos MCP também não estão ativos no PROD. Não tratar 47/47 como teste real de 1.000 clientes Cloudflare.

**Próximos gates P0:** assinar/testar release externa com hardening e default seguro; Stripe real checkout+webhook/idempotência; segundo tenant real e isolamento; homologação da franquia Free (fim do limite, concorrência, replay); stress DEV 24h com teardown e failover; instalar e dar suporte sem mutações sem aprovação. **P1:** Windows Event V2 ou beta Linux-only, cold boot/failover, métricas 24h por host e Cloudflare faturado, observabilidade `last_seen`/`agent_version`, Storage/CI. Ver handoff completo para provas e rollback.

**Não confundir ferramentas:** `H_A_R_A__Commander` é o MCP comercial; `H_A_R_A__Commander_Baseline` é superfície Services/admin. Verificar novamente com plugin comercial ao iniciar novo chat.

## 10/10/2026 — Política comercial manual-on-demand, publicação e contingência

**Contrato decidido:** ao instalar Linux/Windows, o Agent inicia uma única vez para teste/atestado, mas o instalador **não habilita autostart no próximo reboot/login**. O cliente usa `hara-commander start` no Linux ou `hara-commander-agent.ps1 start` no Windows para abrir uma sessão ativa; `stop` encerra. `ASK_EVERY_ACTION` é padrão seguro; não há seletor de autorização persistente ou autostart na página comercial. Técnico pode optar em Linux por serviço persistente explicitamente via sistema operacional. O MCP STDIO local `hara-commander mcp` é distinto do Agent Cloud.

**Comprovação de publicação de assets:** Cloudflare PROD serve `https://commander.haralabs.com.br/install/linux.sh` e `install/windows.ps1` com HTTP 200, arquivos de release **v0.3.41 assinado antigo** e autostart ainda presente (Linux `enable --now`, Windows `AtLogOn`). Publicação é via Wrangler Worker `hara-commander`, `assets.directory=public`; `git push` isolado não a altera. Novo fluxo está SOMENTE nos arquivos candidatos em Git até nova assinatura e deploy versionado.

**Contingência GitHub real:** tag **`hara-commander-signed-agent-v0.3.41`** criada e publicada, apontando para SHA exata `08500d5c4256d25abc77a26ad377e55eadf1742a` com tag readback PASS. `verify_commander_public_artifacts.py --check/--live` verificou assinatura RSA v1 e seis arquivos byte-idênticos Git↔Cloudflare, incluindo manifesto. Nunca montar distribuição comercial nova combinando candidate HEAD com manifesto v0.3.41.

**Storage:** `origin` commit `092f35af...` está divergente; fontes de instaladores/agents NÃO correspondem ao manifesto assinado legado no Storage. `HOLD`, não usar Storage como fallback assinado nem fazer force-push.

**Alterações exclusivamente candidatas:** Linux systemd disabled+start uma vez, `Restart=on-failure`, CLI start/stop controla unit, status mostra `AUTOSTART`, update e reenroll preservam estado parado; Windows Task Scheduler sem trigger, CLI manual start/stop, update preserva off; portal `ASK_EVERY_ACTION` e `TUNNEL_AUTOSTART=OFF` fixos, sem escolha de autostart no site. Harness Linux com assinatura efêmera e mock localhost passou todos os passos de ciclo de vida. Windows precisa homologação real; não atualizar Founder V2 0.3.44 inadvertidamente.

**Documento autoritativo:** `docs/operations/HARA_COMMANDER_MANUAL_START_DISTRIBUTION_AUDIT_20261010.md`. **GATE PARA PROD:** nova release assinada completa + testes de reboot Linux/Windows, canário Cloudflare DEV e readback de hashes antes de substituir a v0.3.41 no domínio público.

## 10/10/2026 — Nova release comercial assinada, Free 15.000, portal start/stop

A migração `0031_free_15000_20261010.sql` foi aplicada no **D1 DEV e PROD**, com readback exato: `TRIAL` = 15.000 chamadas governadas/mês; `STANDARD` = ilimitado. Stripe PROD ainda sem checkout. O site candidato agora mostra Free 15.000 e comandos copiados de `start`/`stop` fixos abaixo do instalador Linux/Windows.

A chave privada v1 não corresponde ao público pinado e não deve ser usada. A autoridade de assinatura **v2 existente** assinou a distribuição comercial `0.3.43` usando RSA-3072. Arquivos públicos íntegros: `apps/commander/release-bundles/commercial-0.3.43-v2/` (4 assets + manifesto, assinatura, JWK público, SHA256SUMS). Nenhuma chave privada no Git. Teste E2E do **pacote assinado exato** em simulador Linux PASS, incluindo instalação sem autostart, upgrade parado, reenrolamento e desinstalação. Windows: política estática PASS; homologação PowerShell real pendente.

Canário Cloudflare DEV `hara-commander-dev-v2` versão `5e17d990-bf6f-43f4-b65f-3a9aa140eb88` com 9/9 assets byte-idênticos ao pacote, health 200. PROD versão candidata *carregada sem deploy* `8c3eec1b-8783-4aff-868f-7f558e1d9db5`, com nomes de secrets de autenticação e MCP presentes; rollback PROD v1 `29e556f3-86af-476d-ba01-a764c3acb6a0`. **Não afirmar PROD v2 ativa antes do readback 100% e 10/10 hashes.**

Documento detalhado: `docs/operations/HARA_COMMANDER_SIGNED_COMMERCIAL_V2_PUBLICATION_20261010.md`. A release assinada anterior continua disponível via tag `hara-commander-signed-agent-v0.3.41`; não misturar chaves/manifestos. Storage segue em HOLD; frota Founder V2 0.3.44 intacta. Gate offline 53/53 PASS, incluindo SQL concorrente e novo catalogo.

## PRODUÇÃO ATUALIZADA — checkpoint final 10/10/2026

**Última verdade prevalece sobre históricos anteriores:** Cloudflare Worker **PROD** `hara-commander` versão `8c3eec1b-8783-4aff-868f-7f558e1d9db5` está em **100%**, com assets comerciais assinados 0.3.43 v2 (chave `commander-release-v2`). `validate_signed_commercial_v2_bundle.py --live` 10/10 assets PASS, SHA após normalização exata do beacon HTML Cloudflare. `validate_prod_runtime_drift.py --expect-assets current` CURRENT PASS. Website e downloads públicos agora entregam nova política **start manual, sem autostart**. Comandos copiar/iniciar/parar ficam sob cada instalador. Free/TRIAL 15.000/mês aplicado no D1 PROD/DEV e readback PASS, Pro ilimitado; Stripe checkout ainda OFF.

Comercial MCP pós-deploy `ping` Núcleo A e Sentinela D PASS em Agent Founder 0.3.44 Event V2; não mudar Founder. Rollback Worker PROD `29e556f3-86af-476d-ba01-a764c3acb6a0`, tag legado assinada `hara-commander-signed-agent-v0.3.41`; novo backup assinado tag GitHub `hara-commander-commercial-v0.3.43-signed-v2` (commit `d7e5f128...`). Manifesto público v2 tem kid v2; não combinar assets v1. Windows ainda BETA sem prova nativa PS 5.1; permitir download não equivale a homologar mutação. Multi-tenant stress/Stripe e OpenAI plugin listing são gates separados.

Relatório e procedimento: `docs/operations/HARA_COMMANDER_SIGNED_COMMERCIAL_V2_PUBLICATION_20261010.md`. Verificador antigo `verify_commander_public_artifacts.py --check` preserva assinatura v1 no Git; `--live` deve usar validador comercial v2, nunca tratar a v1 histórica como atual. Storage protegido segue HOLD `092f35af...`.

## 10/10/2026 — Minimalismo da tela Computadores

Novo refinamento autorizado da UI no portal público (sem alterar cores/identidade): cada linha mostra só nome, sistema, último contato e estado real; Agent/arquitetura/transporte/autorização ficam no menu de detalhes com ações secundárias. O grande guia de onboarding está recolhido por padrão; os botões de diagnóstico e procedimentos de autorização/revogação são preservados. Uma lease local válida não implica máquina online. O total de chamadas Free continua 10.000/mês.

Fonte e contrato: docs/operations/HARA_COMMANDER_DEVICES_MINIMALIST_UI_20261010.md. Gate offline 54/54 PASS, DEV Worker versão 636d9e2f-883c-4a0d-96e1-8280ee2ee4ad com SHA exato 11/11 e health 200. Bundle assinado comercial v0.3.43 e agentes Founder v0.3.44 não foram tocados. Registrar versão PROD depois da promoção e readback.
