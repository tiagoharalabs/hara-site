# HARA Commander — R22 | Windows 0.3.55 ativo e console com histórico sob demanda

**21/10/2026, ~18h16–19h04 UTC.** Execução operacional pelo H.A.R.A. Commander, com Núcleo A e Services como acesso, Windows `HARA_WIN11` como canário e QEMU Guest Agent como canal de recuperação independente. Autorização explícita do proprietário: atualizar para versão recente, testar comandos e abrir console limpo sem eliminar histórico.

## Entrega real: atualização canário Windows 0.3.53 → 0.3.55

- Agent Windows agora **0.3.55** (MCP `ping`, `device.info`, `runtime-status`, arquivo instalado e tarefa `HARA Commander Agent` confirmados). O `device_id` não mudou, a aprovação permanece `SESSION_TRUSTED`, e o transporte é `OUTBOUND_RELAY`.
- Pacote exclusivo `FOUNDER_WINDOWS_CANARY`, **não** comercial/Windows+Linux genérico e **não** publicado na Cloudflare. Fonte assinada e instalada SHA-256 **`07de45201052c6fbc98764dba619f1e83864b96eed0c998f1d007ad04bf5f57f`**, versão declarada 0.3.55.
- Manifesto Windows-only com identidade de dispositivo vinculada, SHA-256 `0a7b63dbe5d286902ed155d5793c0bb22cb3d05c8b0fe95fcfb8edbf6daa18b9`; assinatura oficial `RS256`/RSA-3072 `commander-release-v2`, SHA `1fe5b5470f9edbbb56a42cbfe502a0142b1938a6f76e0c0e93dbcbd9a3a9b066`. Verificada independentemente no Núcleo e **no próprio Windows com .NET RSA** antes da atualização. A chave privada permaneceu no Services, não foi exportada.
- Antes: Agent 0.3.53 SHA `7a6112b51835de4177400057dadce15904e974f20a0f1dba940a0dc41c697708`. Backup dessa fonte em `%LOCALAPPDATA%\HARA Commander\r22-original-0.3.53-backup.ps1`, mesmo SHA, preservado para rollback.
- Atualização executada em tarefa transitória *separada* `HARA Commander R22 Upgrade` sob o próprio usuário Windows, com verificação de identidade, origem e assinatura, backup interno, `Stop-ScheduledTask` e `Start-ScheduledTask` do Agent e rollback em caso de erro. Recibo local `updates\r22-win055\upgrade-receipt.json` registrou **`AGENT_055_RUNNING`**. Tarefa temporária e script temporário de upgrade foram removidos após confirmação; Agent principal permanece **Running**, sem reiniciar a VM.
- QEMU Guest Agent respondeu ao `guest-ping` antes e depois, para recuperação independente. Nenhum Agent Linux, Cloudflare, billing ou sistema do usuário foi modificado.

## Correção de UX entregue no código instalado

**Causa original:** `Start-OperatorConsole` iniciava `$seen=0` e a cada 250ms executava `Get-Content` sobre **todo** o `console-events.jsonl`, depois exibindo todos os registros históricos. O arquivo real tinha mais de 1 MiB de eventos quando a auditoria começou.

A nova versão:
1. Captura a posição **EOF** ao abrir a sessão e exibe **somente novos eventos**, sem apagar/manipular o histórico anterior.
2. Lê incrementalmente apenas novos bytes, com leitura limitada a 128 KiB/ciclo e aguarda a conclusão de linhas JSONL antes de mostrá-las (não recarrega o arquivo inteiro 4 vezes por segundo).
3. Oferece `hara-commander history` (últimos 50) e `hara-commander history 25 <before_id>` com paginação retroativa sobre SQLite **local**, preservando recibos e sem renderizar `action_summary`, token ou argumentos.
4. Preserva `console-events.jsonl` e `operations.sqlite3`. Após a atualização, ambos continuam presentes e aumentaram naturalmente (aprox. 1,47 MB JSONL e 2,35 MB SQLite); não houve `truncate`/remoção.

**Prova no Windows:** fixture PowerShell isolada derivada das funções exatas do candidato executou **13 verificações independentes + marcador final PASS** (EOF sem replay, evento novo, sem duplicação, escrita parcial, finalização de linha, preservação do arquivo, histórico sob demanda, paginação e privacidade), exit 0. `--self-test` completo do Agent 0.3.55 testado no Windows real e aprovado, incluindo regras de aprovação, recibos, SQLite, sanitização e autorização por sessão. O comando do Agent instalado `history 3` funcionou, sem exibir marcador de conteúdo privado.

