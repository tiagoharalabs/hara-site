> Registro histórico da frente .49/.50; estado final em HARA_COMMANDER_WINDOWS_051_HANDOFF_20261012.md.

# H.A.R.A. Commander — homologação operacional Windows .49

Data: 12/10/2026. Estado: **PARTIAL_PASS_UTF8_AND_STDIN_BLOCKERS**. Este documento registra a instalação e as provas reais do produto, com fatos fornecidos pelo responsável da execução e artefatos de laboratório copiados com SHA exato.

## Resultado e limite atual

A VM Windows está ativa com o Agent assinado 0.3.49, que oferece até 900 segundos para aprovação individual e também suporta autorização pela sessão. O usuário aprovou uma ação individual real; `hostname` foi executado pelo H.A.R.A. Commander direto. A primeira escrita também recebeu aprovação e foi executada, porém os bytes de texto com acentos foram corrompidos. O produto ainda não está completamente homologado no Windows.

A prova original de hostname foi realizada em `ASK_EVERY_ACTION`. Depois, o usuário pediu autorização pela sessão aberta; o responsável aplicou `SESSION_TRUSTED`, suportado pela fonte .49. Fechar a janela revoga a autorização; ela não é permanente. A comprovação de hostname pelo MCP sem novo prompt passou, com recibo físico indicando autorização pela sessão. Os testes anteriores de 900 segundos usam clock controlado; esta etapa não deve ser descrita como quinze minutos reais de espera já medidos.

## Instalação e runtime

O canário parado R3 fez Inspect e Apply usando fonte privada .49 congelada. O Apply passou, com stderr vazio, backup conferido, configuração byte-idêntica e XML da tarefa preservado. Não iniciou Agent ou tarefa nem gerou aprovação. Após a abertura da sessão, o Commander direto confirmou .49 ativa; o responsável observou operador PID 4140 iniciado em `2026-10-12T21:13:03.0649236Z` e tarefa Running.

Fonte .49: `7b51d2f243228f27aaf742086fe012c73bc17cd8c180a4f9abbcb1e2c51f3080`.
Manifesto: `d0f375fd95e1e7842abb566359cd8edf2f14c4d10853e844cf2c425d0f9d6124`.

Os artefatos de laboratório QGA comprovam instalação/preservação; o recibo Windows da chamada hostname comprova a execução comercial com aprovação individual. As duas autoridades são identificadas separadamente no JSON de acompanhamento.

## Prova real de aprovação e execução

- Chamada: `HARA-CALL-892f7dfe-df74-44f3-bed8-b082ede767de`.
- Pedido MCP: `HARA-CUSTOMER-MCP-tcGmEAeqgKVUUCtr8elzJYONsq3FySINTH7prOjdkr4`.
- Ação: `hostname`; resultado informado pelo responsável: PASS.
- Recibo Windows: `3a9411069454273a291e433038f6fc53d0a321be814ef69a32afefe856ea0779`.
- Aprovação: humana, individual; `ASK_EVERY_ACTION`, `LOCAL_INDIVIDUAL_APPROVAL`.
- A consulta repetida devolveu o mesmo recibo com metadados redigidos, zero nova chamada e zero uso adicional; não houve reexecução.

## Escrita: execução aprovada, fidelidade UTF-8 reprovada

Chamada: `7ff8cf21-da7f-4260-88cf-ee0a4b1a7568`.
Recibo: `26101351f603778a6d9971289329a77b000dbba88f206ec710d4426a692deade`.

| Medida | Esperado | Obtido |
| --- | --- | --- |
| Tamanho UTF-8 | 89 bytes | 97 bytes |
| SHA-256 | `d2db30144965bb9c1e6fb0674af17e2099908f4d115f52b137face8f64a98655` | `426adfb6fb5153082316592e27f758dfb5afa29c5767a517193b850bcc58b6c1` |
| Igualdade de conteúdo | true | false |
| Mojibake | ausente | presente |

