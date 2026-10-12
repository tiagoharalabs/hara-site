# H.A.R.A. Commander — handoff operacional canônico
## Continuidade Windows 0.3.45, consentimento local e homologação comercial

**Data:** 11/10/2026, America/Sao_Paulo. **Escopo:** atualização documental, sem deploy, sem alterar Agents, identidades ou Stripe. A fonte é a inspeção real do MCP H.A.R.A. Commander, GitHub, documentos internos e canário da VM. Em conflitos, conferir o timestamp e distinguir sessões de teste de produção.

### 1. Estado atual verificado

O produto em homologação é o MCP comercial H.A.R.A. Commander (ChatGPT → túnel MCP seguro → Worker Cloudflare → Agent registrado). Não confundir com Desktop Commander ou MCP interno do Services; provas usando Desktop não homologam esta cadeia.

- Linux Founder: **7/7 ONLINE com Agent 0.3.46**, comprovado novamente: Services, Núcleo A, Sentinela A, B, C, D e Ninja Blue. P0 da perda de stdout PTY foi encerrado: 120/120 linhas pós-exit nos 7 hosts, 4 sessões concorrentes com 480/480 linhas no Services. Rollback para 0.3.45 preservado.
- Windows: único dispositivo Windows ativo **HARA_WIN11 ONLINE em 0.3.45 assinada**, na VM QEMU/KVM commander-win11 (Núcleo A). Ping, device.info, processos/arquivos read-only e process.sessions passaram pelo MCP com recibos. Último list_sessions Windows: **0 sessões gerenciadas**. Registros Windows 0.3.11–0.3.13 REVOGADOS são históricos.
- Windows distribuído a clientes: **0.3.43-v3**. A 0.3.45-v5 continua **canário privado na VM**. Releases 0.3.43-v3, 0.3.44-v4-RC, 0.3.45-v5-RC permanecem separados e assinados. O backup do Agent 0.3.44 da VM foi mantido. SHA-256 da 0.3.45 Windows: c370bff84b283172dcbcc40ee5f426e3b3d09b9181d3227755093d8577443dab.
- Worker PROD confirmado: **a326582b-76f6-4571-8adb-49dbd2675071**, 100%; DEV **d0a8c12c-021e-46f2-ae99-29b324a01e49**, 100%. O Worker só oferece sessões gerenciadas Windows com Agent >=0.3.44. A promoção do Worker não incluiu o Agent v5 público, Stripe ou migração D1.

### 2. GitHub, CI e releases

Repositório GitHub: https://github.com/tiagoharalabs/hara-site . Branch canônica desta frente: local/commander-product-current. Diretório operacional em Services: /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current .

**Antes deste novo handoff**, HEAD local e remoto idênticos: 8ede67ed8dd588dffe0f2ddcb22284174e58e5e7, commit documental sobre a janela do operador Windows. Fonte funcional do Windows 0.3.45-v5 no commit a6d27e8b67ce05ae72f01bf4bdf12e7b93b753a5; GitHub Actions https://github.com/tiagoharalabs/hara-site/actions/runs/38191514098 **SUCCESS, 89/89 no gate offline**. O commit 8ede67e não representa um novo ensaio de runtime.

A candidata v5 corrigiu privacidade: a 0.3.44 guardava no log local uma prévia de comando/caminho apesar de declarar payload_values_exposed=false; a 0.3.45 mantém metadados (ferramenta/request/estado) e só mostra conteúdo na aprovação temporária do operador. O ensaio com marcador sintético, sobre o próprio pacote assinado no Windows 11, passou. Logs históricos prévios não foram apagados/sanitizados.

Validações em laboratório Windows 11 / PowerShell 5.1:
- Agent assinado/parser/autoteste PASS.
- Terminal gerenciado .NET: 120/120 linhas depois do encerramento, interação em duas etapas, limitação correta sob 7.000 linhas.
- Escrita de arquivo com SHA-256, CAS e substituição atômica, SHA obsoleto recusado sem sobrescrever, PASS.
- Segurança fail-closed: **15/15 testes negativos** (sem sessão, negação, nonce incorreto, timeout, limpeza), PASS.
- O teste acima é em laboratório/sandbox. NÃO comprova ação mutante aprovada por humano via MCP comercial.

### 3. Bloqueio atual P0: aprovação humana POSITIVA

