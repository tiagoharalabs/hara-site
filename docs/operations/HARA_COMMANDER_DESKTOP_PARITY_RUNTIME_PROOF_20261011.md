# H.A.R.A. Commander — prova operacional de paridade com Desktop (11/10/2026)

**Resultado:** transferência e restauração via frota PASS; terminal interativo com saída após encerramento **FAIL reproduzível**. Não declarar paridade completa nem cliente SaaS 1.000 homologado.

## Escopo e autoridade

As operações reais desta rodada foram executadas pela integração **H_A_R_A__Commander** (MCP comercial -> Secure Cloud -> Agent 0.3.45) sobre as máquinas Founder, **sem usar Desktop Commander** para transferência, auditoria, interrupção ou recuperação. Diretórios de teste exclusivos em `/tmp_hara/commander-parity-proof-20261011`. Frota Founder observada Linux 7/7 ONLINE, Agent 0.3.45. Não foram alterados dados de clientes, fontes de jogo, filas CSOTN nem serviços de GPU.

## Transferência de dados (PASS dentro da frota)

- A fonte sintética no Services continha 32 arquivos regulares, **12.842.112 bytes**, incluindo binário de 12 MiB, arquivos UTF-8/acentos, diretórios aninhados, arquivo vazio e um symlink relativo interno.
- Serviços -> Núcleo A, Sentinela C e Sentinela D via `rsync` sobre SSH, acionado pelo Agent do H.A.R.A. no Services. Cada destino conferiu via H.A.R.A. local o manifesto SHA-256 de todos os 32 arquivos e o symlink. **3/3 destinos PASS**.
- O binário de 12 MiB apresentou SHA-256 `5546959cd31fb2b1436a0a92eb3c5f623aa2a538f5ba7ec4a46db40776a99314` em todos os destinos.
- Teste de rede interrompida na Sentinela D: `timeout` encerrando `rsync` a 256 KiB/s após **720.896 bytes**, código de interrupção 124; retomada com `--append-verify` concluiu arquivo de **12.582.912 bytes**, SHA idêntico; manifesto completo PASS.
- Manifesto de ~5,18 KiB também transitou **nativamente pelo MCP** (read_file no Services -> write_file no Núcleo/C/D) com recibos.
- `hara.files.copy` nativo copiou arquivo binário de 1 MiB com hash `5a9f73c188e62cdf43baa2f160b13e536cc62d2029b6cdee130a0187f28faf1d`, PASS. O Agent bloqueia cópias locais acima de 2 MiB (`COPY_FILE_TOO_LARGE` no source). **Não existe ainda ferramenta de transferência binária inter-host nativa do produto.** O caminho `rsync/SSH` requer relação de confiança SSH entre máquinas do proprietário e NÃO demonstra transferência geral entre computadores de clientes sem configuração prévia.

## Recuperação remota (PASS com nó alternativo)

- A Sentinela A estava sem sessões interativas RUNNING. O Agent foi parado deliberadamente por comando remoto emitido do Services através do H.A.R.A.; `ping` comercial da Sentinela A retornou **DEVICE_OFFLINE**, como esperado.
- A rotina temporária do Services possuía `trap` de restauração; o Agent foi reativado, e o H.A.R.A. voltou a obter `device.info` em 0.3.45 e execução local. Serviço `active + enabled` e guard `active` confirmados. Nenhum Desktop envolvido.
- Trata-se de **recuperação peer-assisted** por um segundo host disponível, não de recuperação autônoma de host único.

## Operação contínua (PASS com systemd; sessão PTY FAIL)

- Uma tarefa transitória isolada do `systemd --user` na Sentinela A escreveu 25 checkpoints sequenciais durante ~25 s. O Agent H.A.R.A. foi reiniciado durante a execução; foram observadas **25/25 linhas no log**, última linha 24. Tarefa independente do Agent permaneceu ativa durante o restart. Uso restrito ao diretório de teste.
- **Defeito reproduzido de perda de stdout na sessão PTY H.A.R.A.**: sessão de 25 linhas devolveu apenas 8 ao consultar após conclusão, com exit code 0; segunda sessão produziu comprovadamente 120 linhas num arquivo local, mas a leitura MCP pós-exit devolveu **0/120 linhas**, `EXITED`, `exit_code=0`, `buffer_truncated=false`. Isso não é simples truncamento por limite de saída.
- Hipótese técnica confirmável em fonte: `_process_update_state()` chama `waitpid(..., WNOHANG)` e fecha `session["fd"]` imediatamente ao detectar exit; a PTY pode conter bytes ainda não lidos. Necessário drenar a PTY em modo não bloqueante antes de fechar, com orçamento finito e teste de regressão cobrindo stdout pós-exit, stdout UTF-8, stdout grande e retenção limitada. **P0 PARA PARIDADE.**
- Uma tentativa de gravar um novo teste de regressão de código através da ferramenta foi bloqueada pela camada de segurança da plataforma. Não foi contornada. Nenhuma correção de Agent foi aplicada nesta etapa; fleet permanece no release 0.3.45.

## Critérios de conclusão pendentes

1. **P0:** corrigir perda de saída terminal pós-exit, assinar novo Agent, testar primeiro em canário, depois 7/7.
2. **P1:** transferência binária inter-host nativa com chunks limitados, SHA por bloco e SHA global, retomada segura após falha, escrita temporária/commit atômico, proteção a symlink, limites de volume e escopo de tenant, sem exigir SSH entre clientes.
3. **P1:** testes de recuperação de socket enquanto chamada longa está em execução; reconciliar por ID exato e impedir execução duplicada.
4. **P1:** soak de 24h/72h, reinício/reconexão, custo Workers/D1/DO e testes de múltiplos tenants; certificação de 1.000 usuários reais ainda NÃO realizada.

O Stripe fica fora deste gate e a Cloudflare Paid permanece habilitada. Não há dado bancário nos testes.
