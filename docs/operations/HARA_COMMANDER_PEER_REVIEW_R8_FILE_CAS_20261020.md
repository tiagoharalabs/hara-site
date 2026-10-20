# HARA Commander — revisão R8: duas edições concorrentes ultrapassam CAS

Data: 20/10/2026. Revisão independente por Valky, usando apenas H.A.R.A. Commander. Não alterar o checkout/índice do Codex; esta revisão pertence à branch isolada de QA `local/commander-functions-r5-review-20261020`.

## Escopo e nível de certeza

**Reproduzido em execução real das funções de arquivo do Agent sobre arquivos de teste descartáveis, usando dois processos Python distintos.** Não foi provocado incidente no laboratório, não houve edição de código ou conteúdo de cliente, não houve acesso externo nem alteração de Agents em execução.

Fonte inicial congelada: `5a6cb8d10b21a645c2418f168f3d496c0cb4f792`. Rechecado contra `a950e32ef43a6d0049d65e3db353bfc02497f1cd`, com a mesma conclusão. O hash SHA-256 do source Agent aparece nos resultados.

## R8-FILE-CAS-01 — pré-condição SHA não é transação

Arquivos examinados: `apps/commander/public/agent/linux.py`, funções `filesystem_edit`, `_enforce_file_precondition`, `_store_preimage` e `_assert_path_matches_preimage`.

O fluxo calcula SHA do conteúdo, faz snapshot/preimage e revalida path + hash. Depois prepara arquivo temporário e substitui o original por `os.replace`. Uma validação não impede que outra instância tenha validado o mesmo conteúdo antes e escreva seu próprio resultado depois.

Para demonstrar sem depender de timing aleatório, o QA instrumenta somente a chamada à função de validação, *depois que a verificação real passou*, com uma barreira entre dois processos OS distintos. As operações `filesystem_edit`, preimage, hash, escrita e `os.replace` permanecem as funções reais.

Controle sequencial: `BASE` → `FIRST` com o SHA de `BASE`; tentar outra alteração com o mesmo SHA foi corretamente recusado por `FILE_PRECONDITION_FAILED`.

Execução concorrente: dois processos leem `BASE`, cada qual valida o mesmo SHA e deseja `WRITER_A` ou `WRITER_B`. **As duas operações retornaram ACEITA e `precondition_checked=true` com `previous_sha256` idêntico ao de BASE. O arquivo final contém somente a última alteração.** Na primeira execução o arquivo terminou em WRITER_B; na repetição no commit mais recente, em WRITER_A. Ambas mostram o risco de perda silenciosa da edição anterior.

A barreira é artificial e não prova ocorrência dessa simultaneidade no transporte comercial atual. Porém o teste executou realmente duas instâncias Python independentes, situação relevante caso vários processos de MCP local ou outros executores compartilhem o mesmo workspace. A proteção `PREIMAGE_CUSTODY_LOCK` coordena a guarda da preimagem apenas dentro de uma instância; ela não torna atômico o CAS até a conclusão da alteração.

**Classificação:** P1 para adoção operacional paralela do produto; elevar para P0 do release somente se confirmada uma superfície cliente que permite gravadores simultâneos no mesmo alvo sem outro serializador. Não desabilitar preimage/rollback nem alegar falha de tenant isolation; essa não foi testada.

## Proposta de correção e critérios

- As operações de escrita/edição/append/rollback com pré-condição devem coordenar a validação, guarda da preimagem e alteração **no mesmo escopo de exclusão** para os escritores cooperantes. Se houver mais de um processo Agent local, lock exclusivamente em memória não é suficiente.
- Usar lock estável por caminho canônico (ou mecanismo equivalente devidamente testado) entre processos/threads do mesmo usuário e manter a proteção durante o CAS e a substituição. Não guardar um lock enquanto espera rede/pagamento/IA. Planejar ordenação para operações de dois caminhos (move/copy) e evitar deadlocks. Locks cooperativos não garantem exclusão de editores externos que não participem do protocolo.
- Na disputa com SHA antigo, exatamente **uma** alteração deve ser aceita e a outra deve falhar com `FILE_PRECONDITION_FAILED`, sem sobrescrita nem preimagem incorreta.
- Testar também `filesystem_write` rewrite e append, duas ou vinte entradas concorrentes, instâncias Python distintas, timeout/cancelamento, falha após preimage, falha do temp/rename, symlink, processos com usuários/AGENT_DATA diferentes e recuperação segura.
- Preservar os recibos e replay idempotente: retry da mesma requisição não pode gerar outra mutação, e sucesso não implica que o texto de um escritor ficou presente se outro ALTEROU depois. Não prometer transação com softwares terceiros sem prova.

## Arquivos de prova

`docs/evidence/commander-peer-review-r8-20261020/`:

- `peer_file_cas_race.py`: harness real com dois processos, que só opera em HOME/XDG e arquivo temporários. Exit **2** indica risco reproduzido, **não** teste aprovado.
- `r8-initial-results.json` e `r8-latest-results.json`: teste sequencial positivo, dois escritores admitidos e hash/conteúdo finais em commits diferentes.
- `README.md` e `SHA256SUMS`: reprodução e integridade.

Nenhum processo ou arquivo da frota produtiva foi encerrado/modificado. A frente executora permanece em `codex/commander-prelaunch-fixes-20261020`. Quando a correção for incorporada, reexecutar o caso negativo e provar que deixa de reproduzir, com preservação dos testes sequenciais existentes. Não substituir esta repro por um teste que apenas verifica se uma função de locking está presente.
