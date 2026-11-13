# H.A.R.A. Commander — correção de falso COMPLETE no fanout de recuperação

**Data:** 13/11/2026. **Branch isolada:** `local/commander-recovery-fanout-hold-fix-20261113`. **Base:** `53a8a81fd2dc26960d3b6ae253abbfe12961763a`.

## Defeito reproduzido e corrigido

A função real `enqueueRecoveryWork` em `apps/commander/src/recovery-fanout.mjs` começava com `state=COMPLETE`, mas quando `listRecoveryDeliveryCandidates` retornava `HOLD_RECOVERY_TARGET_CONFIG` ela apenas preenchia `delivery_state` e saía do loop, **deixando o estado global `COMPLETE`**. Uma campanha incompleta podia, portanto, aparecer como concluída.

**Prova de falha antes do patch:** o novo teste `producer HOLD: broken delivery configuration never reports COMPLETE` retornou exit 1, com `actual: COMPLETE` e `expected: HOLD_RECOVERY_DELIVERY_ENUMERATION`.

**Correção:** estados de enumeração diferentes de `COMPLETE` ou `DISABLED` agora retornam `state=HOLD_RECOVERY_DELIVERY_ENUMERATION`, preservando `delivery_state` para diagnóstico. O estado `DISABLED` permanece permitido no modo legítimo de varredura sem entrega, sem ativar a entrega automaticamente. Os trabalhos SCAN já admitidos não são ocultados nem falsamente tratados como reconciliação completa.

## Validação

- **52/52** testes `test_recovery_fanout_r163.mjs` PASS, incluindo **três testes adicionais**: configuração de destinatário inválida, varredura parcial com entrega bloqueada e operação SCAN-only.
- **32/32** testes adjacentes `test_recovery_queue_budget_r163.mjs` e `test_recovery_queue_dlq_r163.mjs` PASS: orçamento, deadline, concorrência, recibos idempotentes e fila morta.
- Validador reproduzível `validate_recovery_fanout_hold_20261113.py` executou 84 testes, conferiu os três novos casos e compilou o Worker completo com Wrangler `deploy --dry-run` a partir das fontes correntes e dependências já instaladas.
- Bundle gerado localmente, SHA-256 `792e6b73dbdf6cc75d62ce280bd62534487b39edb23cd90ef99757c3a901a576`; nenhum upload/deploy ocorreu.
- SHA-256 de `recovery-fanout.mjs` corrigido `bc32ea1e5e9473f5955b173e7079ce560c5666a109e3bfd07d8dde4071bf7b07`.
- Recibo `RECOVERY_FANOUT_HOLD_QA.json` SHA-256 `2bfa7ffc3c5c61dbff67ced85bc05718b97976a59b74966f65e08bc670e78d65`.
- Diff revisável e reproduzível `RECOVERY_FANOUT_FIX_20261113.patch` SHA-256 `a647d4d6f234309495762c01bde8a62787afdd7355172b6c154102c388b602bf`.

## Escopo exato — evitar falso GO

**Esta correção é da Queue de alertas/recuperação da frente #163**, que usa `recovery-fanout.mjs`. Ela **não implementa nem homologa automaticamente o consumidor durável de chamadas de dispositivos associado à migration 0043**. São contratos operacionais relacionados, mas diferentes.

**P0 ainda aberto:** registry de instâncias DO realmente ativas e por geração, duas janelas completas de quiescência, snapshots D1/DO/quota/outbox, recuperação forward-only compatível, consumer comercial da 0043 e habilitação das 14 FileTools no mesmo App DEVELOPMENT após GO.

Nenhum Agent real, cliente, endpoint Stripe, secret, Worker Cloudflare PROD/DEV, migração D1 comercial, App OpenAI ou git `main` foi alterado. O artefato corrige **uma falha reproduzida na fonte candidata**, e o gate comercial `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` permanece intacto.

**Estado:** `RECOVERY_FANOUT_INCOMPLETE_DELIVERY_HOLD_84_TESTS_AND_WORKER_BUILD_PASS` / `PRODUCTION_NO_GO`.