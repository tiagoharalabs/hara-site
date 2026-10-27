# Commander 0.3.56 — comandos na frota e observações de latência

**27/27 comandos ROOT aprovados: três por host, em nove hosts. Saúde posterior: 9/9 PASS.**

Este é um ensaio funcional de carga limitada. Foram despachadas inicialmente duas chamadas em paralelo no cliente; após uma observação de latência elevada, as 25 chamadas restantes foram executadas uma por vez. A sobreposição dos processos nativos não foi medida.

## O que foi verificado

Cada comando calculou SHA-256 de um payload em memória com nonce próprio e realizou uma espera de 0,25 s, 0,75 s ou 1,5 s. Os 27 recibos tiveram exit0, nonce, hash, tamanho e UID esperados, hash do comando correspondente ao plano, ausência de timeout/truncamento e retorno autorizado por `PERSISTENT_TRUSTED` / `DEVICE_ENROLLMENT_POLICY`. Os 27 nonces e recibos são distintos. A consolidação conferiu esses campos diretamente nos retornos retidos, além dos checks registrados pelo executor.

## Latência fim a fim e tempo do probe

| Medida — 27 amostras | Mínimo | Mediana | p95 | Máximo | Unidade |
|---|---:|---:|---:|---:|---|
| Chamada fim a fim | 3,084 | 5,918 | 12,501 | 23,041 | segundos |
| Corpo medido do probe | 250,162 | 750,438 | 1501,830 | 1501,877 | milissegundos |

A latência fim a fim foi medida ao redor da chamada da ferramenta no cliente. Inclui o caminho completo e seu agendamento. O tempo nativo usa relógio monotônico dentro do probe, após os imports: inclui hash e espera, mas exclui a inicialização do Python, imports e trânsito do conector. A causa da diferença entre as duas medidas não foi isolada; nenhum defeito do Agent, conector, relay ou rede é atribuído por este registro.

O p95 usa a ordem `ceil(0,95 × n)` da amostra ordenada. É uma estatística descritiva desta amostra pequena; não certifica SLO ou capacidade máxima.

| Rodada | Comandos | Espera solicitada | Tempo nativo mínimo–máximo (ms) | Mediana / máximo fim a fim (s) |
|---|---:|---:|---:|---:|
| 1 | 9 | 0,25 s | 250,162–250,660 | 9,319 / 23,041 |
| 2 | 9 | 0,75 s | 750,171–751,140 | 4,586 / 7,591 |
| 3 | 9 | 1,5 s | 1500,173–1501,877 | 6,470 / 8,416 |

## Resultado por host

| Host | Comandos aprovados | UID | Mediana fim a fim (s) | Máximo fim a fim (s) |
|---|---:|---:|---:|---:|
| sentinela-c | 3/3 | 1000 | 6,633 | 9,501 |
| sentinela-d | 3/3 | 1000 | 5,939 | 23,041 |
| sentinela-a | 3/3 | 1000 | 5,409 | 12,501 |
| ninja-blue | 3/3 | 1000 | 6,033 | 9,319 |
| nucleo-a | 3/3 | 1000 | 5,798 | 6,725 |
| observer | 3/3 | 1001 | 5,706 | 7,591 |
| storage | 3/3 | 1000 | 7,041 | 12,229 |
| services | 3/3 | 1000 | 5,674 | 6,470 |
| sentinela-b | 3/3 | 1002 | 4,586 | 8,416 |

## Fases preservadas e redução de concorrência

1. **Preflight com oito leituras no cliente:** 8/8 `device.info` PASS. O limite operacional de observação de 10 s foi ultrapassado em Sentinela A (10,407 s) e Ninja-Blue (13,274 s). A progressão foi pausada; oito pings posteriores, com concorrência 2, passaram.
2. **Tentativa anterior do subagente:** a ferramenta/orquestração foi abortada após 871,1 s sem recibos confirmados. O despacho efetivo do primeiro par permanece indeterminado. Esse tempo não é duração de processo nem timeout comprovado do Agent. Essa tentativa permanece no registro histórico e não integra o denominador dos 27 recibos ROOT.
3. **Primeiro par ROOT, duas chamadas no cliente:** Sentinela C e D retornaram resultados funcionais corretos. C levou 9,501 s fim a fim; D levou 23,041 s, com 250,435 ms no corpo medido do probe. A fase foi pausada por ultrapassar seu limite de observação de 20 s.
4. **Continuidade ROOT com concorrência 1:** as 25 chamadas pendentes foram completadas, todas aprovadas, sob limite de observação de 30 s. A latência máxima foi 12,501 s; três chamadas foram executadas em cada um dos nove hosts ao final.

Os limites acima são condições operacionais deste ensaio e mudaram conforme a redução de carga. O relatório mantém a ultrapassagem original e não a transforma em PASS de latência.

## Saúde posterior

Após os 27 comandos, os nove hosts responderam a `device.ping` com `pong=true` e versão 0.3.56. A concorrência no cliente foi 2. Os recibos e os checks desse corte estão no JSON consolidado. Essa observação comprova a resposta posterior; não substitui testes de falha induzida ou recuperação funcional.
A latência dos pings ficou entre 2,336 s e 17,882 s. Ninja-Blue (13,622 s) e Sentinela B (17,882 s) ficaram acima da referência de 10 s, com resultados funcionais PASS; essa observação também é preservada e sua causa não foi isolada.

## Limites e rastreabilidade

O ensaio não aplicou carga máxima de CPU, I/O ou rede. Não certifica estresse extremo, hosted20k, aceite Windows, recuperação sob falhas ou lançamento público.

O [resumo JSON](limited-concurrency-summary.json) inclui métricas completas por fase/rodada/host, checks, recibos e hashes das fontes retidas. A exportação usa campos explicitamente selecionados e não copia comandos brutos, tokens, configuração privada, chaves, identificadores de dispositivo ou dados de sessão. Os cortes anteriores permanecem preservados.
