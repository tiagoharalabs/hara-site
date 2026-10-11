# H.A.R.A. Commander — capacidade de 1.000 a 10.000 usuários

Data: 11/10/2026. Solicitação: melhorar a capacidade e avaliar a arquitetura atual. O proprietário aprovou expressamente o visual de Plano e cobrança nesta conversa; a pendência estética anterior está encerrada.

## Conclusão executiva

A arquitetura tem componentes adequados para crescer sem uma reescrita completa, mas **não está homologada para 1.000 ou 10.000 clientes simultâneos**. Validamos estrutura e consultas com 10.000 contas sintéticas e corrigimos um limite real de manutenção. Não executamos uma carga distribuída de 10.000 clientes em Cloudflare nem um soak de 24 horas.

Há dois caminhos comerciais distintos. Em **LOCAL_TUNNEL**, o Agent Linux assinado 0.3.43 sai antes do laço de polling e mantém telemetria agregada horária. Em **OUTBOUND_RELAY**, ele consulta a fila periodicamente. Os números elevados de polling deste relatório se aplicam somente ao segundo caminho; não descrevem todos os usuários do Commander. Event V2 existe na frota Founder 0.3.44, mas está restrito por allowlist em produção. A composição real entre os transportes, o provedor de túnel e o volume de comandos precisam ser medidos antes de certificar simultaneidade.

## Base e custódia

