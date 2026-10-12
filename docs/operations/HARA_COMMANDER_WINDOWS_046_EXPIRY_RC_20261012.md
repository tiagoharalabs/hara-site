# H.A.R.A. Commander — Windows 0.3.46-v6 RC: aprovação com expiração correta

Data da execução: noite de 11/10/2026, America/Sao_Paulo; evidências UTC de 12/10/2026. Base Git: `bf91d52394b457fd7f0cfc76f786ab58ff2d0559`. Desenvolvimento em branch isolada `local/commander-win-consent-expiry-20261012`.

A janela Windows 0.3.45 podia ficar bloqueada em `Read-Host` depois de o Agent expirar a solicitação. Uma resposta tardia exibia `CONCEDIDA` e deixava um arquivo obsoleto, embora a ação fosse recusada pelo Agent. A 0.3.46 encerra a espera no prazo, descarta a entrada vencida e publica somente uma resposta ainda vinculada ao pedido e ao operador. O aviso `ENVIADA` informa submissão; o resultado da ação e seu recibo comprovam execução.

## Implementação

- Entrada local não bloqueante, com polling de 100 ms apenas durante a solicitação, limite de entrada e Enter para negar. Console indisponível ou entrada redirecionada falham fechados.
- Mutex compartilhado coordena publicação, consumo e limpeza. Nonce, request, ferramenta, SHA dos argumentos, prazo, PID e início do operador são revalidados. A limpeza não remove arquivos de outro pedido.
- Criação e remoção da sessão usam o mesmo mutex. Depois do aceite e da limpeza, o Agent reconfirma a sessão antes de autorizar a primitiva. A compilação do wrapper de processos ocorre antes de solicitar consentimento.
- `ASK_EVERY_ACTION` e prazo de 30 segundos preservados. Nenhuma aprovação automática foi adicionada. Encerrar a sessão revoga novas ações; não é promessa de cancelar uma ação que já começou.

## Validação

| Prova | Resultado | Limite |
|---|---|---|
| Commander direto: Windows info/config/sessions | PASS; 0.3.45 inicial e 0.3.46 após canário, zero sessões | Leitura não comprova mutação aprovada |
| Commander direto: terminal Linux interativo | PASS; entrada recebida, exit 0, 120/120 linhas após saída | Ensaio no Services |
| Commander direto: UTF-8 e escrita CAS | PASS; SHA correto escreve, SHA antigo recusa sem efeito | Fixture sintética removida com SHA atual |
| Windows real PS5.1, fonte final r3 | 93/93 PASS | Fixture isolada, sem transporte nem aceite humano real |
| Guard de fonte candidata | 25/25 PASS | Verificação estática complementar |
| Revisão independente da fonte final | PASS | Não substitui canário mutante |
| Assinatura da RC v6 e escopo dos assets | PASS; RS256/RSA3072, autoridade v2 | RC privada |
| Gate completo offline | 91/91 PASS | Não certifica escala ou aprovação humana |
| Timeout real pelo Commander direto após canário | PASS_CLEANUP_ONLY; nenhuma ação, pedido e resposta limpos | Não comprova aceite humano |
| Aprovação humana positiva Windows pelo MCP direto | PENDENTE; chamada expirou sem aceite | Exige digitação na janela local |

A r3 cobre silêncio, entrada parcial, Enter tardio, troca de nonce/pedido/sessão, publicação concorrente, resposta malformada, booleano inválido, timestamps incorretos, limpeza preservando pedido seguinte e revogação/substituição da sessão após limpeza. As r1/r2 são evidências históricas de versões intermediárias do patch.

Fonte final e Agent assinado: `71998b7c5e2dae4f4cbcfe80e5413ab1c6ff8e28ad903734cc1f026dfe8765aa`. Harness r3: `0090403b69733e942af1553a298591ece3bef75bc8d21a2c65474f7dd1c7fded`. Manifesto v6: `ac16e30b51cee8a01b6b122939c11a15fde8897b24ee04cdc0f68bd5f4dcfcf7`.

