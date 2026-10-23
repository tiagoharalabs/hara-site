# Hara Commander — Handoff canônico R12
**Data:** 23/10/2026 · **Estado atual (readback pós-R15):** UI R15 PROD 100%; release pública de Agents HOLD; OpenAI Review não submetido.

Este documento evita perder contexto entre frentes. Não confundir commit em Services/Storage, upload candidato Cloudflare, versão ativa PROD e homologação OpenAI.

## Estado de produção — site

- Worker `hara-commander`: **R15 `d52b55b8-bb9d-45c7-954e-c2bd34f72f3b` a 100%** do tráfego, readback externo PASS. Rollback imediato **R14 `2b8de065-d701-40eb-81da-ec9b4c9f27c7`**; R13 `71ad29df-438b-4239-a4a3-9bf94d7f583c` e R11 continuam históricas.
- R11 commit `894890b9a7115f18b5ac5c0b92617e946e791bcf`, closeout `583b60f6f68ecd9766d3b99d6bf337296d1d860d`, Storage readback PASS.
- R11 login: avisos repetidos sobre senha e banner automático de acesso protegido retirados; botão dourado e brilho suave; erros de autenticação reais permanecem. Configurações: divisórias internas retiradas, blocos sutis e melhor legibilidade.
- R4–R9 já corrigiram espaçamentos Avançado, MCP, Direct expandido, Adicionar, Concluído em uma linha e centralização Uso. Branding desejado é a capivara dourada original sem pirâmide.
- Arquivos R11: `apps/commander/public/index.html`, `app.js`, novo `ux-auth-settings-r11.css`. Testes UI R11 8 PASS, autenticação/isolamento 3 suites PASS, captura Firefox local PASS.
- Readback R11: HTML SHA256 `cb2236ede77a4d21bdc3eee55e6d07e75f83a60dd555fc9c706285ab3c4f4263`; JS `c0ce364072866a9c6a6e1607b5ad63311b4ea62fcc46451b537809801f4b47f0`; CSS `8177f4c60bdc2994fb500fbbec7b075a884f71780444ba534c85f011a9d2458c`.
- HTTP health 200; OAuth configurado; MCP sem auth 401 esperado; challenge OpenAI preservado. Cloudflare pode injetar beacon em HTML e alterar SHA bruto; não confundir com drift de app. Quedas intermitentes do usuário não tiveram RCA confirmado.
- Recibo: `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_LOGIN_SETTINGS_R11_PROD_RECEIPT_20261023.json`.

## Núcleo A — divergência corrigida e verificada em 23/10/2026

