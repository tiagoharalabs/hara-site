# H.A.R.A. Commander — source readback do MCP comercial e possível conflito OpenAI

**Source-only technical note, 13/10/2026. No production mutation.**

## Contrato observado na branch `main`

1. `apps/commander/src/customer-mcp.mjs` (blob SHA `77280d53267dcabe62973975cd03f384c3430728`) declara exatamente cinco tools: `hara.health`, `hara.functions.list`, `hara.functions.describe`, `hara.functions.invoke`, `hara.receipts.get`.
2. A entrada MCP `functions.invoke` aceita no *schema público* `function_id` string (1–180) e `argv` até 64 strings; `functions.describe` aceita ID string (1–180). Esta interface aparenta descoberta genérica/dispatch.
3. **Porém**, `apps/commander/src/device-tool-contract.mjs` (blob SHA `4cb0877bf75f477860811fb4136a6c9835fc9ad5`) fecha a execução: `DEVICE_FUNCTION_ID="device.info"`; `requireFunctionId` rejeita qualquer outro; `canonicalDeviceToolPayload` exige `argv=[]`. Portanto **não há prova de executor arbitrário de funções** no contrato atual. Esta restrição real deve ser incluída na defesa de revisão.
4. `customer-mcp.mjs` usa `readOnlyHint:true` para **todas as cinco tools**, incluindo `functions.invoke`. A operação invoke passa por despacho, reserva/commit de quota e recibo no Worker (ver `apps/commander/scripts/validate_customer_mcp_edge.py`), mesmo quando a ação final `device.info` apenas lê dados. A regra atual da OpenAI classifica iniciar jobs/alterar estado como `readOnlyHint:false`. É necessária **adjudicação de hint por efeito real** antes do Scan Tools, não uma declaração baseada apenas na função terminal.
5. O teste de fonte `apps/commander/scripts/test_customer_mcp_edge.mjs` (blob `1ea47e5268549f172becb669c9f00976333dd37b`) valida exatamente cinco tools e hints atuais, não a aceitação do novo guia OpenAI.

## Correção candidata mínima a avaliar pelo owner #851

Sem mudar os agentes, identidade, canal, quotas ou funções internas:

- No *schema público* das ferramentas `functions.describe/invoke`, restringir `function_id` ao valor literal `device.info` e `argv` a lista vazia. Isso reduz a discrepância entre schema e allowlist real.
- Avaliar em source-only se a superfície deve renomear/expor `device.info` como **tool independente**, removendo a aparência de executor genérico para operações futuras. Qualquer mudança exige atualizar package, cinco cenários positivos/três negativos e testes de compatibilidade, não apenas o README.
- Verificar `readOnlyHint` da tool invoke conforme suas operações efetivas (enfileiramento, reserva de quota, recibos). As outras ferramentas também devem passar pelo teste de side-effects.
- Confirmar no portal o conjunto exato de ferramentas e annotations retornados pelo **Scan Tools oficial**; se a regra continuar ambígua, pedir orientação de revisão, não fabricar aprovação.
- Preservar `customer_services_relay=false`, autenticação HARA Identity, isolamento tenant e bloqueio de shell.

**VERDICT:** `SOURCE_GOVERNANCE_READBACK_PASS`; `OPENAI_INDEPENDENT_TOOL_AND_HINT_REVIEW_OPEN`. O diagnóstico é um **risco de conformidade de publicação**, não descoberta de execução arbitrária atualmente possível. Nenhum patch/runtime enviado ao PROD.
