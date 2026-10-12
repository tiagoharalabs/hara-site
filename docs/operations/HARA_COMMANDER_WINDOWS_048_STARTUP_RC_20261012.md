# H.A.R.A. Commander — Windows 0.3.48: recuperação de sessão sem StartTime

Data: 12/10/2026. Desenvolvimento isolado: `local/commander-win48-startup-20261012`, base `1dd5b8729d24966cb1a2cf7fba3bfd2a64798c5c`. Snapshot local .47: `82030189ad1b25c25176fc4875e4a34aa272570b`. Código .47, bundles históricos e registro operacional .47 preservados.

## Problema e comportamento corrigido

A imagem enviada pelo usuário mostra `InvokeMethodOnNull` durante `start` na .47: `Get-OperatorSession` recebia um processo cujo StartTime estava indisponível e chamava ToUniversalTime sem proteção. Isso interrompia a abertura antes de retomar a tarefa ou criar a janela.

A .48 valida PID maior que 1, lookup do processo, tipo DateTime da hora de início e igualdade do marker dentro de try/catch. Metadados ausentes, inválidos, inacessíveis ou de PID reutilizado retornam sessão nula. Um registro inválido não autoriza reutilização; o fluxo normal pode abrir uma sessão nova. A sessão válida conserva seu PID e início exatos. O delta de fonte em relação à .47 congelada é somente essa função e AgentVersion.

A leitura do StartTime do próprio processo em Start-OperatorConsole continua sem proteção; eventual falha ocorre antes de gravar a sessão. Essa alteração não promete resolver interrupções externas do consumidor, cuja origem segue desconhecida.

## RC privada e testes

Bundle: `apps/commander/release-bundles/commercial-0.3.48-v8-rc`. Fonte92151 bytes SHA `f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805`.
Manifesto765 bytes SHA `5e65b1862c40bc9164609cdcd1401bb55e02e409b44f1b58bca15151e40de32c`.
Installer23774 bytes SHA `1ff4c187de3731634564709f2dc0eb4929058a0859fcdd04432d508d78b6f1c0`.
Autoridade RS256/RSA3072 existente, igualdade fonte/bundle e trust pin v2 validados também no PowerShell 5.1 da VM. Self-test e parser usaram perfil sintético; o transporte real não foi iniciado.

- Startup .48: **68/68 PASS**, 12 cenários, incluindo StartTime nulo, ausente, getter que lança erro, corrida de saída, PID inválido/overflow/reutilizado e sessão válida.
- Controle negativo .47: **68/68**, reproduzindo `InvokeMethodOnNull` no dispatch `start` real por AST, em filho isolado com exit17. A .48 retorna exit0 e pede a fronteira de console novo, sem autorizar o marker inválido.
- Consentimento existente: **111/111**; cadeia completa de recusa: **26/26**; retomada/corridas: **27/27**, todos sobre os bytes finais .48.
- Guard estático de identidade: **13/13**, com reprodução do bug rejeitada; guard de aprovação48: **31/31**.
- Gate offline final: **97/97 PASS**, SHA `c40880e99c651fd763d39b5aff2448145d6ab2344e8027fb54e44509046e80fa`.

A primeira execução95/97 foi preservada: dois validadores ainda exigiam a versão47. Foram corrigidos três literais para48 sem relaxar contratos. Symlink temporário de dependências removido. Os testes PS5.1 tiveram exit0, stderr vazio, sem truncamento, sem modificar perfil/tarefa/IPC reais. Evidências em `docs/evidence/commander-win48-startup-20261012/`.

## Canário e UX

Status de instalação: **instalada e aberta manualmente pelo usuário, com leituras comerciais confirmadas**. A inspeção das16:47:58Z encontrou source47, tarefa Ready sem consumidor, NoIPC e operador8768 com PID/início exatos e StartTime disponível. Esse operador válido foi preservado até a troca controlada.

