# H.A.R.A. Commander — CURRENT (12/10/2026; Windows 49 real e aceite humano positivo, testes em curso)

**O primeiro aceite humano positivo pelo MCP foi comprovado no Windows 49.** A chamada própria de teste hostname, HARA-CALL-6843883f-641b-42e2-a7a1-45a94a3675c0, recebeu claim às 21:21:17.259Z e mostrou PASS local às 21:23:23Z. A imagem enviada pelo usuário mostrou a janela de 15 minutos e a confirmação ENVIADA. O resultado real retornou HARA_WIN11, exit0, sem timeout nem truncamento; recibo 4963b1d2f09e21f27f3507d38c3c62cdddb810462fd08adec30319ac2ddf8dd1. O hostname passou após cerca de 126 segundos, além da antiga janela de 30 segundos; esse teste não esperou os 900 segundos completos.

A leitura real de identificação confirmou Agent 0.3.49, recibo 1109873b28dff84dc1c673f8e8122e9f4d027fdc40b76412efbe5f47a47da2d0, e a listagem retornou zero sessões gerenciadas, recibo 349d01bc835b08fa953e88b3bfd8e650c3641dbff8c304d1c4150b5f85bb6670. A fonte ativa corresponde à assinada SHA 7b51d2f243228f27aaf742086fe012c73bc17cd8c180a4f9abbcb1e2c51f3080. **A origem da instalação permanece UNKNOWN**: os canários anteriores preservados não são prova de uma instalação feita por esta frente. Não se atribui instalação ao Root, SSH ou helper abortado.

A primeira leitura do resultado trouxe a saída; a leitura seguinte trouxe somente metadados com content_redacted=true, sem enfileirar nova chamada e com zero unidades adicionais. O plano Founder estava UNMETERED; esse resultado não valida cobrança ou escala de mil clientes. O watcher não enviou aviso e registrou READ_ONLY_ERROR_QGA_SAMPLE. O aceite observado pelo usuário e o resultado da chamada comprovam o sucesso deste hostname, sem declarar o monitor corrigido.

Evidência: **docs/evidence/commander-win49-approval15m-20261012/windows49-real-human-hostname-root-20261012.json**, SHA 714575b4540a5d81b623f50c3db3b22322a282b5dafadb9cfaed5ed8d9cf6bd0. Escrita CAS, terminal interativo e recuperação Windows continuam em testes; esta atualização não encerra a homologação do produto.

Backend 15min Worker 338e2b88-eae9-41b1-868d-947098fe68a3 e migração 0035 continuam implantados. O código permanece igual ao checkpoint 34c282b2e91c7ff5032fde5a73a7511d1fb012fc, CI 38303773972 SUCCESS /105. Fonte, manifesto e assinatura 49 congelados; downloads públicos 43-v3, held7 e StorageHOLD preservados. Stripe não foi alterado. Documento de operação: **docs/operations/HARA_COMMANDER_WINDOWS_049_APPROVAL15M_RC_20261012.md**.

## Registro anterior preservado — canário abortado e inspeção posterior

# H.A.R.A. Commander — CURRENT (12/10/2026; backend 15min implantado, canário 49 pendente)

Documento atual: **docs/operations/HARA_COMMANDER_WINDOWS_049_APPROVAL15M_RC_20261012.md**. O backend de chamadas de 15 minutos está implantado: Worker 338e2b88-eae9-41b1-868d-947098fe68a3 em 100%, migração 0035 aplicada e validação de health/auth/assets públicos 43 aprovada. A RC privada 49 está assinada e preparada; **instalação 49 e aprovação humana positiva continuam pendentes**.

As duas inspeções de canário, associadas aos controles d060 e85b, passaram. A tentativa Apply com controle 85b terminou em **CANARY_RUNTIME_FAILED** antes de backup, stop da tarefa, substituição de fonte ou launch. A causa original permanece **UNKNOWN**. Os flags de preservação não estabelecidos no Apply não demonstram alteração de configuração ou XML; a leitura posterior confirmou seus hashes intactos. Não houve aprovação automatizada.

A inspeção somente leitura às 20:40:18.053Z encontrou a tarefa **Ready**, zero processos-alvo e o marcador antigo de operador sem processo vivo. A fonte instalada continua 48, SHA f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805; configuração e XML da tarefa foram preservados. Esse snapshot de laboratório não comprova disponibilidade comercial atual, nem identifica quem encerrou a sessão antiga. O fixture de ACL privada passou no sandbox; esse resultado não identifica a causa da tentativa abortada. A próxima variante de instalação com a tarefa parada está em preparação, sem resultado de instalação nesta atualização.

