# HARA Commander — R10 | Homologação funcional real na VM Windows 11

Data: 20/10/2026 (~22:44–22:57 UTC). Auditoria independente via **H.A.R.A. Commander**, com autorização expressa de Tiago. Executada no domínio libvirt `commander-win11` do Núcleo, nome do SO `HARA_WIN11`. **Windows online e respondendo ao MCP**. Isto é um teste real do Agent instalado, não apenas um harness local.

## Escopo/segurança
- **Agent ativo:** `0.3.53`, plataforma WINDOWS, modo `OUTBOUND_RELAY`, autorização `SESSION_TRUSTED`. `get_config` anuncia **19 funções canônicas**; o Agent Linux conectado anuncia 31, a superfície do Chat atual 24, e o código comercial candidato aponta 33. NÃO tratar listas de diferentes contratos como equivalentes sem reconciliação.
- **Fixture exclusiva:** `C:\Users\Public\Documents\HARA_COMMANDER_QA_20261020_WIN11\probe.txt`. Diretório criado nesta auditoria e mantido apenas para a frente repetir verificações. Contém só texto sintético de QA (acentos, Unicode e marcador), nenhum dado de cliente. Escritas CAS foram exclusivamente nesse arquivo.
- Nenhum Agent instalado/atualizado/reiniciado, nenhuma migração D1, nenhuma VM adicional inicializada, nenhuma alteração de firewall, permissões, senha, autologon ou produto comercial. O Agent Windows 0.3.53 permanece em uso.
- As duas sessões de processo criadas no Windows nesta auditoria foram encerradas com `kill_process` e confirmadas `EXITED`. Não encerrei processos de terceiros.
- Código candidato Linux/Windows comercial na frente Codex ainda pode ter versão 0.3.43 sem assinatura; **não substituir o Agent Windows 0.3.53 por esse bundle automaticamente**.

## Confirmação real de conectividade Windows
`list_devices` mostrou HARA_WIN11 ACTIVE/ONLINE, `ping` retornou PASS e `get_device_info` identificou Windows NT 10.0.26300.0 / PowerShell 5.1 / `OUTBOUND_RELAY`. `get_config` apresentou aprovação `SESSION_TRUSTED`. O login do proprietário resolveu o bloqueio observado antes da sessão.

## Matriz de teste direto via MCP conectado

| Função/cenário | Estado demonstrado | Observação |
|---|---|---|
| `create_directory` em Public Documents | PASS | Diretório QA criado sem sobrescrever nada |
| `write_file` `probe.txt` | PASS | 134 bytes em primeira gravação |
| `read_file` com offset=0 e 3 | PASS | 5 linhas preservadas, inclusive `João`, `漢字`, `☕` |
| `get_file_info` | PASS | Tamanho, timestamps e atributos retornados |
| `list_directory` QA | PASS | Fixture foi encontrada |
| `write_file` com `expected_sha256` **incorreto** | DENIED (esperado) | `FILE_PRECONDITION_FAILED`, arquivo relido intacto |
| `Get-FileHash` via `start_process`, `write_file` com CAS correto | PASS | Novo conteúdo de 156 bytes, sexta linha `CAS_POSITIVE_PASS` confirmada; sem ferramenta de hash nativa no conector |
| `read_multiple_files` | DENIED | `UNKNOWN_FUNCTION_ID`: Windows Agent não oferece a função no contrato conectado |
| `search` conteúdo | DENIED | `UNKNOWN_FUNCTION_ID` |
| `edit_block` em arquivo QA | BLOQUEIO | `AGENT_UPGRADE_REQUIRED`; nenhuma alteração feita |
| `process.run` PowerShell curto | PASS | Exit code 0 e saída recebida |
| `process.run` com Unicode | PASS | `ação_漢字_☕` preservado; quebra de linha devolvida como `\r\r\n` em alguns retornos |
| `process.run` `exit 7` | Transporte PASS / comando exit 7 | Correto distinguir sucesso MCP de sucesso do processo |
| `process.run` oito linhas / `max_lines=3` | Truncado, sem recuperação | `output_truncated=true`, `session_retained=false`, nenhum run_id consultável |
| `process.start` gerenciado | PASS | Saiu `RUNNING`, saída inicial e tardia recuperadas pelo `read_process_output` |
| `process.interact` com `Read-Host` | Erro funcional | O PowerShell de sessão gerenciada é `-NonInteractive`; `Read-Host` falhou e texto enviado virou comando PowerShell (erro no STDERR), embora chamada MCP retornasse PASS |
| `kill_process` das sessões QA | PASS, confirmação assíncrona | A resposta imediata ainda podia indicar RUNNING; `list_sessions` depois confirmou ambas `EXITED` |

