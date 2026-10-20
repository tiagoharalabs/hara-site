# HARA Commander — revisão independente R4: resultado, tamanho e contabilização

Data: 2026-10-20. Revisor: Valky. Continuação autorizada pelo proprietário.

## Recebimento anterior e escopo desta rodada

Confirmei no PROGRESS.md que R3 foi **recebida e lida**. A correção de continuidade da fila já está em `72c6820cb6450253818b22f57dd2d080477894d3`; a R2 foi consolidada em `0732c0376719455b32a6dfaa8cf67d7d5dc6dc7d`. Não reabrir itens já corrigidos sem nova reprodução.

Esta revisão usa uma cópia imutável extraída de `0732c0376719455b32a6dfaa8cf67d7d5dc6dc7d` em `/tmp/hara-commander-peer-r4-20261020-9nw7kee4/source`, com 358 arquivos e hashes. Em nova leitura após `72c6820`, as funções `execute_call`, `complete`, `filesystem_read_many`, `filesystem_read`, `completeDeviceCall` e `boundedJson` estavam iguais às examinadas (AST para Python, texto para JS). Não confundir o autoteste Linux já corrigido com os achados abaixo.

Não alterei código do produto, branch, índice Git, Agents ativos, banco remoto, assinatura ou cobrança. Testes em HOME/XDG temporários, banco SQLite em memória, transporte simulado e arquivos artificiais. Nenhuma credencial real utilizada. As escritas reais foram apenas os arquivos QA descartáveis, evidências e esta nota.

## R4-DELIVERY-01 — execução bem-sucedida vira "não alterou nada" quando o envio do resultado falha

**Prioridade P0 de correção antes de lançamento amplo. Reproduzido.**

Fonte: `apps/commander/public/agent/linux.py`, `execute_call()` e `complete()`.

Teste independente executou o `execute_call` e o `execute_tool/filesystem_write` reais com um arquivo temporário. Somente a camada de envio de conclusão e a autorização da fixture foram substituídas. A primeira tentativa de notificar `COMPLETED/PASS`, com `mutation_performed=true` e recibo, lança uma falha de conexão simulada antes do reconhecimento pelo servidor. O mesmo `except` que trata erros de execução então envia uma segunda conclusão:

```text
primeiro envio: COMPLETED / PASS / mutation_performed=true / recibo presente
segundo envio: FAILED / DENIED / mutation_performed=false / recibo ausente
arquivo QA: existe e contém REAL_QA_WRITE_COMPLETED
```

Isso não é uma invasão nem uma falha de rede real provocada. É a demonstração de que o código confunde **falha ao entregar o resultado** com **falha antes de executar**, podendo informar falsamente que uma alteração não ocorreu. A operação local ocorreu uma única vez no teste.

Correção recomendada, sem reimplementar outro executor:

- separar exceções de execução, persistência do resultado e envio de confirmação;
- persistir a conclusão exata/recibo antes de tentar transmiti-la, com reenvio idempotente e limite de tamanho/retenção;
- falha de entrega não pode gerar `DENIED` nem `mutation_performed=false` se a mutação já ocorreu;
- diferenciar falha antes do envio, resposta de aceite perdida e resultado de execução incerto;
- não repetir uma mutação às cegas. Reconciliar pelo mesmo identificador e preservar o resultado já produzido.

Aceite: arquivo escrito e resposta perdida; resposta perdida após aceite; reinício antes/depois de persistir conclusão; falha repetida; eventual envio com mesmo recibo e **efeito único**. Servidor não pode rebaixar COMPLETED para FAILED; cliente não pode receber falsa garantia de ausência de alteração.

## R4-RESULT-SIZE-02 — limites de cada arquivo não limitam a resposta total

**Prioridade P1 de funcionalidade/qualificação. Reproduzido no Agent e no validador real do Worker.**

A ferramenta anuncia até dez arquivos e cem linhas por arquivo. Dez arquivos QA de 60.000 bytes cada passaram individualmente pelo `filesystem_read_many` e pelo `execute_tool`. O envelope efetivo resultou em **604.521 bytes**. `completeDeviceCall()` real recusou esse resultado com `DEVICE_CALL_RESULT_INVALID`, pois aceita até **262.144 bytes**.

Um arquivo artificial com caracteres de controle não-NUL, aceito pela leitura, resultou em **420.770 bytes** após o escape JSON, mesmo com entrada de 60.001 bytes. O endpoint também recusou. Não usamos dados reais do usuário.

A exceção por tamanho ocorre na entrega do resultado e hoje entra no mesmo problema R4-DELIVERY-01, embora neste caso a leitura não seja mutante.

Direção de correção:

- orçamento do envelope **serializado** completo, incluindo UTF-8, escape JSON e metadados;
- orçamento agregado para `read_many`, com continuação por arquivo e sem perder/avançar linhas não devolvidas;
- nunca truncar um JSON no meio nem devolver estrutura inválida;
- evitar aumentar cegamente os limites, pois Worker, canal Event V2, Agent e MCP possuem fronteiras diferentes;
- testar 1/4/10 arquivos, linhas longas, Unicode, controles, resposta do processo e um byte abaixo/acima de cada limite.

Subcaso de entrada R4-REQUEST-SIZE-02C: o esquema MCP permite string com 65.536 caracteres. No `boundedJson` real, conteúdo ASCII desse comprimento produziu 65.588 bytes e passou; texto CJK do mesmo comprimento produziu 196.660 bytes e foi rejeitado pelo limite de 131.072 bytes. É desalinhamento de contrato/UX, não corrupção de dados demonstrada. Expor orçamento em bytes e validar antes de enfileirar/autorizar a operação.

