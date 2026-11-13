# H.A.R.A. Commander — panorama verificável de engenharia e lançamento
**Data do checkpoint:** 13/11/2026 (horário de Brasília)
**Owner do produto:** [hara-site #310](https://github.com/tiagoharalabs/hara-site/issues/310)
**Natureza:** documentação de proveniência e revisão; **não é autorização de deploy, cobrança ou publicação OpenAI**.

## Decisão atual

**Produto comercial: NO-GO para atualizar o backend público.** O último readback autenticado de produção demonstrou a versão antiga do Worker, `12fe1bb3-4c8c-4a37-9793-54bb4525556e`, com 100% de tráfego, D1 comercial com **21 colunas** e **migration 0043 não aplicada**. O bloqueio `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` foi respeitado. Uma chamada de teste ao promotor com `--execute` recusou a operação **antes** de fazer modificações.

O candidato atual tem fonte `apps/commander/src/worker.js` SHA-256 **`9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260`**. O bundle utilizado no ensaio Cloudflare QA foi `049240c088942fe732ab25db37d8620a84cc6801008611967c09cc242fb36657`. Esses hashes identificam o candidato, não uma versão comercial homologada.

O código e as evidências de engenharia podem circular por **PR draft**; o `main` do site institucional pode acionar implantação. Não promover `main`, manifesto público, Worker, D1, Agent, Stripe LIVE nem catálogo de ferramentas apenas para sincronizar Git.

## O que foi entregue e comprovado

| Área | Prova e resultado | Limite que permanece |
|---|---|---|
| Fila 0043 e despacho | No Services: 29/29 testes adicionais da fonte exata, com autenticação, entitlement e negativa de replay. [PR #330](https://github.com/tiagoharalabs/hara-site/pull/330) documenta a evidência. | QA local não comprova consumer comercial real em Cloudflare. |
| Inventário DO | Censo read-only de seis namespaces: **72 objetos com storage em PROD e 4 em QA**. 56 negativas do gate de cobertura; [PR #331](https://github.com/tiagoharalabs/hara-site/pull/331). | Objetos com storage não são a população integral de instâncias ativas. |
| Manifesto e três DO reais | Em workerd local: 11 cenários e 22 negativas; o teste demonstrou o risco de um quinto DO não enumerado. [PR #332](https://github.com/tiagoharalabs/hara-site/pull/332). | Manifesto parcial não autoriza quiescência global. |
| Cloudflare QA da fonte exata | [Fonte privada no Storage: `cb967b5939d26c2cde68ab89bf3e1ac46927916f`]. Três DO reais, quota protegida, D1 QA 0043, Queue idempotente, alarme nativo, mudança FORWARD→CONTAINMENT e bloqueio de novo ingresso: **PASS**. | O ensaio usou adaptador QA, não as rotas comerciais completas; WSS preexistente deu timeout nessa primeira rodada. |
| WSS 1012 na fonte exata | Teste Cloudflare QA corrigido: **fence no DO antes do deployment de contenção**, WebSocket preexistente fechou com **1012**, depois nova WSS recebeu 503. [PR #333](https://github.com/tiagoharalabs/hara-site/pull/333); Storage `ac0124a4e381dce5b7965487e56ca19e7ac907bc`. | O Worker comercial LEGACY não tem a mesma operação de fence. Transição LEGACY→nova versão ainda exige prova separada. |
| Reparação de claims incertos | Fonte de scrub com CAS e preservação de quota: 88 testes de despacho, 255 de regressão P0, 11 DO workerd; 20 negativos dirigidos. O Cron Cloudflare nativo em QA alterou só payload sintético elegível; foi posteriormente **desabilitado**, com zero schedules. | Falha total de escrita D1 continua explicitamente indeterminada; recuperação comercial contínua pendente. |
| Autorização SQL 0043 hospedada | 13/13 SELECTs sintéticos com predicado real em D1 Cloudflare QA: **1 caso válido admitido / 12 inválidos recusados**. Nenhuma tabela de cliente ou DML foi usada. | Não equivale a execução MCP end-to-end em PROD. |
| Billing | [PR #329](https://github.com/tiagoharalabs/hara-site/pull/329): Stripe sandbox mostrou Checkout pago, webhook processado, assinatura e entitlement STANDARD ativo. SQL/billing QA passou. | Não há recibo de execução MCP/quota **após** esse pagamento; Stripe LIVE ainda NO-GO. |
| Stripe LIVE | Catálogo STANDARD (BRL 80/mês) encontrado; endpoint de webhook LIVE encontrado, mas **desativado**. Em Worker PROD, nome de segredo `STRIPE_WEBHOOK_SECRET` ainda ausente; no código versionado, `STRIPE_CHECKOUT_ENABLED=false`. | Verificação de signing secret, permissões, tax e ativação LIVE depende de gates próprios. |
| Agents e FileTools | Agent 0.3.83, fontes de 14 novas FileTools e QA MCP/FileTools: seis suítes, 199 verificações de fonte. | Catálogo do App ainda não atualizado; execução nativa das 14 funções no Reviewer Windows/Linux permanece pendente. |

**Aviso de atualidade:** inventário de disponibilidade de Agents pode mudar entre leituras; última atualização da [issue #310](https://github.com/tiagoharalabs/hara-site/issues/310) registrou temporariamente os dois Reviewer OFFLINE, sem atribuir causa. Não usar o status histórico dos Agents como autorização para instalação/pareamento.

## Camadas distintas de publicação

| Camada | Situação |
|---|---|
| **Services Git local** | Commits de engenharia/testes privados, com branches isoladas e evidência. |
| **Storage Working Mirror** | Custódia de SHA e refs privadas confirmada nas entregas citadas. |
| **Storage Canonical / main** | Não promovido por esta documentação. |
| **GitHub Web** | PRs de evidência/QA **#329, #330, #331, #332, #333**; rascunhos de revisão, não equivalem a fonte privada inteira nem release. |
| **Cloudflare QA** | Ensaios isolados com registros sintéticos, desativação de entradas temporárias e recibos por versão. |
| **Cloudflare PROD / D1 PROD** | Sem implantação do novo Worker e sem migration 0043. |
| **OpenAI App / Stripe LIVE / Agent público** | Sem atualização comercial autorizada por esses ensaios. |

## P0 priorizado: sequência exata de correção

**1 — Ponte LEGACY→nova contenção.** O DO antigo comercial não oferece `enterCutoverFence`. Precisamos ensaiar adoção sem replay, medir geração e epoch por instância, documentar WSS antigo e preservar efeitos incertos. A frente `local/commander-p0-legacy-bridge-wss-qa-20261113` foi identificada como **trabalho em andamento**, sem tratar seus arquivos não commitados como prova fechada.

**2 — Registry vivo e drenagem.** Atestar todas as instâncias efetivamente ativas (inclusive sem storage), WSS, alarmes, RPCs e queues, com duas janelas **globais e temporizadas**, e testemunhos do Observer.

**3 — Snapshot e recuperação compatível.** Preservar D1, DO quota, outbox, requests e reservations de estado desconhecido no mesmo epoch; ensaiar contenção e **reentrada forward-only**. Proibir rollback automático para o Worker LEGACY.

**4 — Aceite hospedado de integração completa.** Cobrir autenticação OAuth, transações MCP/Queue no Worker completo, telemetria SQL corrigida, FileTools em QA e trilha comercial de pagamento pós-entitlement.

**5 — Promoção comercial condicional.** Só após gate GO e autorização vinculada ao source/bundle/version ID: migration 0043, deployment versionado, comparação de recibos e observação pós-deploy. Por fim habilitar catálogo DEVELOPMENT, nunca por suposição.

## Histórico de custódia — SHAs privados, não URLs públicas

- `cb967b5939d26c2cde68ab89bf3e1ac46927916f` — QA hospedado da fonte exata, D1 0043, DO/Queue/alarme/contenção.
- `ac0124a4e381dce5b7965487e56ca19e7ac907bc` — pré-fence de WSS 1012 em QA Cloudflare.
- `dcfe17937a314431a71c2634a0b8fed0ac61187d` — censo e 56 negativas de quiescência.
- `53a8a81fd2dc26960d3b6ae253abbfe12961763a` — manifesto das três classes DO, 11+22.
- `870918bac55e52254069d98aee0b3311b28719b3` — QA de claim 0043 na revisão exata.
- `9725e2129502f086ec6251821e294d2f4c4babec` — Cron nativo em QA, scrub em D1 sintético.
- `02b12f3f2a5b32aaf47f179ae1c8cb517591db0c` — candidate scrub / safe production NO-GO.
- `c804c6143040e751fa67bbe4257771fa50fdaab8` — inventário dos 25 impedimentos e leitura Stripe/Cloudflare sem modificações.
- `95b9ecae14c7f56907e877eb80d834e86229d3b8` — cobertura P0 de recibos e 79 negativas.
- `c438c829455e2efdfc39115b9b23d7c716cca10c` — paridade de catálogo Reviewer 0.3.83.

Esses hashes são identificadores locais ou do **Storage Working Mirror**, não pressupõem que o commit completo esteja no GitHub Web. Cada QA mantém seus recibos originais em `docs/evidence/commander-*/`, sem reescrevê-los.

## Segurança do material publicado

Este índice não inclui conteúdo de clientes, tokens, OAuth, signing keys, IDs de tenant/dispositivo/DO, cursores de inventário, nem a configuração operacional da conta Cloudflare. Os PRs continuam **draft**. Nenhum PR deve ser mesclado sem revisão de conteúdo, proveniência, testes na baseline do GitHub e decisão de release.

**Próxima direção técnica:** fechar a ponte LEGACY→nova contenção em QA, não criar outro orquestrador e não contornar `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN`.