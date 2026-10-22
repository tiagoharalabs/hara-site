# H.A.R.A. Commander — handoff integral R2 | OpenAI Platform e lançamento

**Data-base:** 22/10/2026, após a tela Persona `Application in review` exibida pelo usuário.
**Produto:** H.A.R.A. Commander comercial, MCP na Cloudflare, HARA Identity, Agent local.
**Objetivo deste documento:** continuidade executável em um chat novo, com estados separados de Git local (Services), Storage, GitHub Web, Cloudflare PROD, plugin privado e solicitação de identidade OpenAI.

## 0. LEIA PRIMEIRO — estado atual e próxima ação

1. **OpenAI Platform:** a organização `H.A.R.A. Labs` aparece selecionada no portal de Plugins. O usuário informou que cadastrou seu próprio cartão na cobrança da OpenAI Platform. Isso é **separado** de Stripe e não significa saldo/crédito adquirido ou Pro do Commander ativo. **NÃO registrar, copiar ou expor dados do cartão**.
2. Ao tentar `Upload new or existing plugin`, a OpenAI exigiu uma verificação de identidade via Persona. O usuário compartilhou a tela `Application in review`. **A identidade está em análise, sem confirmação de aprovação**. O portal avisou que atualizações surgirão nas configurações da organização. Não tentar retransmitir documentos, OTP, selfie, cartão ou mudar cadastros enquanto a análise estiver pendente.
3. **O ZIP do plugin público AINDA NÃO FOI ENVIADO** à revisão. A tela Persona é a análise de identidade, **não** a análise, homologação ou publicação do H.A.R.A. Commander no diretório público. Não prometer instalação por clientes externos até os gates aplicáveis.
4. **Artefato candidato existente e validado:** `apps/commander/plugin-submission/hara-commander-capivara-v0.2.0-review.zip`; cópia pronta em `/home/sartorius/Downloads/hara-commander-openai-public-review-v0.2.0.zip` no **Núcleo A**; ZIP 348.239 bytes; SHA-256 `40c5a69ed30b7ed626fe725b1eb2841d423e3e3ef772b49120aad228f606c483`. Não recriar um segundo plugin nem inventar outra versão.
5. **Próximo marco:** após confirmação da OpenAI de que a verificação foi aprovada, voltar a `https://platform.openai.com/plugins`, carregar este ZIP, passar checks, completar desafio de domínio emitido pelo portal, conexão OAuth/DCR e conta de demonstração; enviar para revisão somente quando os gates exigidos estiverem provados. **Não ativar Stripe antes disso.**
6. **PROD não deve ser alterada só por este handoff.** Não reiniciar frota, não alterar Identity/credenciais, não migrar D1, não mover/apagar staging histórico. Usar o **MCP comercial H.A.R.A. Commander**, não Commander Baseline nem Desktop Commander, para inspeções operacionais.

## 1. Cronologia das entregas concretas de produto (22/10)

| Etapa | Estado Cloudflare Worker `hara-commander` | Git/commit, observações |
|---|---|---|
| UI de dispositivos e Uso R1 | Versão `418ed86f-3fc4-48f3-b86e-1d98c10238a4` esteve 100%, deployment `a384649b-1232-42cc-8a9d-35d6bfb056cd` | Commit `f2cb59880fd10be96788df665d50bf683bdf3de4`, branch `local/commander-ui-usage-auth-live-r1-20261022`. Retirou `Autorizar por 6h` dos dispositivos Cloud já pareados; distinguiu pairing duradouro de lease técnico; Uso mostra mês calendário UTC atual e oculta histórico de vida inteira para usuário comum. |
| Avançado largura total R1 | Versão `36a5e658-8cb0-441e-867c-998f1fbc02a7`, deployment `4ccc8011-fdb4-4267-862b-339d43d2e051` | Commit `14780b3b36f75735cd235394d2a1dbf3dd35bd2b`. Remove limite estreito de 1020px só do painel Avançado, Linux e Windows lado a lado, Windows maior, código PowerShell com scroll interno e 3 blocos acessíveis por teclado. |
| Avançado margem vertical R2 | Versão `4d766650-4768-42b4-be7b-6d03d4110a14`, deployment `7365688d-9c36-49ce-8375-126b29de1968` | Commit `57dc2272227fc61cfcaba9875e8ee4c9bfea3432`. Compactação responsiva em viewports baixos; o usuário ainda não aprovou o resultado visual. |
| Avançado folga real R3 | **Versão confirmada 100% no último readback:** `fc0b77ba-227a-49fe-84ad-d7049824a1d7`, deployment `bdc26055-62a1-48a5-9a4d-46fcd64d0730` | Commit `ac200752010cf699958e0ac15ed76301bed24a86`. Pseudo-elemento `::after` no painel Avançado visível cria folga real de rolagem de 112–180px depois da última seção para evitar conflito com dock do GNOME. **Não foi obtida aprovação visual conclusiva do usuário após R3.** |

