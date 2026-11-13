# H.A.R.A. Commander — plano ANTES do ensaio TenantQuota real

**Data:** 13/11/2026. **Branch isolada:** `local/commander-0043-real-quota-workerd-20261113`. **Base:** `44e2d611fdd23cc605aa00ccb648aae9b1a2c133`.

## Evidência inicial e fonte pinada

O ensaio anterior `EXPIRED_CLAIM_QUOTA_RECONCILIATION_INDEPENDENT_PASS_GLOBAL_HOLD` reproduziu a falha no Worker antigo (limpeza de claim CLOUD_QUOTA sem hold quando approval timeout diferente de 900) e passou após corrigir o `redactExpiredDeviceCallContent` na fonte candidata. Porém o adaptador de quota era sintético. O novo ensaio não pode presumir equivalência com o estado real do Durable Object.

- `worker.js` atual SHA-256: `f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682`.
- Migration 0043 original SHA-256: `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3`.
- `approval-relay-storage.mjs` SHA-256: `89ce8ecdd3310315e8ae1bbc224fc12d579f5af1156f0cbf88df19684858df2a`.
- Cloudflare PROD na última observação: `12fe1bb3-4c8c-4a37-9793-54bb4525556e`, 100%, D1 PROD 21 colunas, D1 QA 22. Não reimplantar.
- Commit base limpo; Services e Storage Primary respondendo.

## Hipótese e testes previstos

Executar o Worker **real** compilado por Wrangler `deploy --dry-run` com Miniflare/workerd e `TenantQuota` real, persistência DO SQLite em pasta temporária, sem egress. Executar também a função real `redactExpiredDeviceCallContent` extraída por fronteira de fonte fixa e `settleCallUsage`, usando D1 SQLite isolado com a migração 0043. Vincular o método `TENANT_QUOTA.getByName` ao stub RPC real da instância QA.

Provas mínimas: (1) reserva real `RESERVED`, `startDeviceCall`, expiração e `holdDeviceCall` antes do scrub; (2) prova persistente de `execution_started=1`, `reconciliation_required=1` e quota consumida/retida; (3) segunda execução não libera reserva nem redespacha; (4) reinício do runtime workerd preserva reserva incerta e comprovante de scrub; (5) chamada não reivindicada não cria hold; (6) tentativa de concluir automaticamente uma reserva incerta é recusada.

## Critérios de segurança

Qualquer falha no runtime ou no harness deve retornar **HOLD**, nunca PASS sintético. Não apagar/quitar reservas reais, não fazer retry de efeitos incertos. Worker, D1/DO comerciais, Stripe, App OpenAI e Agents inalterados. Só depois de reproduzir e validar criar recibos write-once, auditor independente, commit no Services, readback no Storage, PR Web em draft.

**Não é prova de instância hospedada.** Mesmo que o runtime local real passe, faltam registry DO comercial, epoch/generation, duas janelas globais, snapshots consistentes e consumer real 0043. `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` permanece.