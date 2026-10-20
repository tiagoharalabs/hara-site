# HARA Commander — R9 | Desempenho da frota e experiência real do MCP
Data: 20/10/2026, ~21:57–22:15 UTC. Observação e auditoria independente via **H.A.R.A. Commander** (sem Desktop Commander). Destino: frente de implementação do Codex no clone `commander-prelaunch-fixes-20261020`.

## Resumo executivo

**O gargalo prioritário da experiência do usuário é tempo na fila/entrega de chamadas, e não falta generalizada de CPU/GPU.** O Commander foi utilizado para obter a telemetria histórica de chamadas, consultar os sete Agents Linux ativos, realizar 12 leituras de baixo impacto, inspecionar sessões e consultar Observer/Storage via SSH somente leitura partindo do Services. A VM Windows estava OFFLINE; NÃO foi ligada ou homologada.

A revisão é uma fotografia e um pequeno experimento operacional: não prova capacidade de um milhão de chamadas/mês, disponibilidade contínua, throughput sob carga ou homologação comercial. Não alterei Agents, serviços, filas, modelos, energia, contas Stripe, dados D1 ou checkout do Codex.

## Evidência direta: 24 horas de uso fundador

A chamada `get_activity(window=24h)` reportou, na coleta consolidada armazenada:
- **3.442 chamadas**, das quais **3.384 concluídas**, **57 falhas**, **1 cancelada**; sucesso reportado **98,3%**.
- Média geral: **935,9 ms na fila**, **848,0 ms de execução** e **1.783,9 ms totais**; **89,4%** abaixo de 3 segundos.
- Ferramentas mais frequentes: `hara.process.run` 1.073, `hara.files.read` 551, `hara.files.write` 294, `hara.process.start` 231, `hara.files.search` 228, `hara.files.read_many` 206.
- Erros recorrentes: FILENOTFOUNDERROR (24), PERMISSIONERROR (17), PATH_NOT_DIRECTORY (6), FILE_TOO_LARGE (4), PROCESS_SESSION_NOT_FOUND (2); não classificar automaticamente todos como bugs, pois existem falhas esperadas de usuário ou alvo.
- **Últimas 100 transações** (amostra, NÃO o dia inteiro): p50 da fila 563 ms; p90 4.154 ms; p95 7.080 ms; máximo 10.222 ms. P95 total 7.717 ms. **78/100 chamadas** nesse recorte tiveram como destino Services. Entre 23 `files.read` recentes, p50 da fila ~3.698 ms; entre 29 `process.run`, p50 ~584 ms. Isso sugere picos de concentração, não prova que o Services seja lento em CPU.
- Uma das 100 transações tinha `queue_ms` ausente. Revisar consistência de relógio/telemetria, preservando valor ausente em vez de inventar zero.

Base sanitizada: `activity.json`. A contagem total aumentou durante a sessão; não misturar a coleta posterior com os 3.403 registros observados minutos antes.

## Microteste real: quatro leituras concorrentes por host (12/12 PASS)

HARA Commander `read_file('/etc/os-release',offset=0,length=8)`, quatro requisições simultâneas para cada: Services, Sentinela C e Sentinela A. Nenhuma escrita ou carga de CPU/GPU. O tempo de fila foi extraído de registros `get_activity` da janela 22:08:10–22:08:52 UTC, e não do tempo de apresentação do conector na interface.

| Host | Transporte confirmado no histórico | Agent | Fila por chamada (ms) | Execução (ms) | Status |
| --- | --- | --- | --- | --- | --- |
| Sentinela C | EVENT_V2 | 0.3.54 | 461, 463, 1.012, 1.159 | 576–616 | 4/4 PASS |
| Services | EVENT_V2 | 0.3.54 | 548, 1.538, 2.665, 3.678 | 538–736 | 4/4 PASS |
| Sentinela A | OUTBOUND_RELAY | 0.3.41 | **9.069, 11.421, 13.742, 16.450** | 576–651 | 4/4 PASS |

**Interpretação:** o atraso da Sentinela A nessa amostra ocorreu quase todo ANTES da execução. A versão/transporte antigo é um fator plausível, ainda não isolado causalmente de jitter, estado da fila ou frequência de polling. Não inferir que outro hardware ou placa de vídeo resolverá isso. O Services apresenta tendência de espera crescente no pequeno lote; merece prova de fairness/concorrência por dispositivo, com mutações sequenciadas corretamente.

