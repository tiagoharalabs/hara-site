# H.A.R.A. Commander — detalhes de dispositivos e título redundante

Data: 10/10/2026. Escopo: somente HTML, JS e CSS do portal.

O botão ⋯ de cada máquina deve abrir Detalhes e ações: sistema, arquitetura, versão do Agent, transporte, política de autorização, último contato, autorização por 6h para Linux e revogação com confirmação.

O painel anterior utilizava details/summary com um popover absoluto e não aparecia ao clicar em algumas interfaces. A nova implementação usa button real, aria-expanded/aria-controls e painel inline, ocupando largura completa abaixo da linha. Abrir/fechar não faz requisições e não executa ações na máquina. A autorização e a revogação continuam exigindo interação adicional e os controles anteriores.

Removido o título repetido Comandos e integrações dentro do card. A aba superior continua nomeada; cartões e comandos continuam intactos. Cache keys HTML/CSS/JS alteradas para 20261010-device-details1.

A política Free=10.000 e Pro ilimitado, o MCP comercial, o Agent assinado 0.3.43, a frota Founder 0.3.44, o OAuth e o banco não foram alterados.

Teste de DOM com renderDevices verdadeiro comprova clique de abertura, fechamento, mudança de máquina, estado ARIA, histórico, autorização e revogação disponíveis. Gate offline 55/55 PASS.

DEV validado: Cloudflare Worker `hara-commander-dev-v2`, versão `b9ecf6c0-dd0d-4020-83ef-0746db2eadc7`, SHA de 11/11 assets exato e health 200. PROD será promovido com rollback e readback independente. Nenhum Agent, token ou quota foi alterado.