O canário InstallOnly passou às17:21 UTC: preimagens e custody do marker verificadas, somente o operador8768 encerrado, zero alvos antes da troca atômica para48, configuração/tarefa/ASK preservadas. Não iniciou tarefa ou janela automaticamente. Tentativa anterior abortada na prechecagem por prazo de metadados vencido, sem tocar na47. Wrappers finais tiveram exit0 e domínioPASS, com stderr_present=true de causa não comprovada, mantido nas evidências.

Nosso CMD foi renomeado com SHA preservado para **Abrir_HARA_Commander.cmd** no Desktop. O usuário o abriu manualmente às17:23:02Z; inspeção independente confirmou operador8184, consumidor4896, tarefaRunning, NoIPC e source/config/XML exatos. Evidência canário SHA8c16eaa376548a414590f829e903c9c7574020a63149b8e703a4a60c525de06a.

Leituras pelo H.A.R.A. Commander direto: device.info PASS, Agent0.3.48/HARA_WIN11, receipt37c611aa98f5c2052f0c41a498e5f91ff13885b14402efa7fe777f705a25223a; process.sessions PASS/count0, receipt84c0feeaffdfa757fc26e64f9548a851233a005fc9d9f5ea51157f8d01a0364b. Esses recibos comprovam acesso e leitura, não execução aprovada por humano.

A notificação no Desktop Linux foi pré-validada via serviço GNOME Notifications, recibo `f50a2f28d87958273c9af8605ed0cb8c351397902ce5b77231a68bbcbcf80d76`. O aviso de aprovação deve ser enviado somente depois de constatar pedido ativo e prazo futuro na VM. Nenhum código ou entrada de aprovação será automatizado. O primeiro sampler sob QGASYSTEM retornou READ_ONLY_ERROR/PENDING_METADATA_UNAVAILABLE e não enviou aviso; o monitor em contexto do usuário está sendo preparado. Não alegar notificação vista ou pedido ativo a partir dessa falha.

## Produto real e limites

A aprovação humana positiva, execução, escrita protegida por SHA-256, interação e recuperação Windows pelo **H.A.R.A. Commander direto** continuam pendentes. Baseline não é a rota nem prova desta frente. Política ASK_EVERY_ACTION e prazo30s preservados; downloads públicos continuam .43-v3, sem promoção desta RC ou alteração de Stripe.

Frota Linux consultada às16:40Z: 7/7 responderam com recibos; seis em .46/EVENT_V2, SentinelaB em .41/OUTBOUND_RELAY. Não assumir que B recebeu correções46. O patch de presença Linux conserva o relógio entre reconexões do mesmo processo, passou34 checks e ainda não foi instalado no runtime; restart do processo e falta de ACKD1 seguem limites registrados na operação47. Arquivos de outras frentes e Storage permanecem preservados.


## Continuidade após o checkpoint 3b4 — 18:33 UTC

O GitHub confirmou o checkpoint `3b4f791147be54919727628e9c577963af030e3f`; GitHub Actions `38284856240` concluiu SUCCESS com gate97/97. Os fatos abaixo ocorreram depois desse checkpoint e permanecem em curação, sem nova publicação.

Às17:42:10Z, a inspeção encontrou consumidor4896 ausente, tarefa Ready e LastTaskResult `0xC000013A`. O operador8184 continuava vivo, com início `2026-10-12T17:23:02.2031480Z` e marker correspondentes. A origem da interrupção é UNKNOWN; o resultado da tarefa não identifica quem encerrou o processo. Fonte .48, sessão ativa e configuração não foram alteradas nesse diagnóstico. Evidência: `windows48-real-hostname-unclaimed-consumer-diagnostic.json`, SHA `2e76ce93e82086e03d1e79c3deef76cc92e1eaa6cb29eeb0dcf3aa21c7ad7fae`.

