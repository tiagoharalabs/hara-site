# H.A.R.A. Commander — correção P0: preservar quota de claim expirado antes da redação

**Data:** 13/11/2026.
**Baseline PRÉ-MUDANÇA já commitada:** `9fa0d7b9ac691e7efa884d361d7996c9c5dc8af0`, relatório `docs/evidence/commander-0043-prechange-ledger-recovery-20261113/STATUS_PRECHANGE_0043_20261113.md`.
**Branch isolada da correção:** `local/commander-0043-expiry-quota-hold-20261113`.

## 1. Falha real — reproduzida antes da mudança

A função original `redactExpiredDeviceCallContent` somente chamava `settleCallUsage` antes de redigir quando `approval_timeout_seconds === 900`. Chamadas executadas sob perfis normais, já reivindicadas (`claimed_at_utc`) e com `usage_mode=CLOUD_QUOTA`, podiam ter o conteúdo redigido após expiração sem reconciliar a reserva Cloud nessa manutenção.

**Prova PRE_PATCH:** a suíte nova sobre o Worker original falhou com:

`claimed non-900 expired call was scrubbed without protecting uncertain Cloud quota` — **0 chamadas de `holdDeviceCall` observadas, 1 esperada**.

Isso não comprova que uma reserva real já foi indevidamente liberada; comprova que a rotina de redação não condicionava sua conclusão à prova de proteção dessa reserva.

## 2. Correção mínima aplicada

Na função real `redactExpiredDeviceCallContent` em `apps/commander/src/worker.js`, adicionado:

```js
const claimedCloudQuota = Boolean(row.claimed_at_utc)
  && String(row.usage_mode || "CLOUD_QUOTA") === "CLOUD_QUOTA"
  && Number(row.usage_units || 0) > 0;
if (Number(row.approval_timeout_seconds)===900 || claimedCloudQuota) {
  // Corpo preexistente: settleCallUsage antes do scrub
}
```

**Contrato de segurança:** uma execução já reivindicada e contabilizada em `CLOUD_QUOTA` exige a reconciliação/hold **antes** da redação do payload. Se a proteção de quota ou a persistência dos metadados D1 falhar, o código preexistente pula a redação; não declara uma limpeza segura e não libera reserva incerta. Chamadas `UNMETERED` e não reivindicadas não recebem um novo débito/retenção Cloud por esta alteração. O comportamento já existente de 900 segundos foi preservado.

Nenhum endpoint, migração, estrutura de dados, orquestrador, Queue, DeviceChannel, Agent ou segredo foi modificado.

## 3. Testes e aceitação

- **8/8 testes novos PASS** sobre a função real de limpeza e `settleCallUsage`, usando SQLite isolado migrado com a 0043 e adaptador sintético de quota.
- Casos cobertos: claim Cloud sem perfil 900; falha de `holdDeviceCall`; compatibilidade com perfil 900; `UNMETERED`; claim ausente; manutenção `EXECUTING → EXPIRED`; falha D1 na gravação de metadados; repetição idempotente sem reexecução/soltura.
- **26/26 testes** de enqueue/aprovação 0043 continuam PASS.
- **29/29 testes** de claim, revalidação e scrub 0043 continuam PASS.
- São três suítes, com potencial sobreposição de requisitos. Não tratar a soma como número de casos de produto independentes.
- Validador reproduzível: `validate_0043_expired_claim_quota_20261113.py` — testa as três suítes, hashes de fonte/0043, build completo do Worker `wrangler deploy --dry-run` e limpeza das dependências temporárias.
- Auditoria independente: `audit_0043_expired_claim_quota_20261113.py` — reconstruiu Worker original do Git baseline, confirmou a **mesma falha anterior** em diretório temporário e conferiu QA e invariantes posteriores.
- Estado auditoria: `EXPIRED_CLAIM_QUOTA_RECONCILIATION_INDEPENDENT_PASS_GLOBAL_HOLD`.

## 4. Integridade

| Elemento | SHA-256 |
|---|---|
| Worker antes | `c9f4c48e553de133598982018a3fbc19f6fcf9165dfd9ddf1609620da61e8dbc` |
| Worker depois | `f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682` |
| Migration 0043 original | `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3` |
| Bundle Wrangler seco | `703727dc4d3504b7609725d09694037039d7602ed45b089bc77c9a88736e282d` |
| Recibo QA | `1b373cea23c6127c55d3a072dd2b0da5024c070d41ba722b30e5294aad3e7b3e` |
| Auditoria independente | `960d44ef09b3b034ec4d7b8dc711ca3ab45d6170eeee929c3d64c2d240992147` |

## 5. Limites, riscos residuais e próxima etapa

A quota DO usada nos testes foi **sintética**, mas o código de reconciliação `settleCallUsage` e o código de limpeza foram reais. O retorno `PASS` atesta **fonte local/SQLite**, não runtime Cloudflare hospedado, nem completude de filas.

**Efeito operacional esperado:** em indisponibilidade de quota DO ou D1, pode haver backlog de registros expirados com conteúdo ainda não redigido. Isso é deliberadamente mais seguro para a contabilidade da execução incerta; é necessário acompanhar a recuperação e validar retenção/redação posterior em QA hospedado.

**Próximos gates:** teste com `TenantQuota` real no workerd; QA hospedado da versão exata; testemunho de instâncias DO ativas, snapshots consistentes, duas janelas globais de quiescência, consumer comercial 0043 e recuperação forward-only. Não promover migration ou Worker PROD, nem ativar FileTools DEVELOPMENT, sem aceite.

**Estado:** `CORREÇÃO_LOCAL_VALIDADA`, mas `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN / COMERCIAL_NO_GO`. Sem Cloudflare mutation, Agent real, Stripe LIVE, instalação ou publicação OpenAI.

## 6. Patch íntegro para revisão GitHub Web

O diff **exato** da correção e das regressões em relação à baseline pré-mudança `9fa0d7b9ac691e7efa884d361d7996c9c5dc8af0` foi preservado em `SOURCE_EXPIRED_CLOUD_QUOTA_HOLD_20261113.patch`, SHA-256 `7226e9d84e23b7383c24a845aa12d91abe06498ef6390aa7c8de7d3c93da4d4b`. Ele contém três caminhos: Worker corrigido, teste novo e atualização de pin da suíte de claim. O patch deve ser revisado sobre a linhagem exata do produto; não faz merge nem deploy por si só.