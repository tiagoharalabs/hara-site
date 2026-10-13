# Diagnóstico do pilot002

O pilot002 original falhou com SOAK_PROBE_ERROR__INTERNAL_ERROR no intervalo 01:40–01:41Z de 13/10. A causa permanece indeterminada. As 18 ondas anteriores passaram, mas o runner descartou o request ID de health e a onda que falhou. O snapshot local conectado não prova que o Durable Object recebeu a chamada naquele instante. Cleanup removeu os logs privados dos Agents.

A revisão encontrou pontos plausíveis em leituras D1 e getByName/stub.fetch; nenhum foi identificado como causa real. hara.health não utiliza TenantQuota ou commit. Erros normais do DeviceChannel manteriam códigos CHANNEL_*. O Worker sanitiza exceções desconhecidas como INTERNAL_ERROR sem registrar classe/stack.

## Repetição limitada

pilot002_bounded_diagnostic.py usa dois fixtures DEV próprios, pin 97471, health por minuto por 20 min, zero retries, limpeza exata e métricas sem payloads. O primeiro lançamento parou localmente antes de criar fixtures (diretório de evidência já existente); essa falha de setup foi preservada. A execução seguinte usa relatório autoritativo pilot002-diagnostic-002/diagnostic-status.json.

A primeira assinatura de tail não iniciou porque --sampling-rate 1 é inválido neste Wrangler; esse intervalo não comprova ausência de exceções. pilot002_corrected_tail_capture.py omite o filtro e captura somente metadados sanitizados de POSTs do pin DEV. Nada de stdout/stderr cru, headers, mensagens, cookies ou payloads é salvo. Um rerun sem erro não apaga a falha original nem encerra a causa.

## Propostas sem aplicação ou deploy

- runner-diagnostics-proposed.patch: ID de health antes de disparar, journal da onda antes das asserções e FAIL antes de cleanup. Quatro casos offline, compilação e git apply --check PASS; sem retry.
- worker-safe-diagnostics-proposed.patch: somente ENV DEV + DEV_SAFE_ERROR_DIAGNOSTICS_ENABLED=true; a ausência do flag desabilita e PROD permanece desabilitado mesmo com flag true. O branch final JSON de erros 5xx emite incidente seguro e adiciona header UUID correlacionado. Fluxo especial auth/callback e 429 não mudam.
- Classe/cause são enums; mensagem vira digest limitado; até quatro frames permitem só função conhecida, linha e coluna. URLs, caminhos, args, headers, payloads, cookies e identidades não são emitidos.
- 23 verificações do helper e 21 de Worker.fetch real com source proposto em memória passaram. Fault D1 é sintético nesses testes; nenhum Worker ou D1 foi alterado por eles.

Fontes: pilot002-diagnostic-source-review.json, worker-safe-diagnostics-proposal.json e os relatórios de diagnóstico/tail. O runtime Founder, PROD, Stripe e fixtures dos outros agentes foram preservados.

## Resultado limitado

A execução diagnóstica encerrou após 1200s: 20 ondas, 48 chamadas MCP documentadas (setup/health/invoke/replay), nenhuma falha nem retry. Isso não inclui todos os enrollments, reconciliações ou eventos de telemetry do Agent. As duas fixtures próprias foram limpas; unidade inativa e MainPID zero; pin 97471 confirmado ao fim. A assinatura corrigida de tail cobriu só os últimos 348s, com 191 eventos ok e nenhum 5xx ou exception. O INTERNAL_ERROR original não foi reproduzido e sua causa permanece indeterminada; o pilot002 original continua FAIL. Nenhuma duração de 24h/72h foi certificada.