Bundle: `apps/commander/release-bundles/commercial-0.3.46-v6-rc/`. Releases v3/v4/v5 preservadas byte a byte; Linux Agent e instalador são idênticos à v5. O instalador Windows muda somente três âncoras de versão. O validador v5 passou a validar seu bundle histórico imutável; a igualdade da fonte ativa com a assinatura é obrigatória no novo validador v6. O gate completo executa ambos, além do guard de expiração.

## Evidências e continuidade

Evidências Windows em `docs/evidence/commander-win-consent-expiry-20261012/`; probes diretos Linux/Windows em `docs/evidence/commander-win46-consent-20261012/direct-product-readback.json`. Chamadas da superfície Baseline não integram as provas diretas deste documento. Os ensaios Windows por QGA são testes de laboratório; não representam execução mutante Windows pelo MCP comercial.

A listagem pelo Commander direto marcou Sentinela C e Ninja Blue como OFFLINE; isso descreve o canal/presença do produto e não prova máquina desligada. Nenhuma reinicialização dessas máquinas foi realizada.

O canário privado v6 foi aplicado na VM: Agent 0.3.46 assinado, backup v5 verificado, configuração e definição da tarefa byte a byte preservadas. Uma resposta NEGADA órfã da chamada antiga foi correlacionada com o registro FAILED/EXPIRED, custodiada e reconciliada sem gerar aceite. A tarefa e o operador mudaram enquanto o diagnóstico estava em curso; a origem dessa mudança não foi atribuída sem evidência.

Depois da troca, `device.info` e `process.sessions` passaram pelo Commander direto. Uma chamada `hostname` expirou sem confirmação; a inspeção posterior confirmou pedido e resposta limpos, operador ativo e tarefa Running. A captura enviada pelo usuário mostrou a janela H.A.R.A. Commander - Sessão e o pedido de aprovação. A busca pela caption exata da versão não havia localizado essa janela; foco e digitação correta não foram comprovados. Aprovação positiva, escrita e terminal Windows mutantes via MCP ainda pendentes. A v6 não foi publicada no Cloudflare por esta frente; Stripe e outros tenants não foram alterados.

Próxima prova: confirmar que o console local 0.3.46 está visível e em primeiro plano, uma chamada `hostname` pelo Commander direto e aprovação manual do desafio local. Depois: escrita sintética com SHA, terminal gerenciado/interação/saída, negação e recuperação, cada ação com seu próprio consentimento. Não repetir escrita após timeout sem reconciliar o estado.

Alterações não commitadas das outras frentes foram inventariadas por SHA e devem permanecer intactas. Publicação Git deve incluir somente os arquivos desta frente; nunca staging global, limpeza ou force-push.

## Atualização posterior: canal retomado e RC .47

A chamada `HARA-CALL-4ea93468-2003-4c58-928f-9ce6911c378a` recebeu recusa local após entrada incompleta (`APROVAR` sem o código), mas ficou sem conclusão no produto e deixou IPC órfão. O Commander confirmou posteriormente EXPIRED/DEVICE_CALL_EXPIRED às 04:17:35.456Z. A causa da interrupção original segue desconhecida. Um teste adicional de cadeia completa em PS5.1 passou 26/26: recusa, DENIED, CompleteCall FAILED e limpeza, com transporte simulado.

Foi encontrado separadamente um bug reproduzível: repetir start com console ativo e tarefa Ready retoma e imediatamente pára a tarefa. A correção será validada na RC .47, sem alterar os bytes congelados do bundle .46. A reconciliação exata dos IPC expirados e a retomada da tarefa existente preservaram configuração, XML, operador e ASK_EVERY_ACTION; as leituras comerciais seguintes passaram. Novo hostname às 04:46:22Z expirou e concluiu FAILED/LOCAL_ACTION_APPROVAL_EXPIRED às 04:46:53.284Z, com limpeza local comprovada.

Ver [continuidade e validação .47](HARA_COMMANDER_WINDOWS_047_LIFECYCLE_RC_20261012.md). A aprovação humana positiva permanece pendente até existir comando executado e recibo correspondente pelo plugin comercial.