A configuração Windows registrada está em **ASK_EVERY_ACTION** e deve continuar assim. A autorização no chat não substitui a digitação da aprovação de CADA ação na janela local. O Agent emite nonce/request_id e SHA-256 dos argumentos com prazo de **30 segundos**. Nunca gerar resposta de aceite em arquivo, por QEMU, por automação ou alterar approval_mode para SESSION_TRUSTED/PERSISTENT_TRUSTED para fingir êxito.

Na VM, sessão obsoleta do operador foi encerrada por PID previamente conferido, marcador obsoleto limpo só após a saída e novo console aberto como o usuário gráfico. O Windows confirmou uma janela H.A.R.A. visível intitulada H.A.R.A. Commander 0.3.45 - APROVACAO LOCAL. Uma janela visível NÃO garante primeiro plano no visualizador da VM. Duas chamadas reais benignas hostname pelo MCP **expiraram com LOCAL_ACTION_APPROVAL_EXPIRED**, sem executar comando ou mutação. Após a última expiração, o console foi reiniciado uma vez para evitar reaproveitar prompt antigo.

**Readback atual após a documentação anterior:** usuário local tem processo de console ativo, sessão marcada e tarefa do Agent Running; sem pedido nem resposta de aprovação pendente; pacote 0.3.45 assinado presente. O processo pai usa wrapper PowerShell, então a linha de comando do owner não precisa conter literalmente hara-commander-agent.ps1 start; não concluir que é inválido apenas por isso. Enumeração Windows confirmou 1 janela H.A.R.A. visível, mas ainda sem garantia de foco.

Problema de UX a corrigir: Respond-ToLocalApprovalRequest usa Read-Host bloqueante. Após o timeout no Agent/Worker, a janela pode continuar aguardando um desafio vencido. Priorizar UI que expire e descarte prompts, notifique o usuário e não bloqueie indefinidamente, sempre sem aprovar automaticamente e com novo teste no Windows 11 real. Não reiniciar sessão enquanto houver aprovação pendente.

### 4. Procedimento EXATO para a próxima frente

1. Confirmar com H_A_R_A__Commander.list_devices / get_device_info(HARA_WIN11) / ping(HARA_WIN11) / list_sessions(HARA_WIN11): v0.3.45 ONLINE, recibos e zero sessões RUNNING.
2. Revisar a presença/visibilidade do console no Windows pelo próprio usuário. VM commander-win11 reside no Núcleo A, QEMU/KVM e QEMU Guest Agent disponíveis. O Guest Agent roda em SYSTEM e pode receber UnauthorizedAccess ao ler dados do perfil; usar tarefa temporária no usuário interativo apenas para INSPEÇÃO, não para aprovar.
3. No Núcleo A existem helpers TEMPORÁRIOS em /tmp_hara/hara_win11_operator_window_control_20261011.py: ações inspect e windows para leitura. Eles não são API estável e podem desaparecer; não executar close/launch a menos que comprovado necessário e sem aprovações pendentes. O caminho dos documentos canônicos é superior aos scripts temporários.
4. Pedir ao usuário que coloque a janela H.A.R.A. visível da VM **em primeiro plano** e confirme que está pronto ANTES do envio do comando. Assim o desafio de 30s não é desperdiçado.
5. Enviar UM comando inofensivo hostname pelo **MCP comercial H.A.R.A. Commander**. O usuário, se desejar, digita APROVAR seguido do desafio exibido, NA VM, dentro do prazo. Não pedir PIN/credenciais no chat. Conferir exit code 0, saída do host, execution_authority HARA_COMMANDER_AGENT e receipt. Se não houver aprovação, registrar DENIED/EXPIRED sem mutação; não repetir comandos de escrita cegamente.
6. Pedir uma segunda operação para o usuário NEGAR e confirmar recusa/ausência de efeito. Depois, sempre com autorização local para cada mutação, testar pasta/arquivo sintéticos, write, read, CAS correto e SHA obsoleto negado; process.start/output/interact/kill, várias linhas e retenção pós-exit, process.sessions. Remover fixtures apenas com aprovação.
7. Ensaiar reconnect/timeout sem duplicar comandos: IDs estáveis e reconciliação antes de novas chamadas. Windows Event V2 é outra RC; a VM comercial corrente usa relay/outbound, não afirmar WebSocket comercial homologado.
8. Publicar prova de aprovação positiva, recibos sem dados sensíveis, estado canário/rollback; só então discutir distribuição comercial pública.

### 5. Referências canônicas de código e evidência

