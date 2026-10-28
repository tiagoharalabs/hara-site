# Commander 0.3.57 — checkpoint da candidata privada

**Data:** 28/10/2026. **Escopo:** candidata assinada e validação nas duas VMs existentes da Sentinela B. **Lançamento público: NO-GO.**

Este é o checkpoint histórico da **0.3.57**. As atualizações e verificações posteriores da 0.3.58/0.3.59 estão no [fechamento de continuidade](../CLOSEOUT-20261028.md); não alteram os resultados registrados abaixo.

**Estado operacional deste checkpoint:** Ubuntu atualizado e conectado na 0.3.57. Windows recusou a atualização; os bytes da 0.3.56 e o vínculo foram preservados, mas a retomada do runtime ainda não foi comprovada. A investigação de inicialização Windows continua aberta.

Este documento sucede o checkpoint de fonte do commit `b4711138ca922dbdc7edcee998b19c860c78fb69`. Os relatórios anteriores permanecem como registros da etapa em que foram produzidos; uma assinatura ou um teste posterior não altera retroativamente seus resultados.

## Fluxo entregue na fonte

O comando **Conectar HARA Commander** verifica o vínculo existente. Uma máquina pareada reutiliza sua credencial e procura uma versão mais recente verificável. Uma instalação sem vínculo orienta o login no portal, solicita o código de pareamento gerado pelo usuário, valida o vínculo e segue para a atualização. Falha de rede ou de catálogo não deve pedir outro código nem substituir uma conexão válida.

Os controladores congelados estão incorporados nos instaladores da candidata 0.3.57. A preparação preservou seus bytes e alterou somente as declarações de versão dos Agents e os oito/cinco literais de versão dos instaladores Linux/Windows, respectivamente. A release assinada 0.3.56 permanece imutável.

## Construção e assinatura verificadas

O [`BUILD-REPORT.json`](BUILD-REPORT.json) registra a construção determinística, ainda sem assinatura. O [`SIGNATURE-REPORT.json`](SIGNATURE-REPORT.json) registra a assinatura real com a chave existente `commander-release-v2`; o [`SIGNATURE-READBACK.json`](SIGNATURE-READBACK.json) registra sua verificação independente, incluindo os quatro artefatos. A chave privada permaneceu no host autorizado e não integra esta entrega.

| Artefato | Bytes | SHA-256 |
| --- | ---: | --- |
| Agent Linux | 265620 | `79c7a7ac51432158ea503dbaf3830d41f1e30deb8585513a7d0e504aed9fbe13` |
| Agent Windows | 172687 | `3552947e632ba16eb0a1384b8e6b0d3a84d507bbe156ff1bb4db360c212895b7` |
| Instalador Linux | 72524 | `2b11dd4cb5219d64692d9df764544752c04f4cb2518742d5c54a3f631178cbed` |
| Instalador Windows | 76549 | `cc6234d0d51e853d9b1a897d496038ceba8b9164d318a70d98f62a7bae3c07ff` |

Manifesto: `d1a9361f5edec6c926d6febc7990e9b0c00df28f5131c6ffe1146ebe348554d0`. Arquivo de assinatura: `5637d5861c49c170af55a8d86f8051df78785c39f4a17b06a41b5c8ed25ddef7`.

Assinar a candidata não promove o catálogo público, não comprova execução nativa e não representa aprovação de release. O campo `intended_event_v2` do relatório é intenção; somente uma observação explícita do runtime pode comprovar seu estado.

## Evidência operacional já concluída

As duas VMs pertencem à conexão `qemu:///system` da Sentinela B física. Todos os horários abaixo são de Brasília; os recibos preservam UTC.

| VM existente | Resultado real anterior à atualização 0.3.57 |
| --- | --- |
| `hara-review-win11-restoretest-20261024` | Pareamento real 0.3.56 concluído às 13:37 na origem de produção. Às 14:10 o novo controlador confirmou vínculo e conexão, sem pedir código. A atualização ficou suspensa por assinatura inválida do catálogo histórico. |
| `hara-review-linux` | Agent 0.3.56 com heartbeat autenticado HTTP 200 às 13:47 na origem de desenvolvimento. Às 13:58 o novo controlador preservou o vínculo e recusou downgrade para 0.3.54, sem pedir código. |