- **Causa da diferença de versão:** antes da promoção, a CLI `~/.local/bin/hara-commander` já apontava para a distribuição `0.3.54`, mas o serviço systemd do usuário ainda executava `~/.local/share/hara-commander/hara-commander-agent` em `0.3.41`. **Não era apenas cache/metadado da lista de matrículas.** A versão da CLI não prova a versão do Agent em execução.
- **Correção concluída:** o executável usado pelo serviço foi promovido para `0.3.54`. SHA-256 do arquivo ativo: `ea42a392a6d350bb6e7e522cca5498ee823d2c41587855d0d3d1ecc41a954da2`, igual ao conteúdo da distribuição Linux `0.3.54` verificada. Backup preservado: `~/.local/share/hara-commander/rollback/hara-commander-agent.0.3.41.e1f44e4695266717.bak`.
- **Ativação/readback:** o Agent foi reiniciado às **13h49min21s BRT**, sem reiniciar o host. Em nova consulta, `systemd` retornou `active/running`, e `hara.device.info`/`hara.ping` retornaram `0.3.54`, `PERSISTENT_TRUSTED`, `pong:true` e a mesma matrícula `HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62` (`ping` às `2026-10-23T17:16:39.860758Z`). A execução por `/proc/<pid>/cmdline` confirmou o caminho do executável do serviço. Identidade/token e arquivos do Codex não foram modificados durante a correção reportada.
- Na listagem anterior, Services, Storage, Observer, Sentinelas A–D e Ninja Blue apareciam `0.3.54`/ONLINE; matrícula Windows legada `HARA_WIN11` (`e8b48d00`) permaneceu OFFLINE. A lista não substitui verificação do processo efetivo, do hash do arquivo e do ping.
- **Diferenciar do P0 de resiliência Storage [#322](https://github.com/tiagoharalabs/hara-site/issues/322):** no Storage, o processo `0.3.54` permaneceu vivo sem heartbeat até recuperação manual após cerca de 12h35; ausência de watchdog e loop sequencial comprovadas, mas instrução causadora do travamento ainda desconhecida. Protótipo externo de supervisor foi testado localmente (19 testes), não publicado nem ativado. Correção de loop/alerta ainda **P0 ABERTO**; não confundir com a promoção bem-sucedida do Núcleo.
- A versão comercial `0.3.56` segue candidata, sem assinatura/admissão/liberação. **Não** usar como substituta da `0.3.54` assinada.

## Revogação e Histórico — R15 em produção (23/10/2026)

- **R15 corrigiu o bug real da revogação, reproduzido em Brave:** `#deviceList` na R14 recebia `data-device-tab=active`, e o clique delegado usava `closest('[data-device-tab]')`, capturando o ancestral e executando `setDeviceTab('active')` antes do botão `Revogar acesso`. A confirmação era zerada, sem POST. R15 usa `data-list-tab` no container e limita os 3 seletores de tabs a `.device-tabs button[data-device-tab]`. Teste CDP Brave real R14: confirmação ausente; R15: confirmação visível, primeiro clique sem POST, segundo clique faz 1 POST mockado e move a matrícula sintética offline para Histórico. Sem revogação real do proprietário no QA. Git Services/Storage fonte `201ce4e35c00b8ebc99da0a554fff7c4ee7dc72a`, closeout `3b4ad3b313de1b12181189473ba42ddfdb836a03`. Recibo `HARA_COMMANDER_REVOKE_CLICK_R15_PROD_RECEIPT_20261023.json`.
- **Revogação é server-side mesmo offline:** `POST /api/portal/devices/revoke` altera `commander_devices.state=REVOKED` e `revoked_at_utc` no D1 e cancela pendentes. `resolveDeviceCredential` nega o token antigo com `DEVICE_AUTH_INVALID`, sem consultar Agent/heartbeat.

### Histórico R13 preservado

- **Em PROD R13**, `Revogar acesso` mostra quadro persistente `Cancelar` / `Confirmar revogação` e valida `ok:true`, `state:REVOKED` e matrícula exata retornada. A API `POST /api/portal/devices/revoke` permanece. A matrícula Windows LEGADA `HARA_WIN11` (offline, Agent .55, ID final `e8b48d00`) NÃO é a VM QA `hara-review-win11` da Sentinela B. **Nenhuma revogação real do proprietário foi executada neste rollout**; testes foram sintéticos.
- **Histórico R13 real, não ocultação:** a UI removeu `Mostrar ocultos` e `Restaurar todos`. O botão `Limpar histórico`, após confirmação de OWNER/ADMIN, chama `POST /api/portal/devices/history/clear`; elimina de fato registros da tabela D1 `commander_device_history` no tenant, com log da operação e leitura de volta. As matrículas já revogadas em `commander_devices`, recibos, chamadas e auditoria técnica **não** são apagados. A migração remota `0036_portal_device_history_clear.sql` passou e fez backfill inicial; ao verificar, 8 revogados=8 no Histórico e 0 limpezas, portanto **nenhum histórico do proprietário foi limpo automaticamente**.
- **Histórico da integração:** o conflito R12 `UU apps/commander/public/index.html` foi resolvido no commit `04fd70c...`, publicado na Cloudflare como R12 `b5f3b28f...` (100%) e substituído por R13. A R13 veio do commit Services/Storage `b3ad8940a4023684a97453c22d0496d46c756687`, com closeout `f870560fa14053a7ae6628f3fd713f57e9b55c02`; QA de 36 verificações JS, 7 SQL e build Worker PASS, leitura externa Storage/Núcleo PASS. A fonte e closeout estão no Git Storage; **não confundir publicação Web/Cloudflare com push da fonte R13 ao GitHub Web**.

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
3. **Não refazer R12–R15:** R15 é a versão ativa, D1 0036 permanece. Se houver problema, usar o recibo R15 e rollback imediato R14 `2b8de065...`; teste real destrutivo só na sessão autenticada e com confirmação explícita do operador.
4. Aguardar VMs com Agents pareados ao REVIEW; executar testes reais 5+3, vídeo, preencher OpenAI e só então submeter.
5. Distinguir confirmação **Git local Services → Git Storage → GitHub Web**; registrar SHAs. Comunicação entre hosts só via rede, nunca ressuscitar USB Link aposentado.