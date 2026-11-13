# H.A.R.A. Commander — pré-mudança: quota DO real e expiração da 0043

**Data:** 13/11/2026. **Estado:** `PRECHANGE_RECORDED_REAL_QUOTA_QA`.
**Branch isolada:** `local/commander-0043-real-quota-prechange-20261113`. **Base:** `44e2d611fdd23cc605aa00ccb648aae9b1a2c133`.

## Evidência do estado anterior

O Worker candidato `apps/commander/src/worker.js` possui SHA-256 `f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682`. A migration 0043 original possui SHA-256 `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3`. Essa origem contém a correção anterior que condiciona a redação de chamadas Cloud reivindicadas à reconciliação de quota.

A rodada anterior foi documentada e preservada nos commits `9fa0d7b9` (pré-mudança), `410c3185` (correção), `59bd2361` (patch) e `44e2d611` (readback PROD). O ensaio 8/8 de expiração, 26/26 de enfileiramento e 29/29 de claim usou a função real de limpeza e `settleCallUsage`, mas um **adaptador sintético de quota**. Ele não prova o comportamento da classe `TenantQuota` em armazenamento Durable Object.

O último readback autenticado da Cloudflare confirmou o Worker comercial `12fe1bb3-4c8c-4a37-9793-54bb4525556e` em 100% do tráfego, D1 PROD com 21 colunas e D1 QA com 22. Essas informações são históricas desta frente e não autorizam inferir que a fonte candidata está implantada.

## Plano do ensaio seguinte

Utilizar a **classe original TenantQuota** do Worker candidato, compilada com Wrangler `deploy --dry-run`, dentro de Miniflare/workerd local, sem acesso à rede externa e com armazenamento persistente temporário de Durable Objects. Usar D1 SQLite isolado migrado com a migration 0043 original para representar a chamada e executar o módulo original `settleCallUsage` mais `redactExpiredDeviceCallContent`.

Critérios mínimos de aceitação:

1. Reserva legítima `reserve`, início `startDeviceCall`, estado vencido e reconciliação `holdDeviceCall` ocorrem no **mesmo TenantQuota real**, com vínculo de request, sujeito e período.
2. Uma unidade reservada e marcada como incerta continua contabilizada, sem liberação ou `settleDeviceCall` indevido; o payload é redigido somente após proteção comprovada.
3. Erro do quota RPC, binding errado, indisponibilidade D1 e resultado já terminal são tratados sem afirmar liberação segura nem reenviar chamada ao Agent.
4. A reserva/reconciliação persistem após reinício do workerd com o mesmo diretório de armazenamento.
5. Testes de regressão prévios, comparação de SHA, verificador independente e build seco continuam PASS; nenhum segredo, token, ID de cliente real ou payload real entra nos recibos.

## Hipóteses, não defeitos confirmados

- A classe real pode retornar `CALL_USAGE_BINDING_INVALID` ou `CALL_RECONCILIATION_REQUIRED` por contrato de unidade/estado diferente do adaptador anterior.
- Um `holdDeviceCall` já idempotente pode oferecer garantias mais fortes; não presumir duplicação sem reproduzir.
- A exceção de quota DO pode permitir backlog de redação, que deverá permanecer retido até reconciliação; nunca aliviar a guarda para diminuir o backlog.

## Autoridade e bloqueios

Esta branch registra o estado **antes** de novas alterações. Próxima etapa em uma branch derivada, depois do commit desta baseline: criação de harness QA, testes, eventual correção mínima se defeito for demonstrado, validação e custódia Services → Storage → GitHub Web draft.

É proibido por esta baseline: deploy PROD ou QA hospedado sem gate, migration comercial, liberação de reserva incerta, retry de efeito incerto, reinício de máquinas de terceiros, uso de credenciais comerciais, Stripe LIVE, publicação OpenAI ou promoção automática de `main`.

**Estado comercial:** `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN / NO_GO`.