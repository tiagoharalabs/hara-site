# H.A.R.A. Commander comercial — P0 Event V2 presence, release e frota
<!-- HARA_COMMANDER_PRODUCT_PRESENCE_RECOVERY_R1_20261021 -->

Data da captura: 2026-10-21 23:08–23:11 UTC. Execução pelo aplicativo COMERCIAL H.A.R.A. Commander `profile=simple`. Não pelo MCP Baseline, nem Desktop Commander.

## Defeito material reproduzido e reparo de sessão

- Services (Agent 0.3.54 Event V2): cadastro OFFLINE, `last_seen_at_utc=2026-10-21T15:33:33.705Z`; unit `hara-commander-agent-v2.service` active, PID prévio 1121102, socket TCP :443 ESTABLISHED; status local `connected=true` desde 18:21Z, portanto registro remoto defasado.
- Núcleo A (Agent 0.3.54 Event V2): cadastro OFFLINE, `last_seen_at_utc=2026-10-21T15:10:25.289Z`; unit active, PID prévio 2279, socket TCP :443 ESTABLISHED; status `connected=true` desde 19:56Z.
- Recuperação **somente do Agent Event V2**, sem alterar versão, launcher, pareamento, credenciais, legado, Codex ou frota: `systemctl --user restart hara-commander-agent-v2.service`, um host por vez, com autorização persistente existente. Services reiniciou e retornou produto MCP `ping=PASS`, `device.info=0.3.54/EVENT_V2/PERSISTENT_TRUSTED`. Núcleo reiniciou após Services e retornou `ping=PASS` e `device.info` idêntico.
- Recibos de reinício comercial: Services `4bff6db89550cad339f8fa207d896fc50118a0d1ef89144290d3523f35a12ee3`; Núcleo `cc5b6b14d46c71316be159cdd1d42b48c8bc5d733bea742d5d16fdb17804839c`.
- Recibos de POST ping: Services `eb5c5b488681a8dd0e95bc8969b2bbc8092774f5d51849eb605cbf3413b669c4`; Núcleo `a1ca52151bf76360315eb7c2b3c181faaf93ca53be0009858ac7d0f5c53b3be3`. Último contato de ambos avançou a ~23:08Z. É **recuperação transitória**, não fix permanente.

## Causa provável específica: incompatibilidade de timers

Fonte revisada read-only em Services:
- `apps/commander/src/worker.js`: online EVENT_V2 até 7h após `last_seen_at_utc`, incluindo gate de chamada; `device-channel.mjs`: handshake `markConnected` persiste presença apenas se `last_seen_at_utc` tem mais de 5h ou modo mudou.
- `experimental/event_v2_agent_loop.py`: `last_liveness = connected_at` reiniciado em cada WebSocket reconnection; `experimental/event_v2_websocket.py`: `DURABLE_LIVENESS_SECONDS=6h`, com jitter +/-15min.
- Contraexemplo: uma reconexão quando last_seen tem 4h59m não persiste novo last_seen (corte 5h), mas reinicia o timer LIVENESS. Primeiro checkpoint posterior pode vir 6h15m depois da reconexão, total 11h14m após last_seen anterior — a porta de admissão do produto corta após 7h. Possível janela offline ~4h14m apesar de WebSocket conectado.
- Exemplo Serviços: last_seen 15:33Z, reconnect 18:21Z (idade 2h48), expiração 22:33Z, próximo LIVENESS ~00:06–00:36Z. Isso é consistente com a falha observada. Atenção: a fonte local NÃO prova sozinha paridade byte-a-byte com PROD Worker, conforme `hara-site#310`. Confirmar por hosted DEV/PROD read-only.
- Teste independente em `test_presence_gap.py` modela o contraexemplo sobre as constantes originais (red proof). Esperado `RED_GAP_REPRODUCED`. Criar depois teste de regressão da implementação proposta.

## Segundo bloqueio: aprovação e versão

Storage/Observer: Agent comercial estável 0.3.43, OUTBOUND_RELAY, `ASK_EVERY_ACTION`, serviço systemd USER ativo e linger=yes, mas `hara-commander status` retorna `HARA_COMMANDER_SESSION=INACTIVE`. Portal classifica OFFLINE após grace. NÃO usar SSH ou outra máquina para burlar sua aprovação local; restaurar sessão por operador e decidir explicitamente política de autorização confiável na UX do produto. O modo `Permitir tudo` do ChatGPT NÃO é autorização persistente do Agent.

Windows 11: produto `HARA_WIN11` Agent 0.3.55, ping PASS, QA de console/rotação permanece owner #240.

Release pública assinada Linux stable continua `0.3.43`, manifesto SHA256 `53c0cbc2b074b9b85b81454c2bce286a8af2fa981e79f3c9b1719c5697880229`; instalador SHA256 `699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463`. Founder Event V2 .54 é host-bound e `FULL_AGENT_SIGNED_PUBLIC_RELEASE=FALSE`; copiar launchers entre hosts ou atualizar v0.3.54 com instalador 0.3.43 é downgrade proibido.

## Ordem para o Codex sem competição de checkout

1. **Owner #163 Event V2:** produzir correção de presença que preserve custo D1, controle de picos, reconexão e separação de autoridade. Preferir deadline vinculado ao registro remoto efetivo/handshake sobre reset cego `last_liveness=connected_at`. Não aumentar TTL como gambiarra, nem introduzir heartbeat HTTP 30s/loop polling. Provar cenário offline com reconexão <5h e jitter máximo, supressão de D1, socket half-open, concorrência superseded, fallback/rollback; DEV hosted antes de PROD.
2. **Owner #310 Linux/release:** integrar patch anti-downgrade, ajustes de primeira instalação (13/13) e update/rollback (11/11), emitir release assinada NOVA coerente para x86_64 e aarch64, verificar SHA/RS256 no artefato exato, canário real e rollback por nó; **não fazer downgrade** dos sete Founder 0.3.54.
3. **Owner #310 Storage/Observer:** com release pública sucessora aprovada, obter aprovação local do operador para migração; não replicar tokens de hosts; POST: SHA, versão do binário ATIVO, systemd enabled/active, modo, reconexão, ping, leitura, write protegido e rollback.
4. **Owner #240 Windows:** manter 0.3.55 funcional, preservar histórico sob consulta e corrigir replay após rotação em nova release Windows assinada.
5. **Owner Codex / hara-platform#1953:** preservar worktrees ativos (em especial `commander-product-current` sujo), não git add -A, não alterar main nem PROD sem DEV/PR/CI/rollback; registrar recibos separados para Services, Núcleo, Storage, Observer e versão/publicação real.

Fontes existentes: `hara-site#310` comentário `6327595112`; patch 38/38 normal+O em `packages/control-plane/HARA_COMMANDER_FLEET_RELEASE_FLOOR_QA_20261021/`; `commander-linux-composed-qa-20261021` 24/24; `review/commander-linux-upgrade-r26-20261021` e `apps/commander/reviews/HARA_COMMANDER_VERSION_HISTORY_R1_20261021` têm análises candidatas, não releases assinadas.

## Estados de aceitação
`SERVICES_AND_NUCLEO_TEMP_RECOVERY=PASS`
`EVENT_V2_PRESENCE_BUG_SOURCE_COUNTEREXAMPLE=RED_REPRODUCED`
`FULL_FLEET_LATEST_SIGNED_RELEASE=HOLD`
`STORAGE_OBSERVER_LOCAL_AUTH=SESSION_INACTIVE`
`PROD_SIGNED_UNIVERSAL_RELEASE=NOT_DELIVERED`
`NO_DOWNGRADE=TRUE`
