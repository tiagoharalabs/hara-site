# HARA Commander — revisão R17: códigos públicos de erro e privacidade MCP

Data: 20/10/2026 BRT. Revisão independente pelo **H.A.R.A. Commander**, sem rede pública, D1, credenciais reais, deploy ou alterações no checkout do Codex.

## P1 de privacidade antes de lançar: Full e Simple aceitam texto arbitrário em forma de código

O Codex fechou a semântica de erros operacionais do MCP completo em `e04fbb8`. As suítes existentes continuam **PASS**: `test_full_mcp_result_consistency.mjs` **11/11**, `test_mcp_result_consistency.mjs` (Simple) **40/40**.

**Novo teste de regressão independente:** a função `publicToolError` tanto de `apps/commander/src/customer-mcp.mjs` (**Full**, SHA `13f915c01d7067d8ccf4553ec2b832e5c7a905c0ed2d0453ec20c3d1683ce1cc`) quanto de `customer-mcp-simple.mjs` (**Simple**, SHA `8a145516d17231b97f1ff127252c3b0a904d5388a9a15c07c970be5eb999765e`) aceita mensagens que combinam com `^[A-Z][A-Z0-9_]{0,119}$` como **código público**. O padrão valida aparência de símbolo, **não se ele é um dos erros públicos conhecidos**.

Em `peer_mcp_two_profiles.mjs`, um executor sintético lança `Error` contendo valor inventado com formato de credencial, somente letras maiúsculas/números/sublinhados; o handler real de ambos os perfis devolve o valor literalmente em `result.content[0].text.code`. Os dois resultados têm `isError=true`. Controles positivos: `POLICY_DENIED` continua publicado como código conhecido, e `FILE_PRECONDITION_FAILED` continua classificado corretamente.

| Perfil | Código conhecido preservado | Mensagem sintética parecida com credencial publicada |
| --- | --- | --- |
| Full MCP | PASS | **SIM — falha** |
| Simple MCP | PASS | **SIM — falha** |

A fixture retorna **exit 2**, significando risco reproduzido, e **não** teste de aceite aprovado. Não foram usados tokens, segredos ou eventos reais de clientes. Isto não é prova de vazamento em PROD. O risco surge se uma exceção em produção contiver segredo ou outro dado interno que, por acaso, corresponda à expressão regular.

## Correção de menor risco para o Codex

Criar **uma política de allowlist de códigos públicos documentados**, reutilizada por Full/Simple: se o erro for um código tipado oficialmente suportado (incluindo a taxonomia já coberta por `operationalToolError`), publicar esse código; para quaisquer outras mensagens, devolver somente `COMMANDER_MCP_TOOL_FAILED`. Não basta sanitizar pontuação ou impor comprimento/regex. Preservar distinção `isError`, recibos e `structuredContent` quando existirem. Não registrar `error.message` privado em log público, `result.content` ou `structuredContent`.

**Regressão de aceite:** as duas variações sintéticas do R17 passam a devolver código genérico em Full e Simple, sem revelar conteúdo; manter `POLICY_DENIED`, `FILE_PRECONDITION_FAILED` e demais códigos públicos permitidos, e as **51 regressões anteriores** (11 Full + 40 Simple) verdes. Testar também payload alfanumérico todo maiúsculo sem separadores e nomes inesperados de exceções. Não mudar o comportamento de erro genérico de forma a permitir retry cego de mutações com estado desconhecido.

**Classificação:** P1 segurança de produto / gate comercial. A correção local/QA pode entrar no trabalho atual do Codex; não depende da chave de assinatura. **O lançamento continua HOLD** pela assinatura v5 e pelos readbacks/instalações ainda não homologados.

## Evidências e entrega

`docs/evidence/commander-peer-review-r17-mcp-20261020/` contém `peer_mcp_two_profiles.mjs`, `two-profile-results.json`, README e hashes. O teste roda num clone isolado de `cbfe848` com os bytes Full de `e04fbb8` copiados, `node_modules` do laboratório e requests em memória; nenhum navegador ou rede foi utilizado. Não modificar a branch ativa do Codex nem executar na produção.

A sessão do Núcleo retornou `DEVICE_OFFLINE` temporariamente durante a cópia de evidências, embora SSH a partir de Services funcionasse; ping direto posterior **PASS**. Não atribuir isso à alteração MCP R17 ou a desligamento do Núcleo sem trace.
