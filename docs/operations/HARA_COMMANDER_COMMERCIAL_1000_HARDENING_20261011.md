# H.A.R.A. Commander — blindagem comercial e meta 1.000 clientes
Data 11/10/2026. Escopo: critérios técnicos e governança. Sem Stripe, sem deploy Cloudflare.

## Status comprovado
FOUNDER_TECHNICAL=PASS: Linux 7/7 ONLINE em Agent 0.3.46, PTY 120/120, RS256, recibos e CI. Fontes: docs/evidence/commander-pty-drain-20261011/acceptance.json e docs/evidence/commander-stripe-free-validation-20261011/summary.json.
COMMERCIAL_BETA=HOLD: instalador comercial assinado atualizado e prova real de segundo tenant autenticado ainda pendentes.
GENERAL_AVAILABILITY=HOLD: Windows runtime, soak multitenant 1k, Stripe TEST homologado, revisão OpenAI pendentes.

## Readiness gate opcional (não instalado no CI)
O candidato apps/commander/scripts/commander_commercial_readiness_gate.py apenas lê JSON de evidência local, não toca Cloudflare, D1, Stripe ou máquinas. Confirma três estados, com FOUNDER=PASS, COMMERCIAL_BETA=HOLD, GENERAL_AVAILABILITY=HOLD. Fonte compilou e CLI retornou os estados esperados. O teste unitário candidato contém expectativa errada (trata 0% de erro como falha), e a plataforma bloqueou sua edição. Gate/teste ainda NÃO integrado ao prelaunch CI nem usado para qualquer deploy. Evidências JSON não são atestado criptográfico independente.

## Windows — diferencial crítico não homologado
Public agent/instalador Windows = 0.3.43, transporte POLL_V1. Windows Event V2 RC = fonte e instalador DEV-only prontos para provas, mas não houve Windows real ONLINE na frota. Validadores de contrato e instalação Windows RC passaram em fonte; teste dinâmico PowerShell ficou UNEXERCISED_NO_PWSH no Services. Validador Windows local activity reportou COMMANDER_WINDOWS_LOCAL_ACTIVITY_MANIFEST_VERSION=FAIL, apesar de outros checks de privacidade passarem. Não promover release Windows sem corrigir essa inconsistência e executar testes reais. Tentativa de incorporar validadores ao gate principal foi bloqueada pela plataforma, sem contorno.

## Escala — plano de homologação necessário
1. DEV, 10 a 100 tenants/Agents autenticados, separados, com operações reais e tentativas de acesso cruzado negadas.
2. DEV, 250 WebSockets Event V2, hibernação DO, reconexões em ondas, no-op idle, D1 e Worker analytics.
3. DEV, 1.000 tenants + 1.000 Agents por 24h, quotas Free/Pro, mutações idempotentes, recibos, timeouts, reconciliação por ID, sem chamadas duplicadas. Rampa limitada e teardown comprovado.
4. Soak de 72h após correções, com falhas de rede/Agent/Worker, CPU/D1/DO, p50/p95/p99 e custo real sem extrapolar simples HTTP health. Não carregar workloads de CSOTN nem usar contas reais.
5. Emitir relatório atrelado ao SHA exato de Worker e Agent. Resultado de 1.000 HTTP GETs ao endpoint de saúde não é homologação de 1.000 usuários.

## Regra de governança
Rotinas internas H.A.R.A. de energia, dreno, wake e upgrade continuam governadas pela infraestrutura do laboratório; não exportar shell privilegiado genericamente para clientes. Endpoints SaaS precisam contratos por operação, aprovações de ações destrutivas, tenant-scoped tokens, limite de concorrência, idempotência, recibos, proteção contra replay e dados privados minimizados.
Cloudflare recomenda Durable Objects com WebSocket Hibernation, sem timers periódicos que impeçam hibernação. Ver https://developers.cloudflare.com/durable-objects/best-practices/websockets/ e https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/

Stripe bancário fica com o proprietário; homologação técnica continua independente. OpenAI exige business verification, conta demo, scan e revisão.
