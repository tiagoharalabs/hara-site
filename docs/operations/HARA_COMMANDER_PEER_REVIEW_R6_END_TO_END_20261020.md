# HARA Commander — revisão R6: resultado ponta a ponta e recuperação após prazo

Data: 2026-10-20. Revisor: Valky. Continuação solicitada por Tiago, somente pelo MCP HARA Commander.

## Escopo e coordenação

Executor permanece em `codex/commander-prelaunch-fixes-20261020`. Esta entrega entra na branch documental de revisão já existente, não cria executor concorrente nem altera o código/índice da frente.

Fonte fixa examinada: `97a35d9bde706db66e4c3a5645cefce083dc08c6`, extraída por `git archive` para `/tmp/hara-commander-peer-r6-20261020-u70bgjaj/source`; 367 arquivos com SHA-256. O conteúdo em edição posterior do Codex não foi usado silenciosamente como se estivesse commitado.

Esta rodada conecta funções reais de Agent, outbox, SQL de conclusão, projeção pública e montagem da resposta MCP. Usa subprocesso por stdin/stdout, autenticação substituída por uma identidade QA, relógio sintético, SQLite em memória e HOME/XDG temporários. Não usa rede real, conta/credencial real, listener HTTP ou arquivos de cliente; não reinicia nem instala Agent. Não é teste de carga, D1 hospedado, Windows nem validação do SDK HTTP completo.

## O que passou independentemente

Reexecutei na mesma cópia fixa:

- `validate_result_delivery_outbox.py`: exit 0; reenvio preserva resultado/recibo, reinício e duplicata não repetem a mutação.
- `validate_result_envelope_budget.py`: exit 0; orçamento de bytes do Agent passa para 1/4/10 arquivos e escapes.
- `test_device_call_usage_settlement.mjs`: exit 0; conclusão sem cliente, falha do DO/retry, recuperação após TTL e negação sem execução.

Os hashes dos 367 arquivos-fonte permaneceram iguais. Logo os achados abaixo não apagam o avanço R4; expõem contratos entre componentes que os testes separados ainda não cobrem.

## R6-OUTBOX-LATE-01 — conclusão tardia pode manter todo o Agent sem aceitar novas tarefas

**P0 de recuperação antes de promover o candidato. Reproduzido em integração local.** O limite de conclusão após prazo já está reconhecido no PROGRESS.md; esta revisão acrescenta a consequência de fila e a reprodução conjunta Agent/Worker, não apresenta o limite como descoberta inédita.

Sequência reproduzida:

1. Servidor QA tem chamada EXECUTING com prazo normal de 50 s.
2. Agent executa `filesystem.write` real sobre arquivo descartável; efeito ocorre uma única vez e o resultado fica READY na outbox local.
3. A primeira transmissão é interrompida **antes de o servidor receber**. Avançamos o relógio QA 51 s, sem esperar nem derrubar rede real.
4. Reenvio chama `completeDeviceCall()` real com schema/migrações reais. Primeiro recebe DEVICE_CALL_EXPIRED e grava EXPIRED; os seguintes recebem DEVICE_CALL_NOT_EXECUTING.
5. `flush_completion_outbox()` deixa READY indefinidamente nesse caminho; o guard real de `drain_durable_calls()` devolve EVENT_V2_RESULT_DELIVERY_PENDING e não chega a solicitar nova tarefa.

Observado: três reenvios entregaram zero resultados; pendência permaneceu 1; execução local permaneceu 1; tentativas de buscar novas tarefas = 0. Nenhuma confirmação falsa e nenhuma segunda escrita foram produzidas — são propriedades corretas a preservar.

**Controle positivo:** quando o servidor recebeu e aceitou a conclusão antes da interrupção, mas sua resposta se perdeu, o reenvio depois do prazo funcionou: uma execução, outbox vazia. Não confundir perder o ACK com perder a transmissão inteira.

Direção de correção:

- contrato explícito para conclusão tardia autenticada, vinculada à chamada já reclamada, dispositivo/tenant, resultado e recibo; manter o fato de ter passado do prazo e não inventar um sucesso tempestivo;
- diferenciar prazo para iniciar/esperar da retenção e aceitação da evidência de execução;
- reconciliar resultado válido tardio sem repetir ação, sem desfazer revogação/cancelamento de operação ainda não iniciada e sem aceitar recibos estrangeiros;
- caminho explícito para conflito definitivo, revogação ou identidade alterada: quarentena/diagnóstico e recuperação autorizada, preservando evidência. Não apagar READY nem remover o guard apenas para obter PASS;
- evitar retry permanente de erro terminal e bloqueio invisível do computador. Retry/backoff para falha transitória precisa de status visível e orçamento.

Aceite mínimo: antes do prazo; primeira transmissão perdida por mais de 50 s; ACK perdido após aceite; identidade/recibo divergente; resultado já redigido; revogação; cancelamento antes de iniciar; reinício; duas conclusões iguais; recuperação de outra tarefa segura após reconciliação. Cota deve acompanhar o resultado durável sem dupla contagem. Caso de estado realmente incerto continua UNKNOWN, não sucesso nem autorização para reexecutar.

