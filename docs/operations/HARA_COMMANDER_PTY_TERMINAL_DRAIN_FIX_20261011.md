# H.A.R.A. Commander — correção de perda de saída PTY (11/10/2026)

Estado: **CÓDIGO CORRIGIDO / TESTES LOCAIS PASS / RELEASE 0.3.46 ASSINADA / CANÁRIO AINDA PENDENTE**.

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
