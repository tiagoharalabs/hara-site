# H.A.R.A. Commander — Windows, 12/10/2026

Estado: homologação parcial do produto. A VM executa o Agent privado 0.3.50 em SESSION_TRUSTED. A correção 0.3.51 está assinada, autenticada dentro da VM e pronta para troca, aguardando o término de uma sessão de terminal ativa.

## Provas pelo Commander direto

A versão 0.3.50 foi confirmada pelo MCP real, recibo 1a8cd81ad3503ce399ee1e3ec8761cccb7a61fb88f90c3e0d7e067ca3e72ef8f. Execução preservou "Olá - ação - 🚀 - 日本語", exit 0, recibo e117b7cb1c6ca6a116e14b72b0aa7182fbc35878dfbe420afa11ed2748b5aee6.

A escrita Unicode produziu 90 bytes e SHA 5207989024a55e03bdbb30aad67f4c2a3c33140375cda1670cacd08aef7d0926, confirmado por Get-FileHash via MCP. A reescrita com SHA correto passou. O SHA antigo foi recusado com FILE_PRECONDITION_FAILED e mutation_performed=false. O arquivo permaneceu com 116 bytes e SHA 4cd3bfe941c1b3ac78cb9d1a866090b7fcc9c3ef4f3df68b28a2a815688865b0.

O terminal recebeu entrada e devolveu as 120 linhas, total 122, exit 0 e output_pending=false. A mesma prova revelou perda de emoji e CJK na entrada literal: o marcador final retornou "Olá ação ?? ???". Portanto, a .50 não fecha a homologação Unicode do terminal.

## Correção privada 0.3.51

Fonte e bundle Windows: SHA 4c563987986249d78c76258d062a4d360ffb88199539429ea97c2f346644656a.

O ConsoleHost do PowerShell 5.1 conserva o leitor OEM de stdin; o escritor padrão observado usa ibm850. A .51 transporta comandos completos com caracteres não ASCII em um envelope ASCII e recompõe o texto UTF-8 no PowerShell, mantendo comandos ASCII e a autorização original. A execução usa dot-sourcing para preservar o escopo da sessão.

511 verificações nativas passaram: Unicode de processo e comandos literais no construtor e na interação (11), entrada e 120 linhas (11), HTTP/arquivo UTF-8 (30), consentimento/expiração (111), janela de 900 segundos (227), início (68), negativas (26) e recuperação de console (27). A recuperação usa o resultado do fixture corrigido r3; os demais resultados finais são r2.

Gate integrado: 115/115, com stress local de 1.000 tentativas e 24 threads. Não comprova escala real ou multitenancy real.

Manifesto d7b0cead0a38fa22172be285c8afbc8003802ce4b2fdc0807d3393986312841d; envelope de assinatura 4a607a4029b954ed9677125f46e1ee64e53740c109c6ca197eaa33cbb6baf84b. RS256/RSA3072, chave commander-release-v2. Quatro arquivos, hashes, parser PS5.1 e self-test passaram dentro da VM. Bundles anteriores e bytes Linux foram preservados.

## Autorização e implantação

SESSION_TRUSTED está ativo: abrir a sessão autoriza suas operações; as chamadas de teste não exigiram aprovação individual. Fechar a sessão revoga a autorização. Configuração preservada, SHA ecf734ae64557ba51767268efa94beab1b924ff5b8145afdd80d17c50078e5b6. Tarefa do Agent preservada, SHA 9bcc1704ecbb8afb3ce5edd4cb1f7a21ed4d470fc91870ff354d9da24d5dfa08.

A correção do cabeçalho JSON UTF-8 do relay foi publicada em produção, versão Cloudflare 3fd724aa-afdb-4b20-a360-b0a013a02c2a. O estágio de implantação preservou os assets anteriores; os bundles .50/.51 continuam privados e o download público .43 foi preservado. O teste unitário do cabeçalho passou em 43 cenários. A sondagem pública /api/health recebeu 403 text/plain da camada de acesso e não é prova do cabeçalho JSON do Worker.

## Próximo passo concreto

Há uma sessão de terminal RUNNING na VM: HARA-PROC-4df86c89f5394828861110c4550f5a67, PID 5448, iniciada em 2026-10-12T22:58:37.6307987Z. Uma leitura limitada de saída foi recusada com IOEXCEPTION; nenhum conteúdo foi impresso e a sessão foi preservada. Os controles de troca exigem ausência de sessões ativas.

Após sua conclusão: colher metadados novos, parar a sessão/worker com identidade exata, aplicar o canário assinado .50 → .51 preservando configuração/tarefa/backups, abrir o console pela shell do usuário e repetir pelo MCP real o comando Unicode, escrita com CAS e terminal de 120 linhas com emoji/CJK. O launcher por tarefa temporária encerrou a primeira sessão; ShellExecute manteve a sessão seguinte e foi comprovado pelas chamadas reais.

A homologação completa e a publicação comercial permanecem abertas. As provas aqui cobrem a VM Founder e testes locais; não são prova de cobrança Stripe, soak prolongado ou carga real de mil clientes.
