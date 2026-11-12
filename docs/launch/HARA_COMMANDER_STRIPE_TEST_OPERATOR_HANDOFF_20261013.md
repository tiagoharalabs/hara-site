# H.A.R.A. Commander — Stripe TEST: ficha de ativação após cadastro

**Estado:** `STRIPE_TEST_NOT_CONNECTED / NO_CHARGES / PROD_UNTOUCHED`. Preparado em 13/10/2026; o proprietário pretende cadastrar a conta Stripe em 14/10/2026. Este material **não** cria preços, cobranças, clientes ou credenciais.

## Fonte operacional existente

- Owner: https://github.com/tiagoharalabs/hara-site/issues/296
- Runbook: `docs/operations/HARA_COMMANDER_BILLING_PROD_ACTIVATION_RUNBOOK.md`
- Wizard TEST: `apps/commander/scripts/stripe_test_activation_wizard.py --check` (reportado `READY_FOR_INTERACTIVE_APPLY` em Services).
- Produto Stripe Billing V1: Checkout subscription, portal, webhook com assinatura/verificação e idempotência, `billing_connections` e `billing_webhook_events`, entitlement e quotas.
- PROD: apenas TRIAL ativo (100 unidades/mês no último readback), STANDARD/SCALE desativados, sem Stripe secrets/preços/live checkouts. Não modificar PROD durante teste.
- DEV Cloudflare: Wrangler autenticado no último readback autorizado; 9 nomes de segredos existentes, **0 nomes Stripe**. Quatro nomes DEV pendentes: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD`, `STRIPE_PORTAL_CONFIGURATION`.
- `STANDARD BRL 80 / mês` existe como valor de referência nos testes históricos do wizard, **não equivale à aprovação de preço pelo proprietário**. Não ativar SCALE automaticamente.

## Preparar conta Stripe TEST no painel privado

1. Cadastrar/autenticar a conta Stripe usando o canal oficial do Stripe, completar verificações da empresa e conferir as configurações fiscais/contato conforme disponibilidade da conta.
2. Entrar no **Test mode / Sandbox**, conferir claramente que não é Live.
3. Criar produto `H.A.R.A. Commander` e, só depois da decisão comercial, preço recorrente `STANDARD` (moeda, valor, intervalo, trial, limites e impostos). Registrar somente o ID público não secreto do preço no inventário privado.
4. Configurar **Customer Portal** em modo TEST, habilitando gerenciamento e cancelamento de assinatura conforme a política comercial; registrar a referência de configuração em ambiente privado.
5. Criar webhook TEST para `https://commander.haralabs.com.br/api/billing/stripe/webhook` usando a configuração de ambiente **DEV** apropriada (não confundir endpoint de PROD com credenciais DEV; confirmar roteamento seguro primeiro). Eventos estritamente necessários:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
6. Guardar a chave secreta `sk_test_...` e `whsec_...` **somente** no sistema de segredos de DEV aprovado (ou conector autenticado autorizado), jamais em chat, GitHub, arquivo de evidência ou print.
7. Rodar novo `--check`, conferir account/mode/ids, e somente então aplicar configuração DEV pelo operador autorizado.
8. Executar Checkout **TEST** com dados de cartão de teste fornecidos pelo Stripe, sem cobrar dinheiro real. Confirmar todos os estados pelo backend e pelo painel Stripe.

## Matriz de teste que precisa ficar verde

| Caso | Esperado |
|---|---|
| Checkout assinado | `checkout.session.completed` aceito e ligado à conta correta |
| Webhook repetido | Idempotência, sem segundo efeito |
| Assinatura ativa | `STANDARD/ACTIVE`, quota e grants correspondentes |
| Assinatura sem pagamento | `SUSPENDED`, execução não autorizada |
| Recuperação | `ACTIVE` restaurado apenas com evento elegível |
| Cancelamento | `REVOKED` sem excluir conta, devices ou recibos |
| Tenant distinto | Sem entitlement indevido ou leitura cruzada |
| Portal | Abre apenas para owner autorizado e retorna ao Commander |
| Secrets | 0 em Git, logs, respostas MCP e bundle de suporte |
| Billing/Execução | Stripe não vira autoridade para executar comandos |
| OpenAI | Plugin usa conta paga existente, sem vender/upgrade/Checkout interno |

## Condições de parada (fail-closed)

- `sk_live_...` em TEST, webhook com assinatura inválida, preço não aprovado, entitlement indevidamente ativo, repetição cobrada, cancelamento mantendo permissão, credencial exibida ou Worker PROD alterado.
- Se `--check` reportar Cloudflare DEV não autenticado, reconectar pelo fluxo do proprietário e **não** contornar autenticação. Só reexecutar wizard após confirmação da conta Stripe TEST real.
- Checkout TEST passa **antes** de qualquer instalação LIVE ou ativação de STANDARD/SCALE em PROD.
- O fundador já tem `FOUNDER_INTERNAL/ACTIVE`, portanto **não precisa pagar a si mesmo** para validar o produto.

## Escopo e dependências humanas

O usuário precisa somente concluir a **conexão/autorização Stripe TEST** e aprovar os valores/limites de STANDARD; todas as operações de API ficam condicionadas a essa autorização. Nenhum plano é presumido como aprovado por esta ficha.

**Integração comercial do site e publicação OpenAI são trabalhos separados.** A política OpenAI atual não permite vender assinaturas digitais dentro do plugin; o site externo é o canal comercial.
