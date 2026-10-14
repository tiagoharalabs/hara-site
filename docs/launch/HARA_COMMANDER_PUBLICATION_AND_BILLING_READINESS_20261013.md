# H.A.R.A. Commander — publicação OpenAI + Stripe | PRE-FLIGHT 2026-10-13

**Estado:** `SOURCE-ONLY / REVIEW REQUIRED / NO PROD DEPLOY`. Este documento não instala, atualiza nem autoriza o Agent, Worker, MCP comercial ou o MCP interno do HARA Services. Não abre Checkout e não cria produtos Stripe.

**Produto**: H.A.R.A. Commander comercial, `https://commander.haralabs.com.br/api/mcp`; tráfego do cliente **não** passa pelo MCP interno do HARA Services. O MCP privado do desenvolvedor no ChatGPT e a superfície de ferramentas de operações da frota **não** equivalem automaticamente ao pacote público de cinco ferramentas.

## Readback executado (via H.A.R.A. Commander Produto, somente GET)

Em 2026-10-13 BRT, no `nucleo-a`, um cliente HTTPS Python sem bearer token nem cookies testou:

| Destino | Resultado |
|---|---|
| `https://commander.haralabs.com.br/api/mcp` | **401** e `WWW-Authenticate` presente: recusa sem login |
| `https://commander.haralabs.com.br/.well-known/oauth-protected-resource` | **200**, recurso MCP e `authorization_servers=["https://auth.haralabs.com.br"]` |
| `https://auth.haralabs.com.br/.well-known/openid-configuration` | **200**, `issuer` exato e `authorization_code` disponível |
| `https://www.haralabs.com.br/` | **200**, conteúdo público |
| `https://www.haralabs.com.br/support/` | **200**, conteúdo público |
| `https://www.haralabs.com.br/legal/privacidade/` | **200**, política substantiva com H.A.R.A. Commander |
| `https://www.haralabs.com.br/legal/termos/` | **200**, termos substantivos |

Esse readback **não** prova login de um segundo cliente nem um `tools/list` autorizado. Nenhum token, credencial ou conteúdo privado foi recuperado.

## Pacote OpenAI reconstituído sem mexer na produção

Origem: snapshot limpo da `main` de `tiagoharalabs/hara-platform`, HEAD `82946a5f7a52a2c6f02c68a7cc4e97dc44ff7082`, em diretório independente no Núcleo A.

Pacote: `~/hara-commander-publication-preflight-20261013/artifacts/hara-commander-submission-candidate-20261013.zip`

