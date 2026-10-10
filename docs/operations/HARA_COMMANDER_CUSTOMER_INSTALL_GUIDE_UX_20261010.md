# H.A.R.A. Commander — nova navegação de instalação e comandos

**Checkpoint autoritativo 10/10/2026 — Publicado em PROD.** Worker Cloudflare `hara-commander` `9943523c-a573-40bc-bc86-2f45b2156643` a **100%**, sem alterar serviços, instaladores assinados, agentes, D1 nem quotas. DEV `hara-commander-dev-v2` `b160e263-fab5-4918-9d11-0ae128e413b4`. O anterior PROD `228fdb6d-fbde-4a1c-91b0-57ac73f5d193` foi preservado para rollback.

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

**Publicação executada e comprovada:** Worker PROD `9943523c-a573-40bc-bc86-2f45b2156643`, health e auth PASS, verificação independente **11/11 SHA** de HTML/JS/CSS e distribuição comercial assinada, runtime drift PASS, MCP comercial respondeu ping no Núcleo A e Sentinela D Agent v0.3.44. Catálogo Free=10.000/mês e Pro sem limite confirmado diretamente no D1 PROD. Rota raiz e assets usam cache keys atualizadas. A nova terceira aba está acessível publicamente.
## Fechamento da publicação no mesmo dia

A implantação havia sido bloqueada por controles da ferramenta na tentativa anterior. Após nova autorização expressa do proprietário, a mesma rotina oficial Wrangler foi executada com sucesso. O DEV `b160e263-fab5-4918-9d11-0ae128e413b4` e o PROD `9943523c-a573-40bc-bc86-2f45b2156643` passaram pelo readback. A nova UX está disponível em `https://commander.haralabs.com.br`.

O PROD anterior, `228fdb6d-fbde-4a1c-91b0-57ac73f5d193`, permanece disponível para rollback. Nenhuma migração D1, rotação de credenciais, atualização dos Agents ou reinício da frota foi necessária. As alterações foram limitadas à distribuição da interface e ao checkpoint de documentação.

**Gates ainda separados:** homologação nativa do cliente Windows, cobrança Stripe e revisão pública do aplicativo OpenAI.