## R4-QUOTA-03 — conclusão normal fica dependente do cliente para fechar a contabilização

**Prioridade P1 comercial/consistência. Reproduzido em SQLite com classe TenantQuota e completeDeviceCall reais.**

Teste: reservar uma unidade CLOUD_QUOTA, persistir chamada EXECUTING, receber resultado COMPLETED com recibo válido e **não executar a consulta/commit do cliente** (equivale a chamador que desapareceu). O caminho normal (`approval_timeout_seconds=0`) persistiu COMPLETED no banco de chamadas, mas deixou a unidade RESERVED. Depois de 601 segundos simulados, a unidade passou para RELEASED/0.

Controle positivo: com o ramo assíncrono (`approval_timeout_seconds=900`) a mesma função fecha a unidade em COMMITTED/1 e ela permanece assim após o avanço do relógio. Esse controle exercita a ramificação do código, não homologa Windows real.

```text
chamada normal concluída: banco=COMPLETED; quota=RESERVED → RELEASED/0
controle assíncrono: banco=COMPLETED; quota=COMMITTED/1 → COMMITTED/1
```

Confirmei que a manutenção de redação também chama `settleCallUsage()` apenas para o ramo 900 na fonte examinada. Não foi induzida desconexão real na Cloudflare.

Correção recomendada: contabilizar a conclusão medida uma única vez a partir de resultado/recibo durável, independentemente da conexão do cliente. Reusar a liquidação existente com retry/outbox/reconciliador crash-safe; D1 e Durable Object são duas autoridades persistentes e uma chamada entre eles pode falhar. Não cobrar duas vezes, não liberar consumo concluído, não devolver cota porque o cliente sumiu e não converter resultado incerto em sucesso. Medição serve ao limite de chamadas; o preço segue fixo em R$80/mês, sem cobrança por transação.

Aceite: callee conclui/cliente desconecta; falha temporária DO após gravação D1; reentrega do mesmo recibo; virada de período; reservas vencidas com execução comprovada e sem execução comprovada; saldos conservados e idempotência.

## Provas e reprodução

Evidências desta rodada: `docs/evidence/commander-peer-review-r4-20261020/`.

- `peer_agent_delivery.py`: usa Agent real, HOME/XDG temporários e fixtures. Exit **2** significa achados reproduzidos, não suite aprovada.
- `peer_worker_accounting.mjs`: classe TenantQuota e funções Worker reais extraídas; todas as 37 migrações em SQLite em memória, rede proibida. Exit **2** significa achados reproduzidos.
- `agent-delivery-results.json` e `worker-accounting-results.json`: resultados, limitações e hashes de fonte.
- `snapshot.json`: commit fixo e hashes dos arquivos; copiar os scripts para novo diretório temporário e extrair `git archive` da mesma base em `source/` para reproduzir sem disputar código editado.
- Os JSONs grandes de resposta são fixtures geradas pelo primeiro script; não precisam ir ao Git e não contêm dados de cliente.

Comandos em cópia QA isolada:

```bash
python3 -B peer_agent_delivery.py
node --disable-warning=ExperimentalWarning peer_worker_accounting.mjs
```

O segundo comando requer Node com `node:sqlite` (na coleta, Node local 24.15.0). Não executar testes apontando HOME/XDG de produção; o script Python já cria seu ambiente descartável.

## Orientação para a frente

Você continua como único escritor do código do produto. Registrar recebimento e tratar R4-DELIVERY-01 antes de marcar a distribuição como funcionalmente pronta. R3 de fila já foi corrigida e será revalidada separadamente; não duplicar a implementação. As demais correções R3 (drenagem contínua, sessões, autenticação) continuam pertinentes.

Nenhum achado nesta nota é uma alegação de incidente efetivamente ocorrido com cliente pagante. É prevenção com reprodução local. Esta nota não amplia autorização de publicação, assinatura oficial, credenciais, alteração remota ou cobrança.

## Revalidação independente da correção de fila R3

Executei a mesma regressão de fila em duas cópias isoladas: base `0732c03` saiu 1, correção `72c6820` saiu 0. Passaram as contagens 0/1/8/9/12/16, revogação entre lotes sem replay e preservação de frame parcial usando socketpair local. Resultado em `r3-queue-fix-independent.json`. Esta é uma correção local confirmada; não representa deploy do transporte comercial.

Hash e leitura de volta das evidências verificados. A fonte da auditoria permaneceu inalterada durante os testes. O arquivo `snapshot.json` conserva os hashes individuais; fixtures grandes artificiais são regeneráveis pelos testes e não foram copiadas ao Git.

## Revalidação PTY do commit 5b27143 — falha de fixture identificada

Reexecutei via HARA Commander em cópia isolada. A suíte original passou 256KiB sem leituras, UTF-8 dividido, vários MiB com memória limitada e parada do coletor. Porém terminou exit 1 na fixture `descendant_stopped`: o processo desapareceu entre `proc_stat.exists()` e `read_text()`, gerando ProcessLookupError. Isso não demonstra descendente vivo: é uma corrida na inspeção de /proc. Não reclassifiquei a execução original como PASS.

Em cópia QA apenas, retirei o teste exists/read e tratei exclusivamente FileNotFoundError/ProcessLookupError como processo já encerrado. Duas execuções do teste corrigido estão em `r3-continuous-drain-proc-race.json`; runtime Linux inalterado. Incorporar regressão determinística para desaparecimento do processo e preservar erros inesperados. O código do produto e o teste da frente não foram editados pelo revisor.
