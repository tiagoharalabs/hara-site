# HARA Commander — R5: uso real das funções e entrega Git das políticas

Data: 2026-10-20, observações iniciadas 19:52 UTC. Revisor: Valky.

## Estado de entrega e coordenação

O executor permanece em `codex/commander-prelaunch-fixes-20261020`, clone `/home/sartorius/hara-workspaces/commander-prelaunch-fixes-20261020`. **Não trocar sua branch nem interromper o WIP.**

Esta entrega documental usa clone e índice próprios: `/home/sartorius/hara-workspaces/commander-dogfood-r5-review-20261020`, branch `review/commander-functions-r5-20261020`, base `27a4520ef06711ed8abb0ef52246e1082f77b702`. Ela contém políticas e QA, não implementação concorrente. Integrar somente o commit documental por cherry-pick/reconciliação no momento seguro; não fazer merge cego de base antiga e não reabrir R2/R3/R4 já corrigidos.

Na inspeção inicial, as duas políticas anteriores existiam nos arquivos do executor e no inbox, mas ainda apareciam `??` em `git status`; não estavam commitadas. Esta entrega as coloca efetivamente no Git isolado, sem usar o índice do Codex:

- HARA_COMMANDER_PRIMARY_OPERATIONAL_POLICY_20261020.md
- HARA_COMMANDER_FUNCTIONAL_IMPROVEMENTS_20261020.md

São preservados integralmente seus hashes anteriores. A política mantém HARA Commander primário e Desktop Commander fora do fallback automático; não altera o modelo comercial nem autoriza deploy.

## Teste pelo MCP real — não apenas inspeção de código

Ferramentas foram invocadas diretamente por H.A.R.A._Commander em `nucleo-a`, conta Founder. Fixture exclusiva: `/tmp/hara-commander-dogfood-r5-20261020-1953`. Nenhum arquivo do cliente, processo real de trabalho, Agent, banco ou serviço foi substituído. Sessão interativa QA terminou naturalmente com exit 0. Apenas um arquivo-cópia QA foi excluído com preimagem e hash.

| Função/cenário | Resultado observado |
| --- | --- |
| create_directory e write_file | Diretório novo e fixture Unicode de 12 linhas criados; SHA-256 retornado. |
| read_file em três páginas de quatro linhas | Offsets 0→4→8; última página eof=true. A página intermediária precedeu a edição de L05, portanto não é teste de snapshot imutável entre alterações. Unicode preservado. |
| edit_block com trecho duplicado | Recusou EDIT_MATCH_AMBIGUOUS; não escreveu conteúdo QA indesejado. |
| edit_block com hash antigo/incorreto | Recusou FILE_PRECONDITION_FAILED; depois a edição única com hash correto funcionou e retornou preimagem/hash novo. |
| search content em duas páginas | Encontrou MARKER_DUP nas linhas 3 e 6, sem repetir a primeira ocorrência; next_offset 1 e depois null. |
| read_multiple_files com arquivo existente + ausente | Sucesso do arquivo existente e FAILED/FILENOTFOUNDERROR por item ausente; chamada externa PASS, não sucesso de todos os arquivos. |
| copy_file → move_file → delete_file | Cópia conservou SHA; renomeação não sobrescreveu; exclusão com expected_sha256 conservou preimage_id. Arquivo original preservado. |
| get_file_info | Tipo, tamanho e data presentes; nenhum hash/etag no retorno examinado. |
| start_process interactive + interact_with_process + read_process_output | Entrada `ação 🍵 confirmada` voltou íntegra como resultado do programa; resposta imediata da interação continha apenas eco, leitura posterior trouxe resultado e exit 0. |
| start_process one-shot, oito linhas e max_lines=3 | Retornou três linhas, total_lines=8, output_truncated=true e session_retained=false. Tentativa de continuar pelo run_id foi recusada com PROCESS_SESSION_NOT_FOUND. |

Hash da fixture após edição e leitura final: `83fb5e3dddecf8b6d74fb73adfde595e716bdf9ddf59aab2e7ecdca8bb267862`. A integridade final foi lida independentemente por comando curto via o próprio HARA. Recibos das chamadas relevantes estão em `docs/evidence/commander-dogfood-r5-20261020/observations.json`.

## R5-F01 — saída de tarefa curta truncada não pode ser recuperada

**Gap funcional reproduzido no MCP ativo; prioridade P1 de usabilidade.** Não é nova perda da cauda PTY R3: aqui o buffer existia, mas foi descartado ao encerrar o caminho one-shot.

Comando artificial de oito linhas, `max_lines=3`, exit 0. Recebemos R5-LINE-00/01/02. O run_id não serviu para recuperar as cinco restantes: PROCESS_SESSION_NOT_FOUND. `process_run()` na base 27a4520 ainda retorna `session_retained=False` e faz `PROCESS_SESSIONS.pop` no final. Portanto o gap também está na base candidata examinada.

