# R8 — revalidação do executor

Em 20/10/2026, li a revisão R8 de Valky e preservei os cinco arquivos de prova dos commits `c833bd3`/`55facec` sem edição. `sha256sum -c SHA256SUMS` passou (exit 0). O Markdown R8 já presente neste clone é idêntico ao blob do commit `c833bd3`. Nenhum Agent ativo, arquivo de cliente ou rede externa foi usado.

| Fonte | Teste | Exit | Resultado |
| --- | --- | ---: | --- |
| `185ac234d5b2ed4f3af168c4407edd155d258881`, Agent SHA-256 `fcb493e6...37abec` | Harness original da revisão, em `git archive` temporário | 2 | Dois editores aceitaram o mesmo SHA; só a última edição permaneceu |
| Mesma fonte | Novo `validate_file_cas_atomicity.py --source .../linux.py` | 1 | Controle sequencial passou; os dois editores foram aceitos, como esperado antes do patch |
| `442eeac6a71cf3f389a305c0fcda21dd51294234`, Agent SHA-256 `e6dce5da...7c5190` | Novo validador com funções reais e processos OS distintos | 0 | Exatamente um aceite e um `FILE_PRECONDITION_FAILED` em edit/rewrite/append/delete; 20 editores, threads, alias de parent symlink, timeout, morte do holder e falha de rename cobertos |
| Mesma fonte | Harness da revisão em cópia temporária, com barreira deslocada para **antes** de entrar na mutação | 0 | Um aceite e um conflito; preimage e arquivo final corretos |

O harness histórico instala a barreira **depois** da revalidação SHA. Após a correção, o primeiro processo segura o lock e espera o segundo, que corretamente não pode chegar à barreira; executar esse harness sem adaptação mede um timeout da própria fixture. A cópia temporária removeu somente o interceptador pós-validação, esperou na mesma barreira antes de chamar `filesystem_edit` e corrigiu a descrição de `scope` no relatório. O original importado permanece com os hashes da revisão. O validador novo usa início sincronizado antes da operação e atraso após a verificação real para tornar a corrida anterior observável sem bloquear uma implementação correta.

Relatórios locais: `executor-before-185ac.json` (SHA-256 `d05c3c7c0e85f94743af561f5dbbbd098a405f85c14f90725f754567569ade58`) e `executor-after-442eeac.json` (SHA-256 `52a5964e8591b735e5649f9a8bfc3391d93429f9a77eac709e257ed6228ca2e2`). Ambos registram zero rede e nenhuma mutação de cliente. A prova após o patch está vinculada ao commit e ao SHA exatos da fonte.

O lock é consultivo, feito no inode do diretório pai com `flock(2)` e mantido durante CAS, preimage e mutação dos escritores cooperantes do Agent Linux. Os pais de move/copy são adquiridos em ordem estável. Um processo que ignora `flock`, uma troca de diretório por outro software, filesystem remoto com semântica diferente, ou Windows não estão cobertos por esta prova. Falha ou timeout de aquisição recusa antes da mutação; não há retry automático de escrita. [Linux `flock(2)`](https://www.man7.org/linux/man-pages/man2/flock.2.html) documenta o caráter consultivo e as diferenças em NFS/SMB.

O gate offline completo passou 141 de 142 verificações (exit 1): o único FAIL foi `SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE`, mantido intencionalmente. O candidato `/tmp/commander-prelaunch-source-candidate-20261020-2208z` contém o Linux deste commit, confirmado por `cmp` e SHA; manifesto SHA-256 `e308f546bbb433ae7990834644c56933ecd75638a961456e07abbe90866af250`. Ele segue sem assinatura oficial, DEV hospedado, instalação em canário ou publicação PROD.
