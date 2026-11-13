# H.A.R.A. Commander — readback hospedado das Queues de QA

**Data:** 13/11/2026. **Método:** chamadas Cloudflare GET autenticadas, executadas por Services; sem operação de escrita no provedor e sem exibição de credenciais ou IDs internos de Queue.

## Resultado autenticado

| Recurso | Consumer hospedado | Lote / retries | DLQ | Backlog |
|---|---|---|---|---|
| P0 exact QA | `hara-commander-p0-exact-qa-20261113` | 1 / 2 | Ausente | 0 |
| P0 integrated QA | `hara-commander-p0-integrated-qa-20261112` | 1 / 2 | Ausente | 0 |
| R163 recovery QA | `hara-commander-r163-canary-20261024` | 1 / 2 | Presente | 0 |

Os bindings hospedados dos scripts `hara-commander` (comercial) e `hara-commander-dev-v2` contêm **zero bindings do tipo Queue**. O R163 canary possui um binding de Queue. A versão comercial consultada continua `12fe1bb3-4c8c-4a37-9793-54bb4525556e`, 100% do tráfego.

**Recibo provider:** `HOSTED_QUEUE_TOPOLOGY_READONLY_20261113.json`, estado `CLOUDFLARE_QA_QUEUE_TOPOLOGY_READONLY_PASS_COMMERCIAL_HOLD`.

**Recibo independente:** `INDEPENDENT_HOSTED_QUEUE_TOPOLOGY_20261113.json`, estado `HOSTED_QA_QUEUES_GET_VERIFIED_P0_DLQ_MISSING_COMMERCIAL_HOLD`; verifica os limites e compara os bindings com os manifests versionados, sem chamadas externas.

## Implicação para o lançamento

A correção de código do consumer de recuperação (DELIVER desativado → RETRY sem ACK; 86/86 PASS) ainda exige implantação controlada e homologação nativa no Worker correto. **Não confundir a Queue R163 de alertas com o consumer de chamadas duráveis do ledger 0043.**

As Queues P0 exact/integrated foram criadas exclusivamente para QA; a ausência de DLQ significa que uma futura sequência de falhas que atinja o limite de retentativas pode fazer com que uma mensagem seja descartada pela plataforma. O backlog zero indica que não havia mensagens aguardando naquele readback, não certifica uma futura execução correta. Manual Cloudflare: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/

## Próxima ação condicionada

Depois da frente LEGACY→bridge/WSS, confirmar o proprietário dos recursos P0 e validar a política de retenção e DLQ **nas Queues existentes** antes de novo teste de falha induzida. Não criar outra fila ou consumidor paralelo para reproduzir as mesmas provas. Em seguida, exigir consumer de 0043, snapshots D1/DO/outbox e recuperação compatível antes de liberar PROD.

**Preservado:** nenhum deploy, migration comercial, configuração de consumer, Queue write, Stripe, Agent, FileTools, App OpenAI, segredo ou cliente real alterado. `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` mantém a promoção `NO-GO`.