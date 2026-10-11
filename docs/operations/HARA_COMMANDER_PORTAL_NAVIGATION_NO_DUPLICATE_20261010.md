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

**DEV e PROD publicados e comprovados.** DEV `hara-commander-dev-v2` versão `d42f7f55-490d-4bab-8959-23c499b96b33`, 11/11 assets e health 200. PROD Worker `hara-commander` versão **`f16f8458-d595-4904-87d6-b9ff31bf5a58` a 100%**, custom domain e cron sincronizados; rollback anterior `48c04065-7de8-41f7-8e3e-48c289bcaa5b`. Readback público independente: **11/11 SHA exatos**, HTML de `/` e `/index.html` idêntico ao fonte após normalizar somente o beacon Cloudflare, ausência de headings duplicados nas quatro rotas, health/auth PASS. D1 Free 10.000/Pro ilimitado PASS; testes offline **56/56 PASS**. Somente arquivos HTML/CSS do portal atualizados, sem mudanças no Worker API, Agents, instaladores assinados ou frota.