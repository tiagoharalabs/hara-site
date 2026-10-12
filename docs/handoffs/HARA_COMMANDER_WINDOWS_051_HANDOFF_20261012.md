# H.A.R.A. Commander — Windows, 12/10/2026

Estado: fluxo básico MCP homologado na VM Founder com Agent privado 0.3.51 e SESSION_TRUSTED. Execução, leitura/escrita UTF-8, CAS e terminal interativo com Unicode passaram pelo Commander real. A homologação comercial completa permanece aberta.

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

## Prova real final da 0.3.51

A sessão externa terminou antes da troca. O canário .50 → .51 passou com zero processos de Agent no ponto de substituição, backups privados, configuração byte a byte e tarefa preservadas. Console reaberto pela shell do usuário; fonte instalada 4c563987986249d78c76258d062a4d360ffb88199539429ea97c2f346644656a. Operator PID 5412 permaneceu vivo e o Agent ficou ONLINE.

Versão .51 confirmada pelo MCP real, recibo e211a9ba0c85a1616d9b840b546e0f9cfac07a58a5e7430999d229a6b88c4488. Execução literal Unicode passou, recibo 30fb85162fb66a1c3903eb821712d4cb2a638f2c2fed8cc39557cdf8129e0fef.

O construtor do terminal preservou "🚀 日本語". A interação devolveu 120 linhas mais marcador Unicode, total 122, exit 0 e output_pending=false; recibo c8909131c5ea2f984748198b8cdabc46ee6e22d6f22aa99d904c968fd98fdbeb. O marcador final foi "HARA51_INTERACTION_PASS: Olá ação 🚀 日本語".

Arquivo inicial: 90 bytes, SHA 25c582bc160431e6344aca1146b3e04c3f5f235e72338effce384340eda25ad0. Reescrita com SHA correto passou. SHA antigo foi recusado com FILE_PRECONDITION_FAILED e mutation_performed=false. Verificação física posterior: 116 bytes, SHA bab6d868800f44aa2a79b97c7b0e3bf7bf93cae7d3914bcf496c6e219d7eb3cd. Leitura pelo MCP preservou todo o texto Unicode, recibo a87a57a1f3cdb2404f1b425475b2c8e6f644201cb616f2e0911f3ceb6b53f4fb.

As chamadas de execução/escrita/entrada passaram sem aprovação individual; get_config confirmou SESSION_TRUSTED, process_execution_requires_local_approval=false e ONLINE. Fechar a sessão continua revogando a autorização.

Uma leitura suplementar do JSON bruto de recibo expirou: HARA-CALL-8fc82367-c9b8-4f99-a16b-ad89d29cfc5c, reconciliada como DEVICE_CALL_EXPIRED. Não foi reenviada. Fica como observação diagnóstica; a leitura do arquivo de homologação e os recibos MCP das operações passaram.

Evidências completas: docs/evidence/commander-win51-unicode-input-20261012/live-product-proof.json. A publicação comercial completa permanece aberta: estas provas cobrem a VM Founder e testes locais, sem comprovar Stripe, soak prolongado ou carga real de mil clientes.
