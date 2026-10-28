# Commander 0.3.56 — componentes nativos Windows QA

**Resultado: PASS_NATIVE_COMPONENTS_NOT_RELEASE_APPROVAL.** Execução real em Windows 11 Pro, conta existente `CommanderQA` sem privilégios administrativos, com perfil carregado e sessão interativa.

Janela: **27/10/2026, 20:58:08–20:59:11**, horário de São Paulo; os timestamps UTC exatos estão no JSON. O processo administrativo terminou com exit0, sem truncamento da captura.

## O que passou

| Etapa | Resultado observado |
|---|---|
| Preparação | Seis arquivos com SHA-256 e ACL verificados; parser PS5.1 dos scripts sem erros. |
| Agent `--version` | Versão 0.3.56, exit0. |
| Agent `--self-test` | Comando real do artefato exato, exit0. Este registro não atribui uma contagem adicional ao self-test. |
| Job Objects | **6 verificações nativas**: atribuição e handshake, encerramento do Job, coleta de worker e descendente, morte abrupta do guardião e ausência da árvore órfã testada. |
| Contexto de usuário | **13 verificações**, incluindo identidade/perfil/token padrão, pin do artefato, DACL privada, DPAPI pai↔filho e tarefa temporária Interactive/Limited registrada, executada e removida. |

Job Objects e contexto de usuário executaram em **Windows PowerShell 5.1.26100.9711**. A tarefa temporária foi registrada e executada de verdade pela conta padrão; não houve simulação do agendador ou elevação do usuário QA.

O Agent testado tem 172.687 bytes e SHA-256 `a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620`. Os bytes do produto não foram alterados nesta rodada.

## Política e encerramento

O bootstrap registrou e aplicou **CurrentUser `Undefined` → `RemoteSigned` → `Undefined`**, com restauração confirmada. A política do processo do runner permaneceu `Undefined`; os testes registraram a política efetiva `RemoteSigned`. Não foi utilizado `Bypass`.

A tarefa bootstrap foi removida. O fixture de contexto confirmou encerramento do filho, remoção da tarefa de teste e ausência de seu diretório temporário. A tarefa antiga **HARA Commander Agent** permaneceu **Disabled**, com o mesmo hash XML antes e depois. Essa prova vem das leituras administrativas: a enumeração limitada do usuário QA não expunha a tarefa antiga e não é usada como prova de ausência global.

**Fechamento independente posterior: PASS_INDEPENDENT_NATIVE_CLOSEOUT**, observado em **27/10/2026 às 21:04:38**, horário de São Paulo. Uma nova leitura confirmou CurrentUser `Undefined`, a tarefa original `Disabled` com o mesmo hash XML, sessão `CommanderQA` e **zero tarefas temporárias, zero processos de fixture e zero diretórios de fixture**. A leitura continuou registrando `installed=false` e `paired=false`.

## Alvo atual e resultados anteriores

O inventário posterior confirmou exatamente duas VMs em `qemu:///system`: `hara-review-linux` e `hara-review-win11-restoretest-20261024`, ambas ativas naquele readback. O teste aqui documentado executou na segunda, usando a conta já existente `CommanderQA`. O nome histórico “restoretest” não transforma este teste em um aceite de restauração.

A tentativa de checkpoint frio anterior continua **HOLD**: a cópia atingiu o prazo de 240 segundos. O boot da imagem original foi verificado, sem substituição de seus arquivos e sem alteração das outras VMs no fechamento daquela tentativa. Não houve restore materializado aprovado.

O primeiro staging vinculado ao domínio Windows original parou porque esse domínio não estava mais definido. Não foi redirecionado automaticamente. O alvo ativo foi inspecionado novamente e recebeu um vínculo explícito em arquivos separados. O responsável ou a causa da mudança de definições não foi determinado por estas evidências.

## Limite do aceite

**O Agent não foi instalado nem pareado nesta execução. O lançamento público continua sem aprovação por estes testes.** O DPAPI usa um payload sintético novo na conta atual; não prova migração de dados protegidos de outra conta. O teste de ACL verifica a DACL real, e o teste de Task Scheduler cobre a tarefa temporária, não o ciclo completo do instalador do produto.

Os 13 checks incluem pré-condições e identidade do artefato; não são 13 cenários independentes de DPAPI. Instalação, pareamento, ciclo da tarefa do produto, recuperação sob falhas e release conservam seus critérios próprios. A VM Linux possui evidência separada. O fechamento independente posterior está incluído neste registro.

## Rastreabilidade

[windows-native-components-summary.json](windows-native-components-summary.json) contém os resultados selecionados, contagens, tempos, hashes dos arquivos preparados, hashes das capturas e referências aos recibos retidos. Não inclui credenciais, configuração privada ou transcrições brutas.
