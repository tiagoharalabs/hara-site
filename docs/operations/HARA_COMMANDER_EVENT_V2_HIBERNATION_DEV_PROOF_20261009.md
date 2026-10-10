# H.A.R.A. Commander — Event V2 WebSocket hibernável: prova real isolada em DEV (09/10/2026, BRT)

## Estado e resultado

**DEV CANARY E2E = PASS. PROD COMMERCIAL RELAY = PRESERVED. PROD EVENT V2 CUTOVER = NOT AUTHORIZED / NOT APPLIED.**

O produto comercial via ChatGPT já realizou `ping`/`get_device_info` E2E no Núcleo A, com correspondência por request id entre recibo local e Cloudflare D1 PROD; ver `docs/operations/HARA_COMMANDER_COMMERCIAL_MCP_REAL_E2E_20261009.md`.

A pedido do proprietário, em 09/10/2026 (BRT), foi instalado e testado **um segundo Agent experimental exclusivamente DEV**, isolado do Agent comercial assinado, no Núcleo A. Nenhuma credencial do dispositivo PROD foi copiada, alterada ou substituída. A configuração própria DEV está em `/tmp_hara/commander-event-v2-dev-canary/` com XDG config/data privados e device token com chmod 0600. O serviço estável `hara-commander-agent.service` permaneceu ativo.

## Evidência do WebSocket hibernável

- Worker DEV URL: `https://hara-commander-dev-v2.tiago-sartori.workers.dev`; `/api/device/channel` responde HTTP 426 quando não há Upgrade WS. PROD URL do canal permanece 404; PROD `wrangler.jsonc` continua **sem DEVICE_CHANNEL binding e sem DEVICE_EVENT_V2_ENABLED**.
- Worker DEV configura `DEVICE_EVENT_V2_ENABLED=true` com binding `DEVICE_CHANNEL` apontando para `DeviceChannel` em Durable Object SQLite.
- `apps/commander/src/device-channel.mjs` usa **`this.ctx.acceptWebSocket(server)`**, `serializeAttachment` / `deserializeAttachment` e `webSocketMessage/webSocketClose`. Não usa timers recorrentes de aplicação; a Cloudflare pode hibernar o objeto quando ocioso, sem interromper a conexão.
- O cliente experimental usa RFC 6455 PING de protocolo a cada 60s de ócio (auto-PONG pela Cloudflare não desperta o objeto); `LIVENESS` de aplicação ~6 horas com jitter de +/-15min; **não faz HTTP polling durante o ócio**.
- O Agent DEV foi pareado e conectado: banco DEV registrou `tunnel_mode=EVENT_V2` e processo local `connected=true`, sem erro, em 2026-10-10T00:01:55Z.
- Primeiro teste real: `hara.health` via Gateway interno DEV → D1 DEV → aviso `CALL_AVAILABLE` pelo WebSocket → Agent isolado → resultado `COMPLETED`; latência ponta a ponta **3829ms**. D1 confirmou a conclusão e `usage_mode=UNMETERED` do tenant piloto.
- Reconexão deliberada do Agent DEV com SIGTERM limpo e restart: `DEV_CLEAN_SOCKET_SHUTDOWN=PASS`, `DEV_EVENT_V2_RECONNECTED=PASS`, `PROD_AGENT_STILL_ACTIVE=PASS`.
- Segundo teste real após reconexão: `hara.health` `COMPLETED`, latência ponta a ponta **2499ms**. O MCP comercial também respondeu `pong=true` do Agent assinado `0.3.41` depois desse teste.

**Não declarar medição de economia real de cobrança Cloudflare ou hibernação de runtime já observada pelo Analytics:** a elegibilidade está demonstrada pela API correta e pela ausência de eventos de aplicação ociosos. Durations/requests deverão ser medidas pelo Analytics Cloudflare com janela observacional.

## Regressões de segurança, testes e identidade

- `validate_event_v2_websocket_client.py`: PASS, incluindo TLS, handshake RFC6455, limites, reconnect/backoff, PING sem heartbeat JSON e idle HTTP polling ausente.
- `validate_event_v2_clean_shutdown.py`: PASS.
- `validate_device_channel_source.py`: PASS após reconciliar asserções de isolamento ao caminho autoritativo `mcpProductContext → context.tenant_id`.
- `validate_event_v2_wiring.py`: PASS após reconciliar asserções ao `resolveCustomerTargetDevice(env, context,...)` usado no Worker atual.
- `validate_event_v2_transient_rpc.py`: PASS, código DEV-only e sem persistência de conteúdo de chamadas transient.
- `validate_event_v2_productization.py`: PASS ao distinguir artefato **publicado assinado 0.3.41** de fonte/candidato **0.3.43 não assinado**. Este ajuste não reduz confiança; impede falso positivo de promoção.
- O probe de `commander_event_v2_dev_quota_probe.py --execute` retornou `QUOTA_RESERVE_STATE_INVALID` **porque o usuário DEV ligado ao canário tem plano STANDARD ilimitado** (`UNMETERED`). Não é prova de falha do limite Free nem PASS de quota. Usar tenant isolado com `CALENDAR_MONTH` e limite pequeno em prova separada. A lógica offline TenantQuota e `LOCAL_BUDGET` havia sido validada, mas bloqueio no limite real PROD não foi exercitado aqui.
- A credencial interna de teste `MCP_PRODUCT_TOKEN` foi **renovada somente no Worker DEV** por helper canônico e armazenada sob caminho temporário privado (0600). A primeira tentativa de probe imediatamente após a mudança retornou 401 durante a janela de propagação; a tentativa seguinte PASS com o mesmo token, sem imprimir valor. Coordenar com outras frentes DEV que dependam do token anterior.
- HARA Identity e Cloudflare PROD (versão corrente Worker) não foram mutados nesta rodada; Cloudflare DEV teve somente pareamento/device, secret interna DEV e transações de teste, além de estado efêmero do DeviceChannel. Não foram alterados planos, assinatura, token PROD, MCP OAuth do cliente ou arquivos do Agent PROD.

## Próxima promoção — fail closed

1. Recuperar a chave **privada correta de assinatura** correspondente ao JWK público pinado na distribuição assinada, ou aprovar uma rotação formal com compatibilidade. **Nunca distribuir Agent 0.3.43 sem assinatura, nem ignorar mismatch** (`RELEASE_SIGNING_KEY_MISMATCH` documentado em `docs/operations/HARA_COMMANDER_SIGNED_BETA_0_3_41_20261009.md`).
2. Integrar Event V2 como transporte opcional na nova release Agent assinada, com fallback operacional para `OUTBOUND_RELAY`, sem rodar dois loops do mesmo device simultaneamente; proteger versão Windows e paridade de capabilities.
3. Promover binding `DEVICE_CHANNEL` e migração DO PROD sob flag desligada, depois opt-in de um único dispositivo Founder, validando OAuth real, quotas e idempotência, revogação, presença e reconexão. Reversão somente Worker + selector de transporte; não restaurar D1 PROD de snapshot.
4. Medir 7/30 dias a queda de requests de idle, latência p50/p95, durações DO hibernáveis, D1 writes/reads e falhas de conexão antes da ampliação de frota. Só após isso anunciar redução efetiva de custos e liberar público.

Fontes técnicas da Cloudflare (atualizadas em setembro/outubro de 2026):
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/platform/pricing/

**Canário DEV conectado ao término do teste**, no mesmo host, mas com identidade separada; o monitoramento contínuo da infraestrutura não é executado por esta conversa.