Evidências sanitizadas em **docs/evidence/commander-win49-approval15m-20261012/**: dois Inspect, Apply, fixture ACL e inspeção pós-aborto. O controle Root R3 SHA 85b57e255187a1e9d00dc69047b03aabe52bf049b463dbb0ab95176244c5cc11 é histórico das 20:31, sem assumir freshness posterior. Os registros anteriores foram preservados.

O código permanece no checkpoint 34c282b2e91c7ff5032fde5a73a7511d1fb012fc, com CI 38303773972 **SUCCESS / 105 checks**. Fonte 49 SHA 7b51d2f243228f27aaf742086fe012c73bc17cd8c180a4f9abbcb1e2c51f3080 e manifesto d0f375fd95e1e7842abb566359cd8edf2f14c4d10853e844cf2c425d0f9d6124 continuam congelados. Este followup altera documentação e evidências. Os testes humanos de aceite positivo, CAS, terminal e recuperação seguem pendentes. Downloads públicos 43-v3, sete alterações de outra frente e StorageHOLD preservados.

## Registro anterior preservado — rollout do backend e preparação do canário

# H.A.R.A. Commander — CURRENT (12/10/2026; canário49 assinado e preparado, runtime48, aceite humano pendente)

Documento atual: **docs/operations/HARA_COMMANDER_WINDOWS_049_APPROVAL15M_RC_20261012.md**. O pedido de15 minutos por ação foi implementado na RC privada49 com prazo900s, texto completo+Enter e heartbeat durante a espera, mantendo ASK_EVERY_ACTION. Fonte7b51d2f243228f27aaf742086fe012c73bc17cd8c180a4f9abbcb1e2c51f3080; manifesto d0f375fd95e1e7842abb566359cd8edf2f14c4d10853e844cf2c425d0f9d6124; assinatura RS256/RSA3072/v2 autenticada também no PS5.1. Bundle privado49-v9 congelado; Linux e63 arquivos de bundles históricos preservados.

Validação Windows:227 checks nativos na fonte final+parser,232 regressões na fonte anterior1e32 e prova AST de70 funções com somente um literal de mensagem alterado. Guards17+32+13 PASS. Backend15min integrado:55 checks específicos PASS, migração0035 aditiva e acompanhamento por handleHARA-CALL. Gate integrado **105/105 PASS**, exit0 em37,602s, peak_child_RSS143692KiB e stderr vazio. A primeira execução104/105 foi preservada. O validador legado foi atualizado para29 binds de enqueue/5 de claim e schema35, conservando seis cenários de concorrência e acrescentando a corrida real de900s. Fonte/Worker/bundle ficaram congelados; dependências temporárias removidas.

**BACKEND_DEPLOYED / CANARY_VM_PENDING:** migração0035 aplicada e nenhuma migração pendente no readback. Worker338e2b88-eae9-41b1-868d-947098fe68a3 em100%; health/auth,12/12 assets e8/8 arquivos assinados43-v3 PASS, além de duas leituras Linux diretas. Evidência production-validation.json SHAefdae1d9603121d4d4c2a4ab049b4ddca57eb64b383d6e901c3552930939bdd5. Agent49 ainda não instalado. A VM continua na48; não enviar nova mutação com a janela antiga de30s. Aprovação humana positiva, escrita CAS, terminal e recuperação Windows continuam PENDENTES. Não houve entrada de aprovação automatizada. PublicHTTP Agent/install/manifest43-v3 permanecem byte-idênticos à distribuição assinada, sem promover49 como download padrão. StorageHOLD e outras frentes preservados; Checkpoint de código34c282b2e91c7ff5032fde5a73a7511d1fb012fc publicado, CI38303773972 SUCCESS com105/105. Recibos reais de rollout seguem nesta continuidade.

## Registro anterior preservado — preparação de15min

# H.A.R.A. Commander — CURRENT (12/10/2026, 18:46 UTC; aprovação de 15 minutos IN_PROGRESS, ainda não instalada)

O usuário pediu explicitamente **15 minutos por ação** após a última tentativa na janela de 30 segundos. Esse pedido orienta a próxima RC privada .49; Agent e tempo de vida da chamada no relay precisam ser alinhados antes do novo canário. **A .49 ainda não foi instalada nem assinada nesta preparação.** A última fonte Windows confirmada continua a .48, SHA `f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805`. Não enviar outra mutação usando o prazo antigo.

A última chamada .48, `6a180fa6-d8d4-4605-baef-9c008cf1dd34`, foi criada às18:44:14.400Z, recebeu claim às18:44:23.663Z e terminou às18:44:54.285Z com **LOCAL_ACTION_APPROVAL_EXPIRED**. Resultado MCP DENIED, metadados FAILED e mutation_performed=false; **não houve aceite humano positivo nem execução do hostname**. O pré-aviso no Desktop teve processo exit0 (receipt `aba499d5de938c430907198a69b9a09c99b105a99308590f41e36ba9f66e45bc`), mas isso não comprova que o usuário viu o aviso. A notificação vinculada ao claim ficou null/não enviada.

O laboratório comprovou a falha do watcher: File.Replace com backup null é rejeitado no PowerShell5.1 depois da primeira gravação. O R3 usa backup próprio, leitor com FileShare.Delete, tentativas de escrita e rejeição de amostras vencidas/observador parado. O controle negativo e as escritas concorrentes passaram; preflight de7,28s produziu5 amostras frescas. Isso corrige o monitor no laboratório, sem provar pedido ativo, aviso entregue ou aceite positivo. R1/R2 e watcher original preservados.

Evidência: `docs/evidence/commander-win48-startup-20261012/windows48-final-short-approval-window-attempt.json`, SHA `64a567881d773c9560bdc7dd0a9f7880fd1f19609f13e1048ae53cd626136e0c`. Os testes de aceite positivo, escrita CAS, terminal e recuperação Windows permanecem pendentes. A correção do estado de expiração no Worker passou36/36 e gate98/98 em código, sem deploy; o checkpoint publicado continua3b4 com CI97/97. A continuidade está preservada na worktree48 e aguarda integração/revisão/testes49 antes da publicação. Downloads públicos .43-v3 e StorageHOLD mantidos.

## Registro anterior preservado — continuidade até as 18:33 UTC

# H.A.R.A. Commander — CURRENT (12/10/2026, 18:33 UTC; Windows 0.3.48 online, aprovação positiva pendente)

Documento atual: **docs/operations/HARA_COMMANDER_WINDOWS_048_STARTUP_RC_20261012.md**. A RC privada .48 continua com fonte assinada SHA `f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805`. O checkpoint publicado é `3b4f791147be54919727628e9c577963af030e3f`, com GitHub Actions **38284856240 SUCCESS / gate 97/97**. As 232 verificações Windows e a correção de StartTime são evidência de regressão; aprovação humana positiva pelo MCP permanece pendente.

Após a abertura manual das 17:23, o consumidor4896 deixou de existir e a tarefa passou a Ready com resultado `0xC000013A`; a causa da interrupção continua **UNKNOWN**. O operador8184 e seu início exato foram preservados. A retomada autorizada executou somente Start-ScheduledTask na tarefa existente, criando consumidor6456 às18:05:45.293Z. Inspeção independente às18:07:22 confirmou tarefa Running e ambos os processos com PID/início exatos, sem alterar fonte/configuração/XML/ASK, sem gerar aprovação ou nova chamada.

Duas tentativas reais tiveram resultados distintos:

- A chamada `894f394e-0ddc-437b-8310-7a642b248812`, criada às17:37:10.999Z, permaneceu **sem claim** e expirou às18:17:39.297Z com DEVICE_CALL_EXPIRED.
- A chamada nova `ab023a25-91c2-4fdb-b74a-8c59ff405fe5`, criada às18:29:37.022Z, recebeu claim às18:29:42.096Z e terminou às18:30:13.058Z com **LOCAL_ACTION_APPROVAL_EXPIRED**: DENIED no MCP, FAILED nos metadados, mutation_performed=false. O comando não foi executado.

O watcher de SHA `aee1c0c53e8e0e5ab2ad3c7ff647ce6ee47a9bd78a94c75c84482a86b4504042` retornou pending_active=false e notification_sent=false durante essa tentativa. **Falha do monitor em investigação**, sem prova de aviso entregue ou foco da janela. Nenhuma resposta de aprovação foi automatizada. Após a tentativa, device.info direto confirmou Agent .48 (receipt `ec5235322dafca6c0f0d126e31c6192f828aeb3c9e607bc7c98e1d4ae20891ef`) e process.sessions confirmou count0. Evidência: `docs/evidence/commander-win48-startup-20261012/windows48-fresh-hostname-expired-watch-miss.json`, SHA `aecf4205c604a8c7371a28e3f47371d7a14ce01b750b28c7cb763f3547384fa6`.

Correção de fonte do Worker integrada nesta continuidade, **sem deploy**: a listagem recent projeta EXPIRED ao vencer o prazo e preserva persisted_state, claim e resultado. Testes reais da função/consulta36/36 e gate offline98/98 PASS; o CI publicado de3b4 permanece97/97. Expiração de EXECUTING não comprova ausência de execução nem autoriza repetição automática. Ver **docs/operations/HARA_COMMANDER_RECENT_CALL_EXPIRY_PROJECTION_20261012.md**. Agent/bundle48 continuam byte-idênticos.

**Pendentes:** aceite humano positivo e execução, escrita protegida por SHA-256, terminal interativo e recuperação Windows pelo H.A.R.A. Commander direto. ASK_EVERY_ACTION e prazo30s preservados. Os novos registros são continuidade em trabalho; ainda não publicados. Downloads públicos .43-v3, patch Linux de presença sem instalação, Stripe, escala real e Storage mantêm os limites registrados abaixo.

## Registro anterior preservado — leitura e instalação das 17:24 UTC

# H.A.R.A. Commander — CURRENT (12/10/2026; Windows 0.3.48 instalada, acesso direto confirmado)

Documento atual: **docs/operations/HARA_COMMANDER_WINDOWS_048_STARTUP_RC_20261012.md**. A falha de abertura mostrada na imagem (`InvokeMethodOnNull` por StartTime indisponível) foi corrigida na .48, preservando PID e início exatos da sessão. **232 verificações Windows passaram** (68 abertura, 111 consentimento, 26 recusa, 27 retomada), além do controle negativo .47 e do **gate offline 97/97**. RC privada v8 assinada, fonte SHA `f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805`.

Canário InstallOnly aplicado às 17:21 UTC, com preimagens e configuração/XML da tarefa preservados. Tentativas com metadados vencidos abortaram sem trocar a .47. O usuário abriu manualmente o botão **Abrir_HARA_Commander.cmd** no Desktop às 17:23; operador e consumidor vivos, tarefa Running e fonte .48 confirmados independentemente. Não houve mudança de ASK_EVERY_ACTION nem aprovação automatizada.

**H.A.R.A. Commander direto**: device.info PASS/Agent .48, receipt `37c611aa98f5c2052f0c41a498e5f91ff13885b14402efa7fe777f705a25223a`; process.sessions PASS/count0, receipt `84c0feeaffdfa757fc26e64f9548a851233a005fc9d9f5ea51157f8d01a0364b`. Aprovação humana positiva, escrita CAS e terminal interativo Windows pelo MCP permanecem pendentes. O aviso GNOME foi pré-validado; o primeiro monitor QGASYSTEM falhou por metadados indisponíveis e não enviou notificação. Monitor em contexto do usuário em preparação.

Frota Linux: 7/7 responderam às 16:40 UTC; seis .46/EVENT_V2, B .41/OUTBOUND_RELAY. Terminal B passou 120 linhas, UTF-8, paginação e exit0. Limite de linhas inicial de sessões gerenciadas é ignorado pelo mapeamento atual; registrado como melhoria pendente. Patch Linux de presença passou 34 verificações e conserva prazo entre reconexões do processo vivo; ainda não instalado no runtime.

Downloads Windows públicos seguem .43-v3. Stripe, escala real de mil clientes e limites de presença após restart não foram homologados nesta frente. Baseline não foi usado para as provas desta continuidade. Outras frentes e Storage preservados.

## Registro anterior preservado

# H.A.R.A. Commander — CURRENT (12/10/2026, 16:30 UTC; Windows .47 com falha de abertura, correção .48 em testes)

Documento atual: **docs/operations/HARA_COMMANDER_WINDOWS_047_LIFECYCLE_RC_20261012.md**. A RC privada .47 foi instalada na VM com fonte assinada e configuração/tarefa preservadas. Consentimento PS5.1 **111/111**, recusa integral **26/26**, retomada **17/17**, corridas **27/27**. Gate completo após patch de presença Linux: **94/94 PASS**.

A imagem real do usuário revelou `InvokeMethodOnNull` na recuperação de sessão: `Get-OperatorSession` dereferencia StartTime indisponível. A .48 está em preparação com descarte seguro de metadados ausentes/inválidos, mantendo PID e início exatos. **Windows ainda não homologado pelo MCP mutante com aceite humano positivo.** O último hostname .46 expirou às 15:59:09Z. Interrupção do consumidor .47 às16:10 (`0xC000013A`) continua sem causa comprovada.

A VM foi ligada e o viewer aberto a pedido do usuário. Foram criados no Desktop Windows `HARA_Commander_Abrir_047.cmd` e instruções da frase completa de aprovação. O CMD aponta ao caminho instalado e dispensa clipboard. Não foi automatizado aceite local; `ASK_EVERY_ACTION` e 30s permanecem.

Services respondeu novamente via H.A.R.A. Commander direto às16:25 com heartbeat normal, sem restart. O patch de reconexão Linux conserva o prazo do processo vivo, com **6 cenários/34 checks** e controle negativo; ainda não instalado no runtime. Reinício do processo e ausência de ACKD1 continuam limites documentados.

Somente **H.A.R.A. Commander direto**, não Baseline, conta como prova comercial. Downloads Windows públicos permanecem .43-v3. Stripe e escala de mil clientes continuam independentes/pendentes. Arquivos de outras frentes e releases históricas foram preservados.

## Registro anterior preservado

# H.A.R.A. Commander — CURRENT (12/10/2026, Windows canário 0.3.46; aceite humano pendente)

## Windows 0.3.46-v6 — expiração corrigida, canário privado aplicado

Documento atual: **docs/operations/HARA_COMMANDER_WINDOWS_046_EXPIRY_RC_20261012.md**. Fonte e RC assinada: `71998b7c5e2dae4f4cbcfe80e5413ab1c6ff8e28ad903734cc1f026dfe8765aa`. **93/93 regressões no Windows PowerShell 5.1 real e 91/91 no gate completo offline.** A janela não bloqueia após deadline; publicação, consumo, limpeza e revogação de sessão foram endurecidos. `ASK_EVERY_ACTION` e prazo de 30 segundos permanecem.

Canário da VM atualizado de 0.3.45 para **0.3.46 assinada**, com backup verificado, identidade/configuração e definição da tarefa preservadas. `device.info` e `process.sessions` pelo **H.A.R.A. Commander direto** PASS, zero sessões. Uma chamada real `hostname` expirou sem aceite; inspeção pós-timeout comprovou pedido/resposta limpos, operador ativo e tarefa Running. **Visibilidade/foco da janela e aprovação humana positiva continuam pendentes**, assim como escrita/terminal Windows mutantes via MCP. Nenhuma aprovação foi automatizada.

A RC v6 é privada: esta frente não promoveu downloads Cloudflare nem mudou Stripe. Releases históricas e Linux preservados. Os testes Linux diretos de interação/120 linhas pós-exit/UTF-8/CAS correto e obsoleto passaram. A listagem direta marcou C e Ninja Blue com canal OFFLINE, sem inferir energia do host ou reiniciar máquinas. Alterações das outras frentes foram preservadas.

O handoff 0.3.45 abaixo é histórico para a versão Windows; procedimentos de autorização e pendências comerciais continuam relevantes. Não tratar suas versões antigas como runtime atual.

## Handoff para próxima frente — GitHub e canário Windows (11/10/2026)

Documento de continuidade consolidado: **docs/handoffs/HARA_COMMANDER_WIN45_CONSENT_COMMERCIAL_HANDOFF_20261011.md**. Ele contém status live da frota, Worker DEV/PROD, releases assinadas, GitHub e CI, provas e limitações do Windows, procedimentos de consentimento humano e de teste E2E, riscos de UX/Read-Host, entregas pendentes de escala/Stripe/OpenAI e arquivos das outras frentes que devem ser preservados.

**Resumo autoritativo:** Linux Founder 7/7 ONLINE em 0.3.46; HARA_WIN11 ONLINE em 0.3.45 assinada, leitura e process.sessions com recibos. Aprovação local positiva de hostname/escrita/sessão pelo MCP ainda **HOLD**; duas tentativas expiraram sem execução. Console do operador permanece ativo, janela H.A.R.A. detectada como visível, mas foco no viewer não comprovado. Nenhum modo de aprovação foi relaxado e não houve deploy adicional nesta atualização documental. A frente seguinte deve começar pelo handoff, não por versões históricas abaixo.



## Operador Windows: janela anterior encerrada, nova sessão visível (11/10/2026)

A sessão obsoleta do operador da VM `commander-win11` foi encerrada por processo-alvo verificado e a marcação obsoleta removida depois da saída. Uma nova sessão foi iniciada no usuário local, com título `H.A.R.A. Commander 0.3.45 - APROVACAO LOCAL`, janela visível pela enumeração de janelas do próprio Windows; não é garantia de estar em primeiro plano no viewer. O Agent permanece ONLINE em 0.3.45, Linux 7/7 em 0.3.46, sem alteração de identidade ou `ASK_EVERY_ACTION`. Duas tentativas sintéticas `hostname` pelo MCP real **expiraram por falta de confirmação no console** (`LOCAL_ACTION_APPROVAL_EXPIRED`), sem execução. O último prompt expirado foi limpo por reinício controlado somente do console do operador. **Aprovação humana positiva AINDA NÃO realizada.**

Próximo teste exige que o usuário já esteja com essa janela em primeiro plano, antes de a frente enviar a chamada (janela de 30s para digitar `APROVAR <desafio>`). Não contornar a aprovação por ferramentas auxiliares. A tentativa de trazer a janela automaticamente ao primeiro plano foi bloqueada pela plataforma. Corrigir posteriormente UX de `Read-Host` bloqueante e expiração. Evidência: `docs/operations/HARA_COMMANDER_WIN45_OPERATOR_WINDOW_AND_CONSENT_20261011.md`.



## Estado autoritativo Windows — homologação de privacidade 0.3.45-v5

O dispositivo `HARA_WIN11` **está ONLINE com Agent assinado 0.3.45**, atualizado a partir da 0.3.44 no usuário real da VM com configuração byte-idêntica, tarefa restaurada e backup da 0.3.44 preservado. `ping`, `device.info` e `process.sessions` passaram via MCP com recibos. A tentativa histórica de `hostname` na 0.3.44 **não foi executada** devido a `LOCAL_ACTION_APPROVAL_EXPIRED` após 22s. A 0.3.45 amplia o prazo a 30s, mantendo `ASK_EVERY_ACTION`, mas ainda sem prova humana positiva.

Um ensaio sintético no Windows 11 identificou que o log local da 0.3.44 persistia prévia de comandos e caminhos privados apesar de `payload_values_exposed=false`. **A 0.3.45-v5 RC assinada corrige isso**, mantendo metadados e a prévia apenas no consentimento transitório, ampliando a janela a 30s. Windows PowerShell 5.1 validou os bytes assinados, SHA, parser e autoteste; a prova de log privado saiu de TRUE para FALSE e os 15/15 testes de recusa/nonce/timeout passaram. Gate local ampliado **89/89 PASS**. As releases v4/v3 e componentes Linux continuam preservados.

A 0.3.45 está **instalada somente na VM canário, não distribuída ao público**, e o GitHub Actions `38191514098` passou no commit `a6d27e8` (89/89). Foi deixado no Desktop o arquivo `HARA Commander - COMO APROVAR v0.3.45.txt`; a janela antiga já foi encerrada e a nova sessão aberta. Basta selecionar a janela visível do H.A.R.A. na VM para a próxima prova. Aprovação humana positiva, comandos mutantes e terminal interativo E2E pelo MCP ainda pendentes. Logs históricos anteriores não foram apagados. Veja `docs/operations/HARA_COMMANDER_WINDOWS_045_PRIVACY_RC_20261011.md` e `docs/evidence/commander-win45-20261011/acceptance.json`.

## Histórico anterior (v4/v3) — não usar como status atual



## Windows local ASK_EVERY_ACTION + terminal gerenciado — RC candidato

O Windows `HARA_WIN11` está **ONLINE no MCP com Agent 0.3.43**, e operações READ_ONLY (ping/info, processos, listagem e leitura de arquivo) foram comprovadas por recibo. Mutações neste Agent v3 retornam `WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED` e sessões PTY `AGENT_UPGRADE_REQUIRED`.

A versão **0.3.44-v4 RC**, ainda NÃO implantada na identidade registrada nem distribuída ao público, inclui aprovação individual efetiva na janela local do operador (nonce, request_id, SHA dos argumentos e timeout 22s, sem alterar approval_mode), arquivos com CAS/atomic replace/reparse-deny e sessões PowerShell gerenciadas (8 processos, 5.000 linhas, 2 MiB, TTL 15min). No Windows 11 isolado: parser e selftest PASS, default sem sessão negou mutações, sessão .NET 120/120 linhas, segunda instrução interativa, ensaio 7.000 linhas com truncamento correto e gravação CAS PASS. Worker só libera ferramentas de sessão para Windows Agent >=0.3.44. Fonte de segurança 20 checks PASS; contrato de ferramentas 37/37 PASS; release RS256 v4 autenticou os quatro arquivos com Linux byte-idêntico a v3; gate total 87/87 PASS LOCAL. **Aprovação positiva por humano e execução E2E v4 pelo MCP ainda pendentes.** Não promover publicamente antes do canário. Relatório: `docs/operations/HARA_COMMANDER_WINDOWS_044_APPROVAL_AND_PTY_RC_20261012.md`.



## Windows updater 0.3.43-v3 — DEV/PROD homologados

CI GitHub run **38185936537 PASS**, 84/84 testes offline no commit `a1d5f72`. O instalador Windows assinado v3, com a correção do sufixo `.update.ps1`, está publicado em DEV (Worker `aaa289cc…`) e PROD (Worker `e5544ad6…`), 100% em ambos, 9/9 assets exatos, saúde/autenticação PASS e drift PROD `CURRENT`. A VM Windows 11 executou a atualização real `0.3.14 → 0.3.43` como usuário logado, preservou a configuração byte a byte e o backup; depois baixou o instalador v3 público e passou no preflight RS256. Os 7 Agents Founder Linux continuam online em 0.3.46.

**HARA_WIN11 ainda aparece OFFLINE** no MCP; falta o usuário iniciar a sessão autorizada localmente. Foi preparado no Desktop público `HARA Commander - CONECTAR MANUALMENTE.cmd`, não executado automaticamente. O AtLogOn legado da tarefa foi preservado, sem troca silenciosa de política. Não declarar paridade de comandos Windows até obter recibos de execução reais. Evidências em `docs/operations/HARA_COMMANDER_WINDOWS_UPDATER_V3_20261011.md` e `docs/evidence/commander-windows-updater-v3-20261011/acceptance.json`. Stripe e D1 inalterados.



## Atualização comercial Windows — v3 verificada na VM

Hotfix `commercial-0.3.43-v3` assinado RS256, preservando todos os Agents e o instalador Linux v2 (byte-idênticos). A única alteração assinada é corrigir o sufixo temporário Windows de `.ps1.update` para `.update.ps1`. Teste real como usuário logado no Windows 11: Agent `0.3.14 → 0.3.43` **PASS**, assinatura SHA PASS, configuração de dispositivo idêntica byte a byte, backup do Agent antigo preservado, tarefa permaneceu `Ready`, sem re-pareamento, sem exibir token. Novo validador v3 e staging canônico PASS; gate offline local **84/84 PASS**. O dispositivo `HARA_WIN11` continua **OFFLINE** pelo MCP após atualização: falta sessão de operador iniciada localmente e homologação E2E; tarefa antiga contém trigger AtLogOn legado que não foi alterado. CI hospedado e deploy DEV/PROD do hotfix devem ser confirmados separadamente. Evidência: `docs/operations/HARA_COMMANDER_WINDOWS_UPDATER_V3_20261011.md` e `docs/evidence/commander-windows-updater-v3-20261011/acceptance.json`.



## Hardening comercial / 1.000 clientes — 11/10/2026

Founder Linux 0.3.46 7/7 ONLINE; atividade MCP das últimas 24h verificada em 7 dispositivos Event V2, mas não certifica 1.000 tenants. Windows comercial em POLL_V1 0.3.43; adaptador Event V2 Windows é RC de fonte DEV-only, não homologado em Windows real. Validadores Windows RC source/installer passaram, sem PowerShell dinâmico no Services; local activity store reportou MANIFEST_VERSION=FAIL. Nova ferramenta opcional de acompanhamento de evidências (commander_commercial_readiness_gate.py) indica Founder PASS, Commercial Beta HOLD e GA HOLD; ainda não é gate de deploy/CI. O teste candidato da ferramenta está com expectativa incorreta e não foi publicado. Ver docs/operations/HARA_COMMANDER_COMMERCIAL_1000_HARDENING_20261011.md. Stripe permanece desconectado, não condiciona beta técnico. Não confundir modelos 1k/10k e 1000 HTTP health com mil clientes simultâneos.


## Autoritativo — correção P0 terminal validada na frota Linux Founder

O fechamento prematuro da PTY após waitpid foi corrigido: drenagem não bloqueante antes de close, limite de 4 MiB/250 ms, retenção de 2 MiB/5.000 linhas. Regressão PTY real **19/19 PASS**, gate offline completo **83/83 PASS** e GitHub Actions run **38180317904 SUCCESS** na fonte `0f337dd5c41413ad4f37e1a5fd28f78a244acc90`. Release **0.3.46 RS256** assinada por dispositivo; todos os sete Linux Founder online em **0.3.46**, confirmados pelo MCP real. Teste pós-exit **120/120 linhas em cada uma das 7 máquinas**, exit=0 e sem truncamento; quatro sessões concorrentes no Services **480/480 linhas** e Unicode **40/40**. Rollback 0.3.45 preservado por host; nenhuma máquina ou app CSOTN reiniciados. P0 `PTY_OUTPUT_LOST_ON_EXIT` **CLOSED_PASS**.

A seção abaixo documenta a evidência histórica de 0.3.45, anterior à correção. Não reabrir P0 por confusão de datas. Ainda pendentes, separadamente: ferramenta binária inter-host nativa, Windows, recuperação/soak multitenant e billing Stripe. Evidências: `docs/operations/HARA_COMMANDER_PTY_TERMINAL_DRAIN_FIX_20261011.md` e `docs/evidence/commander-pty-drain-20261011/acceptance.json`.


## Prova real sem Desktop — transferência, recuperação e stdout pendente (11/10/2026)

Na frente de substituição do Desktop, o MCP comercial executou as provas em diretórios descartáveis: transferência de 32 arquivos e 12.842.112 bytes (inclui binário 12 MiB, Unicode, symlink interno) do Services para Núcleo, C e D, **3/3 destinos com manifesto SHA-256 PASS**. A Sentinela D retomou após interrupção intencional aos 720.896 bytes; SHA final PASS. Transmissão grande usou rsync/SSH sob comandos governados do H.A.R.A., não uma ferramenta de transferência binária nativa. O MCP nativo transferiu manifesto de texto, e hara.files.copy local validou binário 1 MiB; há limite nativo de cópia local 2 MiB.

Uma parada controlada do Agent da Sentinela A resultou DEVICE_OFFLINE e recuperação por outro Agent (Services) via SSH, sem Desktop. Tarefa independente em systemd user preservou 25/25 checkpoints após restart do Agent. **BLOQUEADOR P0 (histórico da 0.3.45, resolvido na 0.3.46):** sessão PTY que imprimiu 120 linhas registradas em arquivo retornou 0/120 no MCP após exit=0 e sem flag de truncamento; reprodução menor 8/25. Possível fechamento prematuro do FD no _process_update_state antes de drenar. Tentativa de gravar teste de código foi bloqueada pela segurança da plataforma, sem contorno; nenhuma mudança de Agent ou release nesta rodada. Prova e critérios: docs/operations/HARA_COMMANDER_DESKTOP_PARITY_RUNTIME_PROOF_20261011.md.

O P0 da saída do terminal foi resolvido na 0.3.46. Não declarar paridade completa até homologar transferência binária inter-host nativa, socket-recovery e soak. Stripe e pagamento permanecem independentes.

## CI 81/81 e persistência boot Founder — 11/10/2026

GitHub CI run 38175694137 PASS no código Stripe-free 7ee4686, 81/81 suítes. Agent V2 Founder Sentinelas C/D habilitado para auto-start (sem mudança de PID e sem ativação do guard para preservar workloads). 7/7 Agent 0.3.45 online. Stripe não configurado, pagamento não testado. Evidências: docs/evidence/commander-stripe-free-validation-20261011/summary.json.


## Beta técnico independente de Stripe — 11/10/2026

Frota Linux Founder 7/7 Agent 0.3.45 ONLINE; H.A.R.A. comercial confirmou 14/14 pings em duas ondas, 7/7 execuções remotas hostname com exit=0 e recibos. Portal protegido de cache/resposta antiga após logout/troca de sessão, deploy DEV/PROD confirmado e CI no runtime 5270796 PASS (run 38175333829). Nova suíte de 13 cenários garante que sem as credenciais Stripe, billing continua fail-closed, o Founder/Free permanece tecnicamente operável e nenhum checkout externo é iniciado. Gate agora 81/81 PASS LOCAL. Modelos 1k/10k e reconnect PASS locais, sem homologação real de 1000 clientes. OpenAI review exige conta demo, vídeo, verificação de negócio e avaliação específica de execução local; Stripe bancário não foi acessado. Docs: docs/operations/HARA_COMMANDER_STRIPE_INDEPENDENT_VALIDATION_20261011.md e docs/evidence/commander-stripe-free-validation-20261011/summary.json.


## Isolamento de sessão para 1k — 11/10/2026 (sem Stripe)

Corrigida corrida de logout/troca de sessão em bootstrap, identidade, dispositivos, dashboard e billing do portal. Respostas anteriores agora não repovoam dados depois de um novo contexto; pedidos antigos são invalidados na saída da sessão. Prova reproduzida antes 3/11 PASS (8 falhas) e depois 14/14 PASS; regressão de atividade 25/25, gate geral local 80/80 PASS. Visual aprovado e Stripe inalterados. A prova é por aba, não substitui isolamento entre tenants no backend; a homologação de 1.000 clientes reais continua pendente. Doc: docs/operations/HARA_COMMANDER_PORTAL_SESSION_ISOLATION_20261011.md.


## CI hospedado e custo de referência (11/10/2026)

OpenAI review ZIP 0.2.0 validado; CI hospedado GitHub Actions run 38173368104 PASS no commit a4b0cca (79 suites offline). Auditoria read-only Cloudflare na janela 19:28-20:28 UTC observou subtotal variável de referência US$ 0.0033500826176; NÂO fatura, sem franquias nem mensalidade, sem capacidade 1k comprovada. Stripe produção ainda pendente de três configurações secretas, necessitando chave sk_test no wizard TEST em Services. Provas sanitizadas em docs/evidence/commander-golive-20261011/.

## Pacote OpenAI atualizado, gate 79/79 (11/10/2026)

Plugin submission ZIP 0.2.0 sob apps/commander/plugin-submission, com notas de release e dados técnicos compatíveis com 33 ferramentas. Validação offline de pacote PASS; gate ampliado 79/79 PASS no Services. Continua DRAFT não submetido, sem demo vídeo/credenciais de revisor/verificação empresarial. Evidências em docs/evidence/commander-golive-20261011/acceptance.json.

## Fechamento Founder 7/7 e entrada comercial (11/10/2026)

Sete Linux Founder online no Agent Event V2 0.3.45 via readback MCP comercial, com contratos/autorização preservados e pacote antigo de rollback por máquina. Provas comerciais Founder: write/edit com hash esperado, hash obsoleto negado, leitura, execução e REPL interativa, recibos do Agent. Novo smoke HTTP DEV 1.000 GET de health/50 concorrentes máximo, 0 erro (NAO representa 1.000 clientes OAuth/Agents). Validação de escopo/ZIP OpenAI 33 tools, 5 positivos/3 negativos: SOURCE_PACKAGE_PASS, nao submissão. Billing PROD catálogo STANDARD BRL80/mes e TRIAL 10k, mas tres segredos Stripe PENDING e zero eventos. Gate local 79/79 PASS, CI hospedado aguardando readback. Referência: docs/operations/HARA_COMMANDER_GO_LIVE_READINESS_20261011.md e docs/evidence/commander-golive-20261011/acceptance.json.


## Atualização efetiva da telemetria Event V2 — 11/10/2026

Runtime 93ebcf0 publicado em DEV/PROD com D1 0034, Workers DEV 15801b6f-6ec2-40e9-8508-2f1d578824df e PROD 3b926608-cff0-4dfb-947f-6ff3099cbe3f, ambos 100%; health/auth PASS. O Agent Founder 0.3.45 (RS256, sete arquivos) está instalado/ativo no services, com persistência local SQLite 0600 comprovada por reinício controlado; outros seis Founders permanecem 0.3.44, pacotes não instalados. LIVENESS cloud ~6h sem requisições HTTP adicionais; snapshots D1 ainda vazios no readback, e não significa falha antes do primeiro checkpoint. Gate local 77/77 PASS; GitHub Actions hospedado PASS no commit 1aec24c, run 38171345712, depois de corrigir limpeza do wrapper Linux no uninstall. Referência: docs/operations/HARA_COMMANDER_EVENT_V2_LOCAL_TELEMETRY_LOW_CHATTER_20261011.md.


## Event V2 telemetria local e menos leituras — 11/10/2026

O Agent candidato grava métricas agregadas em SQLite 0600 por sete dias, com flush em lotes e resumo piggyback no LIVENESS Event V2 existente (~6h com jitter). Sem novos POST/polling de telemetria. D1 salva último resumo por tenant/dispositivo com migração 0034, schema estrito e socket autenticado. MCP adiciona get_device_telemetry (perfil 33 ferramentas). Polling de chamadas adaptativo: modelo 45s 180 para 36 consultas, não medição cloud. Gate offline 77/77 PASS; assinatura Founder 0.3.45 (sete arquivos) verificada, canário Services preparado. Não inferir instalação do Agent nem registro de snapshot D1 antes do canário. Referência: docs/operations/HARA_COMMANDER_EVENT_V2_LOCAL_TELEMETRY_LOW_CHATTER_20261011.md.


## PROD administrativo oficial — 11/10/2026

Código funcional implantado: commit `605ffdad230e34c0f5acc09dd3bcc361a1c11618`. Perfil MCP simples: **32 ferramentas**, incluindo novas primitivas READ_ONLY de uptime, recursos, workspace, SHA-256 e diff; processos, sessões, arquivos, rollback, atividade e recibos continuam disponíveis e governados. Gate local **73/73 PASS**.

Cloudflare DEV: Worker `3ff8b6b0-28f0-4cbc-b8be-2f571bbdaf63` 100%, migração aditiva `0033_portal_read_indexes_20261011.sql` aplicada, health/auth HTTP 200. PROD: Worker `ecbd82d8-6780-4605-8eed-17d844ab3415` 100%, a mesma migração aplicada, health/auth PASS. Assets comerciais assinados 0.3.43-v2 preservados no stage; sem alteração de preços ou agentes assinados.

Frota Founder Linux após PROD e reconciliação por resultados canônicos do Agent: **7/7 ONLINE, Agent 0.3.44** (`nucleo-a`, `sentinela-a/b/c/d`, `ninja-blue`, `services`). Núcleo teve o Agent V2/guard reabilitados; v1 permanece disabled. Sentinela A recebeu wake pela rotina canônica e retornou; Ninja retornou e respondeu pelo produto embora não conste no wake-map canônico. Registros Windows legados permanecem offline/revogados e não integram esta homologação.

O conector já aberto nesta conversa pode manter o schema antigo de ferramentas em cache; novas sessões/conexões devem descobrir as 32 ferramentas do Worker publicado.


## Perfil administrativo ampliado — 11/10/2026

O perfil MCP simples passa de 27 para **32 ferramentas**, adicionando uptime, recursos, inspeção de workspace, hash e diff como primitivas READ_ONLY. Processos e mutações de arquivo já existiam e permanecem governados. Gate local **73/73 PASS**. Documento: `docs/operations/HARA_COMMANDER_ADMIN_PROFILE_20261011.md`.


## Regressão unificada — 11/10/2026; publicação pendente

Worker REAL corrigido: hash esperado e paginação preservados; teste padrão **38/38 PASS**, gate **72/72 PASS**. Candidatas em memória e bloqueios do patch citados abaixo são históricos. Não inferir deploy do commit. Referência: `docs/operations/HARA_COMMANDER_RELEASE_VALIDATION_20261011.md`.


## Consistência dos resultados MCP — 11/10/2026; fonte local, sem deploy

O perfil simples passou a sinalizar erros operacionais com `isError: true`, distinguir timeout de não execução, orientar reconciliação em vez de repetição automática, restringir mensagens públicas de exceção a códigos simbólicos e separar trecho de edição ausente de arquivo ausente. Teste novo contra o handler MCP real, executor simulado no Services: **38/38 PASS**; suíte anterior do perfil simples também PASS. Não confundir este teste com os 38 casos da cadeia de argumentos abaixo. A bateria geral não foi reexecutada e o Worker não foi alterado. Contrato de timeout com valores nulos exige homologação do cliente antes de promoção. Documento: `docs/operations/HARA_COMMANDER_MCP_RESULT_CONSISTENCY_20261011.md`.


## Revisão local de contratos — 11/10/2026; NÃO é novo deploy

A fonte local contém as melhorias de leitura do checkpoint `aa4a90b` e correções posteriores de concorrência da atividade, verificadas no Services contra o arquivo integral: **25/25 PASS**. O novo teste `test_customer_argument_pipeline.mjs` detectou perda de `expected_sha256` em escrita/edição/exclusão e de `offset` em busca/listagem no adaptador do Worker: **fonte atual 16/38 PASS; candidata apenas em memória 38/38 PASS**. **O patch desse Worker não foi aplicado**, pois a tentativa de gravação foi bloqueada. O modo candidato não substitui a aprovação do código do produto.

Não houve deploy, migração, coleta nova de custos, atualização de agentes nem comprovação de escala nesta revisão. A bateria geral anterior de 68 validadores não foi reexecutada. Leituras históricas de Cloudflare abaixo continuam históricas; não promovê-las a verificação desta rodada. Referências: `docs/operations/HARA_COMMANDER_ARGUMENT_PIPELINE_REVIEW_20261011.md` e `docs/operations/HARA_COMMANDER_ACTIVITY_SESSION_CONCURRENCY_20261011.md`.


## Atualização autoritativa — capacidade, 11/10/2026

Visual de Plano e cobrança aprovado pelo proprietário. Capacidade: auditoria e melhorias publicadas, **sem certificação de 1.000–10.000 clientes simultâneos**. Suíte final **63/63 PASS**; testes de fonte/SQLite com 10.000 contas, 20.000 dispositivos e 210.000 sessões; plano da nova consulta confirmado no D1 DEV real. Limpeza indexada em lotes limitados, observação agregada sem dados de clientes e empacotamento comercial assinado testável.

**PROD `9f7526c5-98a9-415a-b756-25200eee0627`**, 100%, 12/12 assets exatos, saúde/autenticação/assinatura PASS. **DEV `96e67af5-9a67-41f0-8322-763fcd3bb237`**. Rollback íntegro **`b500dd23-c33b-4247-ac3e-04c24c8af15a`**. A candidata `97f050a3-ab1c-4175-94f1-fdd9e4614740` foi revertida por divergência de assets e não deve ser usada como rollback.

**Separar LOCAL_TUNNEL de OUTBOUND_RELAY:** túnel local já desliga polling de fila; a projeção de tráfego elevado é do relay. Telemetria horária não equivale à carga total do túnel. Event V2 Founder não comprova escala de clientes públicos. Sem migração D1, mudança de preços, liberação de Stripe LIVE ou reconfiguração da frota.

Relatório: `docs/operations/HARA_COMMANDER_CAPACITY_1K_10K_20261011.md`. Evidências: `docs/evidence/commander-capacity-20261011/`. Fonte runtime `29067c2`; validação final `b486501`. Publicar assets com `stage_signed_commercial_assets.py` + `wrangler --assets`, nunca com `public/` bruto. Storage segue HOLD.

---


**HANDOFF PARA A PRÓXIMA CONVERSA — LEITURA OBRIGATÓRIA:** `docs/handoffs/HARA_COMMANDER_FULL_OPERATIONAL_HANDOFF_20261010.md`. Estado técnico comprovado: PROD `b500dd23-c33b-4247-ac3e-04c24c8af15a` 100%, DEV `39b8e74a-5e5f-40a5-988b-7b0906a59cb0`, centralização horizontal+vertical dos cartões Free/Pro encerrada no código e publicada. **Não confundir implantação com aceitação visual humana: falta verificação estética do proprietário na tela atualizada.** Free 10.000/mês, Pro R$ 80/mês (Stripe checkout LIVE OFF); 57/57 testes offline e 11/11 readback público PASS. O novo handoff reúne as decisões de UX, Fleet Founder 0.3.44 versus instaladores comerciais 0.3.43, limites de autoridade dos conectores, gates Stripe/Windows/Plugin e próximos comandos. Esta linha prevalece sobre as entradas históricas abaixo.


**PROD ATUAL — PLANO E COBRANÇA CENTRALIZADO VERTICALMENTE, 10/10/2026:** Worker Cloudflare `hara-commander` versão **`b500dd23-c33b-4247-ac3e-04c24c8af15a` em 100%**, rollback `0fd13813-9c0a-45c1-9102-8ab5db7c3d26`. A grade Free/Pro já era centralizada na horizontal; agora o `workspace-main` alinha e centraliza verticalmente **o conjunto inteiro** (cards, readiness, status e gerenciamento), com min-height relativo à área abaixo da topbar. Em telas baixas ou estreitas, rolagem normal preservada. DEV `39b8e74a-5e5f-40a5-988b-7b0906a59cb0`, DEV/PROD 11/11 assets SHA exatos, health/auth PASS, cache HTML e CSS convergidos; D1 Free 10.000 e Pro ilimitado, teste offline 57/57 PASS. Nenhuma mudança em API, Agent assinado, Founder, billing, Stripe ou autenticação. Handoff: `docs/operations/HARA_COMMANDER_PRICING_FULL_FRAME_CENTERING_20261010.md`.


**HISTÓRICO — CARDS COMPACTOS ANTES DO ALINHAMENTO VERTICAL DO CONJUNTO:** Worker Cloudflare `hara-commander` versão **`0fd13813-9c0a-45c1-9102-8ab5db7c3d26` 100%**, rollback `f16f8458-d595-4904-87d6-b9ff31bf5a58`. Tela Plano e cobrança: Free/Pro juntos com máximo de 1.080px, colunas simétricas centradas, padding reduzido e responsivo (1 coluna até 1050px). Os outros menus continuam sem headings repetidos; cores H.A.R.A., preço R$80 Pro, Free 10.000/mês e CTA beta preservados. DEV `4219f824-659f-4780-98e7-b85b39c0c980`; DEV/PROD 11/11 arquivos SHA exato e health/auth PASS, `/` e `/index.html` convergidos, D1 Free=10.000, Pro ilimitado. Gate offline **57/57 PASS**. Somente CSS e sua cache key HTML; nenhum Agent, instalador assinado, Worker API, Stripe, serviço Founder, OAuth ou D1 alterado. Documentação: `docs/operations/HARA_COMMANDER_PLAN_CARDS_CENTERED_20261010.md`.


**HISTÓRICO — MENU SEM TÍTULOS REPETIDOS, ANTES DOS CARDS COMPACTOS:** Cloudflare Worker `hara-commander` versão **`f16f8458-d595-4904-87d6-b9ff31bf5a58` em 100%**, rollback imediato **`48c04065-7de8-41f7-8e3e-48c289bcaa5b`**. Menu lateral continua com Computadores, Uso, Plano e cobrança e Configurações; nenhuma dessas rotas repete seu nome como heading na área central. Todas usam `aria-label` acessível. Conteúdo útil sobe para o topo; cartões Free/Pro usam largura total. Textos de Comandos e integrações e Conectar novo ficaram curtos e sem os antigos limites de 920/1000 px; desktop ampla largura mantém uma linha, telas menores quebram naturalmente. DEV `d42f7f55-490d-4bab-8959-23c499b96b33`, PROD e DEV **11/11 assets SHA exato**, rotas `/` e `/index.html` conferidas, health/auth PASS. D1 Free 10.000 chamadas/mês, Pro ilimitado. Gate offline **56/56 PASS**, incluindo teste novo das quatro abas. Nenhum Agent, pacote comercial 0.3.43, MCP, token, serviço Founder ou cobrança alterado. Documento: `docs/operations/HARA_COMMANDER_PORTAL_NAVIGATION_NO_DUPLICATE_20261010.md`.


**HISTÓRICO — correção dos três pontinhos na versão anterior:** Worker `hara-commander` versão `48c04065-7de8-41f7-8e3e-48c289bcaa5b` 100%; rollback `66958dc2-2951-423d-9699-6396e78d2890`. Menu ⋯ agora abre painel inline com detalhes e ações secundárias, sem executar comando só de abrir; botão acessível com `aria-expanded`. Removido título repetido Comandos e integrações dentro da aba. DEV `b9ecf6c0-dd0d-4020-83ef-0746db2eadc7`. SHA público 11/11 PASS, health/auth PASS, Free 10.000 e Pro ilimitado, pings comerciais Services/Núcleo A/Sentinela C/D Agent 0.3.44 PASS. Gate 55/55 PASS, sem mudanças nos Agents ou serviços. Relatório `docs/operations/HARA_COMMANDER_DEVICE_DETAILS_MENU_FIX_20261010.md`.


**HISTÓRICO — COMPUTADORES SEM TÍTULO DUPLICADO E SEM DIVISÓRIAS INTERNAS, antes do conserto dos três pontinhos:** Worker Cloudflare `hara-commander` versão **`66958dc2-2951-423d-9699-6396e78d2890` a 100%**; rollback imediato `4946ed70-bbf0-4605-98a8-063d0af0a8cb`. Removido o `<h1>` redundante no conteúdo, mantendo `aria-label="Computadores"` para acessibilidade; abas subiram. Dispositivos, Conectar novo e Comandos e integrações têm fontes maiores, linhas internas removidas e espaçamento reduzido; bordas externas, cores H.A.R.A., cards e ações preservadas. DEV `e27c8338-b45e-484f-a0b5-5b82705deaad`. DEV/PROD com readback **11/11 SHA** e health PASS; `/` e `/index.html` atualizados, auth PASS; MCP comercial Núcleo A/Sentinela D Agent 0.3.44 PASS. Free=10.000/mês, Pro ilimitado, testes offline **55/55 PASS**. Somente HTML/CSS modificados, sem tocar no Agent/instalador assinado, frota, Worker API, billing ou D1. Documento: `docs/operations/HARA_COMMANDER_DEVICES_COMPACT_BORDERLESS_20261010.md`.


**HISTÓRICO — ESTADO ANTERIOR DA MOLDURA DE COMANDOS, JÁ SUBSTITUÍDO:** Cloudflare Worker `hara-commander` versão **`4946ed70-bbf0-4605-98a8-063d0af0a8cb` a 100%**. Aba Comandos e integrações sem etiqueta REFERÊNCIA RÁPIDA, com uma caixa externa envolvente de largura total e cards simétricos internos Linux, Windows e MCP, preservando a paleta, os comandos e as fontes ampliadas. DEV `7438d28f-266f-46c4-9063-8bb00f2c7eb3`. SHA público 11/11 PASS, `/` e `/index.html` convergidos, health/auth PASS, regressão 55/55 PASS. Rollback PROD imediato `d305c678-7715-4594-b8b9-f1e697112702`. Somente index.html/styles.css publicados; nenhuma mutação D1, Agent, MCP, billing, serviço Founder ou pacote assinado. Ver `docs/operations/HARA_COMMANDER_DEVICES_SYMMETRIC_LAYOUT_20261010.md`.


**HISTÓRICO — etapa anterior de simetria, posteriormente refinada com caixa externa:** Worker `hara-commander` versão **`d305c678-7715-4594-b8b9-f1e697112702`**, 100%. Título Computadores compacto/alto, sem subtítulo; fontes maiores, cards Linux/Windows iguais ocupando toda a largura útil, MCP em largura total, comandos em linhas sem bordas internas. Identidade Navy/Blue/Gold e controles preservados. DEV `d122db6f-7ef4-410a-9656-d50c615d0a07`. DEV e PROD com SHA exato **11/11 assets**, health/auth PASS e `/`/`index.html` atualizados; D1 Free 10.000 e Pro ilimitado, pings comerciais Núcleo A e Sentinela D Agent 0.3.44 PASS. Rollback Worker anterior **`9943523c-a573-40bc-bc86-2f45b2156643`**. Documento de implementação: `docs/operations/HARA_COMMANDER_DEVICES_SYMMETRIC_LAYOUT_20261010.md`. Gate offline 55/55 PASS; nenhum Agent, instalador assinado, segredo, billing ou serviço Founder alterado.

**HISTÓRICO — UX GUIADA PUBLICADA ANTES DO REFINAMENTO ATUAL:** Worker Cloudflare `hara-commander` versão `9943523c-a573-40bc-bc86-2f45b2156643` **100%**, com três abas em Computadores (Dispositivos / Conectar novo / Comandos e integrações). Instalação via token one-time gerado no portal, instalador assinado Linux/Windows e comandos copiáveis. DEV versão `b160e263-fab5-4918-9d11-0ae128e413b4`. Readbacks independentes: Worker, health, auth e assets atuais PASS, **11/11 SHA**; Free 10.000, Pro ilimitado e pings do MCP comercial para Núcleo A e Sentinela D Agent 0.3.44 PASS. Rollback Worker anterior `228fdb6d-fbde-4a1c-91b0-57ac73f5d193`; não houve mudança em D1, Agent ou assinatura. Fonte/execução: `docs/operations/HARA_COMMANDER_CUSTOMER_INSTALL_GUIDE_UX_20261010.md`. Gate offline **55/55 PASS**. Windows ainda beta para operações sensíveis.

**HISTÓRICO — refinamento da lista:** Worker `228fdb6d-fbde-4a1c-91b0-57ac73f5d193` introduziu a lista minimalista com as cores preservadas. Essa versão foi o rollback da publicação guiada anterior; atualmente o rollback imediato é o Worker informado no topo deste handoff. Ver `docs/operations/HARA_COMMANDER_DEVICES_MINIMALIST_UI_20261010.md`. **Sem alteração de D1, quotas, autenticação ou Agents.**

**DECISÃO MAIS RECENTE DE PREÇO/QUOTA — FREE=10.000 chamadas governadas/mês.** O dono revogou a autorização temporária de 15.000. D1 DEV e PROD estão em 10.000 via migração `0032_free_10000_revert_20261010.sql`. Pro permanece ilimitado. A versão **histórica do deploy da quota** foi `43421f6f-5bee-4fe6-9bc4-982a3e10d019`, com readback de 10/10 assets assinados e portal JS/HTML 10.000 PASS; o **Worker atual é o informado no topo deste handoff**, sem alteração do limite. O conteúdo histórico abaixo sobre 15.000 está SUPERADO. Ver `docs/operations/HARA_COMMANDER_FREE_10K_REVERSION_20261010.md`.

**Antes de qualquer mutação ou decisão: ler primeiro**
`docs/handoffs/HARA_COMMANDER_FLEET_EVENT_V2_HANDOFF_20261010.md`.
**Para billing/Stripe:** `docs/operations/HARA_COMMANDER_STRIPE_TEST_ONE_COMMAND_ACTIVATION_20261010.md`.

**Única branch autoritativa de produto:** `local/commander-product-current`.
Worktree Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`.
Repo GitHub: `tiagoharalabs/hara-site`.

## Estado atual comprovado
- **Frota Linux Founder 7/7** em Agent **0.3.44 assinado per-device** e **EVENT_V2 WebSocket**, com `H_A_R_A__Commander.get_device_info` e `ping` comerciais PASS: `nucleo-a`, `sentinela-a`, `sentinela-b`, `sentinela-c`, `sentinela-d`, `ninja-blue`, `services`.
- V2 `active+enabled`, v1 0.3.41 `inactive+disabled` mas preservada para rollback; watchdog/timer ativo em todos. Nenhum reboot nem failover forçado foi realizado. Windows permanece offline/revogado/não homologado em Event V2.
- Worker PROD Cloudflare `hara-commander` versão `29e556f3-86af-476d-ba01-a764c3acb6a0` (100%) no último readback. Allowlist original Núcleo mais seis Founder configurados em **secret** `DEVICE_EVENT_V2_ADDITIONAL_DEVICE_IDS`; sem wildcard, sem liberar outros tenants.
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` ainda PENDING em PROD. **Checkout pago NÃO ATIVO.** Catálogo Free = 15.000 chamadas governadas/mês (migração PROD 0031 confirmada em 10/10); Standard Pro = R$80/mês (ilimitado no catálogo), não comprovadamente faturado.
- **Stripe TEST automation preparada:** `stripe_test_activation_wizard.py --check/--apply` (a segunda exige chave `sk_test_` introduzida privadamente no Services). Cria/reutiliza produto/Price BRL80, webhook assinado, Portal e configura quatro DEV Worker secrets; o assistente não recebeu/instalou nenhuma chave Stripe. Teste integrado SQLite e teste offline do wizard PASS. **Worker DEV publicado** na versão `490c38bf-5ef0-4b55-a33a-2dc6d0c6ad6c` 100%, DEV health 200, sem segredos Stripe; PROD mantido na versão anterior. Restam test Checkout real e live rollout governado.
- **Correção SSH Stripe 10/10:** erro `CLOUDFLARE_DEV_SECRET_LIST_UNAVAILABLE` foi causado por Wrangler sem Node no PATH em SSH non-login (`/usr/bin/env: node: No such file or directory`). O wizard agora resolve Node instalado via NVM sem carregar perfis nem tocar no PATH global. `--check` validado com SSH normal e `ssh -tt` Núcleo→Services e com PATH limitado, sem chaves, pagamentos ou alterações de Cloudflare. O operador, já em Services, deve executar o `--apply` manualmente e digitar `sk_test_` apenas no terminal.
- Métrica anterior Cloudflare de canário Núcleo −20,7% polling, −19,7% requisições Worker entre duas janelas equivalentes; **não transferir esse percentual à frota 7/7 nem à economia de fatura sem nova medição**.
- **Storage diverge de GitHub/local**: `092f35afc52827d6c5584f0401e9f60eaeb3d985`; `STORAGE_RECONCILIATION=HOLD`. Não forçar refs ou burlar hooks.
- O handoff anterior `HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md` e o arquivo de preparação `HARA_COMMANDER_EVENT_V2_FOUNDER_FLEET_STAGE_20261010.md` são **históricos**, não a verdade atual de deploy.

**Nova auditoria de produto e stress em 10/10:** ler também `docs/operations/HARA_COMMANDER_PRELAUNCH_SECURITY_STRESS_AUDIT_20261010.md`. As **31 funções do Agent são suficientes como primitivas do MVP**, mas o perfil simples ChatGPT tinha 24 métodos; **27 métodos estão preparados somente em código-fonte candidato** (inclui preimages, rollback e recibos), sem deploy público. A suíte offline de pré-lançamento **47/47 PASS** executou até **1.000 tentativas concorrentes / 24 threads** por cenário contra SQL exato do Worker em SQLite isolado: fila 16, idempotência 1, cross-tenant 0 e claim 16 únicos. Correções candidatas: limite RAM/sessões, quota de backups 256 MiB/4.096 entradas, `ASK_EVERY_ACTION` como padrão para novos instaladores, risco destrutivo honesto em MCP, `list_directory.offset` corrigido, regressões OIDC e integridade de v1. **Nenhuma dessas correções de agente foi implantada em release assinada**, e os 3 métodos MCP também não estão ativos no PROD. Não tratar 47/47 como teste real de 1.000 clientes Cloudflare.

**Próximos gates P0:** assinar/testar release externa com hardening e default seguro; Stripe real checkout+webhook/idempotência; segundo tenant real e isolamento; homologação da franquia Free (fim do limite, concorrência, replay); stress DEV 24h com teardown e failover; instalar e dar suporte sem mutações sem aprovação. **P1:** Windows Event V2 ou beta Linux-only, cold boot/failover, métricas 24h por host e Cloudflare faturado, observabilidade `last_seen`/`agent_version`, Storage/CI. Ver handoff completo para provas e rollback.

**Não confundir ferramentas:** `H_A_R_A__Commander` é o MCP comercial; `H_A_R_A__Commander_Baseline` é superfície Services/admin. Verificar novamente com plugin comercial ao iniciar novo chat.

## 10/10/2026 — Política comercial manual-on-demand, publicação e contingência

**Contrato decidido:** ao instalar Linux/Windows, o Agent inicia uma única vez para teste/atestado, mas o instalador **não habilita autostart no próximo reboot/login**. O cliente usa `hara-commander start` no Linux ou `hara-commander-agent.ps1 start` no Windows para abrir uma sessão ativa; `stop` encerra. `ASK_EVERY_ACTION` é padrão seguro; não há seletor de autorização persistente ou autostart na página comercial. Técnico pode optar em Linux por serviço persistente explicitamente via sistema operacional. O MCP STDIO local `hara-commander mcp` é distinto do Agent Cloud.

**Comprovação de publicação de assets:** Cloudflare PROD serve `https://commander.haralabs.com.br/install/linux.sh` e `install/windows.ps1` com HTTP 200, arquivos de release **v0.3.41 assinado antigo** e autostart ainda presente (Linux `enable --now`, Windows `AtLogOn`). Publicação é via Wrangler Worker `hara-commander`, `assets.directory=public`; `git push` isolado não a altera. Novo fluxo está SOMENTE nos arquivos candidatos em Git até nova assinatura e deploy versionado.

**Contingência GitHub real:** tag **`hara-commander-signed-agent-v0.3.41`** criada e publicada, apontando para SHA exata `08500d5c4256d25abc77a26ad377e55eadf1742a` com tag readback PASS. `verify_commander_public_artifacts.py --check/--live` verificou assinatura RSA v1 e seis arquivos byte-idênticos Git↔Cloudflare, incluindo manifesto. Nunca montar distribuição comercial nova combinando candidate HEAD com manifesto v0.3.41.

**Storage:** `origin` commit `092f35af...` está divergente; fontes de instaladores/agents NÃO correspondem ao manifesto assinado legado no Storage. `HOLD`, não usar Storage como fallback assinado nem fazer force-push.

**Alterações exclusivamente candidatas:** Linux systemd disabled+start uma vez, `Restart=on-failure`, CLI start/stop controla unit, status mostra `AUTOSTART`, update e reenroll preservam estado parado; Windows Task Scheduler sem trigger, CLI manual start/stop, update preserva off; portal `ASK_EVERY_ACTION` e `TUNNEL_AUTOSTART=OFF` fixos, sem escolha de autostart no site. Harness Linux com assinatura efêmera e mock localhost passou todos os passos de ciclo de vida. Windows precisa homologação real; não atualizar Founder V2 0.3.44 inadvertidamente.

**Documento autoritativo:** `docs/operations/HARA_COMMANDER_MANUAL_START_DISTRIBUTION_AUDIT_20261010.md`. **GATE PARA PROD:** nova release assinada completa + testes de reboot Linux/Windows, canário Cloudflare DEV e readback de hashes antes de substituir a v0.3.41 no domínio público.

## 10/10/2026 — Nova release comercial assinada, Free 15.000, portal start/stop

A migração `0031_free_15000_20261010.sql` foi aplicada no **D1 DEV e PROD**, com readback exato: `TRIAL` = 15.000 chamadas governadas/mês; `STANDARD` = ilimitado. Stripe PROD ainda sem checkout. O site candidato agora mostra Free 15.000 e comandos copiados de `start`/`stop` fixos abaixo do instalador Linux/Windows.

A chave privada v1 não corresponde ao público pinado e não deve ser usada. A autoridade de assinatura **v2 existente** assinou a distribuição comercial `0.3.43` usando RSA-3072. Arquivos públicos íntegros: `apps/commander/release-bundles/commercial-0.3.43-v2/` (4 assets + manifesto, assinatura, JWK público, SHA256SUMS). Nenhuma chave privada no Git. Teste E2E do **pacote assinado exato** em simulador Linux PASS, incluindo instalação sem autostart, upgrade parado, reenrolamento e desinstalação. Windows: política estática PASS; homologação PowerShell real pendente.

Canário Cloudflare DEV `hara-commander-dev-v2` versão `5e17d990-bf6f-43f4-b65f-3a9aa140eb88` com 9/9 assets byte-idênticos ao pacote, health 200. PROD versão candidata *carregada sem deploy* `8c3eec1b-8783-4aff-868f-7f558e1d9db5`, com nomes de secrets de autenticação e MCP presentes; rollback PROD v1 `29e556f3-86af-476d-ba01-a764c3acb6a0`. **Não afirmar PROD v2 ativa antes do readback 100% e 10/10 hashes.**

Documento detalhado: `docs/operations/HARA_COMMANDER_SIGNED_COMMERCIAL_V2_PUBLICATION_20261010.md`. A release assinada anterior continua disponível via tag `hara-commander-signed-agent-v0.3.41`; não misturar chaves/manifestos. Storage segue em HOLD; frota Founder V2 0.3.44 intacta. Gate offline 53/53 PASS, incluindo SQL concorrente e novo catalogo.

## PRODUÇÃO ATUALIZADA — checkpoint final 10/10/2026

**Última verdade prevalece sobre históricos anteriores:** Cloudflare Worker **PROD** `hara-commander` versão `8c3eec1b-8783-4aff-868f-7f558e1d9db5` está em **100%**, com assets comerciais assinados 0.3.43 v2 (chave `commander-release-v2`). `validate_signed_commercial_v2_bundle.py --live` 10/10 assets PASS, SHA após normalização exata do beacon HTML Cloudflare. `validate_prod_runtime_drift.py --expect-assets current` CURRENT PASS. Website e downloads públicos agora entregam nova política **start manual, sem autostart**. Comandos copiar/iniciar/parar ficam sob cada instalador. Free/TRIAL 15.000/mês aplicado no D1 PROD/DEV e readback PASS, Pro ilimitado; Stripe checkout ainda OFF.

Comercial MCP pós-deploy `ping` Núcleo A e Sentinela D PASS em Agent Founder 0.3.44 Event V2; não mudar Founder. Rollback Worker PROD `29e556f3-86af-476d-ba01-a764c3acb6a0`, tag legado assinada `hara-commander-signed-agent-v0.3.41`; novo backup assinado tag GitHub `hara-commander-commercial-v0.3.43-signed-v2` (commit `d7e5f128...`). Manifesto público v2 tem kid v2; não combinar assets v1. Windows ainda BETA sem prova nativa PS 5.1; permitir download não equivale a homologar mutação. Multi-tenant stress/Stripe e OpenAI plugin listing são gates separados.

Relatório e procedimento: `docs/operations/HARA_COMMANDER_SIGNED_COMMERCIAL_V2_PUBLICATION_20261010.md`. Verificador antigo `verify_commander_public_artifacts.py --check` preserva assinatura v1 no Git; `--live` deve usar validador comercial v2, nunca tratar a v1 histórica como atual. Storage protegido segue HOLD `092f35af...`.

## 10/10/2026 — Minimalismo da tela Computadores

Novo refinamento autorizado da UI no portal público (sem alterar cores/identidade): cada linha mostra só nome, sistema, último contato e estado real; Agent/arquitetura/transporte/autorização ficam no menu de detalhes com ações secundárias. O grande guia de onboarding está recolhido por padrão; os botões de diagnóstico e procedimentos de autorização/revogação são preservados. Uma lease local válida não implica máquina online. O total de chamadas Free continua 10.000/mês.

Fonte e contrato: docs/operations/HARA_COMMANDER_DEVICES_MINIMALIST_UI_20261010.md. Gate offline 54/54 PASS, DEV Worker versão 636d9e2f-883c-4a0d-96e1-8280ee2ee4ad com SHA exato 11/11 e health 200. Bundle assinado comercial v0.3.43 e agentes Founder v0.3.44 não foram tocados. Registrar versão PROD depois da promoção e readback.

## Windows 12/10/2026 — homologação parcial

VM com .50 privada e SESSION_TRUSTED, confirmada pelo Commander direto. Execução Unicode, arquivo UTF-8 físico e CAS passaram; terminal retornou 120 linhas, mas perdeu emoji/CJK na entrada literal. .51 corrige stdin, está assinada e validada dentro da VM: 511 verificações nativas e 115/115 no gate integrado. Troca .50 → .51 aguarda uma sessão de terminal ativa (PID 5448), que foi preservada. Ainda falta prova MCP real da .51. Detalhes e hashes: HARA_COMMANDER_WINDOWS_051_HANDOFF_20261012.md. Download público .43 e Linux preservados; nenhuma declaração de homologação comercial completa.
