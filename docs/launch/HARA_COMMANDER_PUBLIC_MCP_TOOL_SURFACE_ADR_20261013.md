# ADR (PROPOSTA) — superfície pública Commander e regra OpenAI de ferramentas independentes

**Estado: P0 AVALIAÇÃO SOURCE-ONLY / NÃO APROVADO.** Não altera o MCP de produção, o agente, o plugin privado instalado nem o plano de controle do HARA Services. Owner da decisão: hara-platform#851; Event V2 não é afetado.

## Conflito identificado com a documentação OpenAI de 13/10/2026

O pacote portátil que passou no validator V5 (SHA256 `0e9be2f9edb0ec5cd42e600ce61c0e746b50176619addbabd2e7f02e4092b900`) declara as cinco ferramentas:

`hara.health`, `hara.functions.list`, `hara.functions.describe`, `hara.functions.invoke`, `hara.receipts.get`.

O [guia de plugins](https://developers.openai.com/plugins/plugin-guidelines) agora determina:

> Expose each model-callable operation as a separate tool with a clear description, input schema, and annotations. Do not use discovery, operation selection, or schema fetching with a generic executor to enable operations not individually exposed for review.

**Risco material:** `functions.list` + `functions.describe` + `functions.invoke(function_id)` pode representar justamente o padrão que permite ao modelo descobrir operações e executá-las por ferramenta genérica. A regra de backend que restringe a `READ_ONLY` melhora a segurança, mas **não prova por si só** que cada operação foi revisada individualmente pela OpenAI.

Além disso, se `functions.invoke` despacha trabalho, registra recibos ou enfileira jobs, `readOnlyHint` precisa descrever o **efeito real da própria ferramenta**, não apenas a função local finalmente invocada. O guia classifica disparar ações / jobs / workflows como não estritamente read-only. Uma justificativa textual no portal não corrige hint errado anunciado por servidor.

## O que verificar no Scan Tools (somente após autorização)

- Nomes e *schemas* realmente anunciados pela **MCP comercial**, não os 31 tools do plugin privado de desenvolvimento.
- Catálogo efetivo de `function_id` e se ele é fechado / imutável por tenant / autorização; existência de functions read-only que acessam rede ou dados sensíveis.
- Tool descriptions sem escolha genérica de operação; prompts inicial/reviewer reproduzíveis.
- Anotações explicitas e coerentes: `readOnlyHint`, `destructiveHint`, `openWorldHint`, sem esconder side-effects (fila, token/quota reserve/commit, recibo).
- Recuperação de erro, idempotência, nenhum vazamento de device de outro tenant, secrets ou IDs internos supérfluos.

## Caminhos candidatos para decisão do owner

### A — Expor operação pública explícita (preferível se o Scan Tools rejeitar a superfície atual)

Manter **intacto** o protocolo interno cliente/agente e os atuais métodos de operação no backend. Criar **camada pública de revisão** estática, com cada operação MCP do app publicada com nome/schema/hints individualizados, baseada em um allowlist de funções que passaram por gates independentes.

Exemplo de recorte inicial, **não implementado**:
- `get_selected_device_health`: consulta saúde do Agent/dispositivo associado à conta.
- `get_selected_device_info`: operação específica, internamente vinculada ao `device.info`, sem `function_id` controlado pelo modelo.
- `get_execution_receipt`: recibo minimizado autorizado para a última operação relevante do próprio tenant.

O recorte não precisa inventar ferramentas adicionais apenas para alcançar cinco. Qualquer mudança da superfície pública precisa manter compatibilidade e autorização por tenant, ter testes de regressão e owner/canário separado antes de deploy. **Não anunciar capacidades que não foram testadas.**

### B — Defender a superfície atual apenas se estritamente limitada e aceitada

Demonstrar ao revisor, com Scan Tools real e contrato autoritativo, que a operação genérica está vinculada a uma lista fechada **de operações explicitamente examinadas** (por exemplo, apenas `device.info`), sem escolha dinâmica não revisada, e que hints refletem chamadas e recibos reais. Solicitar orientação/feedback do portal; não presumir aceitação.

Se B não satisfizer a regra, voltar à proposta A com mudança de fonte submetida a testes.

## Aceitação técnica antes de um release novo

1. Lista autoritativa de funções públicas **fixa, mínima e inspecionável**, sem shell nem mutação arbitrária.
2. Cada ferramenta publica *input schema* específico, *output schema* minimizado e hints corretos.
3. OAuth HARA Identity, tenants, quota e dispositivo selecionado permanecem iguais; customer traffic continua fora do MCP Services interno.
4. Testes positivos 5/3 atualizados para as ferramentas **efetivamente publicadas**; nenhuma promessa de operações antigas se a API mudar.
5. Provas negativas de `shell.run`, cross-tenant, função desconhecida, offline, replay/quota e descasamento de device.
6. `Scan Tools` do servidor **PROD aprovado**; diff de metadados e gravação da demonstração; somente depois submeter.
7. Nada é promovido pelo simples ato de editar esta ADR.

## Restrições comerciais

O plugin público não deve exibir plano/assinatura/preço, vender serviço digital ou iniciar Checkout; no máximo explicar indisponibilidade por entitlement e conectar conta já paga pelo site. Ver https://developers.openai.com/plugins/plugin-guidelines#commerce-and-monetization.

**DECISION=OPEN, PROD_CHANGE=FALSE, REVIEW_OWNER=#851.**
