# H.A.R.A. Commander — nova navegação de instalação e comandos

**Checkpoint 10/10/2026 · produto comercial · UX exclusivamente, sem alterar serviço/assinatura.**

## O que muda

- **Computadores → Dispositivos**: apenas frota, estado, última presença, diagnóstico e detalhes. Removidos dali os grandes cards de Primeiros passos e Onde usar.
- **Computadores → Conectar novo**: sequência curta com três passos na ordem certa: **(1) escolher Linux/Windows, (2) gerar código temporário no portal autenticado, (3) copiar comando de instalação para a máquina e informar o Pairing token quando o instalador solicitar**.
- **Computadores → Comandos e integrações**: nova aba com comandos copiáveis para Linux, Windows e clientes MCP locais/remotos. Há uma nota explícita de que presença/heartbeat sincronizam automaticamente enquanto o Agent está conectado e não existe comando `sync`.
- O modo Direct avançado do Linux continua disponível, mas recolhido por padrão. O usuário comum começa em Cloud (OAuth HARA Identity), sem token no argumento de shell. O Agent instala sem autostart futuro e a autorização permanece ASK_EVERY_ACTION.
- O comando oficial baixa o instalador por **HTTPS** do domínio commander.haralabs.com.br; o instalador confere SHA/manifesto/assinatura. Um link adicional leva à release imutável já versionada no GitHub, sem confundir raw HEAD com distribuição assinada.
- **Windows Agent 0.3.43** suporta start, status, stop. O guia não promete MCP local STDIO Windows, ainda não disponível: indica MCP remoto HTTPS + OAuth. Operações sensíveis Windows seguem em beta/homologação.
- **Linux Agent 0.3.43** suporta start, status, stop, doctor e mcp (STDIO local). Os comandos Direct configure/authorize/tunnel start/stop ficam num disclosure avançado separado.
- Paleta Navy/Blue/Gold/Success, tema claro/escuro, opções neon, logo capivara, classes de botões e estilo de produto foram preservados.

## Contrato funcional e segurança

- O pareamento continua sendo realizado por POST /api/portal/devices/pairing com credenciais same-origin; retorno de token one-time com expiração em dez minutos. Não gravar nem inserir token em URL, clipboard persistente do app ou argumentos da linha de comando; copiar token somente por ação explícita.
- Os botões de instalação continuam usando installCommandLinux / installCommandWindows, downloads oficiais, sem mudança de transporte default ou da política de autorização.
- A nova cópia de comandos lê somente elementos CODE estáticos sob o botão selecionado, sem chamadas de backend nem parâmetros livres.
- O tab switch reutiliza setDeviceSectionTab e adiciona commands com suporte às setas esquerda/direita. As duas abas anteriores continuam funcionais e toda a listagem permanece idêntica.
- Instalar e iniciar uma vez não habilita autostart em login/boot. Em sessões posteriores, iniciar manualmente; sincronização de presença ocorre enquanto o Agent está conectado e usuário atualiza a lista com botão Atualizar.
- Pro/Free não mudam: Free 10.000 chamadas governadas/mês, Pro ilimitado no catálogo, Stripe não ativado.

## Provas pré-publicação

- `node apps/commander/scripts/test_devices_minimalist_ui.mjs` testa a lista e a troca entre três abas.
- `node apps/commander/scripts/test_devices_setup_commands_ui.mjs` testa ordem dos três passos, paring one-time, downloads HTTPS com aprovação ASK_EVERY_ACTION, ausência de token em CLI, comandos reais no Linux/Windows e nota de sincronização automática.
- `validate_prod_static.py`, `validate_device_installers.py`, `validate_bootstrap_supply_chain.py`, `validate_linux_tunnel_start_modes.py` e validações de autorização/cobrança continuam PASS.
- Gate offline consolidado: **55/55 PASS** em 10/10. Não é prova de browser em plataforma Windows nem de 1.000 tenants Cloudflare; sim suíte de contratos local.

## Deploy e rollback

O staged Worker carrega HTML/JS/CSS com o pacote comercial 0.3.43 RSA-v2 intocado. Promover versão via Wrangler DEV e ler SHA dos assets; em PROD conferir 11/11 assets (HTML normalizado removendo apenas o beacon Cloudflare autorizado), Worker health, quotas D1, ping comercial e commit SHA exato GitHub. Worker anterior permanece como rollback. Nunca alterar a frota Founder 0.3.44 apenas para esta UX.

**Estado deste documento antes da promoção:** código-fonte e testes locais completos; acrescentar versão exata Cloudflare DEV/PROD e readback ao publicar.
## Estado de publicação nesta sessão

**Cloudflare DEV e PROD não foram alterados por esta frente.** O gate e a compilação dry-run para os dois Workers passaram, com instaladores/agentes comerciais assinados v0.3.43 byte-idênticos. Porém a chamada remota de implantação Cloudflare DEV foi bloqueada por controles de segurança da ferramenta, incluindo uma tentativa com comando simplificado. Não repetir o deploy por outro canal para contornar o bloqueio; solicitar uma sessão com autorização/fluxo de publicação permitido.

### Passos de verificação quando a publicação for permitida

1. Atualizar o staging com os três arquivos de interface (index.html, app.js, styles.css) da branch canônica e verificar por cmp que os oito assets comerciais assinados continuam idênticos ao backup `apps/commander/release-bundles/commercial-0.3.43-v2`.
2. Publicar a versão DEV por Wrangler com a configuração de staging já validada; conferir HTTP 200 no /api/health e readback SHA exato do HTML, JS, CSS e dos oito assets assinados. Não há necessidade de aplicar migrações D1.
3. No PROD, carregar uma nova versão do Worker, conferir que os segredos necessários foram preservados e que o deploy atual é o esperado; então realizar promoção gradual ou controlada pela rotina canônica, com rollback explícito, sem mexer na frota.
4. Conferir rota raiz / e alias /index.html (normalizar somente o beacon Cloudflare conhecido), cache keys CSS/JS, botões de copiar, endpoints de pareamento existentes, status online/offline, Free 10.000 e um ping pelo MCP comercial.
5. Somente após readback exato, registrar o novo Worker version ID como produção atual e atualizar este handoff.

**Não afirmar distribuição pública atualizada com a nova terceira aba enquanto o deploy e readback não forem concluídos.**