- Worktree: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`, em Services.
- Branch única: `local/commander-product-current`.
- Base anterior: `45cc9729123dbba960471b6a4a2a0ad119c30751`.
- Commit da implementação e primeiras evidências: `0d00521`.
- Produção anterior, preservada para rollback: `b500dd23-c33b-4247-ac3e-04c24c8af15a`.
- Storage permanece em HOLD; não houve force-push nem reconciliação dos espelhos antigos.
- Os arquivos de evidência desta frente estão em `docs/evidence/commander-capacity-20261011/`. Os testes iniciais registram o HEAD-base anterior, porque rodaram antes do commit; o relatório de capacidade registra também SHA-256 do `auth.js` efetivamente testado.

## 1. Arquitetura inspecionada

O caminho de produto usa Cloudflare Worker, D1 `PRODUCT_DB`, Durable Objects para quota por tenant, canal de dispositivo e proteção de taxa, além de HARA Identity/ZITADEL. A identidade humana é separada da identidade dos dispositivos. Não foi introduzido proxy de clientes pelo Services.

Já existiam bootstrap de portal consolidado, TTLs de navegação no navegador, consultas de sessão indexadas, atualização de presença da sessão a cada 30 minutos e cache de metadados públicos OIDC. Esses componentes não foram apresentados como entregas novas desta frente.

O Worker dispõe de Event V2, mas sua liberação PROD continua limitada à frota autorizada. Os instaladores públicos assinados foram confirmados íntegros na versão final. Uma promoção intermediária com assets inconsistentes foi revertida; o incidente está registrado na seção de publicação. Os serviços Founder não foram reconfigurados nesta frente. A telemetria agregada horária do Agent é diferente do heartbeat de presença e do polling de chamadas.

## 2. Correção implementada: manutenção de autenticação

### Problema anterior

A manutenção horária removia no máximo 100 transações OIDC vencidas e 100 sessões elegíveis. Isso representa um teto nominal de 2.400 registros/dia por categoria, insuficiente para acompanhar, por exemplo, 10.000 logins/dia de forma sustentada. A limpeza de sessões ordenava o conjunto elegível com `COALESCE`, embora o DELETE final fosse limitado.

### Comportamento novo

A limpeza usa até 20 rodadas sequenciais, com limite de tempo suave de 5 segundos verificado entre rodadas. Cada consulta OIDC continua limitada a 100 registros. A limpeza de sessões faz duas seleções indexadas de até 100 registros cada, uma por expiração e outra por revogação, e só então as combina; `IN` evita apagar duas vezes uma sessão presente em ambos os grupos.

O teto nominal passa a 2.000 transações OIDC/hora e até 4.000 sessões terminais/hora: respectivamente 48.000 e até 96.000/dia. **São limites máximos de trabalho, não capacidade medida de produção.** A latência D1, o orçamento de tempo e a sobreposição entre os grupos podem reduzir a vazão obtida. O limite de tempo não interrompe uma consulta já em execução.

Quando não existe acúmulo, a rotina termina após uma rodada. Falha no banco é diferenciada de fila vazia. O retorno informa contagens, rodadas e esgotamento do orçamento. Foi revisado e integrado um observador que gera um único registro agregado por execução agendada, sem sessões, tokens, SQL ou dados pessoais: normal, aviso de limite/degradação ou erro sanitizado. Dez casos de observação passaram. Não foi criado um painel novo nem comprovada a coleta externa de um ciclo horário de produção nesta execução.

A retenção de sessões permanece em 30 dias. Validade da sessão, revogação, permissões, autenticação, preço, cobrança e aparência não mudaram. Não houve migração SQL nem remoção de contas ou histórico de chamadas. A mudança aproveita índices já existentes, confirmados no D1 PROD e no plano de execução do D1 DEV.

## 3. Validação executada

| Verificação | Resultado | Limite da evidência |
| --- | --- | --- |
| Suíte anterior | 57/57 PASS | Testes locais, não 1.000 clientes Cloudflare |
| Suíte final | 63/63 PASS | Inclui capacidade, manutenção, observação e empacotamento assinado |
| SQL concorrente de fila | 1.000 tentativas por cenário, 24 threads | SQLite isolado; não tráfego de clientes reais |
| Base sintética menor | 1.000 contas, 2.000 dispositivos, 21.000 sessões | Esquema real, consultas extraídas do fonte |
| Base sintética maior | 10.000 contas, 20.000 dispositivos, 210.000 sessões | Inclui 20 sessões históricas por conta |
| Correspondência de tenant | Zero divergências nas 11.000 consultas verificadas | Não substitui homologação E2E entre tenants reais |
| Preservação de sessões | 10.000 sessões válidas preservadas | Função real de manutenção em SQLite local |
| Limites da manutenção | Rodadas, linhas, erro e tempo testados | Relógio controlado nos testes de política |
| Plano D1 DEV real | Índices de expiração e revogação confirmados | EXPLAIN QUERY PLAN, zero escrita |
| DEV pós-publicação | Saúde, configuração, login, PKCE e cookie PASS | Não equivale a soak de capacidade |

O teste novo de capacidade extrai as consultas reais do código; não se limita a executar uma cópia antiga do SQL. O validador de retenção foi atualizado pelo mesmo motivo. As medições de tempo locais presentes no JSON não são latência D1, de rede ou do produto.

## 4. Situação real observada em produção

Uma leitura agregada, sem dados pessoais e sem escrita, encontrou 2 tenants, 2 usuários, 13 registros de dispositivos, 37 sessões e 1 transação OIDC; o banco ocupava 18.550.784 bytes no momento da leitura. Registros de dispositivos incluem históricos, não significam 13 dispositivos simultaneamente ativos.

As métricas Cloudflare e D1 das janelas 09:40–10:40 e 10:40–11:40 UTC de 11/10 registraram respectivamente 37 e 252 requisições Worker, zero erros Worker, 16 e 110 consultas de fila, e 8 e 54 chamadas comerciais. As amostras da fila tinham intervalo 1. As cargas das janelas são diferentes: não se calcula ganho causal nem economia de fatura a partir dessa comparação.

Essa carga é pequena demais para provar capacidade de mil ou dez mil usuários.

## 5. Cenários de planejamento por transporte

Hipótese explícita: dois dispositivos Linux por conta, todos ligados e autorizados no período considerado. **Somente no cenário OUTBOUND_RELAY**, cada dispositivo consulta a fila a cada 10 segundos quando ocioso ou a cada 2 segundos na janela quente, além do heartbeat de presença a cada 60 segundos. O modo LOCAL_TUNNEL não entra nesse laço; sua telemetria periódica tem intervalo de 3.600 segundos, além de eventos de início/fim, recuperação e outras operações. Inicialização, erros, operações úteis, leases e outras rotas não estão somados. O modelo ignora o tempo de resposta da requisição e é uma aproximação por cadência configurada.

| Cenário | 1.000 contas | 10.000 contas |
| --- | ---: | ---: |
| Dispositivos online supostos | 2.000 | 20.000 |
| Usuários ativos no portal supostos | 250 | 2.000 |
| Portal a 6 requisições/minuto por ativo | 25 req/s | 200 req/s |
| Apenas telemetria horária LOCAL_TUNNEL, média distribuída | 0,56 req/s | 5,56 req/s |
| Transporte ocioso OUTBOUND_RELAY | 233,3 req/s | 2.333,3 req/s |
| Transporte OUTBOUND_RELAY na janela quente | 1.033,3 req/s | 10.333,3 req/s |

A média de telemetria horária não é a carga total do túnel: exclui bursts simultâneos, início/fim, retransmissões, leases, quota, portal, comandos e tráfego do provedor de túnel. O código do fallback sem configuração escolhe OUTBOUND_RELAY; o portal permite escolher o transporte na instalação Linux. Não se presume que todos os clientes estejam em túnel local. A quantidade de contas cadastradas não determina sozinha a carga. Um produto com 10.000 contas e poucas centenas de computadores ligados tem comportamento diferente de 20.000 computadores conectados continuamente.

Como ordem de grandeza, apenas as requisições Worker do transporte **OUTBOUND_RELAY ocioso** durante 8 horas/dia, 30 dias/mês, dariam 201,6 milhões ou 2,016 bilhões de requisições. Com a tabela Workers Paid consultada em 11/10/2026, a assinatura mais esse componente de requisições corresponderia a US$ 62,48 ou US$ 606,80/mês, supondo franquia não usada por outros Workers. Isso **não é o custo total**: exclui CPU, D1, Durable Objects, Identity, chamadas úteis, outros produtos e tributos. É cenário hipotético de relay, não fatura observada nem preço genérico para 10.000 usuários; não se aplica como orçamento do modo LOCAL_TUNNEL.

## 6. Limites e decisões para a próxima etapa

**Prioridade 1 — transporte comercial:** medir a composição real de LOCAL_TUNNEL versus OUTBOUND_RELAY. Para túnel local, homologar disponibilidade, limites e recuperação do túnel completo, além de leases/quota e telemetria. Para grande volume em relay, homologar release assinada Event V2 para clientes, com reconexão, entrega/claim idempotente, retomada, revogação e fallback com limites. Não abrir a allowlist global como atalho. A hibernação WebSocket é apropriada para evitar trabalho contínuo em conexões ociosas, mas sua existência no fonte não prova escala da distribuição pública.

**Prioridade 2 — D1 sob carga real:** medir tempo de serviço, filas, erros, linhas lidas/escritas e latência de cada operação numa rampa DEV controlada. D1 processa as consultas de cada banco sequencialmente; tráfego HTTP e consultas SQL não são a mesma métrica. O limite por banco Paid é 10 GB. Não foi homologada nesta frente uma política de arquivamento físico do histórico de chamadas; sua evolução deve preservar recibos e idempotência, sem apagar dados indiscriminadamente.

**Prioridade 3 — identidade e recuperação:** medir bursts de login no ZITADEL/PostgreSQL, disponibilidade do host de identidade e recuperação. Esta frente não simulou indisponibilidade do Storage, failover ou login de 100 usuários/segundo no provedor real.

**Critério para chamar de homologado:** em DEV isolado, aumentar progressivamente clientes/tenants distintos, registrar a carga realmente oferecida e atendida, latência p95/p99, falhas, backlog, reconexões e custo; incluir período sustentado e testes de recuperação. Proposta inicial de aprovação: sem perda, mistura de tenants, dupla execução ou dupla cobrança; erros não esperados abaixo de 1%; latências dentro dos SLOs de produto explicitamente escolhidos antes do teste; ausência de crescimento contínuo de filas; interrupção automática em sobrecarga. Nenhum desses alvos deve ser marcado PASS apenas por modelo matemático ou saúde de endpoint.

Não há certificação de 1.000–10.000 clientes simultâneos, soak de 24 horas ou custo total demonstrado nesta entrega.

## 7. Fontes públicas verificadas em 11/10/2026

- D1, limites, banco de 10 GB e execução sequencial: https://developers.cloudflare.com/d1/platform/limits/
- Workers, preços de requisições e CPU: https://developers.cloudflare.com/workers/platform/pricing/
- Durable Objects, WebSockets e hibernação: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- Separação de versões carregadas e deployments efetivos: https://developers.cloudflare.com/workers/versions-and-deployments/

As conclusões sobre o Commander derivam do fonte e das evidências desta frente; a documentação Cloudflare não certifica a capacidade da aplicação.

## 8. Publicação e retorno operacional

**DEV final:** `96e67af5-9a67-41f0-8322-763fcd3bb237`, 100%, 12/12 assets exatos, saúde/configuração/autenticação e login PASS.

**PROD final:** `9f7526c5-98a9-415a-b756-25200eee0627`, 100%, 12/12 assets exatos, saúde/autenticação PASS e distribuição comercial assinada v2 validada. Bindings não relacionados a assets foram comparados integralmente com a versão íntegra anterior, incluindo os nomes dos sete segredos e a allowlist Founder; valores de segredos não foram expostos.

**Rollback conhecido íntegro:** `b500dd23-c33b-4247-ac3e-04c24c8af15a`. Não selecionar automaticamente qualquer versão imediatamente anterior: a candidata rejeitada `97f050a3-ab1c-4175-94f1-fdd9e4614740` NÃO é rollback aprovado.

**Incidente de promoção controlado:** a primeira promoção, às 12:01:20 UTC, encontrou divergência entre arquivos candidatos da pasta `public/` e o pacote comercial assinado. Foi revertida às 12:02:12 UTC e a integridade da versão anterior foi reconfirmada. Não houve alegação de que ninguém acessou os instaladores nesse intervalo. O empacotamento passou a usar uma área separada: interface atual mais os oito arquivos do pacote assinado, verificados por hash e assinatura. O novo `stage_signed_commercial_assets.py` e seu teste estão no gate. A nova promoção repetiu DEV e PROD com readbacks completos; apenas o estado final é aprovado.

**Fonte runtime publicada:** `29067c28a4202cbf4cda8ada2b37e954d566fb7f`. O checkpoint de validação seguinte `b4865014865c616e113488b822b328d246d0b064` muda somente o modelo/teste de transporte; runtime, UI e pacote comercial são idênticos. A suíte final 63/63 está vinculada a esse checkpoint. Não houve deploy adicional para alterar somente documentação ou modelos.

Publicação GitHub da frente canônica exige push fast-forward e leitura remota exata; Storage não é destino desta promoção. O checkpoint final do documento é o commit que o contém.

Para a próxima publicação, gerar `python3 -B apps/commander/scripts/stage_signed_commercial_assets.py --output /tmp_hara/<diretorio-novo>` e usar o caminho produzido em `wrangler versions upload --assets <diretorio>`. Não publicar a pasta `public/` bruta como se fosse o pacote comercial assinado. Manter os readbacks de versão, bindings, 12 assets, assinatura, saúde e autenticação antes de declarar conclusão.
