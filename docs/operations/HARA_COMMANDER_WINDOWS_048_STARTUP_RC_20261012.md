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