**Importante:** os erros `UNKNOWN_FUNCTION_ID` e `AGENT_UPGRADE_REQUIRED` são bloqueios reais na versão Windows instalada; não implicam que a função não exista em toda versão futura. A ferramenta `read_file` não entregou token CAS; a homologação usou `Get-FileHash` explicitamente, aumentando as chamadas.

## R10-WIN-LIST-PAGE — offset de listagem ignorado

`list_directory(C:\, limit=4)` foi chamado com offsets 0, 4 e 100. **Os três resultados devolveram os mesmos quatro primeiros itens**, `truncated=true`, sem `next_offset` nem sinal de continuação. Portanto o parâmetro da superfície publicada não está implementado/honrado nesse caminho do Windows. Isto é diferente de paginação entre resultados de um arquivo (`read_file` com offset passou).

**Prioridade P1 funcional.** Corrigir backend/mapper Windows para retorno estável com `next_offset`, `has_more`, `continuation_safe`; em árvore alterada/erro de permissão, declarar incompleto sem falsa continuação. Teste 0/4/100 sobre diretório QA com itens ordenados, depois cenário C:\; não afirmar que `truncated` significa página recuperável se não é.

## R10-WIN-RELAY-LATENCY — execução curta, espera longa

Efetuei **quatro leituras simultâneas e somente leitura** do arquivo de QA pelo MCP Windows. Todas PASS, e o tempo decorrido do lote foi aproximadamente 19,3 s. Na janela correspondente de `get_activity(window=24h)` identifiquei quatro chamadas `hara.files.read` em HARA_WIN11 / `OUTBOUND_RELAY`, Agent 0.3.53, criadas de 22:54:28.468Z até 22:54:28.615Z:

| Métrica | Quatro chamadas |
| --- | --- |
| `queue_ms` | **6.297 / 9.757 / 12.852 / 15.843 ms** |
| `execution_ms` | 611 / 641 / 640 / 640 ms |
| `total_ms` | 6.908 / 10.398 / 13.492 / 16.483 ms |
| Resultado | 4/4 COMPLETED |

Outro registro `hara.files.read` na janela (~22:54:28.017Z) tinha fila 422 ms; não foi incorporado como parte das quatro chamadas por não coincidir exatamente com a sequência. Atribuição aos quatro é por horário/função/destino e não por vínculo direto de request IDs no relatório desta conversa.

O padrão reforça o achado R9 da Sentinela A 0.3.41 `OUTBOUND_RELAY`: o tempo é gasto majoritariamente **na fila**, não na CPU de execução. O Codex já criou `f682037` para **burst do relay Linux**, portanto **não reimplementar esse patch**: qualificar o contrato e o loop de polling do **Windows 0.3.53** separadamente, mantendo idempotência/autorização. Teste antes/depois num canário Windows sob aprovação, sem disparar benchmark pesado na VM produtiva.

## R10-WIN-PTY / CLI e paridade

O Windows Agent 0.3.53 preserva saída Unicode, CAS de escrita e execução curta. Porém process.start gerenciado aceita comandos PowerShell no modo NonInteractive: `Read-Host` falha, texto enviado pelo `interact_with_process` é interpretado como comando posterior (pode causar execução inesperada se clientes presumirem STDIN interativo). O produto deveria explicitar `interactive_input_supported=false` nesse modo ou prover terminal Windows com política de sessão/consentimento testada.

