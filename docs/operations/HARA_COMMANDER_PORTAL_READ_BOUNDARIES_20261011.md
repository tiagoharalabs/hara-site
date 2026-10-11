# Commander — leituras limitadas do portal, 11/10/2026

## Estado desta entrega

Implementação local em `local/commander-product-current`, sobre a base `b1258ec0dfbff096e604a60fe10504f015db696f`. Não houve deploy, migração em produção, nova coleta Cloudflare nem homologação de clientes simultâneos nesta rodada. O commit que contém este documento identifica o checkpoint, caso o registro Git seja concluído; os relatórios de testes conservam o HEAD-base anterior.

## Código acrescentado nesta rodada

- Leituras GET comuns do portal usam leitura incremental de bytes, com limite padrão de 2 MiB por resposta. O cabeçalho de tamanho permite recusa antecipada, mas o limite é aplicado também aos bytes efetivamente recebidos. Respostas excessivas são rejeitadas, não truncadas silenciosamente. Downloads, chamadas externas/localhost e solicitações com opções personalizadas mantêm o caminho nativo.
- Cancelamento fecha o leitor também quando o prazo vence antes de ele ser criado. A leitura deixa de ocupar a entrada de requisições pendentes após conclusão ou falha. Não há repetição automática de ações.
- Opções diferentes de cache não compartilham uma leitura. Opções personalizadas de redirecionamento, integridade, modo e outras políticas preservam a chamada original, sem compartilhamento.
- A invalidação no início e na conclusão das alterações, implementada na rodada anterior, permanece preservada.

O teto se aplica ao corpo de cada resposta coordenada. Não representa limite da memória total do navegador ou do servidor e não limita o número de usuários. Deve ser homologado com os maiores payloads reais antes de promoção; uma conta que exceda o teto requer paginação ou ajuste explícito, não descarte de dados.

## Evidência executada no Services

- Teste novo `test_portal_read_boundaries.mjs`: 12 casos. Antes da correção: 3 PASS e 9 FAIL. Depois da correção: 12 PASS e 0 FAIL, sem HTTP externo.
- Coordenador existente `test_portal_read_coordinator.mjs`: 22/22 casos PASS; seu teste de prazo do corpo passou a usar um ReadableStream real no simulador.
- Bateria geral: 68/68 validadores PASS, com 1.000 tentativas e 24 threads nos cenários SQLite já existentes. Os 22 casos anteriores integram essa bateria; os 12 casos novos foram executados separadamente e ainda não estão integrados ao gate.
- Cinco hashes de arquivos centrais coincidiram antes/depois da bateria. Isso é uma comparação de arquivos, não um build imutável nem atestado de produção.

Evidências no Services: `/tmp_hara/commander-partial-advances-20261011-portal-r2/`. O relatório `full-gate.json` contém os 68 resultados individuais. Os relatórios `boundaries-before.json`, `test_portal_read_boundaries.mjs.final.json` e `test_portal_read_coordinator.mjs.final.json` preservam os casos e hashes.

## Limites e trabalho não integrado

Uma tentativa de integrar um novo registrador de hashes ao gate foi bloqueada pela ferramenta. O gate não foi alterado nesta rodada; os dois arquivos de rascunho desse registrador foram retirados da árvore de fontes e preservados apenas na pasta de evidências. Não foram executados nem apresentados como entrega validada.

Sem alteração de preços, regras de autorização, agentes assinados, lista Founder, serviços da frota ou CSS. A divergência de versões em produção, a medição completa do custo e os testes reais de escala continuam sem encerramento nesta entrega.
