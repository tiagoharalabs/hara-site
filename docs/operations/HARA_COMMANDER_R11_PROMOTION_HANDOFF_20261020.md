# HARA Commander — R11: handoff de distribuição e promoção

Estado em 20/10/2026: **HOLD para instalação comercial pública**. O GET independente do endpoint principal retornou manifesto 0.3.41, assinatura v1 incompatível com o pin v2 do instalador Linux servido e quatro assets fora dos hashes assinados. Exit 2 do gate ao vivo é falha real, não PASS. O 401 isolado do Observer não foi reproduzido e permanece outra investigação.

## Candidato e prova local

`build_commander_commercial_terminal_drain_candidate.py` prepara uma fonte 0.3.43 sem assinatura: Linux com drenagem pós-exit e instaladores que validam o pacote antes do cadastro; Windows Agent comercial permanece 0.3.43. A fonte funcional Windows 0.3.55 da R10 está separada. Não tratar o candidato 0.3.43 como prova de paridade Windows nem publicar sem uma assinatura oficial sobre seus bytes finais.

`stage_signed_commercial_assets.py` exige o bundle corrente `commercial-0.3.43-v5-terminal-drain`, ainda ausente. O novo `require_signed_stage` confere assinatura RS256 com pin v2, manifesto, hashes/tamanhos, os oito arquivos de release byte a byte contra o bundle aprovado, todos os outros arquivos rastreados contra o `public/` atual e as regressões Linux, inclusive a saída pós-exit. O bundle v4 assinado só passa no modo histórico de rollback e falha no teste funcional de terminal.

`commander_versioned_prod_promote.py` agora exige `--stage` absoluto. Faz essa validação **antes** de consultar Wrangler; com `--execute`, promove uma versão única a 100% e depois exige readback de versão, assets exatos do staging e integridade pública independente. Não aceita `public/` bruto como staging. Um timeout ou readback falho após o comando mutante deixa o estado **incerto**: ler o deployment atual antes de decidir rollback ou nova ação; não repetir a promoção às cegas.

## Sequência pendente de autorização

1. O responsável pela assinatura deve decidir a composição final Linux/Windows e assinar oficialmente o manifesto com a chave v2 sob custódia, sem exportar a chave. Validar o bundle completo e a correção pós-exit; nenhum hash isolado equivale a assinatura ou teste funcional.
2. Gerar um staging novo com o script acima. O upload autorizado deve usar **exatamente** esse diretório com `wrangler versions upload --assets <stage>`. Uma versão do Worker contém código e assets estáticos como unidade, segundo a [documentação da Cloudflare](https://developers.cloudflare.com/workers/versions-and-deployments/). Não usar `wrangler deploy` direto nem upload de arquivos soltos.
3. Ler a versão carregada, bindings e nomes de secrets, e qualificar uma versão de rollback que preserve a distribuição e as funções atuais. A v4 histórica possui regressão de drenagem; não é fallback funcional automático. Migrações D1 não voltam com rollback de Worker.
4. Somente com aprovação específica, executar a promoção versionada com `--stage`, `--version`, `--rollback` e `--execute`. Verificar o deployment 100%, assets byte-idênticos ao staging, assinatura sob o pin dos instaladores realmente servidos e 4/4 hashes. Repetir o gate GET a partir de Services, Storage e Observer para observar POPs distintos. Um PASS em um host não prova todos os POPs.
5. Após o readback assinado, realizar clean install comercial isolada em Fedora 43/SELinux e Ubuntu 22/UID 1001, depois Windows 11, com rollback e sem afetar os Agents Founder. O canário Founder Sentinela A 0.3.54 da R12 já foi feito por outra frente autorizada; não é validação da instalação comercial pública.

O fluxo atual usa um único deploy versionado do Worker; ainda **não** implementa URLs imutáveis por release com ponteiro público atualizado por último. A validação pré-enrollment falha fechada se requisições públicas cruzarem bytes de releases diferentes. Readback multiponto e eventual desenho de ponteiro imutável continuam necessários antes de declarar entrega pública estável. Nada neste handoff autoriza assinatura, upload, promoção, migração remota, instalação ou cutover.