**Verificação feita durante esta continuidade:** domínio `https://commander.haralabs.com.br` ainda servia o `index.html` R3 SHA-256 `4e242671dc9357f7f402fb31fa3cb6611bc917fc384754def0cfe9a3a1b1c165`, `advanced-layout.css` R3 SHA-256 `bf0ccad7ffe2da2f150787c130170891ef514dee9485f7c52d8824de6f84745f`, e manifesto de Agent público SHA-256 `53c0cbc2b074b9b85b81454c2bce286a8af2fa981e79f3c9b1719c5697880229`. Consultar novamente antes de qualquer promoção.

**Integridade das releases:** Cloudflare uploads com 0% de tráfego, validação por override, 29 bindings comparados com sete referências de secret preservadas, hashes de HTML/CSS e de app.js, Worker e instaladores. Sem migrations D1, sem atualização dos Agents ou troca de segredos por mudanças de layout. R2/R3 têm rollback por versão anterior no Worker; usar guarda de preimagem de deployment. Ainda há detalhes cosméticos do Avançado: classificados P2, não impeditivos ao beta.

**Pendência de interface separada:** botão `Limpar revogados` na aba Histórico. O usuário solicitou esconder revogados da lista sem apagar recibos de auditoria. Existe *candidato NÃO PUBLICADO* em branch `local/commander-durable-trust-20261022-r1`, commit `ea83525b6bc99a42f8c301517167dc8f352bb868`, com migrations 0037 (trust) e 0038 (histórico), renovação técnica de lease e ocultação auditável. **NÃO PROMOVER o candidato integral** sem revisar contrato, migrations e autenticação. Não confundir esse botão com limpar histórico de execuções local.

## 2. Frota e confiabilidade