Os recibos correspondentes estão no [checkpoint operacional de conexão](https://github.com/tiagoharalabs/hara-site/blob/b4711138ca922dbdc7edcee998b19c860c78fb69/docs/evidence/commander-commercial-056-20261023/continuation-20261027/connect-flow-20261028/README.md). Nenhum desses resultados comprova um pareamento novo realizado pela candidata 0.3.57.

### Testes isolados concluídos

- **Windows:** 23 testes do controlador e 14 testes finais da transação, executados nativamente no PowerShell 5.1 como CommanderQA limitado. Arquivos temporários, ACL e DPAPI foram reais; rede, enrollment e Task Scheduler dos cenários foram simulados. Configuração, Agent e política da instalação real foram preservados.
- **Linux:** 24 testes sintéticos locais, cobrindo seleção de versão, vínculo, validação de assinatura, recuperação e incorporação do controlador.
- Os resultados finais incluem a correção de recuperação de ACL no Windows. Os recibos anteriores de falha continuam preservados.

## Atualização real 0.3.56 → 0.3.57

| Plataforma | Caminho de validação autorizado | Resultado desta etapa |
| --- | --- | --- |
| Windows | Núcleo do controlador congelado, versão privada HTTPS explícita, somente ação `update`, usuário CommanderQA limitado | **HOLD.** Assinatura/payload conferidos; atualização falhou ao atestar a inicialização. Agent 0.3.56, configuração e vínculo preservados, tarefa sem execução confirmada. Recuperação independente também ficou em HOLD. |
| Ubuntu | Ação `update` do instalador assinado, versão privada HTTPS explícita, usuário commanderqa | **PASS em 15:21:45 Brasília / 18:21:45 UTC.** Agent 0.3.57 com hash exato, serviço ativo, runtime novo, heartbeat autenticado HTTP 200, configuração/unidade/CLI/política preservados. |

O aceite exige a versão/hash 0.3.57 em execução, início e heartbeat novos, credencial autenticada e preservação do vínculo, da configuração, da política e da definição de execução. O teste Ubuntu satisfaz esses requisitos pelo caminho explícito de atualização; a descoberta automática do controlador permanece restrita à origem configurada. O resultado não certifica descoberta automática pelo catálogo padrão.

### Ubuntu: atualização real concluída na segunda tentativa

O recibo [`linux-upgrade-attempt-2.json`](evidence/linux-upgrade-attempt-2.json) registra `PASS_DIRECT_SIGNED_0357_UPDATE`, saída zero do instalador e `TARGET_INSTALLED_AND_CONNECTED`. O runtime 0.3.57 iniciou às 18:21:43 UTC e publicou heartbeat às 18:21:44 UTC; a verificação autenticada independente retornou HTTP 200 para o mesmo dispositivo. Configuração, política `PERSISTENT_TRUSTED`, unidade systemd, CLI e origem de desenvolvimento foram preservados. O arquivo de recuperação contém exatamente o Agent anterior.

A [primeira tentativa](evidence/linux-upgrade-attempt-1.json) havia terminado em `HOLD`, antes de substituir o Agent; a 0.3.56 permaneceu ativa, com credencial validada e configuração preservada. O [diagnóstico isolado do self-test](evidence/linux-selftest-diagnostic-1.json) executou uma cópia privada instrumentada, preservou a assertiva original e observou `EXITED`, `exit_code=7` e `process_exit_code=7`, sem instalar essa cópia. Isso não estabelece a causa da falha inicial. A segunda tentativa usou **os mesmos bytes assinados** da candidata; o primeiro HOLD não foi reclassificado como PASS.

### Windows: falha de inicialização ainda em investigação

O recibo [`windows-upgrade-attempt-1.json`](evidence/windows-upgrade-attempt-1.json) registra uma única invocação de `update`, assinatura privada verificada e nenhuma ação de pareamento. O instalador retornou falha; a observação independente encontrou o Agent original 0.3.56 e configuração, vínculo, política e XML da tarefa preservados. A credencial continuava autenticando, mas a tarefa não estava em execução. Um heartbeat anterior recente não foi aceito como prova de recuperação.

O [diagnóstico e tentativa de recuperação do original](evidence/windows-original-recovery-attempt-1.json) identificou `AGENT_UPDATE_START_FAILED` e `HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=STARTUP_ATTESTATION_FAILED`. A tentativa de reiniciar o original também não comprovou heartbeat novo e terminou em `FRESH_RUNTIME_HEARTBEAT_NOT_CONFIRMED`. Portanto, **não há aceite da atualização Windows nem da recuperação de seu runtime neste checkpoint**. O diagnóstico nativo seguinte deverá ter seu próprio recibo; sua preparação não muda esse resultado.

Os drivers não removem pareamentos, não consomem novos códigos e não transferem o Ubuntu de desenvolvimento para produção. O instalador assinado é responsável por sua transação e recuperação. Logs completos e preimagens privadas de configuração ficam nas VMs; somente recibos sanitizados devem entrar no repositório.

## Distribuição e pendências de release

A distribuição privada tem escopo restrito às duas VMs, arquivos assinados fixos e expiração máxima em 28/10/2026 às **15:40 Brasília / 18:40 UTC**. O encerramento deve ser confirmado por recibo que comprove ausência do listener e das regras temporárias. Um horário futuro de expiração não é prova de limpeza realizada.

O catálogo de produção observado anuncia **0.3.41**, com a assinatura histórica v1 rejeitada pelo cliente v2. Desenvolvimento anuncia **0.3.54**, anterior à instalação 0.3.56. A candidata privada não corrige esses catálogos. A promoção exige manifesto, assinatura, quatro artefatos imutáveis e bootstrap web coerentes, seguida de validação pelo caminho público.

Continuam sem aceite neste checkpoint: atualização e recuperação de runtime no Windows, pareamento real da candidata em instalação sem vínculo com a conta pretendida, descoberta/atualização pelo canal público, publicação e revisão externa. Uma VM validamente pareada não deve ser despareada para produzir artificialmente um teste de primeira conexão.

**O resultado desta etapa é uma candidata privada assinada com evidência rastreável; o lançamento público continua NO-GO.**