O processo one-shot truncado não conserva identificador/cursor para recuperar o restante. No Linux, a frente Codex já corrigiu esse problema na R5, mas **essa implementação não está presente no Agent Windows 0.3.53**. Preservar saída de tarefas mutantes sem executá-las novamente; limitar buffer, duração e limpeza. Após kill, fornecer `TERMINATING` ou estado final confirmado, em vez de retornar RUNNING silenciosamente após a solicitação de encerramento.

## R10-WIN-VM-CPU — hardware concedido versus reconhecido pelo Windows

**Anomalia relevante do ambiente de QA, não do código HARA Commander:**

- `virsh vcpucount commander-win11`: 8 vCPUs atuais e máximos.
- Comando real do QEMU `-smp 8,sockets=8,cores=1,threads=1` — confirmada a topologia de **oito sockets**.
- Windows 11 Pro no guest: `Win32_ComputerSystem.NumberOfLogicalProcessors=2`, `NumberOfProcessors=2`, `[Environment]::ProcessorCount=2`; WMI encontrou dois CPUs e total de dois lógicos.
- Portanto a VM recebeu oito vCPUs, mas **o Windows só expõe dois ao software**, compatível com limites de sockets do Windows Pro nessa topologia. Os números do guest foram confirmados por duas consultas e os argumentos QEMU sanitizados.

Recomendação de topologia para futuro QA: **1 socket × 8 cores × 1 thread**, mantendo total 8, ou variante compatível com arquitetura host. **Não aplicar agora**: requer planejar interrupção segura, preservar estado, definir rollback, parar e religar VM, e nova aprovação específica do proprietário. Não culpar exclusivamente esse ponto pela fila de 6–16 s, pois execução foi ~0,6 s.

## Prioridades ao Codex

1. **P0 funcional/paridade comercial:** diagnóstico e implementação/testes de read_many, search, edit e demais ferramentas comparáveis Linux/Windows; publicação de catálogo/grants condizente com implementações, sem upgrade silencioso nem desativar autorização.
2. **P1:** listagem com paginação correta e erros de varredura; testar a API MCP conectada, não apenas funções auxiliares.
3. **P1:** saída de processo Windows recuperável em paginação e terminal interativo com contrato honesto (não prometer Read-Host com -NonInteractive).
4. **P1:** reduzir cauda de fila do relay Windows em QA/canário, usando observabilidade queue/exec/total e comparando com Linux, sem reabrir patch Linux f682037.
5. **P1 ambiental:** topologia 8 sockets/2 CPUs reconhecidas deve ser corrigida em janela aprovada antes de benchmark CPU real; não reiniciar VM agora.
6. **P2:** retorno estruturado do comando com `exit_code` efetivo, CAS via hash de leitura quando suportado, histórico/recibos/rollback e status de kill `TERMINATING`/EXITED verificado.

## Critérios de aceitação

- Testes reais no `HARA_WIN11` pelo HARA Commander após versão comercial assinada canário e com autorização; itens arquivo e processo só na pasta QA. Nenhum teste com token em logs.
- Separar versão Windows instalada **0.3.53**, candidato comercial não assinado **0.3.43**, código Linux mais novo e a aplicação Cloudflare DEV/PROD. Não converter teste Founder Windows em homologação de tenant pago/Windows limpo.
- Medir antes/depois 1/4/8 reads com filas, retornos corretos, ferramentas ausentes corrigidas, interatividade, paginação e CAS. Não parar Agents de Linux nem a VM durante o trabalho do usuário.
- Preservar código e índice Git do Codex. O revisor escreve na branch documental isolada e entrega diretamente à mesma sessão; Tiago não precisa repassar arquivos.

Nenhuma credencial, conteúdo sensível, screenshot privado ou comando empresarial foi incluído. O arquivo QA permanece intencionalmente para reprodução pelo Codex.
