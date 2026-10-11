# Commander — concorrência e sessão no diagnóstico de atividade

Data: 11/10/2026. Base local observada: `aa4a90b228993c9fde4715ccb03e0c7967a437cc`, branch `local/commander-product-current`.

## Estado da entrega

As alterações abaixo foram gravadas por funções de arquivo do Commander na árvore de trabalho do Services e relidas. Não houve comando de shell remoto bem-sucedido nesta rodada, novo commit, publicação GitHub, deploy ou migração. O visual aprovado, argumentos dos comandos, permissões, executores e pacotes de agentes não foram modificados.

## Falhas reproduzidas e corrigidas

1. `loadUsageActivity` usava a variável global de período depois de esperas assíncronas. Uma resposta anterior podia ser armazenada sob o período recém-selecionado ou sobrescrever dados mais novos. Agora o período é capturado ao iniciar e a leitura possui uma geração. Leituras ultrapassadas não renderizam, não alteram o cache e não exibem erros sobre resultados novos.
2. `setGuestHeader` não limpava o cache de atividade nem invalidava as leituras anteriores. Agora limpa as três janelas em memória, oculta o diagnóstico e incrementa a geração. Uma resposta tardia anterior ao logout não repovoa o cache, mesmo após a sessão voltar a ficar ativa. Isto não é teste de isolamento entre tenants no backend.
3. Leituras sobrepostas com o mesmo botão podiam reabilitá-lo cedo ou restaurar o texto intermediário Atualizando. Cada botão agora tem uma leitura proprietária em WeakMap. Somente a última dona restaura o texto e o estado disabled anteriores. Botões distintos são tratados independentemente.
4. Exceções inesperadas de diagnóstico são tratadas sem repassar mensagens técnicas brutas. Falhas e negativas atuais eliminam o cache da janela para evitar exportar dados anteriores como atuais. Falhas de leituras ultrapassadas não alteram a interface nova.

Não houve novo polling, repetição automática de comandos, mudança dos endpoints nem alteração de permissões do acesso local. Uma leitura do Agent já iniciada pode terminar, mas sua resposta desatualizada é descartada. O prazo original do acesso local permanece inalterado.

## Prova executada

Novo teste: `apps/commander/scripts/test_usage_activity_concurrency.mjs`.

Execução no ambiente isolado da conversa, Node v22.16.0, usando as funções exatas lidas de app.js e dependências de permissão, Agent e DOM simuladas. Antes: 24 casos, 6 PASS e 18 FAIL. Depois: 24 PASS e 0 FAIL. O script também contém uma verificação adicional de declarações para execução sobre o arquivo integral; essa verificação adicional não foi contada como executada no ensaio por trechos.

SHA-256 das funções, com espaços externos removidos:
- setGuestHeader antes: `34f4ab9d8a6b4a207ce20449c308646d9e28b78d861920554ca0b1719c384f20`.
- setGuestHeader depois: `27165bfebbc2d321616cb015121049e1275902552ece0dbe783b841403fd547b`.
- loadUsageActivity antes: `4289eae756b48f15b6202619545ac8d56170c033e53b08a093abfcc9956c03f2`.
- loadUsageActivity depois: `2e5e09ae8fa38649fd36b6f7937db15d24ec6ddd73be896519622aa68d634dde`.
- Teste gravado: `e387c62c2e55de65113391f2193acc5dca2a0cfb138e6844de8a0d172ff2879b`.

A bateria anterior de 68 validadores NÃO foi reexecutada para estas alterações. Não se certificou navegador real, produção, carga concorrente de clientes, custos ou versões de agentes.

## Custódia e limitação observada da ferramenta

Backup integral no Services: `/tmp_hara/commander-activity-review-20261011-before-aa4a90b.js`, SHA `025eb363434798e399b03254ade52ca399b0457411e9e7bd19381409ebe2395d`.

Após três substituições únicas, o Commander retornou SHA do app.js `96423032e6416a8ab288f0ce67b700b86d97cbf4051899a46c957527c4fca2b3`. As funções e declarações modificadas foram relidas e correspondem à candidata testada.

As três chamadas enviaram expected_sha256, porém os resultados declararam precondition_checked=false. Os hashes previous_sha256 observados coincidiram com os esperados e preimages foram criadas, mas isso NÃO comprova aplicação atômica da pré-condição. Registrar como inconsistência de contrato a investigar; não alegar proteção otimista comprovada. O fonte atual de customer-mcp-simple.mjs encaminha esse parâmetro, mas a causa da diferença com o runtime não foi determinada nesta rodada.

Correção da anotação anterior: o usuário havia enviado `Texto colado(20261011-165148).txt`. O anexo foi efetivamente lido na revisão seguinte; sua SHA-256 é `68eb5acda4a90ff398a97da9e2754180d49bf7f4d0c69df33ef9336ac11b0f88`. O exemplo registra `broadcast_v1`, `device_app_version=0.2.52`, paginação vazia exibida como `0--1`, saída de processo no Núcleo A e recuperação de canal. Não é prova de funcionamento do Event V2 nem motivo para alterar aquele transporte sem localizar seu código.

Validação posterior nesta conversa: o teste `test_usage_activity_concurrency.mjs` foi executado diretamente no Services, Node v24.15.0, contra o arquivo integral `app.js` SHA `96423032e6416a8ab288f0ce67b700b86d97cbf4051899a46c957527c4fca2b3`: **25/25 PASS**, incluindo a verificação das declarações. Resultado: `/tmp_hara/commander-activity-full-source-20261011.json`. Não houve deploy.
