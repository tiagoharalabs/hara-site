# Commander — cliente e quota DEV, 12/10/2026

Escopo: provas do produto em fixtures DEV isoladas. PROD, Stripe, credenciais de clientes e runtimes Founder não foram alterados nesta subfrente. Os únicos segredos novos são o canary MCP DEV autorizado pelo coordenador, em arquivo privado 0600; valores não estão nos artefatos.

| Prova | Resultado | Evidência |
| --- | --- | --- |
| Dois tenants autenticados: enumeração, seleção, revogação, fila, status e recibos cruzados | PASS; ações cruzadas recusadas, sem vazamento ou mutação | multitenant-live-r2.json |
| Namespace de quota por tenant, mesmo request ID | PASS; ALLOW independente em cada tenant | multitenant-live-r2.json |
| Cliente Free novo: enrollment normal, Agent público assinado .43 e leituras remotas | PASS; três recibos, replay com mesma chamada | remote-functional-scope-review.json |
| Uso Free remoto | PASS; LOCAL_BUDGET emitido e reportado 3, portal 3/10000, saldo 9997 | remote-customer-trial-live.json |
| Escrita e processo no Free | Negados corretamente: GRANT_MISSING; arquivo preservado | remote-customer-trial-live.json |
| Pro QA pré-provisionado, sem pagamento | PASS; SESSION_TRUSTED em console/PTY limitado, escrita/leitura UTF-8, processo e replay idempotente | remote-customer-standard-live.json |
| Quota cloud em Windows nativo Event V2 | PASS; limite controlado 1, oito concorrentes: um ALLOW e sete QUOTA_EXCEEDED | cloud-quota-boundary-live.json |
| Authorize → invoke real → recibo → commit e replay | PASS; COMMITTED, consumo 1, nenhuma cobrança ou execução duplicada | cloud-quota-boundary-live.json |
| Encerramento das fixtures concluídas | PASS; Agent Windows encerrou, revogação normal, perfil privado removido, tenants D1 removidos | completed-fixtures-cleanup.json e cloud-quota-boundary-live.json |

Recibo físico da prova cloud: 5554d7a544d929ad16f3c008de546806b2b6d72268428dbd46f2200d1465b083.
Fonte Windows .53 usada nessa prova: f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299.
A prova de limite 1 exercita o contrato real da quota; não representa dez mil operações Free realizadas nem mil clientes simultâneos.

## Catálogo e MCP

Readback DEV: Free/TRIAL 10000 por mês; Pro/STANDARD sem limite; DEV_ONE_UNIT com limite 1. Migração 0032 reverteu 0031; HTML/app.js DEV também mostram 10000. Fonte: dev-plan-readback.json.

Antes do opt-in, /api/mcp e sua metadata retornam 404 por contrato PROD-only. /api/dev/mcp legado retorna 401 sem bearer e sua metadata retorna 200. Fonte: dev-mcp-endpoint-readback.json.
Os dois relatórios remotos originais terminaram com FAIL somente porque a última asserção esperava 401 no endpoint PROD-only. As operações e limpezas anteriores passaram. remote-functional-scope-review.json conserva essa distinção e aponta para os relatórios brutos; estes não foram reescritos.

## Aceitação OAuth e source

O coordenador autorizou um opt-in explícito para o edge completo do cliente em DEV. O mesmo verificador de bearer real, audience, cliente, issuer e tenant permanece ativo; o token canary não autentica /api/mcp.
Worker.fetch real, com somente a base DurableObject substituída no Node, passou 24 verificações de opt-in/401/404, recurso DEV e guarda PROD. Fontes: dev-optin-offline-tests.json e test_customer_mcp_dev_acceptance_gate.mjs.

O auto-provisionamento por portal em DEV exige simultaneamente ENVIRONMENT=DEV, opt-in ativo e subject real listado em DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS. A lista aceita no máximo dois IDs exatos; lista vazia, wildcard, ID inválido, terceiro ID e usuário não listado são recusados. Tenant.environment usa DEV, valor permitido pelo schema atual. O plano QA é TRIAL; o fluxo PROD e seu Founder continuam iguais.
A função original de provisionamento passou 37 verificações com SQLite real, além dos testes existentes de autenticação e OIDC. Fonte: dev-self-service-offline-tests.json.

A primeira identidade QA real foi vinculada por seed D1 explícito; ela não comprova cadastro orgânico no portal. A segunda QA real passou pelo callback normal do portal com OAuth/PKCE real às 00:59:06Z de 13/10, sem seed D1. Readback independente em DEV confirmou user, identity_binding, tenant ACTIVE/DEV, sessão de portal não revogada e TRIAL/ACTIVE de 10000 por mês, com somente discovery, leitura e recibo. Antes do pairing havia zero devices, zero unidades no ledger de device e zero billing_connections. Fonte: qa2-organic-signup-d1-readback.json. O tenant foi preservado para enrollment e cadeia MCP reais; essas provas subsequentes pertencem ao coordenador e ao agente OAuth.

## Limites

O entitlement STANDARD foi preparado somente para QA e não passou por Stripe. Billing, publicação comercial, carga de mil clientes, soak prolongado e distribuição PROD não são certificados por esta subfrente.
Provas de network error anteriores permanecem como diagnóstico; a última prova de quota usa fixture nova, IDs persistidos, repetição limitada do mesmo ID e liberação exata.

## Defeito encontrado no identificador de entitlement

A fórmula histórica usa fingerprint SHA256 em base64url (43 caracteres), mas gera entitlement_id por slice(40,64).toUpperCase(), deixando só três caracteres. QA2 recebeu HARA-ENTITLEMENT-YEU. Reprodução somente offline encontrou dois subjects artificiais distintos com tenants distintos e o mesmo HARA-ENTITLEMENT-RR0 em 148 hashes. INSERT OR IGNORE pode omitir o plano do segundo cliente nessa colisão. Fonte: entitlement-id-collision-offline.json. O coordenador foi informado antes da homologação geral; nenhuma linha QA2 nem fórmula em produção foi alterada nesta verificação.

## Revisão da correção e auditoria agregada

A correção DEV usa o fingerprint completo, preservando maiúsculas e minúsculas (auth SHA 0abad197…). Revisão da fonte e dos testes confirmou ID completo, dois entitlements de tenants distintos e idempotência, mantendo a escolha de plano. O coordenador informou 43 checks e gate integrado de 119; o revisor não repetiu esses testes nem a reprodução de colisão. Parecer favorável a aplicar apenas essa linha ao auth PROD congelado, sem migração ou atualização dos planos existentes. Fonte: entitlement-full-fingerprint-review.json.

Auditoria SELECT agregada às 01:24:37Z: DEV 169 usuários ACTIVE e PROD 2, todos com entitlement ACTIVE e vigente. DEV distingue 1 signup QA orgânico conhecido, 2 vínculos de convite, 5 fixtures com prefixo conhecido, 1 preseed/origem desconhecida e 160 IDs com formato self-service de origem não verificada. Os 2 IDs PROD também têm origem não inferida por esta auditoria. Nenhum identificador de cliente ou segredo foi emitido; rows_written=0 e changes=0. Fonte: active-users-entitlement-aggregate-readback.json. Nenhum reparo D1 foi indicado por esse resultado.