A retomada autorizada preservou a sessão existente e executou somente Start-ScheduledTask, uma vez, na tarefa já registrada. Criou consumidor6456 com início `2026-10-12T18:05:45.2932270Z`, sem Stop-ScheduledTask, troca de Agent/configuração/XML/ASK, nova chamada MCP ou entrada de aprovação. O wrapper Linux atingiu timeout10s depois do resultado de domínio PASS; um sampler inicial retornou task_running=false. Esses limites permanecem registrados. A inspeção independente às18:07:22.322Z confirmou Running e consumidor6456 vivo com identidade exata, além do operador8184 preservado. Não houve repetição do restart. Evidência: `windows48-existing-task-resume-acceptance.json`, SHA `4d9061a7b570876f6fa8b18f947f39709d4ab0ce6246ea5b38cefa20650940c7`.

| Chamada real Windows | Criada (UTC) | Claim (UTC) | Resultado |
| --- | --- | --- | --- |
| `894f394e-0ddc-437b-8310-7a642b248812` | 17:37:10.999 | Ausente | EXPIRED às18:17:39.297; DEVICE_CALL_EXPIRED |
| `ab023a25-91c2-4fdb-b74a-8c59ff405fe5` | 18:29:37.022 | 18:29:42.096 | DENIED no MCP / FAILED nos metadados às18:30:13.058; LOCAL_ACTION_APPROVAL_EXPIRED |

A chamada antiga não foi recebida pelo consumidor. A chamada nova chegou ao Agent, mas não obteve confirmação humana dentro do prazo; mutation_performed=false e hostname_executed=false. Não usar a expiração de uma chamada com claim como regra geral para inferir ausência de execução: nesta tentativa, a negação local explícita e os metadados de resultado sustentam a conclusão.

O watcher `commander_win48_user_hostname_pending_watch.py`, SHA `aee1c0c53e8e0e5ab2ad3c7ff647ce6ee47a9bd78a94c75c84482a86b4504042`, retornou pending_active=false, notification_sent=false, source48_pinned=true e task_running=true. O monitor falhou em detectar o pedido; isso não comprova ausência do pedido, aviso entregue ou foco do console. A falha segue em investigação e um novo watcher será validado antes da próxima tentativa. Os bytes e a evidência da tentativa anterior são históricos. Os watchers registram e iniciam tarefas próprias temporárias de observação; essas tarefas não são a tarefa do Agent. O helper de retomada preserva a definição da tarefa do Agent e só inicia sua instância existente. Nenhum watcher publica resposta de aprovação.

Depois dessa tentativa, as leituras diretas confirmaram Agent0.3.48 e zero sessões gerenciadas: device.info receipt `ec5235322dafca6c0f0d126e31c6192f828aeb3c9e607bc7c98e1d4ae20891ef`; process.sessions receipt `50f57b21d949fa3550914fa421d2f80997c311685e633cedf5997f2fba4ffba3`. Evidência consolidada: `windows48-fresh-hostname-expired-watch-miss.json`, SHA `aecf4205c604a8c7371a28e3f47371d7a14ce01b750b28c7cb763f3547384fa6`.

**Aprovação humana positiva permanece PENDENTE**, assim como execução aprovada, escrita CAS, terminal interativo e recuperação Windows pelo MCP direto. Nenhum aceite foi automatizado e nenhum prazo ou política foi relaxado.


## Correção paralela da leitura de expiração — código sem deploy

Os oito arquivos revisados da frente commander-call-expiry-status foram incorporados nesta worktree por hashes exatos. A listagem recent passa a projetar EXPIRED para PENDING/EXECUTING vencidos, mantendo persisted_state e metadados persistidos; a leitura não escreve D1, não inventa conclusão e não autoriza retry. A expiração de EXECUTING não atesta que uma ação deixou de executar. Testes36/36 e gate offline98/98 PASS na fonte corrigida, sem deploy Cloudflare. O checkpoint publicado3b4/CI38284856240 continua sendo o gate97/97. Fonte e bundle48 não mudaram. Detalhes e evidências: [operação de expiração](HARA_COMMANDER_RECENT_CALL_EXPIRY_PROJECTION_20261012.md).


