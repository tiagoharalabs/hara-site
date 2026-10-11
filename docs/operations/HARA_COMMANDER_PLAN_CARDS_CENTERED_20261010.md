# H.A.R.A. Commander — Plano e cobrança: cards centralizados

**10/10/2026 · ajuste visual autorizado da versão comercial.**

## Alteração na interface

- Cards Free e Pro permanecem lado a lado no desktop, com **largura total máxima de 1.080 px**, grade centralizada com `margin:0 auto` e duas colunas idênticas. O layout anterior usava toda a largura da página (ficava grande demais).
- Padding reduzido para 22px 24px 20px; título, preço, lista de benefícios e botões ganharam espaçamento vertical menor sem perder legibilidade.
- Grid com gap de 18px, ambos os cards com a mesma altura visual (`align-items:stretch`). Até 1050px os dois cards passam a uma única coluna central com máximo de 520px; em telas pequenas, largura total disponível e padding 20/19/18px.
- Os quatro itens do menu lateral continuam sem títulos repetidos na área central. A paleta H.A.R.A. e os temas existentes são preservados.
- O preço Pro R$ 80/mês, status 'Em preparação', ações beta, Free 10.000 chamadas/mês, prontidão de cobrança e botões não foram alterados. Nenhuma ativação de Stripe ou mutação de dados foi realizada.

## Testes e publicação

- `node apps/commander/scripts/test_plan_cards_centered_ui.mjs`: valida grade simétrica, largura, responsividade, cores, conteúdos comerciais e botões intactos.
- `test_nav_no_duplicate_titles.mjs`, `test_devices_setup_commands_ui.mjs` e `validate_prod_static.py` mantêm navegação e instalação sem regressões.
- Gate offline completo `commander_prelaunch_offline_gate.py` executado com carga 1.000/24 threads, **57 verificações previstas**.
- A publicação deve alterar apenas `styles.css` e seu cache key em `index.html`. Os oito arquivos de instalação/Agents assinados v0.3.43 permanecem byte-idênticos no staging/Git. Usar Worker Cloudflare DEV para provar 11/11 hashes e health; depois PROD com rollback.

**DEV e PROD publicados e comprovados.** DEV `hara-commander-dev-v2` versão `4219f824-659f-4780-98e7-b85b39c0c980`, 11/11 assets e health 200. PROD Worker `hara-commander` versão **`0fd13813-9c0a-45c1-9102-8ab5db7c3d26` em 100%**, domínio/cron sincronizados e rollback imediato `f16f8458-d595-4904-87d6-b9ff31bf5a58`. Readback público independente: **11/11 SHA exatos**, `/` e `/index.html` convergidos, health/auth 200 e D1 Free 10.000/Pro ilimitado. Gate offline **57/57 PASS**. Somente HTML (cache key) e CSS; não houve mudanças em Agents, manifesto assinado, Worker API, D1 ou cobrança.