- SHA256: **`0e9be2f9edb0ec5cd42e600ce61c0e746b50176619addbabd2e7f02e4092b900`** (mesmo hash da evidência histórica #851).
- 6 entradas, ZIP íntegro, arquivos sem marcadores de segredos pelo builder.
- `validate_hara_commander_openai_submission_v5.py`: `PREFLIGHT=PASS`.
- 5 casos positivos, 3 negativos, 3 prompts, nome `H.A.R.A. Commander`, desenvolvedor `H.A.R.A. Labs`, URLs oficiais e logo.
- Ferramentas pretendidas: `hara.health`, `hara.functions.list`, `hara.functions.describe`, `hara.functions.invoke`, `hara.receipts.get`.

O pacote **não** foi enviado ao portal e o escaneamento oficial ainda não foi feito. Os plugins privados atuais na conta do desenvolvedor não devem ser publicizados por engano.

## Gates de publicação — bloqueadores reais

| Gate | Status | Responsável / prova |
|---|---|---|
| HARA Labs identidade empresarial verificada e permissão `api.apps.write` no Platform Dashboard | **PENDENTE DE READBACK HUMANO** | Conta OpenAI do publicador |
| Domínio do MCP validado com token exato do portal | **PENDENTE** | `docs/OPENAI_APPS_CHALLENGE_RUNBOOK.md`; não inventar token |
| OAuth da conta de revisão, sem MFA obrigatório, com device de demonstração isolado | **PENDENTE** | #851 / #310; não colocar credenciais no Git |
| **Scan Tools oficial** no endpoint PROD e revisão das anotações exatas | **PENDENTE / P0** | #851; 5 ferramentas na fonte ≠ Scan Tools ao vivo |
| Semântica de `functions.list/describe/invoke` versus regra OpenAI de uma operação por ferramenta | **P0 DE CONFORMIDADE A REVISAR** | #851, design only; não desdobrar Executor sem gate e revisão de fonte |
| Vídeo reproduzível de demonstração e cinco casos positivos/três negativos efetivamente executados com conta revisor | **PENDENTE** | roteiro no pacote e documentação OpenAI |
| Segurança pré-publicação (rate limiting DEV, testes sessão, auditoria externa) | **ABERTO** | hara-site#189 |
| Windows RC 0.3.54, rollback e prova independente | **ABERTO** | hara-site#240; online 0.3.53 não equivale à homologação RC |
| Aprovação do plugin pelo Diretório da OpenAI | **NÃO SUBMETIDO** | Só se altera após ação no portal e decisão da OpenAI |

Documentação oficial consultada:
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/app-review
- https://developers.openai.com/plugins/deploy/submission-errors
- https://developers.openai.com/plugins/plugin-guidelines

**Regra comercial atual da OpenAI:** não mostrar planos, vender serviços/assinaturas digitais, promover upgrades nem enviar diretamente para Checkout dentro do plugin. Usuários podem conectar contas pagas já existentes. O Stripe comercial é **separado** no site HARA Labs; a listagem OpenAI deve focar no serviço, não em vendas dentro do ChatGPT.

## Stripe — sem uso de credenciais antes do cadastro

- Código Stripe Billing V1 existente: Checkout, Portal, webhook assinado, deduplicação, vínculo assinatura → entitlement.
- PROD (último recibo hara-site#296): Stripe secrets / preços não ativos, `billing_connections=0`, `billing_webhook_events=0`; STANDARD/SCALE não ativos; TRIAL permanece 100 unidades/mês.
- DEV: `stripe_test_activation_wizard.py --check` foi reportado `READY_FOR_INTERACTIVE_APPLY`; Cloudflare/Wrangler do Services foi reautenticado, porém os quatro segredos DEV Stripe seguem ausentes.
- Referência de teste `STANDARD R$80/mês` aparece no histórico; **não presumir preço aprovado**. SCALE, limites de unidades, tributação e periodicidade comercial exigem decisão explícita.
- O fundador possui `FOUNDER_INTERNAL/ACTIVE` e não deve pagar a própria assinatura só para validar a conexão.
- **Próxima etapa após cadastro Stripe TEST autorizado:** produto/preço → webhook/Customer Portal → credenciais DEV em canal privado → checkout TEST → eventos idempotentes → entitlement/quota → MCP → suspensão/cancelamento. **Sem valores de chaves no GitHub, issues, chat ou logs.**
- Referência operacional: `docs/operations/HARA_COMMANDER_BILLING_PROD_ACTIVATION_RUNBOOK.md` e hara-site#296.

## Limites e decisão de release

**Pronto agora:** base V1 homologada, primeiro cliente fundador via HARA Identity, ZIP OpenAI regenerado e validado offline, sete superfícies HTTPS públicas testadas, código Billing V1 testado sinteticamente.

**Não declarar pronto para venda pública:** nenhum Stripe checkout real/TEST deste ciclo, nenhuma conta Stripe conectada, nenhuma aprovação OpenAI, nenhuma execução oficial de Scan Tools, revisão externa de segurança e Windows RC ainda abertos.

Uma beta **Linux-only** controlada pode ser avaliada após fechar conta externa + billing TEST + segurança/termos; não anunciar Windows antes de #240. Escala 20k não é pré-condição para primeiro cliente controlado, mas #163 permanece antes de promessa de escala.

## Owners canônicos

- Produto/OpenAI: https://github.com/tiagoharalabs/hara-platform/issues/851
- Continuation integrada: https://github.com/tiagoharalabs/hara-site/issues/310
- Billing: https://github.com/tiagoharalabs/hara-site/issues/296
- Segurança: https://github.com/tiagoharalabs/hara-site/issues/189
- Windows: https://github.com/tiagoharalabs/hara-site/issues/240
- Event V2 e escala: https://github.com/tiagoharalabs/hara-site/issues/163

**Política de mudança desta PR:** somente documentação/runbook e verificador GET. Nada de PROD deploy, Worker secrets, alterações de D1, upgrade do Agent, plugin público submetido ou Stripe product/price criado.
