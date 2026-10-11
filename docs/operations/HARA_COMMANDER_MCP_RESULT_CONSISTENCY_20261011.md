# Commander — consistência de erros e resultados MCP, 11/10/2026

## Escopo

Correção aplicada à fonte de `apps/commander/src/customer-mcp-simple.mjs`, sobre a base local `e3dcbbb7fc29970319fc5ffb8ac8d60fbe031b5a`. O módulo foi editado por processo autorizado, com verificação do SHA anterior e backup. Não foi alterado `worker.js`, nenhum agente, pacote assinado, permissão, preço, executor ou CSS. Não houve deploy, rede de teste com clientes, migração de banco ou coleta de custo.

## Mudanças implementadas

1. Falhas operacionais conhecidas e resultados explicitamente malsucedidos recebem `isError: true` no resultado MCP, preservando os campos estruturados e a cópia JSON textual. Uma resposta HTTP bem-sucedida não deve ocultar a falha da operação. Sessões RUNNING e respostas PASS continuam sem flag de erro. Um exit code não zero de comando não é convertido automaticamente em falha da ferramenta ou inferência de sucesso de domínio.
2. `DEVICE_CALL_TIMEOUT` e `CHANNEL_TRANSIENT_TIMEOUT` deixam de recomendar repetição. Preservam o estado TIMEOUT, mas usam `mutation_performed: null`, `completed: null`, `execution_outcome: UNKNOWN`, `retryable: false`, `requires_reconciliation: true` e `automatic_retry_allowed: false`. A orientação é consultar a chamada existente e seus recibos. Isso é correção da informação ao cliente, não implantação de um mecanismo exactly-once, cancelamento remoto ou garantia contra toda duplicação.
3. Mensagens arbitrárias de exceção não são mais publicadas após mera troca de pontuação por underscores. São aceitos apenas códigos simbólicos com formato restrito e tamanho limitado; frases, caminhos, cabeçalhos e JSON se tornam `COMMANDER_MCP_TOOL_FAILED`. Não se afirma que isso seja um detector universal de segredos; um código simbólico válido continua sendo preservado.
4. `EDIT_MATCH_NOT_FOUND` agora informa `match_found: false` e recomenda reler o arquivo. Não declara `exists: false`, pois ausência do trecho não comprova ausência do arquivo.

Os nomes sugeridos para reconciliar timeout são `get_recent_tool_calls` e `get_receipt`, já expostos no perfil simples. Não é afirmada identificação unívoca da chamada quando o erro não contém seu ID. O operador deve reconciliar com os identificadores disponíveis e não escolher arbitrariamente a chamada mais recente.

## Validação executada no Services

Novo teste: `apps/commander/scripts/test_mcp_result_consistency.mjs`.

- Antes: 38 casos, 5 PASS, 33 FAIL.
- Depois: 38 casos, 38 PASS, 0 FAIL.
- Ambiente: Node v24.15.0, handler MCP real executado em processo local com executor sintético. Nenhum comando do dispositivo, HTTP externo, fila de produção ou Cloudflare foi invocado pelo teste.
- A suíte anterior `test_customer_mcp_simple_profile.mjs` passou após atualização explícita de quatro expectativas alteradas: erros operacionais devem expor isError; timeout não deve recomendar repetição. As verificações de nomes de ferramentas, limites, mapeamentos e anotações foram mantidas.

SHA fonte anterior: `37432b67193c47e87c5620261b040edde7da071525460d89d8fa500fe7270d27`.
SHA fonte corrigida: `e724d47bb63f023266b158622f08312271171019bc537dc164e3966d2a8e8716`.
SHA teste novo: `9a896fb430350ccfa95ad83166cd2de9386b1c6b9c8afe4aa8ab183b89005512`.
SHA suíte anterior atualizada: `ae881396ec0b566a95732827b30d978811206beca5d665ae987ab7f34a518ad5`.

Evidências no Services:
- `/tmp_hara/commander-result-consistency-before-20261011.json`.
- `/tmp_hara/commander-result-consistency-after-20261011.json`.
- `/tmp_hara/commander-result-profile-regression-20261011.txt`.
- Backup: `/tmp_hara/commander-result-consistency-before-20261011.mjs`.

## Referência externa verificada

A especificação MCP 2025-11-25, seção Tools/Error Handling, define isError para falhas de execução da ferramenta. A seção Cancellation reconhece corridas em que a operação termina antes de o cancelamento chegar. Referências consultadas nesta revisão:
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation

## Limites e bloqueios preservados

O Worker continua com as falhas conhecidas de encaminhamento de expected_sha256 e offset. Não foi tentada outra rota para aplicar o patch bloqueado anteriormente. A suíte geral de 68 validadores NÃO foi reexecutada nesta rodada. Os 38 casos acima não equivalem a 38 cenários de carga, nem ao teste anterior de passagem de argumentos, que também tem 38 casos e é uma suíte diferente.

O novo teste ainda precisa integrar a automação de validação antes de promoção. Falta homologar a mudança de contrato dos timeouts nos clientes reais, em especial o tratamento dos campos nulos e de isError. Permanece pendente a apuração completa de custos, convergência das versões em produção e carga de 1.000–10.000 clientes reais. Esta entrega local não aprova publicação em produção.
