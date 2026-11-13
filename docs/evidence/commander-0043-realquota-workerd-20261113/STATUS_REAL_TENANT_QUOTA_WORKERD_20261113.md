# H.A.R.A. Commander — expiração 0043 com TenantQuota real em workerd

**Conferência:** 13/11/2026. **Escopo:** QA local, Worker real compilado, Durable Object SQLite persistente.
**Branch:** `local/commander-0043-realquota-workerd-20261113`.
**Baseline pré-mudança commitada e custodiada ANTES dos testes:** `37429bdcafa3945acc72977023684c7087598e34`, com relatório em `docs/evidence/commander-0043-real-quota-prechange-20261113/`.

## Entrega técnica efetiva

O Worker original `apps/commander/src/worker.js` foi compilado com Wrangler `deploy --dry-run`; a classe original `TenantQuota` foi executada no workerd/Miniflare, com SQLite de Durable Objects persistente, e vinculada à função real `settleCallUsage` e ao cleanup `redactExpiredDeviceCallContent`. O D1 de chamada foi isolado em SQLite migrado pela **0043 original** (21→22 colunas). Nenhum mock substituiu a **lógica de negócio** do TenantQuota.

**7/7 casos PASS no ensaio inicial e 7/7 PASS em uma execução independente adicional**, com resultados e SHA do bundle idênticos.

### Cenários aprovados

1. Claim expirado, reivindicado, quota Cloud: `reserve` e `startDeviceCall` reais, `holdDeviceCall` antes da redação; o consumo permanece 1 unidade e a redação só ocorre após o hold.
2. Perfil assíncrono de 900 segundos preserva comportamento anterior e hold obrigatório.
3. Falha sintética de transporte do RPC `holdDeviceCall`: sem marca de redação bem-sucedida e sem liberação de quota; recuperação posterior preserva a unidade.
4. Vínculo de sujeito incorreto perante o TenantQuota real: `CALL_USAGE_BINDING_INVALID` rejeitado e a reserva não é liberada.
5. Falha injetada no D1 ao gravar metadados: a reserva já protegida permanece, a redação é suspensa; nova tentativa após recuperação conclui sem consumo duplicado.
6. Chamada `EXECUTING → EXPIRED`: a função de manutenção real marca expiração, protege a quota e evita novo trabalho em execução repetida.
7. Reinício do workerd: o mesmo TenantQuota recupera SQLite persistido, ainda mostra uma unidade protegida, e um hold repetido é idempotente.

O transporte de falha, o D1 e as chamadas são **sintéticos e locais**. A falha injetada no RPC não foi uma indisponibilidade real do provedor Cloudflare. O `TenantQuota` testado, seu SQLite e seus métodos RPC são os da fonte original.

## Artefatos e integridade

| Artefato | SHA-256 |
|---|---|
| Worker candidato (inalterado) | `f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682` |
| Migration 0043 original | `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3` |
| Bundle Wrangler do workerd | `34e4897ac2e9b2d7fb96b390d88ff4fabc9057eba05315635756b3509a4c113d` |
| Recibo QA original | `7ddd4a13131de8e940be5f7b68d51eb4740f223dc4b6affec10fbc6f533b0238` |
| Recibo da auditoria independente | `0c49dad45dd3b5594421f7cf4d00057faee319b7fd37d0cbf42277c6c135a8e2` |

**Código novo (apenas QA):** `apps/commander/scripts/test_0043_expired_claim_real_quota_20261113.mjs`, `run_0043_expired_claim_real_quota_20261113.py` e `audit_0043_expired_claim_real_quota_20261113.py`.

**Recibos:** `docs/evidence/commander-0043-realquota-workerd-20261113/REAL_TENANT_QUOTA_WORKERD_QA.json` e `INDEPENDENT_REAL_QUOTA_READBACK.json`. O segundo recibo registra a execução repetida em outro armazenamento local descartável e verifica os sete cenários, o código original e os limites de autoridade.

O armazenamento de QA foi removido após cada execução. Nenhum token, segredo, ID de DO comercial ou payload de cliente foi usado ou publicado.

## Aceite alcançado versus ainda bloqueado

**Concluído nesta rodada:** `REAL_TENANT_QUOTA_EXPIRY_WORKERD_PASS_GLOBAL_HOLD` — integração local do cleanup real com TenantQuota real e persistência pós-restart. Isso fecha a lacuna do **adaptador de quota sintético** da rodada anterior neste escopo.

**Não concluído:** prova hospedada do mesmo SHA em Cloudflare QA, registry exaustivo das instâncias DO ativas com geração/epoch, duas janelas globais de quiescência (WSS/RPC/alarmes/Queue), snapshots consistentes de D1/DO/quota/outbox, consumer comercial real da fila de chamadas 0043, recuperação forward-only do ledger.

Não realizar `migration 0043` em D1 PROD, não promover Worker comercial, não abrir checkout LIVE e não ativar FileTools no mesmo App até os respectivos gates. O `main` canônico, Agents e aplicativo OpenAI permanecem intactos.

**Estado comercial:** `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` / **NO-GO**.

## Regressões históricas reexecutadas na mesma fonte

Para evitar validar apenas a nova integração DO, reexecutei também as três suítes originais, ainda sobre o Worker candidato SHA-256 `f14550bb...`: **8/8** de expiração com adaptador sintético, **26/26** de aprovação/enqueue e **29/29** de claim/autorização/scrub. Todas PASS. O recibo `CARRYFORWARD_0043_REGRESSIONS.json` (SHA-256 `7e09f21bb762f3916f8ff1bda59b3c8df73ed2e6beb1e7813a0cf91303874375`) preserva os hashes de cada script e saída; não se afirma que as suítes representem casos únicos sem sobreposição. Nenhum runtime hospedado foi acionado.

## Readback Cloudflare após o teste local

A leitura autenticada somente de leitura, registrada em `POSTQA_PROVIDER_READONLY_20261113.json`, confirmou Worker comercial `12fe1bb3-4c8c-4a37-9793-54bb4525556e` a 100%, D1 PROD `commander_device_calls` com **21 colunas** e D1 QA 0043 com **22 colunas**. Não houve mutações. O SHA da fonte candidata permanece distinto da implantação comercial; isso **não** é aceite hosted QA.