Melhoria: quando a saída exceder o envelope, disponibilizar identificador/cursor de resultado com retenção limitada e TTL, ou log local limitado consultável. Não manter sessões/procs vivos só para guardar texto, não crescer memória sem limite e não exigir executar o comando de novo. Descartar apenas por política explícita e responder `RESULT_EXPIRED`/estado equivalente quando terminar a retenção, não sugerir que a tarefa nunca existiu.

Aceite: saída de 8 linhas solicitada em páginas de 3 recuperada sem repetir execução; comando mutante com contador local continua produzindo efeito exatamente uma vez; limite de bytes/memória/TTL; expiração e isolamento por dispositivo/usuário. Preservar a simplicidade do one-shot para resposta pequena.

## R5-F02 — operações de hash/recuperação existem no código mas não nesta superfície conectada

**Diferença comprovada entre código/capacidades e as ferramentas disponíveis nesta conversa. Causa não diagnosticada.**

`get_config(nucleo-a)` anuncia ferramentas internas como `hara.files.hash`, `hara.files.preimages.list`, `hara.files.rollback` e `hara.receipts.get`. O módulo `customer-mcp-simple.mjs` na base 27a4520 também lista `hash_file`, `diff_files`, `list_file_preimages`, `rollback_file`, `get_receipt`, entre outras.

Entretanto, a descoberta completa do conector H.A.R.A._Commander neste chat apresentou **24 ferramentas** e não incluiu esses nomes. Não concluir que o backend não implementa: pode ser contrato do plugin, versão exposta, seleção da conexão ou ferramenta fora do conjunto disponível ao cliente. Esta auditoria não alterou o plugin nem suas permissões.

Impacto concreto: a edição/exclusão gera preimage_id, mas aqui não existe uma ferramenta nativa de listar/restaurar essa preimagem; para editar um arquivo que só li, `read_file` e `get_file_info` tampouco me dão um hash utilizável em expected_sha256. Posso obter por comando, mas isso adiciona atrito e necessidade de execução para uma tarefa de arquivos.

Melhoria: reconciliar contrato publicado, tools/list e ferramentas efetivamente entregues ao cliente. Expor capacidades já implementadas, com grants/consentimento preservados, em vez de duplicar novas implementações. Considerar hash/versão opcional no retorno de leitura/metadados, associado aos bytes realmente lidos, sem impor cálculo integral caro a todo arquivo. A inclusão de ferramentas no plugin/conexão deve ser promovida pelo fluxo adequado; não muda runtime de autorização.

Aceite: editar arquivo pré-existente com precondição sem shell; listar preimagem, mostrar diff e restaurar apenas o arquivo QA, com CAS/recibo; cliente sem grant recebe negação; nenhuma restauração de arquivo real nesta auditoria.

## R5-F03 — contrato de resultado pode economizar chamadas e interpretação

**Melhoria de UX/contrato, não falha de dados demonstrada.**

A interação devolveu primeiro eco PTY e exigiu nova leitura para obter a resposta efetiva. Isso é compatível com a descrição atual, mas a ferramenta pode facilitar o fluxo retornando indicação explícita de eco/progresso/continuação ou oferecendo espera limitada por saída nova, sem prometer distinguir universalmente eco e saída sem suporte do terminal.

Em read_multiple_files, um item falhou e o envelope foi PASS. O erro por item está presente, portanto não é ocultação; recomendar também `successful_count`, `failed_count`, `overall_status=PARTIAL`, com compatibilidade e sem fazer exceção do lote inteiro. Muitos resultados vêm como JSON dentro de `stdout` dentro de outro JSON; avaliar retorno estruturado consistente para reduzir parsing e redundância, preservando recibo e distinção transporte/comando/domínio.

As negações esperadas de edição vieram com `operational_authority=LOCAL_OPERATOR_SESSION` mesmo quando a causa é ambiguidade ou CAS, não aprovação. Melhorar categoria e orientação do erro para que o cliente não tente liberar permissões indevidamente. Manter os códigos corretos existentes.

## Próximos passos para o executor

Concluir a frente R4/retention em andamento. Em seguida priorizar R5-F01 e reconciliação da superfície R5-F02; aproveitar testes existentes e registrar benefício antes/depois. Não abandonar correções de autenticidade, cotas e recuperação por causa de melhorias de UX.

Registrar recebimento deste pacote e o SHA do commit documental. A branch `review/commander-functions-r5-20261020` é apenas entrega/revisão; o executor continua em `codex/commander-prelaunch-fixes-20261020`.

O uso real desta sessão comprova as funções e cenários descritos, não milhões de transações, homologação Windows ou instalação do candidato. Os Agents ativos continuam na versão previamente instalada. Nenhum teste foi lançado em massa e nenhum serviço produtivo foi reiniciado.
