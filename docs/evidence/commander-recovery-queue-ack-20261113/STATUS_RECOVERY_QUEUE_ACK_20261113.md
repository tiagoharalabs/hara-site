# H.A.R.A. Commander — correção do ACK indevido na Queue de recuperação

**Data:** 13/11/2026. **Branch Services:** `local/commander-recovery-queue-ack-failclosed-20261113`. **Base:** `21fef323082e631167ca06612375ee4eb31ba887`.

## Defeito realmente reproduzido

Depois que uma mensagem `DELIVER` era admitida pela Queue, uma mudança de configuração que desativasse `COMMANDER_RECOVERY_DELIVERY_ENABLED` fazia `dispatchRecoveryDeliveries()` retornar `DISABLED`. A rotina `consumeRecoveryWork()` aceitava essa resposta como se fosse uma entrega concluída e chamava `message.ack()`, embora não houvesse entrega nem recibo. Isso podia eliminar a mensagem da fila indevidamente.

**Teste anterior à correção (RED):** `DELIVER queued before feature disabled must retry and never ACK without receipt` retornou `actual: ACKNOWLEDGED` e `expected: RETRY` ao executar o módulo anterior em cópia isolada. A evidência está ligada ao SHA do código anterior.

## Correção entregue

`apps/commander/src/recovery-fanout.mjs` agora exige `result.state==='COMPLETE'` para reconhecer a conclusão de mensagens `DELIVER`. Resultados `DISABLED`, `HOLD_*`, `PARTIAL` ou inesperados não podem resultar em ACK: o consumer chama `message.retry({delaySeconds})`, preservando o destino de retentativa/DLQ. A lógica de mensagens `SCAN` permanece independente e o modo SCAN-only continua legítimo.

**Teste depois da correção (GREEN):** a mensagem anteriormente bloqueada passou a resultar em `RETRY`, com zero ACK, zero chamadas ao destinatário e zero registros indevidos de entrega. Após reabilitar o destinatário sintético, a mesma mensagem gerou recibo idempotente `DELIVERED` e somente então o ACK. Segundo teste garantiu retentativa quando a entrega já estava desabilitada.

## Testes e build

- **86/86 testes PASS**, cobrindo fanout, orçamentos D1, tentativas, concorrência, idempotência e DLQ.
- Verificador reproduzível `apps/commander/scripts/validate_recovery_queue_ack_20261113.py` executou os mesmos testes, reproduziu o RED com a fonte anterior por `git show` em ambiente temporário e compilou o Worker completo com `wrangler deploy --dry-run`.
- Bundle dry-run completo SHA-256 `335ed42f33021cc962f23be33983e28b548970e34a344895004cc2fb13a2ac53`, sem upload nem deploy.
- Recibo `RECOVERY_QUEUE_ACK_QA.json` SHA-256 `cdf6d8d2048dd55ac083f63abc9dcbe2ffcaff15b62f8043f9099e540a784755`.
- Auditoria independente `QUEUE_ACK_RED_GREEN_AND_DRYRUN_INDEPENDENT_PASS_HOSTED_HOLD`, SHA do readback `76003d164f56d6aa16dd61875d3508c75620ccc58c7846bfe2c0dc6a599f03c1`.
- Patch exato de módulo e testes: `RECOVERY_QUEUE_ACK_FAILCLOSED_20261113.patch`, SHA-256 `2af913daf6ee8858bec6c4629fd44c635918d6a7e1ffb7e8ca480ca1c75201b4`.

## Impedimento de configuração detectado

Os arquivos versionados `apps/commander/wrangler.jsonc` e `wrangler.dev.jsonc` **não declaram produtores nem consumidores de Queues**. O canário QA `wrangler.r163-queue-qa.jsonc` declara produtor, consumer e DLQ com retry configurado. Essa verificação é da **configuração-fonte**, não atesta por si só o estado efetivo do runtime Cloudflare.

Segundo a documentação oficial Cloudflare, `message.ack()` confirma definitivamente a mensagem, enquanto `message.retry()` solicita nova entrega. Se não houver DLQ, mensagens que excedem o limite de retentativas podem ser descartadas. Por isso, também é necessário atestar bindings, retries e DLQ no Worker hospedado antes do GO.

## Limites e próximos gates

Este patch corrige a Queue de **alertas e recuperação R163**, não a homologação do consumer de chamadas duráveis na migration 0043. Para esse P0, permanecem necessários a identidade exata do Worker hospedado, snapshots D1/DO/outbox/quota, gerações dos DOs ativos, duas janelas globais de quiescência, consumer real e recuperação forward-only. A FileTools e a publicação OpenAI continuam separadas.

**Produção sem alterações:** nenhum Cloudflare deploy, migration PROD, Agent, Cliente, Stripe LIVE, secret, revogação, autenticação ou App DEVELOPMENT foi modificado. O `main` remoto e o Storage Canonical não foram promovidos. Estado `PROD=NO_GO`, `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` preservado.