# H.A.R.A. Commander — Fleet Agent signed 0.3.41 rollout (2026-10-09)

## Estado autoritativo verificado

**Sete hosts ativos em produção, Agent 0.3.41 assinado**, confirmados por download real do instalador, runtime local, cadastro Cloudflare PROD D1 e `ping` real com recibo no Agent.

| Host | Antes | Depois | systemd --user | Linger | Execução |
| --- | --- | --- | --- | --- | --- |
| nucleo-a | 0.3.41 | 0.3.41 | enabled, active | yes | ping PASS |
| services | 0.3.40 | 0.3.41 | enabled, active | yes | ping PASS |
| sentinela-a | 0.3.40 | 0.3.41 | enabled, active | yes | ping PASS |
| sentinela-b | 0.3.40 | 0.3.41 | enabled, active | yes | ping PASS |
| sentinela-c | 0.3.40 | 0.3.41 | enabled, active | yes | ping PASS |
| sentinela-d | 0.3.40 | 0.3.41 | enabled, active | yes | ping PASS |
| ninja-blue | 0.3.40 | 0.3.41 | enabled, active | yes | ping PASS |

Máquinas A/B/C/D e Ninja estavam com o Agent 0.3.40 já instalado e cadastrado, porém `hara-commander-agent.service` **inativo/desabilitado**. O Services estava ativo na versão 0.3.40. O Núcleo A já estava na 0.3.41.

### Procedimento real executado

- A partir do Services, conexão SSH legítima, sem alterar `sshd` ou distribuir chaves, para A/B/D/Ninja; Sentinela C via Remote Desktop Commander conectado. Services atualizado localmente.
- Baixado `https://commander.haralabs.com.br/install/linux.sh` via HTTPS com SHA-256 exato `99b25c7671326b983ff1fa670ce0044f9a89674dcd1b2d78cf8ab4a6cccb828b`. Validado `bash -n`.
- Executado `bash <signed_installer> update`, com `HARA_COMMANDER_AGENT_INTEGRITY=PASS`, `HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS` e `HARA_COMMANDER_AGENT_UPDATE=PASS` em cada atualização.
- Após atualização, `systemctl --user enable --now hara-commander-agent.service`, `doctor` PASS, saúde remota PASS e SHA-256 do Agent binário oficial `e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730` PASS.
- `device.env` existente preservado byte a byte (SHA-256 antes/depois idêntico) em todas as seis atualizações. Tokens não expostos nem reenrolados. Nenhum host reiniciado.
- `loginctl enable-linger` aplicado pelo próprio usuário nas Sentinelas A e D; a política estava `Linger=no` e foi confirmada `yes`. Os demais já tinham `yes`.
- Nenhuma fila de jogo/recompilação foi ligada e nenhum Agent 0.3.43 candidato não assinado foi instalado.

### Dupla comprovação da conexão

1. PROD D1 `commander_devices` listou **sete** registros `ACTIVE`, todos `agent_version=0.3.41`, `tunnel_mode=OUTBOUND_RELAY` e `last_seen_at_utc` recente (2026-10-09).
2. O conector **H_A_R_A__Commander_Baseline** executou `hara_ping` individualmente nos sete hosts: todos `state=PASS`, `execution_authority=HARA_COMMANDER_AGENT`, com `bridge_receipt_sha256` presente.

**Limite explícito:** os pings são pela autoridade `HARA_SERVICES` do conector Baseline. Esta evidência comprova os Agents remotos e o transporte atual, mas **não** homologa o E2E do ChatGPT autenticado pelo MCP comercial Cloudflare (`https://commander.haralabs.com.br/api/mcp?profile=simple`). Essa homologação comercial ainda exige conexão distinta, OAuth e teste real de cliente. A versão assinada PROD continua 0.3.41; candidata 0.3.43 segue sem assinatura válida.

### Manutenção

O serviço de usuário fica habilitado e a configuração de linger o mantém executável enquanto os computadores estão ligados, mesmo sem sessão gráfica, sujeito ao estado real de rede/energia. Não confundir offline do Remote Desktop Commander com estado do Agent H.A.R.A. Commander. Não alterar políticas de CPU/GPU, nem criar sessões de treinamento na D para validar o Agent.
