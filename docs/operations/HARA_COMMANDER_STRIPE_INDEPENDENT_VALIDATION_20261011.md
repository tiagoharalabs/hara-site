# H.A.R.A. Commander — homologação técnica independente do Stripe (11/10/2026)

## Escopo

A implantação das correções do portal e a validação operacional foram autorizadas sem que o proprietário tenha concluído sua conta no Stripe. Nenhuma conta bancária ou chave Stripe é necessária para estes ensaios; não houve transação financeira, criação de assinatura nem configuração de webhook.

## Produção comprovada

- Agentes: 7/7 Linux ONLINE em 0.3.45, catálogo H.A.R.A. Commander.
- Caminho real produto comercial: 14/14 pings em duas ondas distribuídos pelas sete máquinas; sete execuções `hostname` foram concluídas com exit code 0 e recibo do H.A.R.A. Agent, sem passagem pelo Desktop Commander. Os tempos das ondas não devem ser publicados como latência individual.
- Segurança: o `app.js` corrigido protege bootstrap, dashboard, identidade, dispositivos e billing de respostas antigas após logout/troca de sessão. Testes exatos de VM antes 3/11, depois 14/14 PASS; atividade 25/25 PASS; gate completo na fonte 80/80 PASS.
- DEV Worker versão `fba1a6e8-a38e-4497-aa25-7ea4776b6053`, health/auth OK e arquivo app.js SHA-256 `7c3ec0b7bf6de107474cf674b8365136e91535a1929e8bf1af56fa12672c4a31` igual à fonte testada.
- PROD Worker versão `7d148653-fc93-4cd6-94cc-07c3d26b52c5`, 100%, health/auth OK, mesmo SHA-256 do app.js em rede. GitHub Actions run 38175333829 sucesso na revisão do código `5270796f3b338b4258242b8c30259311f9661f23`.

## Billing sem Stripe

O código do plano TRIAL e acesso Founder continua operacional enquanto o Stripe estiver indisponível. O catálogo STANDARD exibe os termos comerciais aprovados, mas o checkout não é marcado como pronto, não há Customer Portal e chamadas de cobrança são recusadas antes de fazer requisições externas. Casos sintéticos específicos em `test_no_stripe_technical_mode.mjs` passaram 13/13 com 0 requisições reais ao Stripe. O teste não é um pagamento realizado.

## Capacidade

Os modelos existentes de Event V2 ativo 1k e tempestade de reconexão passaram, bem como SQL local para 1.000/10.000 tenants; reavaliar caso aumentem intensidade ou número de dispositivos por cliente. O DEV passou anteriormente 1.000 requisições GET ao health com 0 erros e concorrência máxima 50. **Ainda não existe certificação integrada para 1.000 logins OAuth e 1.000 Agents simultâneos.** Esse marco exige load/soak com múltiplos tenants reais de teste, D1/DO/Workers observados, custo, latência, queda de rede e isolamento.

## OpenAI e dependências de aprovação

A validação técnica do MCP e do plugin não depende de Stripe, mas a publicação pública exige Business Verification, conta reviewer com login funcional e sem MFA inacessível, vídeo de demonstração, Scan Tools e análise pela OpenAI. A documentação oficial também recomenda contato prévio com a OpenAI para plugins cujo valor central inclui execução local e acesso arbitrário a arquivos/hardware, o que se aplica ao H.A.R.A. Commander. Não apresentar o app como aprovado.

Links oficiais: https://developers.openai.com/plugins/deploy/submission , https://developers.openai.com/plugins/deploy/app-review , https://developers.openai.com/plugins/guides/submit-claude-plugin .

## Pendente externo

Stripe: cadastro bancário e teste de faturamento continuam sob controle do proprietário, sem urgência imposta por esta frente. D1 de telemetria Event V2: primeiro snapshot real ainda precisa ser observado após o liveness periódico; não usar uma contagem zero antes da janela como falha de execução. Handoff anterior / GitHub sempre prevalece pela revisão e data mais recente; entradas históricas sobre versões antigas são histórico, não status atual.

## Fechamento de CI e persistência de boot

GitHub Actions run 38175694137 PASS na revisão 7ee4686 com 81 validadores, sem Stripe e sem segredo. Sentinelas C e D receberam apenas enable do Agent V2 no systemd user (mesmo PID antes/depois, sem restart do Agent). Guard local periódico dessas duas máquinas permaneceu inativo para evitar interrupções do laboratório. As outras cinco máquinas já mantinham o Agent habilitado. Tarefa técnica de carga real 1000 usuários e Store cloud snapshot permanecem abertas.