Limites: microteste pequeno, horário ocupado, amostras pontuais e coleta por janela que pode incluir outras chamadas homônimas (encontradas 12 chamadas alinhadas a 12 operações). Nada foi instalado para igualar versões. Base: `microburst.json` e `microburst-timing.json`.

## Conectividade, sessões e versões observadas

- Ping pelo próprio Commander **PASS para sete Agents Linux**: Services, Núcleo A, Sentinelas A/B/C/D e Ninja Blue.
- `list_devices` retornou 13 entradas incluindo dispositivos revogados; **sete Linux ONLINE**, uma inscrição Windows ativa OFFLINE em 0.3.53 e entradas históricas REVOKED. Não ligar VM ou reativar cadastro nesta revisão.
- `get_config` informou **31 capacidades internas iguais** nos sete Linux, com autorização persistente Founder. A conexão Chat atual publica **24 ferramentas**, enquanto o código/ZIP candidato cita 33 ferramentas no perfil comercial. É preciso reconciliar catálogo/distribuição/grants sem interpretar os números como equivalente funcional. Hash, recibos e rollback já implementados não aparecem todos na superfície aqui exposta.
- Serviços: `list_sessions` encontrou **13 RUNNING de 34 registros**, sendo **12 das 13 RUNNING com mais de 24h**. A maioria dos processos principais observados por `ps` é bash; outros são git. Não comprova abandono, mas deixa cerca de três vagas perante o teto histórico de 16 sessões ativas. O Agent ativo ainda não expõe os novos campos de owner/capacidade implementados no código candidato. **Nenhuma sessão foi morta**. Aplicar política de revisão pelo dono e correção do paginador apenas em canário aprovado.
- `list_devices` mostrava timestamps `last_seen_at_utc` mais antigos em alguns Event V2; os pings atuais passaram. Separar cadastro/último checkpoint/conexão efetiva/ping recente na UX.
- Uma operação `copy_file` para gravar evidência retornou **DEVICE_OFFLINE / retryable=true** para Núcleo, mas ping subsequente de Núcleo e Services retornou PASS e a gravação restante concluiu depois. Classificar como disponibilidade/transporte **transitório observado**, sem afirmar que o computador desligou ou que o status era falso. Instrumentar socket, entrega, retry seguro e distinção entre erro de transiente e de cadastro.

Bases: `sessions.json`, `capabilities.json`; o evento transitório está descrito aqui sem payload de clientes.

## Hardware e headroom: observações instantâneas, não benchmark

| Host | CPU (load 1m / CPUs lógicas) | RAM disponível | GPU/uso no instante | Observação |
| --- | --- | --- | --- | --- |
| Núcleo A | 4,86 / 16 | 90,20 GiB | RTX 4090, 10,3 GiB VRAM, 28% GPU | Execução atual concentrada; memória e CPU ainda têm margem na fotografia |
| Sentinela A | 0,42 / 12 | 52,81 GiB | **RTX 5070** (identificada ao vivo), 120 MiB VRAM, 0% | Conferir inventário; aqui usa transporte antigo |
| Sentinela B | 0,22 / 12 | 55,90 GiB | RTX 2070 Max-Q, 6 MiB, 0% | Disponibilidade instantânea, não capacidade de modelo validada |
| Sentinela C | 1,17 / 12 | 111,64 GiB | RTX 5080, 2,2 GiB VRAM, 0% | Processos Python podem usar CPU; GPU 0% é fotografia |
| Sentinela D | 0,03 / 16 | 58,44 GiB | Consulta NVIDIA indisponível | 2,38 GiB swap usada e processos Python/llama-server com grandes RSS; NÃO classificar como vazia nem migrar modelos cegamente |
| Services | 1,37 / 12 | 26,49 GiB | Sem leitura NVIDIA | CPU ociosa frente à fila de chamadas; investigar serialização/roteamento |
| Ninja Blue | 0,59 / 16 | 21,37 GiB | GPU integrada fora desta consulta NVIDIA | Composefs causa falso alarme se medir somente a raiz |

Na Sentinela D, `ps` mostrou um processo python3 com ~38 GiB RSS e vários `llama-server` com RSS expressivos; RSS não é memória física exclusiva e soma de processos pode contar páginas compartilhadas. Não reiniciar/evictar modelos por essa fotografia. O inventário local de Sentinela A deve usar GPU viva RTX 5070, sem confiar em registro histórico.

**Ninja Blue:** `/` é composefs/overlay somente leitura e informa zero livre (46 MiB total, 100%). Isso **não é o volume gravável cheio**: `/var/home` é Btrfs, com aproximadamente **1,6 TiB disponíveis**, ~15% utilizado. Métricas e alarmes do Commander devem escolher volume gravável adequado e exibir mount/fstype.

