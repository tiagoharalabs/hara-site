# Hara Commander — Handoff canônico R12
**Data:** 23/10/2026 · **Estado:** UI R11 PROD; release pública de Agents HOLD; OpenAI Review não submetido.

Este documento evita perder contexto entre frentes. Não confundir commit em Services/Storage, upload candidato Cloudflare, versão ativa PROD e homologação OpenAI.

## Estado de produção — site

- Worker `hara-commander`: versão **dd25fde5-d8d2-4a70-af80-5f58dce8cd8d**, 100% tráfego; rollback `20540b42-c5d2-4a90-98e9-01500368d7f1`.
- R11 commit `894890b9a7115f18b5ac5c0b92617e946e791bcf`, closeout `583b60f6f68ecd9766d3b99d6bf337296d1d860d`, Storage readback PASS.
- R11 login: avisos repetidos sobre senha e banner automático de acesso protegido retirados; botão dourado e brilho suave; erros de autenticação reais permanecem. Configurações: divisórias internas retiradas, blocos sutis e melhor legibilidade.
- R4–R9 já corrigiram espaçamentos Avançado, MCP, Direct expandido, Adicionar, Concluído em uma linha e centralização Uso. Branding desejado é a capivara dourada original sem pirâmide.
- Arquivos R11: `apps/commander/public/index.html`, `app.js`, novo `ux-auth-settings-r11.css`. Testes UI R11 8 PASS, autenticação/isolamento 3 suites PASS, captura Firefox local PASS.
- Readback R11: HTML SHA256 `cb2236ede77a4d21bdc3eee55e6d07e75f83a60dd555fc9c706285ab3c4f4263`; JS `c0ce364072866a9c6a6e1607b5ad63311b4ea62fcc46451b537809801f4b47f0`; CSS `8177f4c60bdc2994fb500fbbec7b075a884f71780444ba534c85f011a9d2458c`.
- HTTP health 200; OAuth configurado; MCP sem auth 401 esperado; challenge OpenAI preservado. Cloudflare pode injetar beacon em HTML e alterar SHA bruto; não confundir com drift de app. Quedas intermitentes do usuário não tiveram RCA confirmado.
- Recibo: `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_LOGIN_SETTINGS_R11_PROD_RECEIPT_20261023.json`.

## Readback do Agent — 23/10/2026 13h49 BRT

- **Núcleo A:** `hara.device.info` e `hara.ping` pelo **Hara Commander do produto** retornaram Agent `0.3.54`, `PERSISTENT_TRUSTED`, `pong:true` em `2026-10-23T16:49:50Z`. A lista de matrículas ainda exibia `0.3.41`; tratar como metadado defasado e **não iniciar downgrade/upgrade redundante** sem nova prova.
- Na lista consultada, Services, Storage, Observer, Sentinelas A–D e Ninja Blue apareciam `0.3.54`/ONLINE; matrícula legada Windows `HARA_WIN11` (`e8b48d00`) permanecia OFFLINE, versão `0.3.55`. Esse status não substitui ping individual. Sem revogação real nesta rodada.

## Revogação e Histórico — P1 ainda não publicada

- Em PROD, `Revogar acesso` depende de segundo clique em até 6 s, UX confusa. API `POST /api/portal/devices/revoke` existe. O usuário quer revogar matrícula Windows LEGADA `HARA_WIN11` (offline, Agent .55, ID final `e8b48d00`), NÃO a VM de QA `hara-review-win11` na Sentinela B. Nenhuma revogação real confirmada.
- Código de melhoria **R10 preparado**, não promovido: confirmação persistente, validação de resposta, falhas 403/404/409 visíveis, Histórico e `Limpar histórico` reversível em armazenamento local por subject+tenant (não apaga auditoria). 5 testes simulados PASS. Fonte: `commander-devices-revoke-history-r10-20261023`, documento `docs/operations/HARA_COMMANDER_REVOKE_HISTORY_UX_R10_20261023.md`.
- **Readback pós-handoff (23/10, 13h50 BRT):** o conflito histórico `UU apps/commander/public/index.html` da branch `local/commander-revoke-history-r12-20261023` foi resolvido e integrado sobre R11 no commit `04fd70cfc71fe4d423b10adbed225d633a5b0810`. `git ls-files -u` = 0; worktree sem alterações rastreadas (há `node_modules` não rastreado, preservar). Closeout registra 21 verificações R12 PASS, sem revogação real e **sem deploy PROD**. Continuar somente com gate de publicação independente, QA visual/funcional e readback.

## Blocker P0 — release assinada Linux/Windows

