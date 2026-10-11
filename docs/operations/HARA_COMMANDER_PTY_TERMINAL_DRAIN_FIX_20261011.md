# H.A.R.A. Commander — correção de perda de saída PTY (11/10/2026)

Estado: **P0 CLOSED_PASS / 0.3.46 ASSINADA E HOMOLOGADA VIA MCP COMERCIAL / FROTA LINUX FOUNDER 7/7 ONLINE**. As etapas preparatórias abaixo foram concluídas; resultados reais ao final.

## Defeito reproduzido

O Agent 0.3.45 podia retornar saída incompleta ou vazia de sessão gerenciada apesar de exit code 0. Em teste real, um programa imprimiu 120 linhas comprovadas em arquivo, mas `hara.process.output` não retornou nenhuma. A causa está em `_process_update_state()`: quando `waitpid(WNOHANG)` informa o fim do processo, o master PTY era fechado sem drenar os bytes ainda disponíveis.

## Correção proposta no Agent

A função `_drain_completed_process_output` consome os bytes pendentes do descritor **antes de fechá-lo**. O FD é não bloqueante; a rotina encerra ao encontrar EAGAIN/EOF/EIO e não fica aguardando um descendente que retenha o slave aberto. A drenagem tem orçamento de 4 MiB e 250 ms, mantendo os limites de retenção existentes de 2 MiB e 5.000 linhas e marcando possível truncamento caso esgote o orçamento. Interrupções EINTR são retomadas. A saída parcial é finalizada somente após a drenagem.

## Evidências antes de promover

- Teste `apps/commander/scripts/validate_process_terminal_drain.py`: 19/19 PASS com PTYs reais, sem Cloudflare, incluindo 120/120 linhas pós-exit, Unicode, leitura repetida/cursor, leitura durante o processo, saída acima dos limites e exec one-shot.
- Gate offline geral 83/83 PASS, com suíte e verificação de assinatura isolada `validate_event_v2_terminal_release.py`; sem D1/PROD mutation.
- Release **0.3.46** criada em `/tmp_hara/commander-event-v2-0.3.46-founder-pty-signed-v2`, pacote de sete arquivos, RS256 e âncora v2 preservada; manifesto SHA256 `411cacad9a6719a3d21c3abab7ead55f528a19a35a0704f6edc6c2c079f202f1`.
- Bundle Services individual `/tmp_hara/commander-event-v2-0.3.46-services-signed-v2`, manifesto SHA256 `a619336b5a276619984c5244e34e90831e77be5ba272bd42554c427e080e2061`; assinatura e autoteste PASS.
- Chave privada permanece em Services, não exportada; release 0.3.45 intacta. Agentes públicos/comerciais 0.3.43-v2 não foram modificados; Worker Cloudflare não foi alterado.

## Gates de canário

1. Exigir zero sessões interativas RUNNING no Services e status Agent/guard normal.
2. Copiar bundle 0.3.46 individual para novo diretório de release; verificar assinatura local; salvar backup da unit 0.3.45.
3. Alterar apenas caminhos da unit do Agent V2, daemon-reload e reiniciar **somente esse Agent**, com rollback automatizado em qualquer erro de ativação.
4. Confirmar `device.info` v0.3.46 pelo H.A.R.A. MCP comercial e recibos reais.
5. Rodar pelo MCP processo com 120 linhas + exit=0, UTF-8, sessões continuadas, terminadas e one-shot. Checar que o texto total pode ser recuperado depois do exit.
6. Registrar comparação antes/depois e aprovar rollout governado da frota 7/7; máquinas de laboratório C/D apenas se não houver sessões Commander ativas, sem reiniciar outras tarefas, e com rollback por dispositivo.

**Não promover frota nem afirmar P0 encerrado até passar o teste MCP de canário real.** O armazenamento local de métricas e o heartbeat esparso Event V2 continuam independentes desta mudança.

## Fechamento da execução real — 0.3.46, 11/10/2026

**P0 CLOSED_PASS.** O commit funcional `0f337dd5c41413ad4f37e1a5fd28f78a244acc90` foi publicado no GitHub com readback exato; GitHub Actions run `38180317904` concluiu **SUCCESS**, com 83/83 validadores. Gate PTY local 19/19 PASS.

- **Services**: canário 0.3.46 assinado e verificado; processo que em 0.3.45 retornava zero de 120 linhas agora devolveu **120/120**, primeira linha `HARA_PTY_FIX_000` e última `HARA_PTY_FIX_119`, exit 0, sem truncamento, recibo do MCP real.
- Concorrência Services: quatro sessões PTY ao mesmo tempo, 120/120 por sessão (**480/480**), todas exit 0, sem mistura de conteúdo, com recibos. Unicode: 40/40 linhas `áé🚀` preservadas.
- Rollout por dispositivos RS256 aos outros seis Linux Founder pelo H.A.R.A. Commander no Services, com assinatura verificada antes da troca, backup da unit e rollback automático por host. Para Sentinela D, a sessão que estava RUNNING terminou antes da atualização; nenhuma sessão foi encerrada à força.
- Leitura direta no MCP comercial após cada restart confirmou Agent 0.3.46. Catálogo final: **7/7 Linux ONLINE, Agent 0.3.46** (Services, Núcleo A, Sentinela A/B/C/D, Ninja Blue).
- Teste real pós-exit de 120 linhas efetuado **individualmente nos sete dispositivos**, inclusive Ninja Blue: sete resultados 120/120, exit=0, `buffer_truncated=false`, primeira/última linha corretas, e recibos do Agent.
- Não houve reboot dos computadores nem reinício de serviços CSOTN/jogos. Só o Agent Commander V2 de cada nó foi reiniciado; timers guard C/D não foram ativados indevidamente. Release 0.3.45 e backups de unit preservados localmente em cada host.
- **Escopo:** versão Founder Linux somente. Pacote comercial público e Windows não foram alterados. Cloudflare Worker/D1 e Stripe não sofreram mudanças nesta correção.

Evidência estruturada em `docs/evidence/commander-pty-drain-20261011/acceptance.json`. Os próximos gates (outros que não P0) continuam: transferência binária nativa entre clientes sem SSH, recuperação autônoma do host, Windows e 1.000 clientes multitenant em soak real.
