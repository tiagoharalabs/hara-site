# HARA Commander — R12 | Estado funcional da frota e migração segura da Sentinela A
20/10/2026, 23:36–23:50 UTC. Revisão/execução operacional pelo **H.A.R.A. Commander**, sob autorização expressa do proprietário para atualizar as instalações da frota. Não usar Desktop Commander.

## Resultado, observado de verdade

**HARA Commander não havia parado na frota inteira.** Foram executados 8/8 `ping` MCP com sucesso: Services, Núcleo A, Sentinelas A/B/C/D, Ninja Blue e VM de homologação HARA_WIN11. Também foram feitas **8/8 leituras MCP de arquivos** com PASS (`/etc/os-release` nos Linux e `C:\Windows\win.ini` na VM). Estas oito instalações já cadastradas eram alcançáveis antes do cutover.

A discrepância era de versão/transporte: seis Linux internos usavam Agent **0.3.54/Event V2**, Sentinela A usava **0.3.41/relay legado**, VM Windows usa **0.3.53/relay**. Storage e Observer são nós de infraestrutura acessíveis via SSH no Services, mas **não possuem Agent principal HARA instalado/cadastrado**. A falha pública de assinatura v1/v2 e quatro hashes diferentes, reproduzida na R11, impede sua instalação pela distribuição pública atual.

## Ação executada: Sentinela A v0.3.41 → v0.3.54 Event V2

1. Pré-verificação assinada no pacote já presente exclusivamente na própria A: release `0.3.54-event-v2-fleet-20261013-1639-r2`, **FOUNDER_CANARY** vinculado ao device_id correto. Manifesto schema v2, key kid `commander-release-v2`, RSA-PKCS1v1.5/SHA256 válida com fingerprint v2 conhecido `93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`, sete arquivos correspondentes a SHA-256 e tamanho do manifest. Não utilizou chave privada. Selftest real `python3 -B .../candidate/linux_founder_event_v2.py --self-test` saiu 0 e confirmou ferramentas/recibo.
2. Preservou Agent legado 0.3.41 e `device.env` originais; não copiou segredos de outras máquinas. Um único processo HARA da A foi observado como EXITED; não havia sessão ativa de trabalho do MCP a encerrar.
3. O canal de recuperação independente foi criado **via Services→Sentinela A SSH**, sem alterar `~/.ssh/known_hosts` global: chave ED25519 do servidor A obtida diretamente pela sessão HARA e comparada a `ssh-keyscan`, guardada em `/tmp/hara-commander-a-rollout-20261020/known_hosts` sob permissão privada. SSH BatchMode com StrictHostKeyChecking passou, comprovando canal fora do Agent que seria parado.
4. Preparou **rollback automático de 3 minutos**, com timer transitório `hara-commander-a-failsafe-20261020.timer` e script usuário 0700 `~/.local/share/hara-commander/rollbacks/rollback-a-20261020.sh`. Se tivesse disparado, pararia v2 e restauraria a unidade legada. O temporizador foi desarmado **somente depois** de validação real de conectividade e funções v2.
5. O único cutover executado foi parar `hara-commander-agent.service` antigo e iniciar `hara-commander-agent-v2.service` já instalado. `systemctl --user start` passou; os demais serviços, programas de captura, computadores e modelos não foram reiniciados.
6. **Readback funcional pelo próprio Commander em Sentinela A:** `ping` retornou `agent_version=0.3.54`; `get_config` retornou 31 ferramentas e autorização `PERSISTENT_TRUSTED`; `read_file('/etc/os-release')` PASS com paginação; comando `printf; hostname; date` pelo `process.run` PASS, exit 0. Confirmada a mesma identidade de dispositivo, sem novo pareamento.
7. Comprometeu os units de boot: Event V2 **active/enabled**, legado **inactive/disabled**. Timer failsafe **inactive**. Conferido novamente às **23:50 UTC**: v2 active, legacy inactive, `NRestarts=0`, zero linhas com `Traceback/ERROR/FAIL/Exception` no journal filtrado desde 23:44 UTC e novo HARA ping 0.3.54 PASS. Script de rollback foi preservado para recuperação futura; **não foi executado**.

