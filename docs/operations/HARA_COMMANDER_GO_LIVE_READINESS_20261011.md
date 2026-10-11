# H.A.R.A. Commander — go-live técnico e comercial (11/10/2026)

Estado: FOUNDER LINUX 7/7 ONLINE NO AGENT 0.3.45; DEV/PROD OPERACIONAIS; STRIPE E REVIEW PÚBLICO PENDENTES. Não se declara capacidade certificada de 1.000 usuários reais, cobrança ativa ou aprovação pela OpenAI.

## Proprietário como primeiro usuário real

O próprio plugin H.A.R.A. Commander executou no Services (não por relay Desktop): criação de pasta, escrita, edição com expected_sha256 e precondition_checked=true, negação por hash anterior com FILE_PRECONDITION_FAILED, leitura de confirmação, processo one-shot com exit 0, sessão Python interativa (start/interact/output/exit) com exit 0 e recibos. Tudo em conteúdo sintético no /tmp_hara.

A frota Founder Linux inteira foi atualizada com pacotes assinados RS256 por dispositivo e rollback local: services, nucleo-a, sentinela-a, sentinela-b, sentinela-c, sentinela-d e ninja-blue. Após os upgrades, o catálogo MCP mostrou 7/7 ONLINE e 0.3.45; consultas diretas às máquinas confirmaram a versão. Ações reiniciaram apenas o serviço Agent V2, não as máquinas. Windows legado permanece sem homologação.

## Capacidade real vs. modelo

Cloudflare DEV recebeu 1.000 requisições HTTP de GET /api/health: 100 em concorrência 10, 300 em 25, 600 em 50; 1000/1000 sucesso, zero erros, p50 42.03 ms, p95 231.45 ms, p99 482.81 ms. Evidência local privada /tmp_hara/commander-paid-dev-health-1000-20261011.json. O novo script commander_paid_dev_health_ramp.py exige --execute para tráfego; por padrão é offline.

O modelo SQLite com 1.000 contas/2.000 dispositivos e 10.000 contas/20.000 dispositivos/210.000 sessões passou. Ambos os testes NÃO representam 1.000 usuários OAuth/ChatGPT autenticados, dispositivos ativos, Durable Objects, carga simultânea real nem custo de produção. Esses fatores precisam de um ramp/soak multitenant medido. O último resumo de atividade MCP de 24h mostrou 2.091 chamadas, 2.062 concluídas, 20 falhas e 98,7% de sucesso observado, incluindo ensaios negativos; não certificar SLO sem separar tráfego de teste.

## Telemetria

Event V2 0.3.45 possui SQLite local com modo 0600, retenção de sete dias e agregados enviados no LIVENESS existente a cada ~6h, sem novo polling HTTP. Um reinício controlado no Services provou persistência. No último readback D1 PROD, commander_device_telemetry_snapshot ainda tinha 0 registros. Falta observar o primeiro snapshot real após a janela de checkpoint; não antecipar ou inventar entrega cloud.

## Stripe: cobrança ainda inativa

Preflight remoto PROD: schema PASS; TRIAL 10.000 chamadas/mês, STANDARD ativo a BRL 8.000 centavos/mês sem quota mensal de chamadas. Mas STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET e STRIPE_PRICE_STANDARD estão PENDING; billing_connections=0; billing_webhook_events=0; COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE. DEV também sem quatro configurações, incluindo STRIPE_PORTAL_CONFIGURATION. A rotina de Stripe de TESTE foi conferida com --check e retornou READY_FOR_INTERACTIVE_APPLY.

Próxima ação que requer o operador: no terminal do Services, dentro da árvore canônica, executar python3 -B apps/commander/scripts/stripe_test_activation_wizard.py --apply e digitar sk_test_ exclusivamente no prompt secreto local (nunca no chat). A rotina, test-only, cria ou reutiliza produto/preço mensal BRL 80, webhook, portal e instala configurações DEV. Concluir TEST Checkout, eventos assinados/idempotentes, suspensão/recuperação/cancelamento e tenant Pro isolado da conta Founder antes do modo LIVE. Não cobrar cartão real ou tocar conta Founder na homologação.

## Pacote técnico atualizado para upload

O arquivo apps/commander/plugin-submission/hara-commander-capivara-v0.2.0-review.zip está preparado e validado (SHA-256 40c5a69ed30b7ed626fe725b1eb2841d423e3e3ef772b49120aad228f606c483). Contém 33 ferramentas referenciadas no source, cinco casos positivos, três negativos, OAuth DCR e notas de release. O ZIP 0.1.0 está aposentado como histórico. A ausência de vídeo de demonstração e conta separada de revisor continua bloqueando envio público.

## Revisão da OpenAI

O pacote já existente apps/commander/plugin-submission contém plugin.json, mcp.json, ícones e ZIP; validação offline SOURCE_PACKAGE_PASS, 33 ferramentas, cinco testes positivos e três negativos, URLs HTTPS. Metadados OAuth/PKCE S256/DCR de produção passaram precheck, mas fluxo de consentimento e troca de tokens de uma nova conta revisora via ChatGPT continuam não comprovados. Teste protegido sem token é negado (401).

Bloqueios externos: verificação de negócio/organização H.A.R.A. Labs, permissão Apps Management, token verdadeiro do desafio de domínio emitido pelo portal, tenant e login de demonstração isolados, vídeo real, tool scan, submissão e aprovação pela OpenAI. O pacote NÃO foi submetido nem aprovado nesta entrega. Senhas de review devem ir somente ao formulário privado apropriado.

## Próximos gates sem falsos positivos

1. Stripe TEST via chave sk_test_ digitada pelo proprietário no Services; homologação completa com tenant TEST distinto de Founder.
2. Capturar primeiro snapshot real 0.3.45 -> Event V2 -> D1 e correlacionar tráfego/custo/latência.
3. Testar logins, OAuth, MCP e Agents multitenant sob 10 -> 100 -> 250 -> 1.000 usuários reais/sintéticos autenticados em DEV, com ramp, soak, erros, custos e limites de concorrência. Não chamar 1k certificado antes disso.
4. Submeter plugin com review 5+3, conta demo, vídeo, verificação empresarial e aprovação da OpenAI.
5. Windows e faturamento LIVE ainda exigem homologação própria; Storage segue HOLD divergente, sem force-push.

Fontes internas: docs/operations/HARA_COMMANDER_BILLING_PROD_ACTIVATION_RUNBOOK.md; docs/operations/HARA_COMMANDER_EVENT_V2_LOCAL_TELEMETRY_LOW_CHATTER_20261011.md; docs/OPENAI_APPS_CHALLENGE_RUNBOOK.md. Documentação oficial: https://developers.openai.com/plugins/deploy/app-review e https://developers.openai.com/plugins/deploy/submission.