- Máquinas: Services, Núcleo A, Sentinelas A/B/C/D, Ninja Blue, Observer, Storage e VM `HARA_WIN11`.
- Na última consulta do MCP comercial durante o handoff: **9 Linux ONLINE na versão de Agent interno 0.3.54**. VM Windows 11 estava OFFLINE, conforme o usuário informou que a manteve desligada; último Agent v0.3.55. Os revogados antigos que aparecem no inventário são históricos, não devem ser reativados.
- Sentinela B e Storage tiveram divergência **processo ativo mas presença Cloud OFFLINE**. Investigação via Services SSH: user systemd ativa/habilitada e acesso SSH operacional. Sentinela B usa `hara-commander-agent-v2.service`, Event V2; status de conexão e último contato obsoletos. Storage usa `hara-commander-agent.service`, Outbound Relay; heartbeat parou. Reinício **somente dessas unidades de Agent** restaurou online e ping PASS dos dois; computadores não foram reiniciados nem reemparelhados. **Não é correção definitiva de watchdog/reconexão.** Acompanhar [hara-site #163](https://github.com/tiagoharalabs/hara-site/issues/163).
- Todos os testes reais pelo plugin comercial: execução de comando no Services Event V2, Storage Relay e Observer ARM64 Relay; `write_file` → `read_file` → `delete_file(expected_sha256)` no Storage Relay e na Sentinela C Event V2 com receipts e remoção dos arquivos temporários.
- Telemetria de 24h de `get_activity` na auditoria: 5.831 chamadas, 5.705 concluídas, 114 falhas, 97,8% sucesso, média 1.829ms (fonte majoritariamente interna Founder; **não** medir adoção de clientes com isso).

## 3. Distribuição assinada e segurança (dois canais diferentes)

- **Release comercial pública do Agent é v0.3.43**, schema `hara.commander-agent-release.v1`. Manifests/assinatura/JWK públicos disponíveis em `https://commander.haralabs.com.br/release/`; quatro arquivos públicos: `agent/linux.py`, `agent/windows.ps1`, `install/linux.sh`, `install/windows.ps1`. Teste em 22/10 de verificação criptográfica **RS256 + `kid=commander-release-v2` + 4/4 SHA/tamanhos + trust anchor pública da frota = PASS**. Não confundir com Agent Founder/internal **v0.3.54** e Windows beta v0.3.55, nem baixar v0.3.43 para reinstalar e provocar downgrade.
- Instalador público Linux: política de `start` manual, sem autostart após reboot, `ASK_EVERY_ACTION` como padrão; o usuário precisa instalar o Agent no computador próprio, mas **não deveria configurar manualmente a URL MCP** ao instalar o plugin pelo diretório OpenAI. Modo Direct é opcional distinto de Cloud.
- Segurança: testes locais de revogação sobre claim pendente negam nova execução após revoke; fixtures de tenant cross-tenant DENIED, Identity e MCP Simple (33 ferramentas) PASS, mas **falta ponta a ponta com segundo tenant real, outro Linux e revogação real**. Segurança e consentimento `PERSISTENT_TRUSTED` para Direct durável pertencem a candidato não implantado, não prometer comportamento futuro como disponível.
- O `validate_signed_commercial_v2_bundle.py --live` antigo leu source de um worktree defasado e reportou asset mismatch; verificador independente **sobre bytes da release PUBLICADA** confirmou autenticidade. Corrigir gate antigo para diferenciar source antigo de pacote publicado, não publicar um novo Agent só para satisfazer SHA de fonte stale.
- Script de auditoria pública no Services: `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_LAUNCH_AUDIT_20261022_R1/verify_signed_public.py`.

## 4. OpenAI Platform / Plugin Directory — estado detalhado

**A) Já disponível em desenvolvimento/privado:**
- Plugin próprio USER, privado, `H.A.R.A. Commander` dev v1.0.0; ID de gestão `plugin_asdk_app_6ac9741d1cf881918d3d6f9d7e21c476`, release `PluginRelease_2a420e4922248191ad34993768bdeb4f`.
- Há outro plugin privado de **Commander Baseline**/conexão com computador. São coisas diferentes. Não atualizar/desinstalar um para lançar o outro. O plugin privado inclui referência interna `.app.json` e não é o artefato portátil do diretório público.

**B) ZIP público pronto no Git:**
- Repositório `hara-site`, pasta `apps/commander/plugin-submission/`.
- Arquivo `hara-commander-capivara-v0.2.0-review.zip` de **348.239 bytes**; SHA256 **`40c5a69ed30b7ed626fe725b1eb2841d423e3e3ef772b49120aad228f606c483`**; quatro entradas: `plugin.json` (v0.2.0), `mcp.json`, `assets/logo.png` 512×512, `assets/icon.png` 256×256. ZIP bytes conferidos contra fontes do repo e SHA no Núcleo A idêntico.
- MCP Streamable HTTP `https://commander.haralabs.com.br/api/mcp?profile=simple`; OAuth `https://auth.haralabs.com.br`, registro dinâmico do cliente **DCR**, recurso `https://commander.haralabs.com.br/api/mcp`, scope `openid`. Endpoint sem login retorna 401 por design; protected-resource metadata retorna HTTP 200; authorization-server metadata HTTP 200.
- Metadados do publicador H.A.R.A. Labs, categoria Developer Tools, URL website/suporte/privacidade/termos respondendo 200, logo e ícone, 3 prompts de exemplo, cinco testes positivos e três negativos. Validador local `validate_public_package.py` PASS e sem material secreto encontrado.
- Cópias do ZIP: Services `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_OPENAI_PUBLIC_SUBMISSION_20261022/hara-commander-openai-public-review-v0.2.0.zip` e **Núcleo A** `/home/sartorius/Downloads/hara-commander-openai-public-review-v0.2.0.zip`. Não publicar ZIP de dev com `.app.json` no lugar deste.
- Documentação de upload: `https://developers.openai.com/plugins/deploy/submission`; portal `https://platform.openai.com/plugins`.

