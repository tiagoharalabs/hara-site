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

**DEV publicado e comprovado:** Cloudflare `hara-commander-dev-v2` versão `d122db6f-7ef4-410a-9656-d50c615d0a07`, com 11/11 assets públicos byte-idênticos ao staging e HTTP health 200. **PROD pendente neste ponto do registro**; promover somente com rollback e readback de todos os assets. A release comercial 0.3.43 segue assinada, sem alterações.