**Resultado:** os sete Agents Linux inscritos estão em 0.3.54 Event V2. Isto NÃO prova binários idênticos: todos os sete compartilham `public/agent/linux.py` SHA `9f27d636fa8d0b2f012bdee08dfa5996eb15d896a0da9a8dd0ba1c8b0394c58c` e `candidate/event_v2_full_agent.py` SHA `8a533885af73e46cca7140f150a15aab0ff7e0619d54647b5ab22056e798f774`, mas duas variantes do loop Event V2 coexistem com hashes `cd9ae70961cf4c68851df9866777ecc99b872656cf4f32700ac0cf394d579e76` e `f1a7d9fc4faf57185d0d2bcb17e741882db866c627967bf02e1d98754d212950`. Os manifests são assinados por máquina, e a etiqueta 0.3.54 não equivale a igualdade byte a byte.

Assinatura RSA v2, device binding, sete hashes e manifest verificados em Services, Núcleo A, Sentinelas A/B/C/D. No Ninja Blue foram verificados versão, digest do manifest e sete SHA dos assets; a tentativa de verificação RSA completa sofreu bloqueio da ferramenta nesta sessão, **não** tratá-la como PASS RSA. Não houve atualização nesses outros seis hosts: já estavam na versão interna 0.3.54.

## Hosts ainda não uniformizados — bloqueios reais de produto

- **Storage (Fedora 43) / Observer (Ubuntu 22.04):** as dependências iniciais Python, curl, systemctl --user e DBus responderam; não há Agent principal nem `device.env`. Pacote **público** foi verificado na R11 com assinatura kid `commander-release-v1`, mas instalador Linux servido exige `commander-release-v2`; os quatro hashes públicos diferem do manifesto. Instalação, enrollment e publicação continuam **HOLD** por falha verificável de integridade. Não executar instalação sem assinatura oficial, não copiar identidade de outro host e não burlar controles.
- **VM Windows HARA_WIN11:** permanece instalada na versão 0.3.53 e acessível; é VM de QA, não um nó Linux adicional. O branch Codex possui Windows 0.3.55 candidate/RC **ainda não homologado para troca nem publicamente assinado**. Não rebaixar/instalar o bundle comercial Windows 0.3.43 sem assinatura em cima do 0.3.53.
- **Produto comercial público:** o candidato local Linux 0.3.43 sem assinatura oficial não é a versão interna 0.3.54/Founder. Nenhum deploy Cloudflare, migração D1, Stripe LIVE, alteração de VM Windows ou assinatura de release foi executado nesta frente. A preparação de release imutável coeso e pré-verificação **antes de enrollment** continua prioridade P0 para o Codex.

## Pedidos precisos à frente Codex

1. Receber o readback de upgrade bem-sucedido da **Sentinela A** e atualizar inventário/capacidades com build/hash, sem reiniciar novamente. Não desativar o serviço de captura de tela da A. Validar após passagem de tempo a frescura de socket Event V2 separada do campo histórico `last_seen_at_utc`.
2. Corrigir publicação v2/v1 e 4 SHA divergentes. Publicar pacote **único, oficial, assinado, verificável do cliente**, sem misturar hashes/assinaturas de branches ou agentes internos; não consumir pairing antes do preflight assinado; validar live GET por Storage, Observer e Services.
3. Só após release público íntegro e autorização adequada, instalar independentemente em Storage/Observer com credenciais próprias de device, startup user/systemd Fedora SELinux/Ubuntu e rollback; testar `ping`, leitura, comando não mutante, eventual melhoria de segurança.
4. Windows tem RC/canal separado; provar equivalência funcional em VM e assinatura oficial antes de promover, nunca sobrescrever 0.3.53 no escuro.
5. Os seis Agents Linux que já estavam em 0.3.54 não precisam de *reinstall* pela identidade numérica; reconciliar drift de loop/build por teste e manifest, com rolling updates somente se houver release realmente mais nova e assinada.

## Reversibilidade e segurança

O rollback pré-existente da A continua disponível, **não acionado**: script `~/.local/share/hara-commander/rollbacks/rollback-a-20261020.sh`. Em emergência, operador autorizado via SSH validado no Services pode executá-lo e conferir serviço/ping. Ele desativa v2 e restaura 0.3.41 preservado, não copia credenciais. A ref/temporizador de contingência normal já foi desarmado.

A alteração da Sentinela A foi explicitamente solicitada pelo proprietário como atualização da frota. Restante da frota sem mutações produtivas. Distinguir **código corrigido**, **candidato assinado**, **Agent instalado**, **canário verificado**, **PROD comercial** — não confundir este canário Founder com lançamento ao público.
