# H.A.R.A. Commander — TenantQuota REAL no workerd: expiração 0043

**Data:** 13/11/2026. **Estado:** `REAL_TENANT_QUOTA_EXPIRY_INDEPENDENT_PASS_HOSTED_HOLD`.

## Ordem de custódia

Documento PRECHANGE escrito e commitado **antes** da implementação no commit `15306dc6de16f80f09dcfc4c7939ed8f7f9f2586`, pai `44e2d611fdd23cc605aa00ccb648aae9b1a2c133`. Nenhum código-fonte do Worker foi alterado para o teste.

## Teste efetivo

O Worker original SHA-256 `f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682` foi compilado por Wrangler **`deploy --dry-run`** e carregado em Miniflare/workerd, com a classe real `TenantQuota`, isolamento de egress e persistência DO SQLite temporária. A migration 0043 original SHA-256 `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3` foi aplicada apenas ao SQLite sintético de calls.

O teste usou `settleCallUsage` e o código original de `cleanupExpiredDeviceCalls` / `redactExpiredDeviceCallContent` extraído da fonte, com `env.TENANT_QUOTA.getByName` apontando para o **RPC real** de `TenantQuota`, não para um objeto simulado.

**5/5 PASS:**

1. Reserva de quota efetiva no DO e `startDeviceCall` para chamada QA sintética.
2. Expiração, `holdDeviceCall` real, redação do payload e unidade de quota mantida.
3. `settleDeviceCall` recusou liberação automática da execução incerta (`CALL_RECONCILIATION_REQUIRED`); hold idempotente.
4. Limpeza repetida não fez redespacho nem liberação.
5. Reinício verdadeiro do workerd com mesmo armazenamento manteve a unidade protegida e recusou novamente a liberação.

**Recibo:** `REAL_TENANT_QUOTA_WORKERD_QA.json`, SHA-256 `645efdf4f4e60ca8cd7cfdd5d9fa16fcd077eebd742860a00674b1013b015ca9`. **Bundle seco:** SHA-256 `34e4897ac2e9b2d7fb96b390d88ff4fabc9057eba05315635756b3509a4c113d`.

## Auditoria e limites

Auditor independente confrontou o código, a migration, o manifesto, cinco nomes/casos, integridade dos arquivos e o documento PRECHANGE imutável; estado `REAL_TENANT_QUOTA_EXPIRY_INDEPENDENT_PASS_HOSTED_HOLD`, recibo `INDEPENDENT_REAL_QUOTA_READBACK.json` SHA-256 `f421e251b9f1feeca892c9d1c91b2f088a20e44e0fbac987da5cc12b43266039`.

Falhas iniciais do harness: caminho write-once incorretamente bloqueava a pasta com PRECHANGE e falta de vínculo temporário das dependências `zod`. Ambas corrigidas **somente no harness**, reexecutado PASS; vínculo temporário removido.

**Não executado:** Cloudflare hospedada, DO comercial, D1 remoto, Agent real, fila/consumer comercial 0043, quiescência global, snapshots de produção, Stripe LIVE ou App OpenAI. `hosted_qa_proven=false` e `commercial_cutover_authorized=false`.

Próximo gate: homologar esse mesmo ciclo e build exato em Cloudflare **QA isolada**, com credenciais legítimas e recibos da quota DO real, depois o registry de instâncias ativas, as duas janelas globais, snapshots conjuntos e recuperação forward-only. A migration 0043 comercial continua bloqueada (`LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN`).