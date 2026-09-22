# HARA Commander — Ponto 0 / encerramento desta frente — 2026-09-22 20:44:14Z

## Finalidade

Este documento marca o encerramento da frente atual e o ponto canônico de retomada do HARA Commander V1.

A missão canônica é:

`HARA account -> Linux/Windows computer -> Commander Agent -> outbound HARA relay -> ChatGPT/Codex -> exact governed five-tool bridge`

Commander V1 é um produto simples de conectividade do cliente. Não é NOC, Paradox, console de saúde/degradação, shell/SSH/filesystem genérico ou produto de Cloudflare Tunnel por cliente.

## Autoridade técnica

Documento de missão:
`docs/status/HARA_COMMANDER_PRODUCT_V1_MISSION_CURRENT_20260922.md`

Handoff técnico:
`docs/handoffs/HARA_COMMANDER_DEVICE_CONNECT_SUCCESSOR_HANDOFF_20260922T203602Z.md`

Arquitetura relay:
`hara-platform/docs/architecture/HARA_REMOTE_MCP_RELAY_V1.md`

HARA Site baseline antes deste marcador:
`e84bcaea6544a2f4d4688e07c1ca3e43b24346e1`

## Estado provado

PASS:
- HARA Identity e tenant/plan/entitlement;
- reviewer dedicado;
- pairing one-time e curto;
- installers Linux e Windows;
- persistência Linux systemd-user;
- persistência Windows Scheduled Task;
- Windows DPAPI + ACL;
- device credential, heartbeat, presença e revogação;
- ausência de cloudflared por dispositivo;
- relay outbound durável;
- polling outbound do Agent;
- claim atômico PENDING -> EXECUTING;
- retorno COMPLETED/FAILED;
- roundtrip de resultado;
- idempotência;
- unknown/arbitrary tool fail-closed;
- hara.health E2E pelo dispositivo;
- linguagem `Degradado` ausente da UI normal;
- authenticated first paint corrigido.

Worker DEV:
`e6303c51-135c-4f83-bd56-c3a6fdcb772f`

Functional relay baseline:
`abc1768f39c29bacb52396c10494d0ba1f931b4c`

## Boundary de maturidade

O transporte outbound é real, mas o produto ainda não está fechado em cinco tools.

Pendências obrigatórias para a próxima frente:
1. portable local bridge das cinco tools exatas;
2. bind public MCP identity/tenant -> dispositivo online selecionado;
3. rotear health/list/describe/read-only invoke/receipt pelo relay;
4. retornar resultado sanitizado + receipt;
5. testar installer/runtime Windows em host Windows real;
6. rodar canário ChatGPT/Codex read-only sem Desktop Commander;
7. só depois avançar OpenAI portal scan/submission;
8. billing/payment provider continua depois do canário real.

As cinco tools exatas permanecem:
- `hara.health`
- `hara.functions.list`
- `hara.functions.describe`
- `hara.functions.invoke`
- `hara.receipts.get`

Shell, filesystem e SSH arbitrários devem permanecer ausentes.

## Regra de retomada

Toda nova frente deve ler primeiro este marcador, a missão CURRENT e o handoff `203602Z`.

Não reabrir decisões já fechadas:
- produto simples device-connect;
- outbound-only Agent;
- HARA-owned relay;
- Cloudflare apenas no ingress HARA;
- sem tunnel Cloudflare por cliente;
- sem NOC/Paradox/degraded-state na UI;
- dark mode como referência visual;
- Clarus apenas refinamento visual subordinado;
- publicação e billing depois do ordinary-client canary.

## Estado da frente

`FRONT_STATE=CLOSED_FOR_SUCCESSION`

`POINT_ZERO=HARA_COMMANDER_DEVICE_CONNECT`

`NEXT_GATE=EXACT_FIVE_TOOL_PORTABLE_DEVICE_BRIDGE`

Este encerramento não declara o produto comercial completo; declara a frente atual documentada, reconciliada e segura para sucessão.
