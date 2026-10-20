# HARA Commander — R7 revisão independente de sessão/capacidade e autenticação

20/10/2026. Fonte e testes independentes preparados por Valky, somente H.A.R.A. Commander. Este documento é apoio à sessão Codex existente, não solicitação de novo executor.

## Prova que passou

Fonte congelada: `56a1175d03ec7fcf47607056e7b287e4974c396f`, obtida por git archive em diretório QA. Executei testes existentes, com resultados em `docs/evidence/commander-peer-review-r7-20261020/r7-independent-tests.json`:

- `test_hara_identity_customer_auth_pressure.mjs`: exit 0, incluindo coalescing de verificações do mesmo token em chamadas simultâneas, independência entre tokens, revogação sem cache persistente, resposta 503 para falha do provedor e prazo de timeout.
- `test_oidc_discovery.mjs`: exit 0, validação de endpoints HTTPS e URI.
- `validate_process_session_policy.py`: exit 0, paginadores somente no filho não interativo, owners/alertas e capacidade SEQUENCIAL.

Não são testes de Identity PROD, canário Windows ou execução remota e não provam robustez sob chamadas simultâneas no mesmo processo.

## R7-PROCESS-CONCURRENCY — lacuna condicional de proteção de capacidade

Fonte: `apps/commander/public/agent/linux.py::process_start()`. A função conta sessões RUNNING e verifica MAX_PROCESS_ACTIVE_SESSIONS antes de `pty.fork()`; grava a nova sessão depois do fork. Não há reserva atômica/lock ao redor dessas três fases.

Preparei `peer_concurrent_sessions.py`, que executa a própria função `process_start` em duas threads QA e substitui APENAS o `pty.fork` por uma barreira/FD descartável. Portanto não há fork ou comando real, nem ações de clientes. Com `MAX_PROCESS_ACTIVE_SESSIONS=1`, as duas chamadas cruzaram a barreira depois de passar na checagem e ambas foram aceitas: **2 sessões ativas para limite 1** (exit 2 = achado reproduzido). Ver `r7-concurrent-process-results.json`.

**Escopo e limitação importantes:** isto prova que a operação não é segura caso duas invocações entrem simultaneamente na MESMA instância Python. Não demonstra que o transporte comercial existente permita essa concorrência: o loop STDIO local consultado é serial e o Agent Event V2 pode processar chamadas sequencialmente. A superfície ThreadingHTTPServer do portal local não foi demonstrada como invocadora de process_start. Não classificar como incidente produtivo nem bloquear release sem examinar alcançabilidade real.

Sugestão de melhoria se concorrência for parte da estratégia do produto: reservar capacidade antes do fork sob lock de admissão, revalidar após falha de fork, liberar reserva no erro e não segurar lock durante tarefas longas. Testar limite=1 e 16, duas ou mais chegadas simultâneas, falha de fork, erro na criação do coletor, sinal/limpeza, retentativas e rejeições precisas. Caso o sistema garanta serialização por processo, documentar/validar o contrato e testar múltiplos processos em paralelo para limite por DISPOSITIVO versus por INSTÂNCIA.

## Observação real de frota (sem mutações)

`H.A.R.A._Commander.list_sessions(services)` retornou 22 sessões, sendo 13 RUNNING e 9 EXITED. Várias RUNNING começaram em 13/10. Não há dados suficientes para chamar essas sessões de abandonadas e nenhuma foi encerrada. No Agent ativo ainda não aparecem campos novos de owner/capacity; o patch c254758 permanece código não publicado neste host.

`list_devices` mostrou `ONLINE` e `last_seen_at_utc` bastante antigo para algumas máquinas Event V2. Pings reais para sentinela-c, ninja-blue, sentinela-d e nucleo-a responderam PASS por volta de 20:49 UTC. Isso mostra que last_seen não equivale necessariamente à conectividade presente num transporte com checkpoints espaçados. Recomendar status distinto para cadastro ativo, liveness por checkpoint e ping/transport atual. Não marcar máquina offline apenas pela idade de last_seen no modo Event V2.

## Retorno à frente Codex

Nenhuma alteração no código do executor, branch Codex ou Agent produtivo. Documento/fixtures nesta branch de revisão devem ser avaliados sem repetir frentes já fechadas. Prioridade à correção R4/R5/R6/aceite Windows/assinatura já em andamento; R7 é melhoria preventiva P2 se o Agent operar chamadas concorrentes dentro do mesmo processo.

O proprietário não deve ter de repassar o relatório. Coordenar pelo inbox da sessão existente e registrar correções com escopo exato (reproduzido local / DEV / canário / PROD), sem inventar capacidade de processamento nem reinstalar HARA.

## Reconferência contra HEAD mais recente

Com o Codex ainda avançando, extraí o commit `73c3dd25b4900e30d6657370fbe1e5c2a87f102d` para outro diretório QA, sem modificar o worktree dele. A mesma barreira de duas threads produziu duas sessões aceitas com limite um (exit 2). Resultado em `latest-concurrent-results.json`. Continua sendo prova de concorrência induzida na função, não de caminho de produção multithread confirmado.
