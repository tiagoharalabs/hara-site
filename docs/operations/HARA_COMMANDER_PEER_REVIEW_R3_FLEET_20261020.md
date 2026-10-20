# HARA Commander — revisão independente R3: frota, pressão e recuperação

Data de coleta: 2026-10-20, início 19:08 UTC (16:08 BRT). Revisor: Valky.
Escopo: nove hosts via SSH autorizado + MCP do produto; fontes copiadas para snapshot isolado; testes sintéticos sem requests reais de autenticação, pagamentos ou carga em PROD. Nenhum Agent, serviço, configuração de rede ou arquivo de código do executor foi modificado. O Codex continua único escritor dos patches de produto.

**Complemento à R2, não substituição.** Fonte congelada em `/tmp/hara-commander-peer-r3-20261020-3_pqdnj6/source`; HEAD observado `3213b6dd52c487f6d72ebefa74bfe9e04c161c23`, com WIP explicitamente identificado e hashes por arquivo em `source-snapshot.json`. Os 64 arquivos ficaram estáveis durante a cópia. Não interpretar essa árvore com WIP como commit publicado.

## Resultado executivo

Não encontrei falta de CPU/RAM na amostra dos nove hosts. Encontrei gargalos de software reproduzíveis, dependência de autenticação concentrada no Storage e diferenças de build que a versão `0.3.54` sozinha não revela. Não comprar hardware nem reconstruir o transporte antes de corrigir/testar estes pontos.

## R3-QUEUE-01 — fila pode parar no limite do lote após reconexão [P0 candidato; reproduzido local]

Fonte: `experimental/event_v2_agent_loop.py`, `drain_durable_calls` e `run_connected_session`.
O lote é limitado a oito chamadas. Ao reconectar, ocorre um único drain; depois, novos drains dependem de `CALL_AVAILABLE`. Keepalive e LIVENESS não iniciam a continuação.

**Prova com a função real e fila simulada:** 12 chamadas persistidas antes da reconexão, 8 executadas e 4 remanescentes após três iterações de keepalive sem novo evento. Não houve queue remota, Agent real nem perda de dados em PROD nesta prova.

Risco: chamadas que perderam a notificação enquanto o socket estava fora podem ficar esperando novo wake/reconexão e expirar. Não eliminar o limite de lote nem introduzir polling ocioso permanente.

Correção sugerida: ao atingir o limite cheio, agendar continuação limitada e cooperativa até encontrar fila vazia, respeitando revogação, deadlines e backpressure. Testar 0/1/8/9/12/16 pendências na reconexão; nenhum novo enqueue artificial pode ser necessário para concluir as antigas. Testar revogação entre lotes e evitar replay de execução mutante. Owner #163, aceitação #240.

## R3-PTY-02 — processo de muito stdout depende de futuras leituras do cliente [P0 candidato; reproduzido com PTY real]

Fonte: `public/agent/linux.py`, `process_start`, `_drain_process`, `_prune_process_sessions`. O Agent drena stdout durante as APIs de start/read/interact, mas não há coletor independente contínuo nessa implementação.

**Prova real isolada:** child Python descartável escreve 262.144 bytes e um marcador de conclusão. Após um segundo sem leitura do cliente, o marcador não existe e o child não termina. Ao executar `_drain_process`, o mesmo child conclui com exit 0 e cria o marcador. Nenhum processo/arquivo do usuário foi atingido; cleanup só dos children criados no teste.

A correção de drenagem pós-exit não resolve isto: aqui o processo não consegue chegar ao exit porque o buffer do PTY fica cheio.

Correção sugerida: coletor contínuo limitado (seletor/event loop ou thread por grupo com limites explícitos), ring buffer/spool com retenção definida, sem stdout ilimitado na RAM. Teste de 256 KiB/alguns MiB sem nenhum `read_process_output`, saída Unicode fragmentada, truncamento sinalizado, cancelamento/revogação e limpeza de descendentes. Não mudar sessões interativas intencionalmente longas em one-shot por acidente.

## R3-SESSION-03 — 13 de 16 sessões do Services ocupadas há horas/dias [P1 alto; observado ao vivo]