**C) Pendente e operação do usuário:**
- A sessão OpenAI Platform reconheceu a organização `H.A.R.A. Labs`, botão `Upload new or existing plugin` disponível, mas exigiu verificação de identidade.
- O usuário fez cadastro do cartão pessoal/empresarial na OpenAI Platform, com dados preenchidos **exclusivamente no site, não por nós**. Não armazenar números, nome, CVV, endereço ou CNPJ em handoff.
- A janela Persona mostrou pedido de confirmação de e-mail, mas depois o usuário comprovou por screenshot o estado **`Application in review`**; é o **processo de identidade do publicador**. A página informa que atualizações chegam às configurações da organização. Não inferir aprovação até readback oficial.
- **Não houve upload do ZIP**, submissão pública nem publicação. Também não houve vídeo de reviewer ou conta de demonstração final, nem recebimento do desafio oficial de verificação do domínio. Não criar arquivo genérico de challenge sem token emitido pelo portal.
- Ao obter aprovação, seguir: (1) novo acesso à página Plugins, (2) **upload do ZIP acima**, (3) scan automático e conserto somente dos blockers, (4) configurar domínio e conexão OAuth/DCR, (5) usuário/VM descartável e vídeo para reviewer, (6) Submit for review, (7) Publish **após aprovação**. O usuário pediu que nós conduzíssemos o máximo possível pela janela do navegador; em Chat, o Browser conectado disponível foi **somente leitura**. Para interagir no portal quando necessário, usar **Work mode (Cloud Browser)** ou controle remoto explicitamente autorizado, sem tentar contornar 2FA/cadastro/Persona.
- **Não afirmar que ChatGPT Enterprise é necessário**, nem misturar cobrança OpenAI Platform (setup da conta) com Stripe do H.A.R.A. Commander.

## 5. Billing e modelo de lançamento

- D1 PROD lido com SQL SELECT: `TRIAL` Free ACTIVE `CALENDAR_MONTH` 10.000 chamadas; `STANDARD` Pro ACTIVE, ilimitado. Catálogo ≠ checkout em produção.
- `billing_connections=0`, `billing_webhook_events=0` na leitura; nenhum binding `STRIPE_*` no Worker ativo; site pode exibir Pro R$80/mês, mas **checkout e recebimento não estão prontos**. Não efetuar cobrança automática ou anúncio de assinatura funcional. O usuário planeja ativar Stripe depois de disponibilidade do plugin na OpenAI.
- Ordem acordada com o usuário: **verificação + submissão/aprovação na OpenAI → instalação/distribuição via ChatGPT sem configurar URL MCP → beta com 2–3 testadores externos (contas próprias) → Stripe test-mode checkout/webhook/cancelamento → oferta paga**. Instalar Agent local e aprovar OAuth continuam necessários mesmo com o plugin listado.
- Beta fechado Linux + Cloud MCP primeiro. Win11 está beta limitado; não prometer paridade de operações sensíveis antes de homologação real.
- Stripe plugin foi apresentado como opção de conexão para facilitar configurações, mas **conexão não foi confirmada**. Sem criar product/price na conta Stripe neste handoff.

## 6. Gates P0 operacionais (ainda NÃO comprovados) e prioridade

1. **P0-A publicação OpenAI:** esperar status da identidade, abrir rascunho pelo ZIP existente, comparar requirements atuais do upload; confirmar domain proof, OAuth, reviewer, segurança e status oficial. Não confundir review Persona com review plugin.
2. **P0-B cliente independente:** segundo tenant HARA Identity, máquina Linux *limpa* fora da frota Founder, instalador público v0.3.43, start manual, consentimento por ação, sessão no ChatGPT pelo plugin, chamadas `list_devices`, `ping`, `read_file`, `hostname` autorizado. Documentar tempo de onboarding/erros, nenhum token.
3. **P0-C isolamento e revogação:** cross-tenant DENIED sem metadata leakage, revogar device descartável do tenant de teste, chamadas após revoke negadas, receipt e cleanup, sem afetar devices Founder.
4. **P0-D watchdog/reconexão:** reproduzir socket/heartbeat parado B/Storage, reconectar automaticamente quando sessão autorizada estava ativa, mas **não violar stop manual** nem reemparelhar; owner na issue #163. Verificar política Direct/Cloud para trust durável.
5. **P0-E porta de release/gates:** `commander_commercial_readiness_gate.py` antigo usa Founder 0.3.46 e um blocker `CUSTOMER_SIGNED_DISTRIBUTION=False` hardcoded, então `COMMERCIAL_BETA=HOLD` pode conter falso negativo de versão de source. Atualizar leituras canônicas sem inventar segundo tenant real.
6. **P1 Stripe:** modo teste com produto/Price ID validado, webhook assinado, D1 entitlement, limitação/quota e cancelamento. Somente depois de P0, sem cobrar testador por serviço não homologado.
7. **P2 UX:** restinho do layout Avançado/dock, botão `Limpar revogados` auditável, UX de erros; não bloquear P0.

