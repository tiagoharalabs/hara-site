# H.A.R.A. Commander — controle manual Founder (10/10/2026)

O usuário pediu instalação nova em todas as máquinas atualmente online e comandos de start/stop. A frota Founder utiliza Agent 0.3.44 Event V2 assinado, enquanto o novo instalador comercial é 0.3.43. **Não fazer downgrade nem reinstalação comercial** na frota Founder.

Foi instalado o comando local executável `~/.local/bin/hara-commander-v2` nas seguintes máquinas por canais autorizados:
- `nucleo-a`, `sentinela-c` e `services`: via Desktop Commander Remote, com teste real de `systemctl --user`.
- `sentinela-d`: via MCP **comercial** `H_A_R_A__Commander.start_process`, com autoridade `HARA_COMMANDER_AGENT`, recibo e saída `HARA_D_MANUAL_CONTROL=PASS`.

Nas quatro, `hara-commander-agent-v2.service` continua ativo, porém **disabled** no boot; `hara-commander-v2-guard.timer` foi **disabled --now**, permanecendo inactive. `hara-commander-agent.service` legado permanece inativo, e binários assinados 0.3.44 foram preservados. **Nenhuma conexão ativa foi derrubada.**

Comandos Founder: `hara-commander-v2 start`, `hara-commander-v2 stop`, `hara-commander-v2 status`. Não confundir com o CLI legado `hara-commander start`, que ainda aponta para o Agent v0.3.41.

As demais máquinas `sentinela-a`, `sentinela-b`, `ninja-blue` estavam inacessíveis no inventário comercial ou nos canais remotos permitidos, e não foram alteradas. O inventário do Services e Sentinela C estava defasado/offline no MCP comercial apesar de os serviços V2 locais estarem ativos. Windows não foi alterado.

**Risco assumido:** o guard de recuperação automática Founder foi desabilitado para respeitar o modo manual; essa proteção não opera mais. Para restaurar a política anterior de conexão persistente por decisão explícita do operador local, habilitar `hara-commander-agent-v2.service` e `hara-commander-v2-guard.timer` após revisar impactos da recuperação/fallback. A instalação de controle é exclusivamente local, não é uma nova release comercial pública.
