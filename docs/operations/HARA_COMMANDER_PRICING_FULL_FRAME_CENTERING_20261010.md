# H.A.R.A. Commander — centralização integral de Plano e cobrança

**10/10/2026 · solicitação explícita do fundador · alteração exclusivamente visual.**

## Problema real identificado

Os cards Free e Pro já estavam **centralizados horizontalmente** em uma grade de largura máxima de 1.080 px. Porém o `workspace-main` continuava no fluxo vertical normal, colocando o grupo no topo e deixando grande área vazia embaixo. Uma nova redução da largura dos cards não resolveria essa assimetria no frame.

## Correção aplicada

- A área de conteúdo da rota `plans` usa flexbox com eixo vertical (`flex-direction:column`), `justify-content:center` e `align-items:center`, com altura mínima `calc(100dvh - 74px)` (fallback `100vh`), correspondendo à janela útil abaixo da topbar.
- **Toda a composição** é centralizada como um conjunto: cards Free/Pro, indicadores de prontidão comercial, texto de status e ação opcional de gerenciamento de cobrança. Os elementos compartilham limite de 1.080 px e margens horizontais automáticas; o `billing-management` tem classe explícita em lugar de estilo inline.
- Os cards continuam simétricos, 1.080 px de largura total máxima, Free=10.000 chamadas/mês, Pro=R$ 80/mês; sem alteração de valores, cores, ações ou cobrança.
- Em largura até 1.050 px, os cards continuam empilhados, com grupo de cobrança limitado a 520 px. Em telas baixas (até 700 px de altura), justificação vertical volta ao início para não ocultar controles. Em celular, mantém o scroll natural, com padding apropriado.
- Novo cache key de CSS `20261010-centered-plans-vertical1` evita resíduo do estilo anterior.

## Garantias

- `test_plan_cards_centered_ui.mjs` valida agora também centralização **vertical**, todos os elementos da composição, comportamento responsivo, cores e continuidade dos controles.
- `test_nav_no_duplicate_titles.mjs`, `test_devices_setup_commands_ui.mjs` e `validate_prod_static.py` preservam páginas, menus e comandos.
- Gate completo offline `commander_prelaunch_offline_gate.py --stress 1000 --threads 24` garante contratos e concorrência sem efeitos em produção.
- A distribuição comercial assinada v0.3.43, os Agents Founder, MCP comercial, OAuth, Workers API, D1, Stripe e autenticação não são alterados. Apenas HTML/CSS do portal são implantados.

## Publicação

**DEV publicado e verificado:** Worker `hara-commander-dev-v2`, versão `39b8e74a-5e5f-40a5-988b-7b0906a59cb0`, com **11/11 arquivos SHA byte-idênticos** (HTML/CSS/JS + oito assets comerciais assinados), health HTTP 200. **PROD ainda não foi promovido neste checkpoint.** Produção requer versão anterior conhecida, segredos preservados, promoção versionada, readback público e rollback configurado. Gate offline **57/57 PASS**.