## 7. Branches e fontes — não perder o trabalho

- Histórico R1 UI/uso: `local/commander-ui-usage-auth-live-r1-20261022` HEAD `f2cb59880fd10be96788df665d50bf683bdf3de4`.
- Layout R1: `local/commander-advanced-wide-r1-20261022` HEAD `14780b3b36f75735cd235394d2a1dbf3dd35bd2b`.
- Layout R2: `local/commander-advanced-bottom-spacing-r2-20261022` HEAD `57dc2272227fc61cfcaba9875e8ee4c9bfea3432`.
- Layout R3 PROD: `local/commander-advanced-bottom-clearance-r3-20261022` HEAD `ac200752010cf699958e0ac15ed76301bed24a86`.
- Auditado beta: `local/commander-beta-launch-gate-r1-20261022` HEAD `1b5d3791640c07e399ce6202530672e49eeda39d`, doc `docs/operations/HARA_COMMANDER_BETA_LAUNCH_GATE_R1_20261022.md`.
- **Handoff deste turno R2:** branch isolada `local/commander-openai-submission-handoff-r2-20261022`, derivada de 1b5d379; conferir commit final, Storage e GitHub Web nos recibos adicionais publicados na issue #310. O presente Markdown é a fonte de continuidade. Não rebase/merge automaticamente os candidatos na produção.
- Git local é worktree do Services; remote canônico `origin=ssh://storage/srv/hara/archive/github-mirrors/working/hara-site.git`. **Storage e GitHub Web são destinos diferentes**. O estado do Worktree `commander-product-current` possui mudanças em arquivos do Windows e bundles untracked de outra frente — NÃO limpar, descartar, incluir no commit nem mover staging. Usar branch isolada.
- Evidências locais dos releases em Services:
  - `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_UI_USAGE_AUTH_RELEASE_20261022_R1/`
  - `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_ADVANCED_WIDE_20261022_R1/`
  - `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_ADVANCED_BOTTOM_SPACING_R2_20261022/`
  - `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_ADVANCED_BOTTOM_CLEARANCE_R3_20261022/`
  - `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_LAUNCH_AUDIT_20261022_R1/`
  - `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_OPENAI_PUBLIC_SUBMISSION_20261022/`.
- Issue principal produto [hara-site #310](https://github.com/tiagoharalabs/hara-site/issues/310). Convergências: [presença #163](https://github.com/tiagoharalabs/hara-site/issues/163), [segurança #189](https://github.com/tiagoharalabs/hara-site/issues/189), [Windows #240](https://github.com/tiagoharalabs/hara-site/issues/240), [billing #296](https://github.com/tiagoharalabs/hara-site/issues/296) e [Codex #1953](https://github.com/tiagoharalabs/hara-platform/issues/1953).

## 8. Instrução copiada para o próximo chat

> Continue a frente **H.A.R.A. Commander — OpenAI Platform, submissão e beta externo**. Leia `docs/handoffs/HARA_COMMANDER_OPENAI_IDENTITY_SUBMISSION_HANDOFF_R2_20261022.md` na branch `local/commander-openai-submission-handoff-r2-20261022` (Services/Storage) ou espelho documental do GitHub Web. Antes de executar, compare HEAD local/Storage/GitHub e o Worker ativo na Cloudflare. A identidade do publicador na OpenAI estava `Application in review`; **NÃO** era aprovação do plugin. ZIP público v0.2.0 SHA256 `40c5a69ed30b7ed626fe725b1eb2841d423e3e3ef772b49120aad228f606c483` no Núcleo A Downloads. Aguarde confirmação da identidade para upload, sem refazer o plugin privado. Priorize testes de segundo tenant/revogação/reconexão e prepare reviewer/5+3 casos; Stripe depois. Não alterar Agents Founder, billing/card, D1 ou produção sem gate e autorização, não apagar staging, manter receipts SHA e handoff das mudanças.

## 9. Segurança do próprio handoff

**Nenhum número de cartão/CVV, endereço pessoal, email/OTP, documento de identidade, chave privada, token, segredo OAuth ou credencial de dispositivo deve ser acrescentado ao Git ou aos comentários públicos.** O usuário confirmou apenas o resultado `Application in review`, sem aprovação ainda. A continuidade deve lidar com status, não com documentos privados.