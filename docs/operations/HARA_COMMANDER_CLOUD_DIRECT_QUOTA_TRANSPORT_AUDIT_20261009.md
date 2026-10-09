# H.A.R.A. Commander — auditoria: transporte Cloud vs Direct e franquia (2026-10-09)

## Conclusão principal

**O modo comercial Cloud (produção assinada Agent 0.3.41) NÃO se transforma em um canal direto ChatGPT → Agent após OAuth.** Todas as chamadas MCP do plugin público alcançam `https://commander.haralabs.com.br/api/mcp?profile=simple` na Cloudflare. O Worker autentica o bearer via HARA Identity, resolve tenant/dispositivo, aplica a política de uso, cria chamada `HARA-CUSTOMER-MCP-*` e entrega ao Agent por `OUTBOUND_RELAY`. O resultado retorna pelo Worker. HARA Services administrativo não é o proxy do produto; o rótulo legado `operational_authority=HARA_SERVICES` no Agent não deve ser usado para inferir o trajeto.

O **Direct (LOCAL_TUNNEL)** é outra modalidade, com MCP local e túnel privado da OpenAI, não é substituto transparente para o plugin público. O cadastro do cliente via OAuth não provisiona automaticamente um Secure MCP Tunnel privado na OpenAI Platform.

## Contadores — não confundir

**Franquia de chamadas governadas, autoritativa para bloqueio:**
- Tabela `plans` PROD D1 verificada ao vivo: `TRIAL / Free` = `CALENDAR_MONTH` com 10.000 unidades; `REVIEW` = `CALENDAR_MONTH` com 100; `FOUNDER_INTERNAL` = `NONE` sem limite; `STANDARD / Pro` = `NONE` sem limite.
- `TenantQuota.reserve` (Durable Object) bloqueia previamente operação governada ao esgotar quota (`QUOTA_EXCEEDED`). A unidade é confirmada no sucesso com recibo SHA-256 (`commit`); falhas liberam reservas (`release`), e reservas antigas são liberadas após atingir 600s de idade, no próximo processamento de quota. Idempotência impede cobrança duplicada por mesmo request id.
- Ferramentas `hara.ping`, `hara.health`, `hara.functions.list`, `hara.functions.describe`, `hara.receipts.get` **não geram unidade cobrável**; outras ferramentas governadas, incluindo `get_device_info`/operações sobre arquivos, podem ser cobradas. `quotaFunctionIdForTool` é a função autoritativa.
- `LOCAL_BUDGET` com blocos de 100 unidades assinados existe e foi testado; para distribuição Cloud com Agent 0.3.41, o padrão medido é `CLOUD_QUOTA` ou `UNMETERED` conforme plano e dispositivo. A elegibilidade de orçamento local do Linux exige Agent >=0.3.36; se não há bloco ativo, usa `CLOUD_QUOTA`.

**Contador informativo do site:** `productTransactionHistory` soma `commander_device_calls` da conta (7 dias/total) e o total local de sessões MCP. É **contagem de chamadas registradas**, não a franquia de sucessos cobráveis. Uma chamada de ping ou falha pode aumentar o contador visual sem consumir franquia.

**Heartbeat e polling:** não consomem quota. No Agent público 0.3.41 `HEARTBEAT_SECONDS=60`, `CALL_POLL_IDLE_SECONDS=10`, `CALL_POLL_HOT_SECONDS=2`, `PRODUCT_LEASE_REFRESH_SECONDS=4h`. Teste `validate_agent_request_efficiency.py` modela **10.086** requisições de infraestrutura por dia por Agent ocioso e **70.602** por dia para sete Agents ligados, sem serem 70 mil transações cobráveis. Não reduzir apenas heartbeat sem replanejar presença (`DEVICE_ONLINE_GRACE_SECONDS=240`).

**Telemetria periódica Direct:** `AGENT_TELEMETRY_INTERVAL_SECONDS=1h`, `LOCAL_METERING_MIN_INTERVAL_SECONDS=1h`, metadados `usage_report` sem conteúdo. Modalidade Direct faz `MCP_START`, `AGENT_HEARTBEAT` horário, `AGENT_STOP` sujeito à regra de duração; a contagem local é distinta do Gateway comercial e pode apresentar sincronização eventual. Não alegar que esta é a modalidade atualmente instalada.

## Provas desta rodada

- Plugin conectado `mcp__H_A_R_A__Commander__get_usage_stats`: `FOUNDER_INTERNAL`, `period_kind=NONE`, `limit=null`, `metered=false`. Portanto **não serve para demonstrar o bloqueio de Free**.
- Plugin `get_activity(window=24h)`: 75 chamadas Cloud registradas, com estados e ferramentas; detalhe de origem `CLOUD_CALL_HISTORY`.
- PROD D1: `plans` Free 10k, Review 100, Founder/Internal ilimitado e Pro ilimitado; apenas **um entitlement FOUNDER_INTERNAL e um REVIEW ativos** no readback. **Nenhum Free ativo** para confirmar esgotamento em produção nesta rodada. As 75 chamadas PROD do período consultado estavam em `usage_mode=UNMETERED`.
- Regressões de código: `validate_local_budget_blocks.py` PASS (quota e blocos, incluindo excesso de capacidade), `validate_quota_reservation_ttl.py` PASS, `validate_tenant_quota_storage_efficiency.py` PASS, `validate_agent_hourly_telemetry.py` PASS, `validate_agent_cloudflare_telemetry.mjs` PASS, `validate_agent_request_efficiency.py` PASS.
- **Prova de esgotamento via cliente Free real em PROD: NÃO REALIZADA.** Evitar classificar como homologação completa de billing. Também não confundir a modalidade Direct privada com produto público Cloud.

## Recomendações concretas

1. **Manter Cloud como modo público**: cada chamada MCP HTTPS atravessa Worker e pode ser medida/limitada em tempo real sem depender de heartbeat. Não armazenar conteúdo fora da janela transitória necessária.
2. Substituir polling frequente de `OUTBOUND_RELAY` por canal de evento/WebSocket `EVENT_V2` persistente e reconexão com backoff para reduzir chamadas ociosas; o MCP remoto ainda transmite comandos pela Cloudflare. Validar em DEV e publicar apenas versão Agent assinada.
3. Criar aceitação isolada com tenant `TRIAL` e franquia pequena em DEV para demonstrar explicitamente `N-1` passa, `N` passa, `N+1` recebe `QUOTA_EXCEEDED`, e idempotência/falha não duplicam consumo, antes de chamar billing de PROD homologado.
4. Para a visão de *somente autenticar na HARA e depois trafegar ferramentas diretamente entre ChatGPT e Agent*, avaliar Direct separado; não prometer que o plugin público pode fazer isso só por ter OAuth.

**Nenhuma alteração de plano, limite, cobrança ou infraestrutura produtiva realizada nesta auditoria.**
