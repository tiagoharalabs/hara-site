# Event V2 comercial — evidência local e gate de promoção

Base QA `482169251b347b77380d8becf878e5c515c75c8a`, branch `codex/commander-prelaunch-fixes-20261020`. Comparada com `origin/local/commander-event-v2-pong-deadline-20261013`: o filtro de wake para socket atual foi incorporado e coberto por teste. Nenhum transporte paralelo foi criado. A fila D1 continua a autoridade; a notificação WebSocket só acelera o claim.

## Evidência local

| Prova | Resultado | Limite da prova |
| --- | --- | --- |
| `test_event_v2_notify_delivery.mjs` | PASS | socket substituído/sem attachment não conta como entregue; falha de envio não impede outro socket válido |
| `validate_event_v2_wiring.py` | PASS | insert D1 antes da notificação, claim, recibo, caminho de falha e flag PROD protegida em fonte |
| `validate_event_v2_presence_reconnect.py` | 34/34 PASS | prazo original e checkpoint preservados após desconexão/reconexão |
| `validate_event_v2_websocket_client.py` | PASS | PING mascarado, framing, TLS, reconexão, drenagem e ausência de polling ocioso em fixture |
| `validate_event_v2_clean_shutdown.py` | PASS | fechamento e estado local após SIGTERM |
| `validate_event_v2_fleet_allowlist.mjs` | PASS | PROD nega dispositivo não listado, mesmo autenticado |

## Qualificação comercial pendente

O Agent comercial público `0.3.43` permanece no transporte `OUTBOUND_RELAY`; os Agents Event V2 assinados observados são da frota Founder. O bundle comercial v5 preparado nesta branch ainda não tem assinatura oficial. Os resultados acima são regressões locais, não uma instalação limpa de cliente Linux ou Windows, nem uma prova de DEV/PROD.

Para liberar uma instalação comercial Event V2, usar o cliente Event V2 já existente, preservar o fallback `OUTBOUND_RELAY` e verificar em tenant novo com credencial própria: pacote assinado e hash/versão, inscrição, socket, PONG, desconexão, reconexão, notificação, claim único, recibo SHA e quota. Testar o rollback do Worker por flag de Event V2 e o retorno ao Agent assinado anterior sem dois Agents simultâneos. Não alterar os sete dispositivos Founder nem incluir um ID comercial na allowlist PROD nesta sessão.

**Estado:** corrigido no código: filtro de wake; testado local: sim; testado DEV: não; publicado PROD: não. O gate comercial continua HOLD por assinatura e prova de cliente novo.