- Em produção, manifesto público assinado anuncia **0.3.41** (SHA `7e42f25404e414b74b375ccb47b7ed8ba7d8c572dc45db994d89012207f08f7c`), Agent Linux **0.3.43**, Agent Windows **0.3.52**, instaladores Linux .43 / Windows .49. **Quatro de quatro assets não correspondem ao SHA/tamanho declarados**. Manifesto antigo tem RS256 válido, mas não autentica os blobs novos.
- Issue principal [hara-site #310](https://github.com/tiagoharalabs/hara-site/issues/310); Windows [#240](https://github.com/tiagoharalabs/hara-site/issues/240). O kit antidowngrade R3/R4 e o validador de quatro assets devem permanecer. O gate Node de dois assets é **complementar e intencional**; não tratá-lo como substituto nem como defeito por não aceitar os quatro assets diretamente.
- Candidato `commercial-0.3.56-candidate` em `commander-public-release-repair-20261023` (branch `local/commander-commercial-056-candidate-20261023`) tem conteúdo coerente mas **não assinado, admitido, instalado E2E nem publicado**. Manifesto SHA `ee485c46414729a51ea5b8719b9bd6a4d572995dd85397ee0c20de22b1db4595`.
- Testes do candidato: Linux 14/14 PASS; lifecycle Linux simulado 8/8; PowerShell nativo Windows 34 verificações; gerador 13/13; gates Node 38/38 e Python 16/16; oito adulterações negadas.
- P0 restante: ExecutionPolicy Restricted bloqueia execução direta do .ps1 no Windows; resolver distribuição nativa assinada SEM Bypass. Manifesto RS256 não é assinatura Authenticode. Admitir fontes comerciais, signer custodiado, public staging de bytes exatos, Windows/Linux E2E, rollback e readback PROD. Não renumerar/rebaixar Founder .54, Windows .55 ou substituir com bundle .43 histórico.
- Referência: `docs/operations/HARA_COMMANDER_COMMERCIAL_056_CANDIDATE_20261023.md` no checkout Codex. `PUBLIC_INSTALLERS=HOLD` até prova nova.

## QA — VMs da outra frente

Handoff recebido do owner de VMs: `hara-review-win11` Windows 11 e `hara-review-linux` Ubuntu Server 24.04.5, ambas ligadas e com autostart na Sentinela B; firewall e redes de revisão persistentes. Atalhos privados no Desktop do Núcleo. Windows antigo do Núcleo removido, ISOs/UEFI/TPM/staging preservados; ~68 GiB liberados segundo owner. Abertura por duplo clique de atalhos ainda merecia confirmação. **Infra pronta não é Agent comercial instalado/pareado.** Não competir com a outra frente nem expor SPICE/SSH. Manter Sentinela B sem suspensão durante review.

## OpenAI Platform — ainda não enviado

- Plugin `hara-commander` draft **0.2.0 carregado**, domínio validado, OAuth conectado, MCP + 33 ferramentas descobertas, scan sem findings. Status **Not published / Not submitted**, review info incompleta.
- Selecionado All supported countries; traduções extras opcionais.
- Conta dedicada no tenant `HARA Review`: `openai-reviewer@haralabs.com.br`. Login `https://commander.haralabs.com.br/auth/login`; campo `Username and password`. Senha **não** inserir em Git, arquivos, issue ou conversa. Validar login sem MFA/email code e digitar somente no formulário privado da OpenAI.
- Cinco testes positivos planejados: listar demo, detalhes, ping, leitura sintética, escrita autorizada com receipt. Três negativos: offline, isolamento cross-tenant, escrita sem consentimento. Precisam de execuções reais nas VMs pareadas, não mocks; vídeo real legível com OAuth, comandos e revogação.
- Conferir pacote/ícone do ZIP 0.2.0 no portal antes de submeter; não assumir reupload pós-R11. Stripe e billing comercial não bloqueiam o review do plugin.

## Regras para próxima frente

1. Conferir estado ATUAL em Cloudflare e Git, pois snapshot pode ficar velho.
2. Ajudar Codex #310 a fechar release comercial, não editar trabalho ativo nem staging.
3. Resolver `UU` da revogação R12 respeitando R11 PROD, com testes e promoção independente.
4. Aguardar VMs com Agents pareados ao REVIEW; executar testes reais 5+3, vídeo, preencher OpenAI e só então submeter.
5. Distinguir confirmação **Git local Services → Git Storage → GitHub Web**; registrar SHAs. Comunicação entre hosts só via rede, nunca ressuscitar USB Link aposentado.