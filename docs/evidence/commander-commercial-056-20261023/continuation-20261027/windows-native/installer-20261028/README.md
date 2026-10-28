# Windows QA — instalador acionável e preflight nativo

Atualização observada em **2026-10-28 02:50:18 UTC** (27/10, 23:50:18 em Brasília).

**Estado: instalação e pareamento pendentes. Release pública: NO-GO.**

## Alvo exato

- Host físico: Sentinela B, conexão `qemu:///system`.
- VM: `hara-review-win11-restoretest-20261024`, título **VM Win11 Sent B**.
- UUID: `154e2853-3d1d-4d23-a43d-706f76ad7939`.
- Sessão: `HARA_WIN11\\CommanderQA`, padrão e interativa.
- Conta HARA Identity pretendida: `openai-reviewer@haralabs.com.br`.

O usuário Windows e a conta HARA Identity são distintos. Nenhuma senha foi alterada.
A senha do Identity não foi recuperada; a imagem fornecida pelo usuário mostra uma entrada salva no Brave do Núcleo A. O histórico e o navegador disponíveis nesta execução não permitiram recuperar/reutilizar esse acesso.

## Entregue e observado

| Entrega | Evidência |
| --- | --- |
| Entrada acionável por dois cliques | `Instalar-Commander.cmd` e `Verificar-Commander.cmd`, com wrapper fixado por hash. |
| Atalhos na Área de Trabalho | **Instalar HARA Commander** e **Verificar HARA Commander**, alvo/argumentos e proprietário conferidos. |
| Instalador real .56 | SHA-256 `2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401`; não foi substituído por simulação. |
| Preflight nativo | **PASS_NATIVE_PREFLIGHT**, exit0, às 02:39:18Z, através do CMD real, em PowerShell 5.1 sob CommanderQA. |
| Verificações do preflight | Saúde Commander, manifesto .56, assinatura e requisitos de tarefa passaram. |
| Política de execução | CurrentUser voltou para `Undefined` após o preflight. |
| Conflito da tarefa antiga | XML e SDDL da tarefa desativada de sarti arquivados; tarefa removida às 02:42:30Z sem execução; nome global disponível para CommanderQA. |
| Instruções e resultados locais | Atualizados na pasta `C:\\Users\\CommanderQA\\Desktop\\HARA Commander 0.3.56 QA`, com hashes. |

O preflight retornou `mutation_performed=false` para o produto. A preparação administrativa de arquivos, confiança temporária e tarefa antiga é registrada separadamente nos recibos. **O Agent ainda não estava instalado nem pareado no readback final.**

## Distribuição e certificado temporários

A URL pública específica .56 retornou **404**; o manifesto público sem versão continuava informando **0.3.41** nesta execução. Portanto a campanha usou distribuição HTTPS privada e temporária, restrita ao IP desta VM e a oito artefatos estáticos fixados por hash. Não se promoveu a release pública.

As tentativas iniciais de importar o certificado em CurrentUser aguardaram confirmação do Windows; a tentativa com certutil atingiu seu limite de 45 segundos e foi recuperada. Isso não constitui PASS de importação desassistida. O R4 aprovado usou o certificado público exato provisionado pelo operador administrativo no LocalMachine Root desta VM dedicada, preservando validação TLS e verificação de assinatura. A chave privada não foi transferida.

O serviço foi limitado a uma hora, desde 02:08:57Z, com remoção de regras de firewall em ExecStopPost. A remoção do certificado foi **agendada para 03:09:00Z / startup**. No readback de 02:50:18Z, essa tarefa estava Ready, sob SYSTEM. **Agendamento não é evidência de limpeza executada.** Verificar recibos e estado nativo após a janela. Se a janela expirou, a preparação temporária precisa ser renovada antes de instalar.

## Próxima dependência concreta

Obter um código de pareamento legítimo na conta **OpenAI Reviewer**, usando login fresco no portal Commander e **Gerar código**. O código é de uso único e expira em dez minutos. Não usar a senha do Identity no prompt de pairing. Não se gerou token administrativo, não se forjou sessão e não se modificou autenticação.

Depois do código: executar a instalação real no mesmo CommanderQA, conferir Agent/config/tarefa/heartbeat e completar instalação, reinstalação, desinstalação e rollback conforme os gates aplicáveis. A autorização de Tiago continua válida; a dependência é acesso autenticado, não nova autorização genérica.

Os testes anteriores de componentes (6 JobObject e 13 de contexto de usuário) e a correção de rede continuam documentados no diretório pai. Eles, junto com este preflight, não encerram #240, #310 ou #322.

## Arquivos de evidência

- [Readback nativo selecionado](evidence/final-readback.json).
- [Contrato e limites dos launchers](launcher/README-launcher.md).
- `helpers/`: fontes exatas de preparação e execução desta campanha, vinculadas ao alvo e à janela acima. São registros operacionais, não um instalador genérico para executar novamente.
