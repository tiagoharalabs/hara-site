# Windows QA R6: reentrada após distribuição encerrada

Data: 28/10/2026. Todos os horários com Z são UTC; Brasília está três horas atrás nesta data.

## Resultado concreto

R6 foi instalado nos três arquivos de entrada do Desktop de CommanderQA na VM existente `hara-review-win11-restoretest-20261024` (UUID `154e2853-3d1d-4d23-a43d-706f76ad7939`) da máquina física Sentinela B. O instalador assinado .56 permaneceu byte a byte igual. A cópia anterior R5 foi preservada e validada em `backup/r5-before-r6` antes da atualização.

A validação foi feita no PowerShell 5.1 real, na sessão limitada de `HARA_WIN11\\CommanderQA`, SID `S-1-5-21-1207901905-1500652706-889822281-1005`:

| Caso | Resultado | Hora UTC |
|---|---|---|
| Parser e hashes dos launchers, cópia R5 e instalador original | R6_LAUNCHERS_VERIFIED; zero erros de parser | Rodada atual |
| Configuração R2 vencida | PASS_NATIVE_EXPIRED_GUARD | 15:55:36Z |
| Janela R3 disponível | PASS_NATIVE_PREFLIGHT | 15:56:50Z |
| Inicialização interativa supervisionada | INSTALLER_RUNNING sob CommanderQA | 16:03:33Z |
| Inspeção do produto e atualização das instruções | Sem configuração/tarefa de produto; pareamento pendente | 16:06:21Z |

O caso vencido retornou `QA_RELEASE_WINDOW_EXPIRED` antes de chamar o preflight oficial, baixar o Agent ou solicitar código. A política de execução permaneceu RemoteSigned e não houve configuração nem tarefa de produto.

O caso atual comprovou HTTPS 200, preflight oficial com assinatura válida e o Agent completo: **172.687 bytes**, versão **0.3.56**, SHA256 `a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620`. O cache foi removido e a política foi preservada. O hash do instalador assinado continua `2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401`.

**Esses resultados não são instalação/pareamento concluídos.** Até a leitura registrada, não havia pareamento comprovado nem comprovação de inventário/MCP no escopo da conta reviewer. A integração Browser respondeu que exige o contexto do navegador de origem; não houve extração de cookies, troca de senha ou emissão de sessão alternativa.

## Por que a nova tentativa falhou

O registro de 05:18:12Z mostra R5 em `PREFLIGHT_BEGIN`, `NATIVE_OPERATION_FAILED`, sem payload verificado e sem instalação/pareamento. A distribuição temporária R2 havia sido encerrada a pedido do usuário na pausa: listener/regras encerrados às 05:03Z e certificado temporário removido. Depois, o usuário autorizou a retomada. O atalho permanecia disponível, mas a preparação de rede/confiança não estava mais ativa. R5 não expunha essa distinção com clareza.

R6 agora confere a validade da janela antes de qualquer preparação de confiança e faz um GET limitado do manifesto na URL configurada, com TLS normal e sem redirecionamento. Falhas recebem `QA_RELEASE_UNAVAILABLE` ou `QA_RELEASE_RESPONSE_INVALID`, com metadados limitados de transporte. Essa consulta apenas comprova disponibilidade; as verificações posteriores de assinatura, bytes, SHA e versão continuam obrigatórias.

A janela antiga usada no teste negativo não foi falsificada nem prorrogada para produzir PASS. Os dois casos tiveram tarefas, arquivos e execuções QGA independentes, com readback administrativo do estado do produto.

## Janela R3

O servidor da Sentinela B foi reaberto às **15:53:46Z**, com duração máxima de **10.800 segundos** tanto no processo quanto no systemd. Aceita apenas a VM Windows QA `192.168.252.113/32` e serve os oito arquivos .56 fixados em memória. A URL é `https://192.168.10.23:18443/releases/0.3.56`. As regras têm limpeza automática; nenhum endpoint de API ou upload foi adicionado.

Um certificado novo evita conflito com os agendamentos antigos de limpeza. DER SHA256 `893aeec40a123d5fd74fd312fa1ed90e4c9881e10a562cdc126026c3d848f29e`; thumbprint `91455FF01AE18E0F3721E3D56B5382A1F4145129`. Foi adicionado pela API normal de certificados à VM de QA. A tarefa `HARA-QA056-TemporaryTLS-Cleanup-R3-20261028` está agendada para **18:54:45Z** e no startup. A execução futura dessa limpeza ainda precisa de readback; não está declarada como já realizada.

O supervisor interativo iniciou CMD PID2164, wrapper PID3128 e instalador filho PID6088 sob o SID QA. Sua janela termina até **17:32:57Z** (14h32 de Brasília), antes da distribuição. Ele usa taskkill /T /F ao alcançar o limite, confere a saída do pai e registra HOLD se não confirmar término. O encerramento da janela não prova encerramento de todos os descendentes, rollback ou sucesso do produto; esses estados exigem leitura independente. Os scripts desta rodada são históricos e finitos, com guardas de criação única; não devem ser repetidos cegamente quando a janela terminar.

## Ubuntu e fluxo público

A leitura atual da VM `hara-review-linux`, UUID `d7a27a4a-41c3-4c14-a84e-187443566a3c`, às 15:48:46Z, confirmou .56 instalado para `commanderqa` UID2000. SHA do Agent: `ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d`. A origem é **desenvolvimento**, `https://hara-commander-dev-v2.tiago-sartori.workers.dev`, dispositivo `HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889`; o runtime havia sido atualizado às 15:48:11Z. A instalação foi preservada. O inventário principal de produção/Founder não é prova de visibilidade desse registro pela conta reviewer; a correspondência de ambiente e titular ainda precisa ser validada.

O readback público às **15:57:04Z** confirmou que o site ainda entrega manifesto **0.3.41**, Agent Windows **0.3.52** e instalador com o hash anterior da **0.3.49**. Os quatro assets continuam divergentes do manifesto. R6 não corrige nem promove essa distribuição pública. O pacote histórico assinado .43-v4 foi localizado e conferido, mas não foi restaurado sem reconciliar compatibilidade, aceites e a versão atual do Worker. A versão ativa identificada anteriormente nesta rodada era `8b6d44ce-dd16-4dbb-aa1a-114153c53851`; nenhuma mutação de produção foi feita.

O Desktop agora explica o caminho correto desta rodada: usar o portal com `openai-reviewer@haralabs.com.br` para gerar o código e inserir somente esse código no instalador QA aberto. O comando público não deve ser tratado como alternativa funcional. LEIA-ME, resultado e checksums foram atualizados com preimagem local.

**Release pública: NO-GO.** Pareamento Windows, propriedade/visibilidade no escopo reviewer, lifecycle, distribuição pública e demais gates do quadro #310 continuam abertos. Não houve alteração de senha, assinatura nova de release, publicação OpenAI, merge em main ou promoção comercial nesta rodada.

## Evidências e fontes

- `native-reentry.json`: as duas validações nativas, pins, distribuição, confiança e leitura Ubuntu/pública.
- `interactive.json`: processo interativo, identidade, prazo e estado observado do produto.
- `helpers/`: fontes exatas dos launchers, driver, servidor, limpeza e supervisor utilizados.
- `source-proposal/`, quando presente: proposta separada de preflight no instalador fonte. Não assinada, não instalada e sem teste nativo executado nesta rodada.