## R6-PROJECTION-02 — leitura cabe no Worker, mas é cortada como texto na resposta pública

**P1 funcional alto; impede uso confiável de leitura múltipla. Reproduzido.**

O orçamento novo do Agent limita `read_many` a aproximadamente 96 KiB, abaixo dos 256 KiB aceitos por `completeDeviceCall`. Porém `projectCustomerToolResult()` passa o JSON interno de `result.stdout` para `trimPublicText()`, que corta após 65.536 caracteres e acrescenta um marcador textual. Isso pode cortar o JSON no meio.

Usei `execute_tool/filesystem_read_many` reais, fixtures de 100 linhas por arquivo, depois as funções públicas reais `projectCustomerToolResult`, `trimPublicText` e `publicToolResult` extraídas do código:

| Arquivos | Envelope do Agent | stdout antes | stdout após projeção | JSON interno parseável no cliente |
| --- | ---: | ---: | ---: | --- |
| 1 | 60.724 bytes | 60.226 caracteres | 60.226 | Sim — controle positivo |
| 4 | 97.985 bytes | 97.357 caracteres | 65.570 | Não |
| 10 | 97.990 bytes | 97.226 caracteres | 65.570 | Não |

Os tamanhos podem variar alguns bytes conforme o caminho temporário. Nos casos quebrados, estado externo permanece PASS, `isError` não é marcado, e `structuredContent.result.stdout` contém a mesma string cortada. **O JSON externo MCP permanece válido**; o erro é no JSON de resultado encapsulado em stdout, que perde estrutura e os offsets de continuação que estariam na parte removida. Não alegar corrupção do protocolo inteiro.

Isso explica por que o teste de bytes do Agent passa mas o resultado que a ferramenta entrega ainda pode ser inutilizável.

Direção de correção:

- tratar payload estruturado como estrutura até a entrega final; não usar corte cego de caracteres sobre JSON;
- orçamento compatível no Agent, endpoint, projeção, perfil simples/completo e Event V2; bytes UTF-8, escape JSON e metadados contam;
- paginação por arquivo/resultado com offsets preservados, indicação estruturada de incompleto e motivo; não remover silenciosamente itens ou modificar o significado de recibos;
- manter limite de segurança — simplesmente eliminar limite ou aumentar todos sem medir não é a solução;
- testar `JSON.parse(structuredContent.result.stdout)` quando esse for o contrato vigente, e não apenas o resultado interno anterior à projeção. Uma futura resposta estruturada direta precisa de compatibilidade documentada.

Aceite: 1/4/10 arquivos, 65.535/65.536/65.537 caracteres de resultado, emojis/controles, metadata grande, erro por item e continuação completa sem reexecutar uma operação. Testar também resultado de terminal encapsulado em JSON, sem duplicar o gap R5 de one-shot descartado.

## Provas entregues

`docs/evidence/commander-peer-review-r6-20261020/` contém:

- `peer_end_to_end.py` e `peer_worker_bridge.mjs`: reprodução sem serviços externos; saída 2 significa achados reproduzidos.
- `r6-results.json`: controles positivos, casos negativos, tamanhos e hashes dos componentes.
- `existing-tests.json`: três suítes anteriores reexecutadas com exit 0.
- `snapshot.json`: commit e hashes dos arquivos examinados.
- `REPRODUCE.md` e `SHA256SUMS`: instruções e integridade.

A primeira tentativa de montar o harness teve um erro de sintaxe na fixture JavaScript do revisor, corrigido antes de produzir estas evidências. Não era erro do produto e não foi contado como achado. Após o ajuste, a suíte final reproduziu os dois cenários, com zero tentativas reais de rede e sem alteração dos fontes.

## Integração na fila

Preservar as correções R4 e finalizar o WIP atual com checkpoints. Priorizar R6-OUTBOX-LATE-01 antes de promoção; R6-PROJECTION-02 junto do aprimoramento de leitura/respostas R5. Não criar uma segunda outbox, um terceiro protocolo de resultados ou outra superfície paralela. Reutilizar as estruturas existentes e acrescentar testes de ponta a ponta.

A revisão não autoriza deploy, migração remota, acesso a chaves, upgrade de Agents ativos nem cobrança. Quando corrigido, demonstrar os dois controles positivos ainda passando e os casos negativos agora recuperados, mantendo o estado do resultado verdadeiro.

## Revalidação contra o avanço mais recente

O Codex avançou para `e4e2c0042fa17e662488a345cd597e6a16f4fdeb`, acrescentando arquivo histórico de conclusões. Como completeDeviceCall mudou, não assumi que a reprodução antiga continuava válida: extraí esse commit em outra cópia e executei novamente a integração. Ambos os achados reapareceram, com exit 2, zero rede real e controle positivo de ACK perdido passando. Resultado em `latest-rerun.json`, mantendo a coleta de 97a35d9 intacta.
