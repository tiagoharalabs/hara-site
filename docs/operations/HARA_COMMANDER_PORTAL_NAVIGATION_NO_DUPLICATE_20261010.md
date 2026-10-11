# H.A.R.A. Commander — navegação sem títulos repetidos e textos responsivos

**Decisão do proprietário, 10/10/2026.** Todos os itens do menu lateral são autossuficientes: o nome exibido em Computadores, Uso, Plano e cobrança e Configurações não deve reaparecer como título principal ao abrir a página.

## Correção funcional e visual

- Removidos os headings redundantes e respectivas frases de explicação em Uso, Plano e cobrança e Configurações. Computadores já havia sido corrigido. Os quatro `<section class=view app-view>` agora têm nomes acessíveis `aria-label` idênticos aos itens do menu, sem IDs `aria-labelledby` órfãos.
- O painel de Uso começa diretamente pelo resumo da franquia e cartões de métricas. Plano e cobrança começa pelos cartões Free/Pro; Configurações, pelos controles de identidade/acesso, sem cabeçalho desperdiçando espaço.
- O espaçamento superior das três páginas ficou igual ao de Computadores (10px desktop, 9px móvel). Os cards de plano usam a largura útil inteira, com textos de plano maiores, sem limite fixo de 900px.
- Os textos introdutórios das abas Comandos e integrações e Conectar novo foram reduzidos a uma frase cada. Removidos os tetos artificiais de 920px e 1000px no CSS: o parágrafo usa toda a largura da página. Em desktop amplo permanece uma linha; em telas menores há quebra natural, sem transbordamento.
- Não foram alterados os passos do pareamento, gerador de token, comandos copiáveis, cor da capivara, tema, CSS de status, agentes nem APIs.

## Testes e publicação

- Teste novo `test_nav_no_duplicate_titles.mjs` percorre os quatro links reais da navegação, valida as seções com `aria-label`, ausência de headings repetidos e presença dos conteúdos reais de cada aba; inclui o contrato de largura/responsividade.
- `test_devices_setup_commands_ui.mjs` e `test_devices_minimalist_ui.mjs` preservam as ações, estados e histórico.
- `validate_prod_static.py` foi atualizado para garantir a ausência dos títulos repetidos (sem alterar os nomes da navegação).
- Gate offline geral (`commander_prelaunch_offline_gate.py --stress 1000 --threads 24`) mantém os modelos de concorrência, autorização e cobrança, sem tocar PROD.
- Para publicar em Cloudflare, só HTML/CSS e cache key CSS mudam; validação de 11/11 assets incluindo os oito artefatos da release assinada v0.3.43 e health API; rollback Worker versionado preservado. Free continua com 10.000 chamadas/mês, Pro ilimitado.

**DEV validado:** Worker `hara-commander-dev-v2` versão `d42f7f55-490d-4bab-8959-23c499b96b33`; **11/11 assets SHA exatos** e health HTTP 200. PROD ainda não promovido no momento deste registro. Gate offline **56/56 PASS**, incluindo teste novo das quatro rotas.