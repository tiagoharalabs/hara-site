# H.A.R.A. Commander — ajuste final de densidade nas três abas

**10/10/2026 · produto `local/commander-product-current` · alteração exclusivamente visual.**

## Regra de UX autorizada

- Não repetir o título **Computadores** dentro da rota quando a navegação lateral já indica Computadores. O `<section>` mantém nome acessível via `aria-label="Computadores"`, sem retirar semântica para leitores de tela.
- Subir Dispositivos / Conectar novo / Comandos e integrações: padding do workspace da rota reduzido de 19 para 10 px (9 px em telas menores), pequena redução de espaço antes do conteúdo.
- **Dispositivos:** remover as linhas horizontais entre as máquinas, manter a moldura externa. Diminuir a altura mínima de cada item de 64 para 54 px e o padding vertical de 11 para 7 px. Fonte do nome 15 px, segundo texto 12,5 px, status 12 px e ação/resumo 12,5 px.
- **Conectar novo:** remover divisórias horizontais dos passos de escolha de plataforma, geração de código e instalação, mantendo ícones numerados, grupos e borda externa do card. Reduzir padding vertical de 12 para 9 px, aumentar nomes dos passos para 14 px e textos para 12,5 px; resumo com 13,5 px.
- **Comandos e integrações:** preservar o card externo envolvendo Linux/Windows/MCP. Remover separadores horizontais também nas linhas de comandos, reduzir o padding por linha de 15 para 12 px. Mantidos os botões Copiar e o texto dos comandos.
- A identidade H.A.R.A., o ouro das abas, os temas claro/escuro e a capivara não são modificados. Não alterar MCP, Worker API, aprovação, pairing, billing, SQLite, Agents ou instalação.
- Cache key CSS alterada para `styles.css?v=20261010-clean-rows1`, evitando resíduo de CSS no browser. JavaScript permanece byte-idêntico à release atual.

## Testes e deploy

- `node apps/commander/scripts/test_devices_setup_commands_ui.mjs`: teste de contratos da UI, incluindo ausência do título redundante, tipografia, densidade, zero divisórias nos passos e lista.
- `node apps/commander/scripts/test_devices_minimalist_ui.mjs`: contagem real de estado e ações existentes preservadas.
- `python3 -B apps/commander/scripts/validate_prod_static.py`: rota acessível sem título visível redundante, sem mudança de autenticação nem política de autorização.
- `python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py --stress 1000 --threads 24`: suíte completa.
- Antes de publicar, comparar os oito assets da distribuição assinada v0.3.43 com o staging (SHA idêntico). O deploy DEV/PROD só precisa enviar HTML/CSS. Confirmação pública usa readback 11/11, health, Worker version e quota Free 10.000.

**DEV e PROD publicados e comprovados em 10/10/2026.** DEV `hara-commander-dev-v2` versão `e27c8338-b45e-484f-a0b5-5b82705deaad`, assets 11/11 e health 200. PROD Worker `hara-commander` versão **`66958dc2-2951-423d-9699-6396e78d2890` a 100%**, triggers custom domain/cron sincronizados, rollback imediato **`4946ed70-bbf0-4605-98a8-063d0af0a8cb`**. Uma primeira promoção encontrou cache misto de assets e fez rollback automático; na promoção seguinte, readback **CURRENT** já na primeira checagem. Verificação pública independente confirmou **11/11 SHA**, rotas `/` e `/index.html` byte-idênticas à origem após normalizar somente beacon Cloudflare, health e auth HTTP 200, D1 Free 10.000/Pro ilimitado, pings MCP comercial Núcleo A/Sentinela D Agent Founder 0.3.44 PASS. Gate offline **55/55 PASS**. Sem alteração de binários/assinaturas, Worker API, dados ou serviços da frota.
