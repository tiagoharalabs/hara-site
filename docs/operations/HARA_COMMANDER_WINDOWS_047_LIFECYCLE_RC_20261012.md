# H.A.R.A. Commander — Windows 0.3.47: retomada com console existente

Atualizado em 12/10/2026, 16:30 UTC. Base canônica inicial: `bf91d52394b457fd7f0cfc76f786ab58ff2d0559`. Snapshot local Windows .46: `1dd5b8729d24966cb1a2cf7fba3bfd2a64798c5c`. Esta RC é privada e permanece congelada. **A homologação comercial Windows continua pendente; a imagem do usuário revelou uma falha adicional de abertura, em correção na .48.**

## Correção da .47

Na .46, repetir `start` com console existente e tarefa Ready iniciava o Agent, tentava abrir outro console, recebia `OPERATOR_SESSION_ALREADY_ACTIVE` e interrompia a tarefa no finally. A .47 retoma a tarefa e reutiliza a sessão existente, revalida a sessão após iniciar a tarefa e limita a interrupção ao caller que efetivamente abriu a sessão. O pedido e a resposta de aprovação também vinculam PID e início do consumidor. A janela explica que `APROVAR` sozinho não autoriza: a frase inclui o código individual.

Fonte .47 SHA-256: `254517c46acf47102ebed5fe31fcb5d880ca0de47b98debeebdcaf4b1b324e36`.
Installer: `4651d11e4be34ff7b78511c05b767e655e36f179c2da3bb47def5893a25de235`.
Manifesto do bundle `commercial-0.3.47-v7-rc`: `62433a8dc4e2b39c37f1ce8be7538c92eb207541bfcc5f7babb78cee83bb8e7e`.
Assinatura RS256/RSA3072 da autoridade existente; nenhum material privado foi publicado.

## Testes e canário

Testes PowerShell 5.1 reais: 111/111 consentimento, 26/26 cadeia completa de recusa com transporte simulado, 17/17 retomada e 27/27 corridas/fechamentos. Gate .47 final: 93/93 PASS. A correção Linux de presença adicionou um teste e o gate completo seguinte passou 94/94. Releases congeladas .43–.46 e assets Linux do bundle mantiveram seus bytes.

Tentativas R1–R4 foram interrompidas por precondições de tarefa/processo que mudaram; seus resultados HOLD não foram convertidos em PASS. O Apply R5 de .46 para .47 passou às 16:04 UTC, com preimagens privadas, zero processos alvo durante troca, SHA da fonte, configuração, XML/principal da tarefa e `ASK_EVERY_ACTION` preservados. Recibo do Apply: `3d973f98f7f97a7af99c07d48ee781e22e75540e8c286f320ad77ead863494fa`. Pós-condições independentes passaram. O wrapper registrou stderr presente, sem conteúdo recuperável; a origem do aviso permanece desconhecida.

Às 16:10 a tarefa estava Ready, resultado `0xC000013A`, sem consumidor. A causa da interrupção não foi comprovada. O marker antigo apontava para um operador morto. Às 16:22 outro operador, PID8768/início16:15:33Z, estava vivo e correspondia ao marker, mas a tarefa permanecia Ready. Esse registro válido foi preservado.

O usuário pediu um arquivo executável no Desktop da VM por falta de clipboard. Foram criados, sem sobrescrever arquivos existentes, `HARA_Commander_Abrir_047.cmd` e `HARA_Commander_Como_Aprovar_047.txt` no Desktop OneDrive do usuário. O CMD usa o caminho instalado e continuará apontando à fonte corrigida. Nenhuma aprovação foi digitada automaticamente.

## Falha de abertura identificada na imagem do usuário

A imagem de 16:13 mostra `InvokeMethodOnNull` em `Get-OperatorSession`, na leitura `$proc.StartTime.ToUniversalTime()`. Um processo retornado pode não oferecer StartTime; o acesso sem proteção interrompe o start. A .48 está sendo preparada com retorno nulo para metadados ausentes, inválidos ou que lançam exceção, preservando a identificação por PID e início. O diagnóstico posterior constatou o PID8592 ausente e o operador8768 válido; isso não reproduz a condição transitória da imagem nem comprova sua causa de sistema.

Evidências: `docs/evidence/commander-win47-lifecycle-20261012/`, incluindo canário R5, pós-condições, Desktop e diagnóstico somente leitura. A .47 congelada fica como controle negativo dos testes da .48.

## Presença Linux

Services ficou falsamente OFFLINE apesar do processo e socket vivos. A reconexão reiniciava o prazo de liveness de aproximadamente seis horas; a última escrita persistida perdia a janela de TTL7h. O patch em `event_v2_agent_loop.py` conserva o relógio entre reconexões do mesmo processo e avança o checkpoint somente após envio bem-sucedido. São 6 cenários/34 verificações PASS e controle negativo falhando no source antigo.

Services voltou a responder pelo plugin direto às 16:25 UTC com o heartbeat normal, antes de instalar o patch: recibo `6c986a063e7512fbefc5564d1dc11ece152e8dc0e6eef3f940bb019845678cb1`. Não foi reiniciado nem atualizado nesta recuperação. O patch ainda não foi homologado em runtime. Reiniciar o processo ainda reinicia seu relógio; envio no socket não comprova ACK de persistência D1.

## Situação comercial e limites

A última chamada real Windows `hostname`, ainda na .46, foi `HARA-CALL-43c74efe-5ef1-4a9a-bd16-8b5c1472c3a6`: FAILED/`LOCAL_ACTION_APPROVAL_EXPIRED` às 15:59:09Z. A aprovação humana positiva na .47 não foi comprovada. Execução, escrita protegida por SHA-256, interação e recuperação Windows pelo MCP comercial continuam pendentes.

O incidente anterior `HARA-CALL-4ea93468-2003-4c58-928f-9ce6911c378a` terminou EXPIRED no produto. A recusa e arquivos órfãos foram custodiados e reconciliados com hashes e identidades exatos; nenhum UPDATE direto de D1 ou aprovação foi fabricado. A interrupção do consumidor permanece sem causa comprovada.

Laboratório QGA, testes com transporte simulado e leitura via SSH são evidências de desenvolvimento, não prova de ação comercial autorizada por pessoa. Somente o plugin H.A.R.A. Commander direto conta para esta homologação. A VM foi ligada por solicitação do usuário pela manhã; não houve reenrollment. Distribuição Windows pública permanece .43-v3, Stripe independente, escala de mil clientes não homologada e alterações de outras frentes preservadas.