O MCP `list_sessions(services)` confirmou 13 sessões RUNNING. Várias começaram em 13/10 e continuavam em 20/10. Recebimento de evidência: `bridge_receipt_sha256=49aeae0b5047eec0cace0e87ee3a43130b49116e8b68cb92940929dc0ea8338d`.
A inspeção de `/proc` mostrou 13 filhos diretos do Agent e múltiplos `git -> pager`/`psql -> pager` aguardando entrada. Limite da fonte examinada: `MAX_PROCESS_ACTIVE_SESSIONS=16`. Não qualifiquei toda sessão antiga como abandonada sem consultar seu owner, e não matei nenhuma.

Melhoria: modo não interativo explícito deve desativar paginadores (PAGER/GIT_PAGER/PSQL_PAGER) por subprocesso; sessões interativas precisam de lease/idle policy e dono visível. Exibir ocupação, última atividade e razão de bloqueio; alarmar antes do limite. Testar que job longo autorizado não é interrompido indevidamente, e que sessão abandonada libera recursos pelo fluxo autorizado. Não usar kill global nem restart do Agent para limpar a fila.

## R3-AUTH-04 — fan-out de autenticação para o Storage [P1 de capacidade/disponibilidade; reproduzido com mocks]

Fontes: `src/mcp-hara-identity-customer.mjs` e `src/oidc.js`.
O caminho JWT tem comportamento diferente; **este achado é do caminho de token opaco**. Ele realiza introspection e userinfo por chamada MCP. O cache atual armazena discovery/JWKS, não essas respostas de token.

Prova usando a função real e fetch totalmente simulado:
- 25 autenticações sequenciais com o mesmo token-fixture: 25 introspections + 25 userinfo, zero discovery adicional;
- 10 primeiras autenticações concorrentes: 10 discoveries + 10 introspections + 10 userinfo;
- nenhuma requisição observada recebeu `AbortSignal`;
- provedor simulado sem resposta permaneceu pendente no limite de observação de 80 ms. Isso NÃO mede o timeout da plataforma; a ausência de deadline da aplicação foi constatada no código.

No Worker, o `catch` de `verifyHaraIdentityCustomerMcpBearer` retorna sempre Unauthorized/401, incluindo indisponibilidade de discovery/introspection. Falha do provedor não é prova de credencial inválida.

Correções propostas: deadline/abort próprio, coalescência de discovery/JWKS em voo, classificação 401 versus 503 com Retry-After para indisponibilidade, e métricas de latência/fan-out. Avaliar JWT validado localmente ou cache curto de introspection **somente com contrato explícito de expiração/revogação**. Não servir autorização indefinidamente em falha, não remover audience/issuer/scope e não cachear segredo bruto em log. Risco de autenticação em massa no N150 não é CPU saturada observada; precisa teste de carga DEV com tokens sintéticos. Owner #167 e #1486.

## R3-RELEASE-05 — mesma versão, builds diferentes na frota [P1 de rollout; observado]

- Sentinela A: Agent clássico `0.3.41` ativo; Event V2 inativo. O registro Event V2 remanescente é de 15/10 e não descreve o processo atual.
- Núcleo, Services e B: Event V2 `0.3.54`, loop SHA `cd9ae709...`; sem o checkpoint de liveness compartilhado entre sockets.
- C: `0.3.54-pong-deadline-c-20261013-r1`, loop `7571ad80...`, transporte `9a5b6b11...`; checkpoint compartilhado e marcador PONG deadline presentes.
- D e Ninja: loop `f1a7d9fc...`, checkpoint compartilhado presente, transporte `96b10a82...` sem marcador PONG deadline.

Os sete arquivos declarados nos manifestos dos seis Agents Event V2 conferiram com seus próprios hashes, e o hash do manifesto conferiu com os metadados da assinatura. **Não revalidei criptograficamente as assinaturas nesta comparação**, logo não declarar certificação. A diferença parece de build/rollout, não prova de adulteração.

Telemetria UTC 20/10 até a coleta: Núcleo 14 reconnects e 0 liveness_attempts com ~68.826 s conectados; Services 6 reconnects e 0 liveness_attempts; C 3 reconnects e 3 liveness; D 8/3; Ninja 2/3; B 8/1. São contadores locais acumulados, não taxa de falha de chamadas. No código antigo, reconectar reinicia a contagem de seis horas; isso é compatível com o problema já corrigido em outras variantes. Não afirmar causa de cada reconexão sem logs específicos.

Melhoria: publicar release_id + manifesto SHA + transport revision + boot/session id, além de agent_version. Reconciliar canários existentes e promover gradualmente, sem um update público antigo sobrescrever o Agent Founder. Testar presença/reauth offline com reconexões frequentes e sem aumentar gravações ociosas D1.