- apps/commander/public/agent/windows.ps1 — fonte 0.3.45, aprovação individual, process manager, CAS e log metadata-only.
- apps/commander/src/worker.js — version gates por plataforma.
- apps/commander/release-bundles/commercial-0.3.45-v5-rc/ — release privada assinada.
- apps/commander/release-bundles/commercial-0.3.43-v3/ — release pública Windows anterior.
- apps/commander/scripts/commander_prelaunch_offline_gate.py — suíte agregada.
- apps/commander/scripts/validate_signed_windows_045_v5_rc.py — assinatura do release v5.
- apps/commander/scripts/validate_windows_045_privacy_contract.py.
- apps/commander/scripts/test_windows_044_capability_gate.mjs.
- docs/operations/HARA_COMMANDER_WINDOWS_045_PRIVACY_RC_20261011.md.
- docs/operations/HARA_COMMANDER_WIN45_OPERATOR_WINDOW_AND_CONSENT_20261011.md.
- docs/evidence/commander-win45-20261011/acceptance.json.
- docs/operations/HARA_COMMANDER_PTY_TERMINAL_DRAIN_FIX_20261011.md.
- docs/operations/HARA_COMMANDER_COMMERCIAL_1000_HARDENING_20261011.md.

No Desktop da VM existem HARA Commander - CONECTAR MANUALMENTE.cmd, HARA Commander - COMO APROVAR v0.3.45.txt e pasta de testes/Resultados. O Desktop do usuário pode estar redirecionado para OneDrive. Usar o procedimento de usuário real para homologação, não um processo SYSTEM nem o Desktop Commander para validar a cadeia MCP.

### 6. Pendências comerciais fora deste P0

- Binário nativo entre hosts: Linux passou via rsync/SSH para Núcleo/C/D com manifesto SHA, Unicode, symlink e retomada de 12 MiB. Falta ferramenta nativa independente de SSH entre clientes.
- Windows Event V2 WebSocket experimental e instalador RC precisam de conexões reais, reconexões, recibos, restart e clean install; não anunciar como PROD.
- Segundo tenant autenticado isolado e prova de autorização cruzada negada ainda pendentes.
- Mil clientes: modelos locais e 1.000 chamadas HTTP health NÃO certificam 1.000 Agents/tenants simultâneos; necessita rampa 10→100→250→1000, soak, custo Workers/D1/DO, idempotência e segurança.
- Stripe ainda sem cadastro bancário finalizado e sem fluxo LIVE; não bloquear beta técnico nem ativar billing fictício.
- Submissão OpenAI depende de business verification, demo isolada, vídeo, revisão e aprovação. Não afirmar homologação pública.

### 7. PRESERVAR outras frentes (Git worktree parcialmente sujo)

No status inspecionado ANTES do handoff já existiam alterações NÃO COMMITADAS que não pertencem a esta tarefa. Não adicionar, reverter ou deletar:
- apps/commander/candidate/install_windows_rc.ps1 (modificado)
- apps/commander/experimental/event_v2_windows_agent.ps1 (modificado)
- apps/commander/scripts/validate_windows_local_activity_store.py (modificado)
- docs/operations/HARA_COMMANDER_WINDOWS_044_APPROVAL_AND_PTY_RC_20261012.md (modificado)
- apps/commander/scripts/test_commander_commercial_readiness_gate.py (não rastreado)
- apps/commander/scripts/validate_event_v2_windows_ps51_compat.py (não rastreado)
- docs/evidence/commander-win44-canary-20261011/ (não rastreado).

São frentes paralelas e/ou testes incompletos. Proibido staging global git add -A, reset --hard, git clean, force-push e force-sync do Storage. Para publicar handoff: adicionar SOMENTE este documento e o ponteiro dentro de HARA_COMMANDER_CURRENT.md.

### 8. Critérios de encerramento

P0 Windows: ação individual aprovada manualmente com recibo real, outra negada sem efeito, prompt com timeout e visibilidade corretos, sem conteúdo privado em log persistente.

P1 Windows: arquivos/edição CAS e terminal interativo via MCP com aprovações distintas, reconexão/recuperação/rollback, Windows Event V2 homologado separadamente.

Beta comercial: instalador assinado final, segundo tenant isolado, documentação de suporte; depois escala e OpenAI/Stripe. **Não chamar produto comercial blindado antes dessas provas.**

**Resumindo:** Linux está pronto para operações canônicas do fundador. Windows canário 0.3.45 está online e lê informações pelo MCP, mas a confirmação humana POSITIVA é a prova ainda faltante. Não recomeçar do Desktop, não recriar identidade Windows e não mexer no Stripe nesta frente.