A inspeção nativa comprovou `content_equal=false` e `has_mojibake=true`. A hipótese de charset HTTP está em investigação; ainda não é a causa encerrada neste registro. A aprovação/execução do write não deve ser contada como aprovação da fidelidade dos dados.

## Saída de processo: corrupção Unicode real independente da entrada HTTP

Na .49, um comando composto apenas de ASCII construiu `Olá - ação - 🚀` usando expressões `[char]0x...`. A saída devolvida pelo produto foi `Ol� - a��o - ??`.

Recibo: `08d2dd962333710f2b2beb56600911484fc2ff1dc1d2bf32554b3f50fc16b885`. A chamada passou na sessão `SESSION_TRUSTED`, sem novo prompt. Isso é uma falha operacional concreta de saída Unicode; a construção ASCII do comando evita atribuí-la simplesmente aos bytes Unicode do comando HTTP. A correção precisa cobrir a fronteira de processo e sua devolução pelo Agent, além da escrita HTTP.

## Preferência atual: autorização pela sessão

O usuário não quer confirmar cada ação repetidamente durante os testes. A configuração foi alterada pelo responsável para `SESSION_TRUSTED`; a sessão interativa existente do operador PID 4140 continua válida.

| Metadado | Valor |
| --- | --- |
| Configuração anterior, preservada em backup | `e8810f67c0ccaa8780a401f767e5ff99660def8d8815b7288c7a9e4d156bc7f8` |
| Configuração atual | `ecf734ae64557ba51767268efa94beab1b924ff5b8145afdd80d17c50078e5b6` |
| Recibo de aplicação no Núcleo | `d99f10cb5ad91180d4d116649a01898404c818b64dd06ffc8c56d45095aaa9b7` |
| Outras chaves da configuração | Semanticamente preservadas |
| Revogação | Fechamento da janela/sessão do operador |
| Execução MCP sem prompt adicional | PASS; hostname real no Commander direto |

A chamada sem prompt `HARA-CALL-44e3cbfb-e0e3-44de-8ca0-0465b28fb986` executou hostname. Recibo físico Windows: `657e743b75f3f05166301cbbba1f569be510a4a26ba7331bdd720a7183f6bbaa`, com `human_approval_required=false`, `local_authorization_mode=SESSION_TRUSTED` e `authorization_source=LOCAL_OPERATOR_SESSION`. get_config confirmou `SESSION_TRUSTED`, `local_session_authorizes_governed_mutations=true` e `process_execution_requires_local_approval=false`.

A preservação byte-idêntica de configuração no recibo R3 refere-se ao momento da instalação, anterior a esta alteração expressamente autorizada. Nenhum conteúdo de configuração é incluído neste documento.

## Terminal e entrada: provas distintas

O terminal foi iniciado após aprovação humana: recibo `2ee6dbcb86859d8fe5da4db56ff4eb8904eb7e59b6d9e975acdf1f8e20db3126`. A chamada de interação também teve recibo PASS, `5d446276683337a52eb21cc05c73b7a65c9c83ec369a77d8335e855d9d2b0546`, porém a entrada enviada foi perdida. Portanto start PASS e interact PASS não fecham stdin funcional.

O diagnóstico nativo reproduziu zero caracteres ao usar a variável automática de entrada e demonstrou preservação de 102 caracteres na variante. O fixture C# de stdin permanece reprovado e em investigação; não se atribui um total de testes aprovados a esse fixture.

O encerramento gracioso da sessão de processo finalmente passou: PID 6380, estado `EXITED`, código 0. Essa prova confirma o encerramento; não corrige a perda de entrada nem fecha recuperação completa.

## CAS: escrita condicionada e recusa de SHA antigo

A reescrita com precondição SHA-256 `426adfb6fb5153082316592e27f758dfb5afa29c5767a517193b850bcc58b6c1` passou no Commander direto, sem novo prompt. Recibo: `46fb090d17eb33364aa436aa4e423e2b88463469ff2b6b5352d416c60f44b3b4`.

