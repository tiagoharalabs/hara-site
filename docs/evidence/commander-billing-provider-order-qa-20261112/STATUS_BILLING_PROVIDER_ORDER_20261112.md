# H.A.R.A. Commander — QA de Billing, Stripe e autoridade do provedor

**Coleta:** 12/11/2026 (BRT). **Fonte base:** `5f75599ad104f2e7179630e9da048b5e483fe96e`.
**Branch Services isolada:** `local/commander-billing-provider-order-qa-20261112`.

## Entrega de regressão

A suíte `apps/commander/scripts/billing_sqlite_webhook_e2e.mjs` foi ampliada sem modificar o módulo de produção `billing.mjs`. Na mesma assinatura, um evento de suspensão recente é seguido por um evento de ativação anterior. A revisão moderna consulta o estado autoritativo da assinatura e fatura no Stripe antes de sincronizar o entitlement.

- Novo teste: `BILLING_SQLITE_SAME_SUBSCRIPTION_OUT_OF_ORDER_PROVIDER_AUTHORITATIVE=PASS`.
- Estados confirmados: `SUSPENDED → SUSPENDED → ACTIVE`, inclusive quando o payload do último evento está desatualizado.
- `node apps/commander/scripts/billing_sqlite_webhook_e2e.mjs`: exit 0; suíte completa preservada.
- `python3 -B apps/commander/scripts/validate_billing_v1.py`: exit 0.
- `node apps/commander/scripts/billing_v1_selftest.mjs`: exit 0.
- Teste workerd da revisão moderna (Miniflare com dependência existente, vinculada apenas num diretório temporário): exit 0, Checkout PASS e redirect não autorizado BLOCKED.

O bug demonstrado numa fonte histórica não foi tomado como diagnóstico da revisão atual. Esta prova é de fonte, não de implantação hospedada.

## Evidência hospedada, somente de leitura

**Stripe sandbox / Cloudflare DEV:** a assinatura STANDARD de demonstração possui Checkout pago, quatro eventos `PROCESSED` (`checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `invoice.paid`), conexão Stripe `ACTIVE` e entitlement STANDARD `ACTIVE`. A consulta à configuração confirmou quatro nomes de secrets no DEV, sem ler seus valores. Health HTTP 200, checkout sem sessão HTTP 403 e HMAC inválido HTTP 400; o evento inválido não foi persistido.

**Histórico demo:** 161 entitlements STANDARD `EXPIRED` para 161 subjects distintos, datados de setembro, coexistem com um entitlement STANDARD ativo criado em novembro. Os dados não foram alterados. Não classificar esses registros automaticamente como duplicatas sem análise de procedência.

**Stripe LIVE / Cloudflare PROD:** produto e preço STANDARD BRL 80/mês existem, portal ativo, nenhuma assinatura LIVE listada; webhook LIVE `disabled`. Na lista de nomes de secrets PROD faltam `STRIPE_WEBHOOK_SECRET` e `STRIPE_PRICE_SCALE`. A revisão verificada declara `STRIPE_CHECKOUT_ENABLED=false` na configuração-fonte PROD; o binding exato da implantação não foi provado nesta rodada. Stripe Tax retornou indisponibilidade para o país da conta. **BILLING LIVE permanece NO-GO**.

## Gatilhos para próximos testes

1. Confirmar SHA efetivo da imagem Worker hospedada e confrontar com os testes de fonte; não inferir igualdade pelos logs.
2. Provar quota/entitlement e execução/recibo MCP para o mesmo tenant de demonstração, sem expor material de cliente.
3. Usar tenant descartável para ciclo real hospedado `SUSPENDED → ACTIVE → REVOKED`; preservar a assinatura demo ativa.
4. Fechar configuração fiscal, segredo do webhook LIVE, plano SCALE e autorização de abrir vendas, em fluxo separado.
5. Preservar camadas independentes Services Git, Storage Working Mirror, Storage Canonical, GitHub Web e release PROD/OpenAI.

**Limites:** nenhum `deploy`, cobrança real, mudança de assinatura, upload de secret, modificação de D1 PROD, instalação de Agent ou alteração do pacote submetido à OpenAI.

**Issue de acompanhamento:** `tiagoharalabs/hara-site#296` (comentários 6837312767 e 6837909054).