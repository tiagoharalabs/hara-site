# H.A.R.A. Commander — alinhamento, fonte e simetria na tela Computadores

**10/10/2026. Escopo:** refinamento visual autorizado, exclusivamente HTML e CSS do portal na linha `local/commander-product-current`. Não alterar Worker API, Agent, OAuth, quota, D1 nem assinatura da release.

## Critérios de UX implementados

- Removido o subtítulo genérico de Computadores. Cabeçalho agora tem 23 px, começa em 19 px da borda superior da área útil, com distância de apenas 8 px até as abas. Mantida a posição horizontal com o restante do workspace.
- Abas Dispositivos, Conectar novo e Comandos e integrações permanecem no mesmo alinhamento, com tipografia de 13 px e sublinhado dourado atual.
- Removido o limite antigo de 1.160 px da referência de comandos; agora a área usa 100% da largura disponível, alinhada às outras abas.
- Retirada a borda/background da caixa contêiner externa de Comandos e integrações. Os únicos cards são Linux e Windows em duas colunas idênticas e MCP em largura total; grid com stretch para igualar as alturas.
- Os comandos são linhas alinhadas, com coluna à esquerda para verbo/descrição, à direita para código e Copiar. Bordas somente entre linhas; retiradas as caixinhas, bordas e barras de rolagem internas de cada comando. Comandos Windows longos quebram linha sem perder capacidade de copiar a string completa.
- Tipografia de comandos ampliada: título do card 18 px, ação 14 px, descrição 12 px, código 12,5 px, botões Copiar 12 px, e títulos da página menores/mais próximos do topo. Cabeçalho da referência 22 px.
- Mesmo layout adaptável: em telas com até 1.280 px os cards empilham sem compressão; em mobile as linhas passam a uma coluna. Paleta H.A.R.A. navy, azul, dourado, estados, ícones e temas claros/escuros não alterados.
- Tela Conectar novo teve ajustes leves de legibilidade (títulos, texto e comando) sem mudança nos passos, pareamento nem comportamento.
- Cache keys de styles.css e app.js alteradas para `20261010-symmetric-commands1`, evitando usar CSS anterior após o deploy.

## Provas e segurança

- `node apps/commander/scripts/test_devices_setup_commands_ui.mjs` valida os comandos, as três abas, o pacote público e o contrato específico de fonte, simetria e redução de caixas.
- `validate_prod_static.py`, `test_devices_minimalist_ui.mjs` e `commander_prelaunch_offline_gate.py` validam a navegação e a integridade funcional.
- Não houve alterações nos instaladores Linux/Windows, Agent v0.3.43 comercial assinado, Founder v0.3.44, tokens, autenticação HARA Identity, cobranca/Stripe ou migração D1. Free permanece 10.000 chamadas governadas/mês.
- O staging da Cloudflare DEV e PROD só pode receber index.html e styles.css desta frente (o app.js fica byte-idêntico, apesar do cache key). Conferir 11/11 arquivos no DEV e PROD, Worker health, autenticação e rollback.

## Situação de publicação

**DEV e PROD publicados e comprovados:** DEV `hara-commander-dev-v2` versão `d122db6f-7ef4-410a-9656-d50c615d0a07`, 11/11 assets e health 200. PROD `hara-commander` versão `d305c678-7715-4594-b8b9-f1e697112702` com **100% do tráfego**, custom domain e cron sincronizados; rollback `9943523c-a573-40bc-bc86-2f45b2156643`. Readback público independente: **11/11 SHA exatos**, tanto `/` quanto `/index.html` convergiram, health/auth PASS, D1 Free=10.000 e Pro ilimitado; pings comerciais Núcleo A/Sentinela D Agent 0.3.44 PASS. Gate offline 55/55 PASS. A release comercial 0.3.43, assinatura e os serviços Founder continuam inalterados.

## Refinamento adicional aprovado — moldura única externa

- O texto redundante `REFERÊNCIA RÁPIDA` foi removido da aba Comandos e integrações; o título funcional permanece.
- O contêiner externo `panel.devices-command-guide` voltou a ter moldura discreta de 1 px, raio de 14 px e padding de 20/24 px, preenchendo a mesma largura útil das abas Dispositivos/Conectar novo. Usa os tokens já existentes `--line` e `--white`, incluindo tema dark, **sem trocar as cores**.
- Dentro da moldura permanecem apenas os três cards Linux, Windows (colunas simétricas) e MCP (largura total), mantendo fonte ampliada, comandos em linhas sem caixas internas e botões Copiar originais.
- HTML e CSS somente, sem mudanças no JavaScript, Worker API, credenciais, agentes, assinatura ou preços. Cache-bust do CSS atualizado para `20261010-command-frame1`.
- Testes `test_devices_setup_commands_ui.mjs`, `test_devices_minimalist_ui.mjs`, `validate_prod_static.py` e gate offline **55/55 PASS**. Dry-run DEV/PROD PASS. DEV Worker `7438d28f-266f-46c4-9063-8bb00f2c7eb3`: **11/11 assets com SHA exato**, health 200.

**Estado de publicação neste registro:** DEV comprovado. Documentar versão PROD e readback real após a promoção.