Bases: `resources.json`, `toprss.json`, `backend.json`.

## Backend fora dos sete Agents MCP cadastrados

Via **HARA Commander em Services → SSH somente leitura autorizado**:
- **Observer:** load1 0,27; aproximadamente 8,8 GiB de RAM disponíveis; raiz ~76% usada, ~38 GiB livres; uptime ~64 dias. Recomendo tendência/retention e aviso preventivo, NÃO incidente de armazenamento.
- **Storage:** load1 0,67; aproximadamente 9,8 GiB de RAM disponíveis; raiz ~10% usada, ~226 GiB livres; uptime ~17,9 dias. **Esses números são do filesystem consultado**, não capacidade total de todo o Storage.
- Observer e Storage não figuram como Agents inscritos neste conector; não inferir que devam virar dispositivos comerciais nem alterar topologia de autorização sem decisão.

## Fila de melhorias **para o HARA Commander** (não projeto concorrente)

**R9-P1-01 — Despacho/latência por host e transporte.** Reproduzir em QA e canário reservado os quatro read_file por host e carga progressiva com observação de queue_ms/exec_ms, especialmente OUTBOUND_RELAY 0.3.41 da Sentinela A. Investigar polling/backoff, Event V2, fair scheduling e notificações. Preservar ordenação de mutações, idempotência e grants. Meta: reduzir cauda p95/p99 real, sem prometer milissegundos sem homologação nem atualizar automaticamente Agent em uso.

**R9-P1-02 — Fila e sessões Services.** Comprovar 13/16 RUNNING e owner de 12 sessões antigas; proposta de revisão/renovação do dono, detecção de pager nas sessões não interativas, aviso de capacidade e liberação explícita sem matar trabalho de outra frente. Testar 12/16 e 16/16, quotas de sessão por dispositivo, valor de `PROCESS_SESSION_CAPACITY_EXCEEDED`. Não confundir fila MCP com slots PTY: medir separadamente.

**R9-P1-03 — Observabilidade correta no produto.** Expor média e p95/p99 de queue/exec/total por ferramenta, dispositivo e transporte, amostragem/limites e status do socket. Alarmes de armazenamento conscientes de mount/fstype (Bazzite root imutável), GPU NVIDIA/AMD/indisponível distinta e metadata de build/hash real. O caso DEVICE_OFFLINE transitório precisa status e retry seguro, sem falsos relatos de conclusão/ausência de mutação.

**R9-P1-04 — Superfície e distribuição.** Reconciliar 31 IDs canônicos do Agent, 24 ferramentas expostas aqui e 33 anunciadas no pacote fonte; paridade para hash, rollback, receipt, leitura em lote e processos. Não duplicar funções nem expandir privilégios para conseguir aparência de paridade. QUALIFICAR Windows 0.3.53 OFFLINE em ambiente reservado. Candidato Linux/Windows 0.3.43 segue sem assinatura; NÃO tratar como atualização da instalação interna 0.3.54, nem promover sobre acesso primário sem readback/rollback.

**R9-P2-05 — Instrumentação e tendência da frota.** Observar RAM/swap/VRAM com amostras ao longo do tempo; GPU 0% num instante não é prova de ociosidade contínua. Observer raiz 76% pede alerta de tendência; Ninja só usar volume gravável. Modelos carregados na Sentinela D precisam monitorar RSS/CPU/VRAM com cuidado; **não alterar distribuição de modelos nesta frente** sem contrato operacional separado. HARA Commander deve expor capacidades, não mover modelos por conta própria.

**R9-P2-06 — Jornada de escala autorizada.** Depois de assinatura e canário, medir read-only microburst 1/4/8/16, múltiplos computadores, reconexão, resultado tardio, cancelamento, leitura íntegra e pedidos negados. Testes de um milhão de chamadas e 1.000 organizações somente em QA/DEV provisionado, com orçamento próprio; as 3.442 chamadas Founder NÃO são homologação comercial.

## Handoff e segurança

As oito provas são JSONs sanitizados. Não contém IP, token, comandos pessoais, conteúdo de clientes nem dados financeiros. Uso real foi somente leitura, exceto a gravação destas evidências locais em QA. O Codex continua como único escritor do código do Commander. Ele já corrigiu R8 CAS em `442eeac`; **não reabrir R8**. A revisão R9 deve aprofundar gargalos novos de latência/observabilidade. Nenhum deploy, migração D1, assinatura, VM Windows, power cycle ou encerramento de sessão foi feito.