Repetir o mesmo SHA após a atualização foi recusado com `FILE_PRECONDITION_FAILED`. A leitura posterior confirmou que o texto atualizado foi preservado.

Hash dos bytes consultado pelo Commander: `d540d43e240254af78fd4c7b050dbfc7d15d3c5db19ea1763270be1be181db62`, 66 bytes, recibo `1fd31dfae780e7e976ea776e74b9f8d4d2e647da2554496c2a44c9aff7d13345`. Esse ensaio fecha a precondição e a recusa de escrita concorrente; não substitui o roundtrip de acentos que falhou anteriormente.

## Candidata .50: teste de fronteira HTTP

O fixture nativo HTTP da candidata .50 passou **30/30**. Esse resultado cobre o fixture e não equivale a fonte .50 instalada ou roundtrip UTF-8 pelo MCP real. Os testes finais de UTF-8 e stdin dependem do código final, da assinatura/canário e de nova prova operacional. A renomeação de entrada aplicada pelo responsável produziu a fonte intermediária `42c1c9e75f8ef2e6e654d800ddae610310404a55be5d0d0682aa3801ce5ace06`. A revisão de encoding de processo/fixture está em andamento; o hash final ainda mudará e a fonte intermediária não foi assinada. Fonte Linux e download Windows público .43 continuam iguais.

## Próximas provas

1. Corrigir a codificação na fronteira identificada e comprovar bytes exatos com acentos pelo MCP direto na candidata .50.
2. Corrigir a entrada perdida e fechar terminal interativo completo e recuperação/retomada usando recibos do produto.
3. Registrar o resultado final do watcher e seus testes antes de promover a correção.
4. Reexecutar os gates necessários para o código final e publicar apenas os caminhos desta frente.

## Custódia, integração e evidências

Worktree isolada Services: `/tmp_hara/commander-win50-utf8-20261012`.
Branch: `local/commander-win50-utf8-20261012`.
Base canônica confirmada por GitHub e refs locais: `680cf20df32b6ac1d221244c151fc6f4bb617ff6`.

O origin no Storage apontou para `092f35afc52827d6c5584f0401e9f60eaeb3d985`, com ancestral compartilhado `2cf10e5cac0d44f6fd9c01211053feb6afaa0944`, divergindo da linha do produto. Essa worktree foi preservada isolada, sem merge, commit ou publicação. A correção UTF-8 parte da linha GitHub/local atual; a candidata .50 ainda não foi aplicada neste registro. Nenhum checkout ou reset foi feito nas worktrees antigas. A worktree de fonte .49, o relay e os controles r4–r7 antigos continuam preservados. Nenhum AGENTS.md aplicável foi encontrado nos worktrees ou ancestrais.

Evidências em `docs/evidence/commander-win49-approval15m-20261012/`:

| Artefato novo | SHA-256 |
| --- | --- |
| `windows49-cutover-inspect-f5bac384d556d1c4-result.json` | `ed35419a333225f89840513222304e9dd9cc0f828fa7331ffbf823e311cea0ad` |
| `windows49-cutover-apply-f5bac384d556d1c4-result.json` | `75435e3ef8f8bde1703cb8f5cdc523a8cffa19db05c2b3235c492e42fb314019` |
| `windows49-stopped-r3-parser-proof.json` | `ef4b2aa12c34f9a994de2333bef73d359fcd67261aa4b5ab280dc99a6d12d167` |
| `windows49-real-product-homologation-current.json` | Manifesto de acompanhamento dos fatos acima; será atualizado com os resultados finais. |

O JSON de acompanhamento tem proveniência explícita para fatos comunicados pelo responsável da execução. Não substitui o corpo original do recibo do Agent. Não contém conteúdo de configuração, credenciais ou código de aprovação.