## Última tentativa de30s e pedido explícito de15min — próxima RC49

A chamada6a180fa6-d8d4-4605-baef-9c008cf1dd34 foi criada às18:44:14.400Z, recebeu claim às18:44:23.663Z e falhou às18:44:54.285Z com LOCAL_ACTION_APPROVAL_EXPIRED. O MCP retornou DENIED/mutation_performed=false; os metadados FAILED e o resultado local não comprovam aceite humano positivo. Hostname não executou. O pré-aviso no Desktop encerrou seu processo com exit0, receipt aba499d5de938c430907198a69b9a09c99b105a99308590f41e36ba9f66e45bc; visualização pelo usuário não comprovada. A notificação após claim está null/não enviada.

O usuário relatou que30s interrompiam a digitação e pediu explicitamente15 minutos por ação às15:46BRT/18:46UTC. A próxima RC privada49 está IN_PROGRESS para alinhar o prazo do Agent e o tempo de vida no relay. Ainda não está assinada ou instalada nesta preparação; a última fonte instalada comprovada é48. Não enviar nova mutação com a janela anterior. Os arquivos da48, sua assinatura e testes históricos permanecem preservados.

Evidência: windows48-final-short-approval-window-attempt.json, SHA64a567881d773c9560bdc7dd0a9f7880fd1f19609f13e1048ae53cd626136e0c. Aceite positivo, escrita CAS, terminal e recuperação seguem PENDENTES. A curação do código de expiração/98checks e das evidências desta continuidade aguarda integração49 e liberação antes da publicação; sem deploy público, Storage ou mudança nos downloads43.


## Monitor R3: falha nativa reproduzida e corrigida no laboratório

O observador original encerrou antes de RECEIVED; a primeira amostra ficou desatualizada. O laboratório reproduziu no PowerShell5.1 a rejeição de File.Replace com backup null depois do primeiro Move. O R2 ainda falhou por amostra vencida. As falhas foram preservadas em windows48-lab-watcher-r1-r2-failures.json (SHAb79b756d10a51e72cc550d25be2d76dadb40d2b14bc283523497cc5591ac7c75).

O novo watcherR3 mantém arquivo próprio de backup, abre o leitor com FileShare.ReadWrite/Delete, retenta escritas e separa erros de gravação. O host rejeita amostra vencida ou observador parado. Fixture nativa PASS: controle negativo nullbackup, duas gravações com backup e replace enquanto leitor concorrente aberto. O preflight contínuo passou7,28s com5 amostras frescas, zero falhas de escrita, tarefaAgentRunning e pending_active=false. Evidência windows48-lab-watcher-native-fix-acceptance.json (SHAe268ac042bf6447a0324f903caffcf17decfb829e950cb53fcb85913c36e43c0); watcherR3SHA25097b0fd621c078f9ed71e4064ccb934da636f8c5bb3b7c22d78f1925fcdb9f.

Seis tarefas próprias e inativas de observação foram removidas depois de custody e XML privado protegidos; o primeiro timeout do cliente foi preservado e uma inspeção independente confirmou ausência das seis tarefas, backups presentes, tarefaAgentRunning e XML exato, sem Stop/restart do Agent ou operador. Evidência windows48-owned-inactive-observer-cleanup.json (SHA3aeaecb964b882fd4e5e1655706b59e368817a133e403809399fe1cf9c73fc3a).

FonteAgent48 e watcher originalaee1c0 permanecem imutáveis. Não houve entrada/resposta de aprovação automatizada, notificação comprovada ou aceite positivo. O R3 sobre48 é histórico; a próxima tentativa deve usar o prazo solicitado de15min na49 depois de revisão, testes e instalação privada autorizada.