## R3-IDENTITY-06 — recuperação/HA ainda não provadas nesta rodada [P1; não confundir com incidente]

Storage respondeu com 4 CPUs, ~9,6 GiB disponíveis e carga 0,16. `hara-identity.service` é oneshot active/exited e `hara-identity-tunnel` está running. Endpoint público discovery respondeu HTTP 200 (~0,30 s em uma amostra). Backup agendado rodou em 20/10 03:20 BRT com `Result=success` e `ExecMainStatus=0`.

Docker/arquivos privados não eram legíveis pelo usuário operacional; respeitei a restrição. Não foi verificada cópia externa do backup, restauração, réplica ou promoção de standby. `active/exited` não é probe de saúde do ZITADEL/PostgreSQL. Não alegar que falta backup: há timer/resultado exitoso.

Aceitação proposta: restore em namespace/lab isolado, prova de login e validação de token após restauração, RPO/RTO definidos, probe sintético de autenticação independente e teste de indisponibilidade planejado apenas em DEV. GPU/Sentinelas podem apoiar QA e standby apenas sob orçamento de CPU/RAM/IO; não inserir inferência nem a frota inteira no caminho das chamadas de clientes. Réplica no mesmo enlace/energia não resolve falha de enlace/energia.

## Leitura correta dos recursos

Todos os nove hosts responderam. Não havia pressão de memória recente relevante na coleta; são amostras, não benchmark de capacidade. Observer tem ~37 GiB livres na raiz, e Núcleo ~650 GiB. A raiz imutável do Bazzite/Ninja gera um percentual enganoso: `/home` tem ~1,6 TiB livres; não é falta de disco.

Services: cgroup do Agent marcava ~4,06 GB, mas ~3,24 GB eram file cache e ~0,78 GB kernel; o processo Agent tinha ~53 MiB RSS. B: cgroup ~4,69 GB, dos quais ~4,65 GB file cache; Agent ~37 MiB RSS. Não chamar isso de vazamento de 4 GB nem reiniciar serviços para “liberar RAM”. O problema concreto do Services são sessões persistentes, não RSS do Agent.

## Cloudflare: recomendações de capacidade, não migração imediata

D1 tem processamento sequencial por instância e teto de 10 GB por banco; reduzir consultas/scan/round trips antes de fragmentar fisicamente. Read replication depende de Sessions API e não acelera escritas; não ler autorização/revogação de réplica stale sem contrato de consistência. Hibernação WebSocket reduz duração faturável, mas não remove custos de D1/DO/auth nem substitui o teste de recuperação.

Fontes oficiais consultadas em 20/10/2026:
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/d1/best-practices/read-replication/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/platform/pricing/

## Ordem proposta ao Codex

Manter as correções R2 de billing/expiração em andamento. Acrescentar primeiro regressões de QUEUE-01 e PTY-02, depois política de sessões e AUTH-04; separar source fix de implantação nas máquinas. Não corrigir tudo em um commit nem tomar a presença ONLINE como aceite funcional. A migração comercial/Stripe e publicação oficial seguem seus gates e limites já estabelecidos.

Evidências e scripts desta revisão: `docs/evidence/commander-peer-review-r3-fleet-20261020/`. Snapshot completo permanece no diretório temporário indicado no começo. Scripts exigem esse snapshot ou `HARA_PEER_SOURCE` apontando para uma árvore de fonte compatível; versões posteriores podem corrigir os achados e devem produzir resultados diferentes.

## Adendo — correções R2 reexecutadas independentemente nesta rodada

Depois do censo e dos testes R3, congelei outra cópia da árvore em andamento e rodei os três testes novos do executor com `globalThis.fetch` real bloqueado: `billing_sqlite_webhook_e2e.mjs`, `test_billing_checkout_attempts.mjs` e `test_paid_entitlement_expiry.mjs`. Todos saíram 0. Os cenários locais agora cobrem claim órfão/ativo, fencing, eventos atrasados, indisponibilidade do provedor, Founder, checkout concorrente e prazo pago. Registro: `r2-fix-independent-rerun.json`, com hashes exatos dos arquivos testados. Isso confirma avanço local da R2; não é Stripe TEST real, D1 hospedado, promoção PROD nem encerramento dos achados novos R3. Evidências desta pasta agora totalizam 16 arquivos incluindo SHA256SUMS.
