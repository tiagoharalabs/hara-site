# H.A.R.A. Commander — correção: consumer não pode confirmar mensagem sem entrega

**Data:** 13/11/2026. **Branch:** `local/commander-recovery-consumer-ack-fix-20261113`. **Base:** `21fef323082e631167ca06612375ee4eb31ba887`.

## Falha real reproduzida

Quando um job `DELIVER` entrava na fila com `COMMANDER_RECOVERY_DELIVERY_ENABLED=true`, e depois essa flag era desabilitada antes do consumo, `dispatchRecoveryDeliveries` retornava `DISABLED`. O consumer considerava o resultado bem-sucedido e executava `message.ack()` sem entrega. **Reprodução antes da correção:** `actual: ACKNOWLEDGED`, `expected: RETRY`.

## Correção entregue

Em `apps/commander/src/recovery-fanout.mjs`, o consumer agora admite o ACK somente se um resultado com `state` explícito for `COMPLETE`, além das checagens já existentes de pendências, HOLD e exaustão. Para `DISABLED` ou outro estado não concluído, reprograma retry de acordo com a política de fila. O fluxo `SCAN`, que retorna agregados sem `state`, mantém seu contrato histórico e seus testes. Nenhum novo sistema de filas foi criado.

## Testes e recibos

- Teste novo de desabilitação após enfileiramento, `RETRY` sem ACK, ausência de HTTP/recibo, reativação e entrega final PASS.
- **85/85** testes na suíte de recovery-fanout, orçamento, leases e DLQ PASS.
- Validador independente `validate_recovery_consumer_ack_20261113.py` concluiu PASS; compilou o Worker completo por Wrangler `deploy --dry-run` com dependências locais existentes.
- Recibo write-once `RECOVERY_CONSUMER_ACK_QA.json`, SHA-256 `852329d9fc548a734d2222d3de6d5d8ad90e960f5f78ef9a969021a5570b26f2`.
- Bundle de teste SHA-256 `e9718ffb838d92fc4b0beb7abefafd04812f8d69c87db7a5ed1146d9c222c3de`.
- Patch revisável `RECOVERY_CONSUMER_ACK_FIX.patch`, SHA-256 `499fad44e042c5a739b9f9baa5bfc335dde18db2ad2c6a1e1ab2cad60c12c6e3`.

## Limites de aceitação

É uma correção real na fila de alertas/recuperação da frente #163, **não a prova do consumer comercial das chamadas da migration 0043**. Esse gate P0 permanece aberto, assim como inventário DO ativo, duas janelas globais de quiescência, snapshots consistentes e recuperação forward-only. O teste não contactou Cloudflare, Agents, Stripe ou clientes. Nenhum Worker PROD/DEV foi implantado, nenhum D1 hospedado ou App foi alterado.

**Estado:** `RECOVERY_CONSUMER_DISABLED_DELIVERY_ACK_RETRY_85_TESTS_BUILD_PASS` na fonte candidata; `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` continua `NO-GO` comercial.