**Observação de UX:** o operador mantém uma janela antiga aberta, que já havia carregado o script 0.3.53. A janela deve ser **fechada com Ctrl+C e reaberta com `hara-commander start`** para adotar o código novo; não encerrei a sessão pessoal do usuário remotamente. Esse reinício visual específico ainda depende de confirmação do operador.

## Testes funcionais reais pelo HARA Commander, após update

| Teste | Resultado |
| --- | --- |
| `ping`, `device.info`, versão e Device ID | **PASS** 0.3.55, mesma identidade |
| Leitura de arquivo e Unicode em diretório QA público | **PASS** |
| Listagem com `offset=2` | **PASS**, página correta |
| Escrita com SHA incorreto | **DENIED esperado** `FILE_PRECONDITION_FAILED` |
| Escrita CAS com SHA correto + readback | **PASS**, conteúdo sintético intacto |
| PowerShell com Unicode e `exit 7` | **PASS da chamada**, `exit_code=7` corretamente preservado |
| `process.run` oito linhas com `max_lines=3` | **PASS**, retorno com `run_id`, `session_retained=true`, páginas offset 3/6, oito linhas recuperadas sem reexecutar |
| Histórico SQLite local `history 3` | **PASS**, consulta explícita, sem conteúdo privado |
| Microburst 4 `read_file` paralelos | **4/4 PASS**; fila **1.913, 4.772, 5.816, 6.740 ms**, execução 689–811 ms |
| Operações `read_many`, `search`, `edit_block` pela superfície MCP conectada | **BLOCKED** (duas `UNKNOWN_FUNCTION_ID`, uma `AGENT_UPGRADE_REQUIRED`) |

**P1 importante para Codex:** embora o Agent 0.3.55 esteja rodando, o `get_config` **conectado** ainda retorna **19 capacidades**. A fonte de Worker mais nova na branch revisada já declara **22** para Windows 0.3.55; o Worker/backend implantado permanece com roteamento/catálogo anterior. **Não culpar nem reinstalar o Agent Windows:** preparar/testar deploy de Worker/manifest/capabilities com version readback, aprovação formal Cloudflare e canário, para liberar as três funções. Não executar deploy PROD sem gate.

**Desempenho:** a fila do `OUTBOUND_RELAY` ainda domina a latência no microburst; execução do Agent em ~0,7–0,8 s. Medição pequena e pontual, não é p95/p99 de SLA. Uma chamada `ping` devolveu `IOEXCEPTION` transitório, e nova tentativa retornou **PASS**; não inferir queda permanente da VM.

## Comparação com toda a frota e release público

- Sete Linux Founder continuam Agent **0.3.54 Event V2** (duas variantes de loop assinadas), Observer/Storage comercial **0.3.43 OUTBOUND_RELAY** e Windows Founder atualizado **0.3.55 OUTBOUND_RELAY**. **Não temos uma única versão de Agent em todas as plataformas** — a atualização de Windows é canário separado, não rebaixou os demais.
- O instalador público Windows/Linux serve **0.3.43 v2 assinada**, com quatro hashes de release válidos (verificação R21). Não está na 0.3.55 e não deve ser rotulado como última versão geral.
- A paridade atual de capacidades do Worker é Linux Founder 31, Windows candidato 0.3.55 previsto 22, mas Worker hospedado Windows apenas 19. As diferenças funcionais devem ser documentadas ou implementadas; não prometer 31/31.
- Propriedade/segredos de cada máquina foram preservados, sem copiar token de outros hosts ou diminuir controle de aprovação.

## Próximo trabalho curto para Codex

**P0 produto/UX:** integrar este fix de console (EOF ao abrir, stream incremental, `history` paginado) e seus testes na fonte oficial, sem usar `$seen=0` novamente; manter o histórico por dispositivo e o consentimento do operador. **P0 backend:** atualizar o Worker hospedado após testes e autorização Cloudflare para liberar `read_many/search/edit` no 0.3.55 e comprovar 22 capacidades reais. **P1 performance:** reduzir cauda do polling relay no Windows e preservar ACK/outbox/semântica de retry. **P1 release train:** produzir e assinar release comercial Linux+Windows coerente (não confundir Founder e comercial), validar Storage/Observer/Windows clean install/rollback; não rebaixar a frota Linux.

**Branch isolada de revisão, não o checkout ativo Codex.** Assinatura aplicada a uma única identidade Windows via pacote canário público seguro. `validate_windows_r22_signed_canary.py`, `validate_windows_r22_history.py`, fixture de teste do Windows, JSON de evidência e hashes registrados. Sem produção Cloudflare.
