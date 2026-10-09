# H.A.R.A. Commander — cliente MCP comercial autenticado, execução real no Núcleo A (2026-10-09)

## Resultado: E2E COMMERCIAL MCP → D1 → AGENT = PASS

A partir da ferramenta do **plugin ChatGPT H.A.R.A. Commander recém-cadastrado**, e não do conector nomeado Baseline, foram chamadas:
- `mcp__H_A_R_A__Commander__ping({computer:"nucleo-a"})`: `state=PASS`, `pong=true`, Agent versão `0.3.41`.
- `mcp__H_A_R_A__Commander__get_device_info({computer:"nucleo-a"})`: `state=PASS`, `platform=LINUX`, `architecture=x86_64`, `transport_mode=OUTBOUND_RELAY`.

O plugin estava configurado no ChatGPT para `https://commander.haralabs.com.br/api/mcp?profile=simple` com HARA Identity OAuth (configuração demonstrada pelo proprietário na interface). O Worker da Cloudflare verifica Bearer de HARA Identity antes de executar chamadas MCP; a URL pública sem credenciais retorna `401`. Nenhum segredo/token foi obtido, lido ou copiado.

### Prova forte: recibo do Agent + registro PROD D1 com MESMO request_id

1. Ping realizado pela ferramenta ChatGPT, com resultado `PASS` e recibo SHA-256 cuja forma abreviada é `622a870e3733…`.
   - Recibo local em `nucleo-a`: SHA-256 do conteúdo confere exatamente com o nome do arquivo; `tool_id=hara.ping`, `transport_mode=OUTBOUND_RELAY`, `state=PASS`, `completed_at_utc=2026-10-09T23:16:09.945Z`.
   - Request id: prefixo `HARA-CUSTOMER-MCP-` (não publicar identificador integral).
   - Consulta independente ao D1 produtivo `hara-commander-product-prod.commander_device_calls` pelo request id exato obtido do recibo local retornou **exatamente 1** registro: `hara.ping`, `COMPLETED`, criado `2026-10-09T23:16:09.141Z`, concluído `23:16:10.085Z`, dispositivo `nucleo-a`.
   - `CUSTOMER_MCP_D1_AGENT_REQUEST_CORRELATION=PASS`.

2. `get_device_info` realizado pela mesma ferramenta do plugin ChatGPT, com recibo abreviado `d3b0b5b187d3…`.
   - Recibo local no Agent verificado por SHA-256: `hara.device.info`, `OUTBOUND_RELAY`, `PASS`, `completed_at_utc=2026-10-09T23:14:33.785Z`.
   - O request id exato do recibo local correspondeu a **exatamente 1** registro PROD D1: `hara.device.info`, `COMPLETED`, criado `23:14:32.923Z`, concluído `23:14:33.924Z`.
   - `CLOUDFLARE_D1_AGENT_DEVICE_INFO_CORRELATION=PASS`.

### Esclarecimento: marcador HARA_SERVICES na versão 0.3.41 é legado e enganoso

O código do Agent `apps/commander/public/agent/linux.py`, na função `execute_tool` e no `write_receipt`, marca **qualquer chamada `_transport != LOCAL_MCP`** como `operational_authority="HARA_SERVICES"`, inclusive chamada realmente vinda do Worker comercial via `OUTBOUND_RELAY`. Esse campo não comprova participação do MCP administrativo. O mesmo Agent fixa `runtime_authority_from_chatgpt=false` para qualquer chamada, portanto tampouco serve sozinho como medidor de origem ChatGPT. O Worker `projectCustomerToolResult` só repassa o marcador; por isso ele é enganoso na apresentação.

**Prova correta de trajeto:** plugin ChatGPT H.A.R.A. Commander nomeado, requisição e recibo autenticado do Agent, request ID correlacionado por consulta independente ao D1 Cloudflare, status `COMPLETED`, duas ferramentas distintas.

A configuração comercial está funcional para esta conta conectada no ChatGPT e o Núcleo A testado. Isso não substitui testes com cliente diferente/segundo tenant, matriz de negação, operações de escrita nem revisão de publicação da OpenAI. Não alegar aprovação pública do plugin ou conformidade geral.

### Próximos ajustes recomendados

- Corrigir em release futura a proveniência remota do Agent (distinguir `HARA_COMMANDER_CLOUD_MCP` de administração Services) e projetá-la corretamente no Worker, mantendo retrocompatibilidade com recibos e auditoria anteriores.
- Fazer testes de segurança entre tenants distintos, falha de autorização, revogação e escrita autorizada antes de distribuição pública.
- Preservar a versão pública assinada `0.3.41`; candidato `0.3.43` ainda condicionado à assinatura governada. Nenhuma mutação foi realizada nos computadores durante esta prova.
