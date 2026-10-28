# Conexão e pareamento — evidência de 28/10/2026

**Estado deste checkpoint:** controladores instalados e executados nas duas VMs reais; 23 testes isolados do controlador Windows, 14 testes isolados de transação Windows e 24 testes locais Linux aprovados. Os instaladores candidatos deste checkpoint ainda são fonte sem uma nova assinatura; não foram executados como instaladores nas máquinas.

Todos os horários em texto são de Brasília; os recibos preservam UTC.

## Vínculos reais

- **Windows 11**, domínio `hara-review-win11-restoretest-20261024`: o pareamento real concluiu às **13:37**, Agent 0.3.56 na origem de produção. Às **14:10**, o novo controlador reconheceu o vínculo, confirmou conexão e retornou `CONNECTED_UPDATE_HOLD`: catálogo antigo rejeitado por `RELEASE_SIGNATURE_INVALID`. Não solicitou outro código. Configuração, Agent e política CurrentUser preservados.
- **Ubuntu**, domínio `hara-review-linux`: Agent 0.3.56 já pareado no ambiente de desenvolvimento. Heartbeat autenticado HTTP 200 às **13:47**. Às **13:58**, o controlador retornou `PAIRING_VALID_UPDATE_HOLD / AUTO_DOWNGRADE_REFUSED`, pois o canal assinado oferecia 0.3.54. Configuração, Agent e symlink original do CLI preservados.

Os dois domínios foram acessados pela Sentinela B física, na conexão libvirt `qemu:///system`. Não foi criada outra VM, removido um vínculo válido ou trocada a origem da VM Ubuntu.

## Pontos de entrada instalados

Windows, perfil CommanderQA:

- Área de Trabalho: **Conectar HARA Commander.lnk**.
- Pasta **HARA Commander Conexao QA**, contendo o controlador, CMD e instruções.
- SHA do controlador: `2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da`.

Ubuntu, perfil commanderqa:

- Comando `hara-commander-connect`.
- Controlador em `/home/commanderqa/.local/share/hara-commander-connect-qa/commander_connect.py`.
- Entrada **Conectar HARA Commander** na Área de Trabalho e no menu de aplicativos.
- SHA do controlador: `a696a233e81b1b89b536fd4097af7b571762c953e54266cba49349308db74c1d`.

O controlador foi executado de fato em ambas as VMs. No Ubuntu, a entrada de menu foi validada; a marcação de confiança do arquivo Desktop não era suportada pelo serviço de metadados presente, portanto não se declara um clique gráfico comprovado. O CLI original do Agent não foi substituído.

## Testes dirigidos e correção de recuperação

**Windows/PowerShell 5.1, usuário CommanderQA limitado:**

- **23/23** testes do controlador às 14:09: já pareado, pedir código apenas quando necessário, atualização mais nova, rejeição de assinatura/hash inválidos, erro de rede e preservação de vínculo.
- **14/14** testes da transação de pareamento às **14:37:24**. Operações de arquivos, permissões e DPAPI foram reais em diretórios temporários; rede, enrollment e Task Scheduler foram simulados. Nenhum token real foi criado ou consumido por estes testes.
- Os testes finais também exigem recuperação dos bytes de configuração, Agent e runtime, credencial DPAPI anterior, estado de execução, permissões e remoção do diretório temporário após recuperação confirmada.
- Parser nativo aprovado para o helper, harness e instalador candidato final.
- A configuração, o Agent e a política de execução reais foram conferidos e preservados antes/depois.

O diagnóstico encontrou `PrivilegeNotHeldException` ao reaplicar um descritor completo com `Set-Acl`. A correção restaura apenas a seção de acesso, sem alterar proprietário, grupo ou auditoria. O Windows normaliza o marcador `AUTO_INHERITED`; o recibo R5 demonstrou DACL byte a byte idêntica, mesmo proprietário, grupo e proteção, com diferença apenas nesse marcador. A verificação final admite somente esse marcador (`0x400`); todos os demais bits, ACEs, direitos e ordem continuam exatos.

Os recibos de falha R3/R4/R5 foram preservados. O PASS final R6 não reinterpreta aqueles resultados.

**Linux:** 24 testes sintéticos aprovados, incluindo assinatura efêmera, seleção de versão, tratamento de vínculo, recuperação de arquivos e incorporação exata do controlador no instalador.

## Catálogo e limite de release

A consulta usando o User-Agent real do aplicativo retornou HTTP 200 nas duas origens. Produção ainda anunciava 0.3.41; desenvolvimento, 0.3.54. A consulta inicial com o User-Agent padrão do Python recebeu 403 e não é tratada como indisponibilidade do canal do aplicativo.

O novo fluxo está incorporado nos instaladores candidatos de fonte. Continua faltando neste checkpoint comprovar o pareamento real da candidata numa instalação sem vínculo e a atualização para uma candidata nova assinada. As duas VMs já pareadas não devem ser despareadas para fabricar esse cenário.

**Lançamento público continua NO-GO.** Os recibos daqui não promovem arquivos públicos nem encerram os gates de release, resiliência e revisão externa.

## Recibos

- [Pareamento Windows concluído](windows-pairing-confirmed.json)
- [Heartbeat Ubuntu](linux-connection-confirmed.json)
- [Consulta aos catálogos](release-readback.json)
- [Controlador Windows na conexão real](windows-connect-native.json)
- [Controlador Linux na conexão real](linux-connect-native.json)
- [23 testes do controlador Windows](windows-controller-fixtures.json)
- [14 testes finais de transação Windows](windows-transactions-native.json)
- [Diagnóstico inicial de permissões](windows-transactions-diagnostic.json)
- [Recuperação com verificação reforçada](windows-transactions-r4.json)
- [Diagnóstico do marcador nativo](windows-transactions-r5-diagnostic.json)
