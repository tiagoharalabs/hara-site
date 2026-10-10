# H.A.R.A. Commander — Computadores: refinamento minimalista

**10/10/2026 — identidade visual mantida.** Refinamento restrito ao HTML/JS/CSS da tela de dispositivos. Não modifica Agents comerciais assinados 0.3.43, Founder 0.3.44, autenticação, billing, D1 ou Worker API.

## Experiência implementada

- Lista exibe nome, sistema, último contato compacto, estado derivado da conexão real (Pronto, Atenção, Offline) e até uma ação direta (copiar Diagnóstico).
- Uma linha textual mostra N online e M offline, sem cards adicionais. Mantidos filtros Ativos/Histórico, Atualizar e Conectar novo.
- Agent version, arquitetura, transporte, modo de autorização e hora exata foram deslocados para um menu nativo de Detalhes (disclosure com summary), acessível por teclado.
- Autorizar 6h/Renovar e Revogar estão preservados no menu secundário; a revogação mantém o mecanismo de confirmação em duas etapas.
- Lease Direct válida não mascara uma máquina offline; somente ligação real permite o rótulo Pronto.
- Guias Primeiros passos e Onde usar continuam disponíveis, mas recolhidos por padrão numa seção discreta; ficam ocultos enquanto a aba Conectar novo estiver aberta.
- CSS somente para [data-view=devices], com regras próprias de tema dark e mobile. Cores/tokens de marca Navy/Blue/Gold/Success, ícone capivara e neon não foram alterados.
- HTML usa versões novas de assets styles.css?v=20261010-devices-minimal1 e app.js?v=20261010-devices-minimal1.

## Evidências

- Node VM test_devices_minimalist_ui.mjs executa a função renderDevices real contra DOM simulada para conferir contagens, presença vs lease, aba histórico, metadados ocultos, ação de diagnóstico, autorização e revogação disponíveis.
- validate_prod_static, validate_device_installers, validate_bootstrap_supply_chain, validate_portal_origin_guard, validate_portal_activity_contract, validate_manual_on_demand_commercial: PASS.
- Gate offline H.A.R.A. Commander 54/54 PASS, com teste de concorrência isolada já existente e zero mutações de frota.
- DEV Worker hara-commander-dev-v2: versão 636d9e2f-883c-4a0d-96e1-8280ee2ee4ad; 11/11 assets byte-idênticos ao estágio, health HTTP 200.
- Stage de deploy: /tmp_hara/commander-public-commercial-v2-20261010/apps/commander. Os 8 componentes da release assinada são byte-idênticos ao backup em Git.

## Promoção, monitoramento e rollback

Antes do deploy PROD conferir secrets, versão anterior e hashes. Promover somente assets/Worker mantendo D1 Free=10.000 mensal, o mesmo MCP/Cloudflare e o mesmo pacote comercial assinado. Conferir HTML, JS, CSS e 8 assets assinados por SHA; para HTML, remover apenas o beacon Cloudflare reconhecido. Se o readback falhar, reverter versão Worker anterior. A frota Founder e seus serviços não entram no plano de atualização.

**Estado atual deste registro:** staging e DEV comprovados; registrar o identificador da versão PROD após publicação e readback real.