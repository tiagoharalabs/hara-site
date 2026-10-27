# Commander 0.3.56 — atualização privada da frota

Gerado em 2026-10-27T22:53:49.882253+00:00.

**Resultado observado:** 9/9 hosts com atualização e runtime nativos aprovados; 9/9 com `device.info` pelo Commander principal na versão .56.

Execução remota de `id -u`: **9/9 PASS**, com exit0 e autorização `PERSISTENT_TRUSTED` por política do enrollment.

**Lançamento público: NO-GO.** Este registro comprova a execução privada descrita e não aprova publicação.

## Resultado por host

| Host | Instalação/runtime | Commander E2E | Início da .56 | Heartbeat posterior |
|---|---|---|---|---|
| sentinela-a | PASS | PASS | 2026-10-27T22:39:14.362725+00:00 | Sim |
| sentinela-b | PASS | PASS | 2026-10-27T22:47:32.347692+00:00 | Sim |
| sentinela-c | PASS | PASS | 2026-10-27T22:37:37.290002+00:00 | Sim |
| sentinela-d | PASS | PASS | 2026-10-27T22:38:26.207923+00:00 | Sim |
| nucleo-a | PASS | PASS | 2026-10-27T22:29:31.675972+00:00 | Sim |
| ninja-blue | PASS | PASS | 2026-10-27T22:31:45.479938+00:00 | Sim |
| observer | PASS | PASS | 2026-10-27T22:40:04.664169+00:00 | Sim |
| storage | PASS | PASS | 2026-10-27T22:46:57.831539+00:00 | Sim |
| services | PASS | PASS | 2026-10-27T22:43:13.417173+00:00 | Sim |

Os hosts migrados pelo helper convergem para a unidade standard; onde a unidade V2 já existia, ela permanece preservada para rollback, parada e desabilitada após o health. O opt-in legado da V2 não é transferido. O updater conserva o enrollment e as cópias de rollback, com verificação própria por host.

## Ocorrências e provas adicionais

- **Nucleo-A:** a primeira tentativa retornou rc7 por conflito com a CLI legada. A comparação dos hashes confirmou a compensação: Agent, configuração e unidade preservados, com o serviço .54 ativo. Após a migração explícita da CLI, a segunda tentativa concluiu a atualização e o runtime .56 com PASS, seguidos de E2E. A primeira falha permanece no registro.
- **Processo real no Nucleo-A:** `process.run` executou `id -u`, retornou UID 1000, com exit0 e autorização `PERSISTENT_TRUSTED`.
- **Storage:** a primeira tentativa terminou HOLD por `ACTIVE_AGENT_CMDLINE` durante a observação imediatamente após o start; o updater havia retornado exit0. O readback independente confirmou restauração dos arquivos, configuração, unidade e CLI, remoção do drop-in e serviço .54 ativo com heartbeat novo. Com o fix do helper, a retentativa 02 concluiu a migração .56 com PASS e E2E. A primeira HOLD continua registrada. A corrida observada pertence ao helper; não demonstra defeito do produto .56.

O fix do helper aguarda somente a observação transitória `ACTIVE_AGENT_CMDLINE` após o start, por até 5 s e dentro do deadline existente. A identidade do executável permanece obrigatória. O JSON vincula os hashes das fontes e os 8 testes dirigidos nativos em cada um de Storage e Sentinela B.

## VM Ubuntu e limites

A VM Ubuntu tem evidência de checkpoint frio, restauração materializada e boot da baseline pelo libvirt normal, seguida do update oficial .56. O updater preservou o estado manualmente parado. Um start nativo posterior não transforma um heartbeat histórico em prova de operação remota.

O readback Windows mais recente está registrado separadamente: usuário de console presente = False; perfis QA carregados = 0. Essa leitura não comprova instalação nem aceitação Windows.

A aceitação Windows, a recuperação funcional do produto, o refresh OAuth ponta a ponta, os gates de segurança e a publicação continuam exigindo evidências próprias. O R2 anterior permanece STOP; testes do R10 não são promovidos a aceite de restore. Event V2 não é habilitado nesta rodada.

## Encerramento da distribuição privada

Estado: **PASS_PRIVATE_DISTRIBUTION_CLOSED**, observado em 2026-10-27T22:49:56.830051+00:00. O servidor e o timer foram parados; o listener e as regras temporárias UFW/nft estão ausentes. O UFW continua ativo e as regras originais de isolamento QA foram restauradas. Os três comandos de encerramento retornaram rc0 e as verificações de readback estão no JSON.

## Rastreabilidade

O arquivo [fleet-rollout-summary.json](fleet-rollout-summary.json) contém os resultados por etapa, versões, hashes, timestamps, recibos E2E e SHA-256 dos arquivos de origem retidos. Não inclui comandos brutos, credenciais, configuração privada ou chaves.
