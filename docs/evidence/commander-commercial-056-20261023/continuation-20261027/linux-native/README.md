# Commander 0.3.56 — Linux QA: modo persistente e MCP local

**Resultado: Agent .56 verificado, autorização persistente aplicada pela CLI oficial e três chamadas reais de MCP local aprovadas na conta `commanderqa` (UID 2000). O serviço reiniciou com sucesso e registrou um heartbeat novo. O Cloud MCP ponta a ponta da VM continua pendente de seleção no escopo disponível.**

## Entregas comprovadas

| Verificação | Resultado |
|---|---|
| Agent instalado | 0.3.56; 265.620 bytes; SHA-256 `ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d`; proprietário UID 2000 e modo 0700. |
| CLI | `--version` retornou 0.3.56; `--self-test` e suporte terminaram com exit 0. |
| Autorização | CLI oficial `approval-mode always`: `ASK_EVERY_ACTION` → `PERSISTENT_TRUSTED`. |
| Configuração | Outras linhas preservadas, preimage registrado, proprietário UID 2000 e modo 0600. O hash anterior coincide com a captura de metadata. |
| Serviço após restart oficial | `active/running`, PID 3428 (antes: 1072), início em 28/10/2026 às 00:13:27 UTC; autostart desabilitado. |
| Modo após restart | Suporte confirma `PERSISTENT_TRUSTED` com `operator_session_active=false`. |
| Heartbeat novo | Suporte registra sucesso em **28/10/2026, 00:13:28.640788 UTC**; sem erro de runtime registrado. |
| Saúde HTTPS | Ambientes de desenvolvimento e principal: exit 0, HTTP 200 e `ok=true`. |
| Catálogo MCP local | Protocolo `2025-06-18`, servidor 0.3.56 e 24 ferramentas distintas. |
| Chamadas locais reais | `get_config`, `get_device_info` e `start_process`, sem erros JSON-RPC ou resultados de erro. |

O processo de teste retornou **UID 2000**, nonce e SHA-256 corretos, com exit 0, sem timeout ou truncamento e sem sessão retida. A consolidação recompôs o comando da fixture e conferiu seu SHA-256 contra o recibo do Agent. A autorização foi `PERSISTENT_TRUSTED` por `DEVICE_ENROLLMENT_POLICY`.

A fixture nativa completa — início do servidor local, três RPCs e término — mediu **0,265 s**. Essa medida não representa latência pela nuvem. O catálogo de 24 ferramentas não significa que as 24 foram executadas: os três RPCs acima são os efetivamente demonstrados. A observação de modo persistente sem sessão de operador ocorreu no suporte após o restart; não representa outra execução de processo após o restart.

## Pendência de Cloud MCP e limites

As chamadas reais usaram **`LOCAL_STDIO`**, com autoridade `HARA_COMMANDER_LOCAL`. O acesso do orquestrador para executar a fixture não constitui prova de Cloud MCP ponta a ponta da VM Ubuntu. A configuração de produto aponta para **desenvolvimento**, com transporte `OUTBOUND_RELAY`; a URL e os dados privados foram omitidos.

No MCP principal, as duas consultas da VM — por nome e pelo ID de dispositivo registrado — retornaram **`DEVICE_NOT_FOUND` / `DEVICE_SELECTION`**, sem mutação. O inventário do escopo disponível retornou nove dispositivos e não incluiu os identificadores consultados. Nenhum processo foi encaminhado à VM por essas consultas. A seleção/registro no escopo de conta disponível continua pendente; **a causa não foi determinada e esses resultados não demonstram falha do processo Linux**.

O heartbeat de **13/10/2026** pertence à captura anterior ao restart e é histórico. O heartbeat novo está comprovado pelo readback nativo do suporte; não há neste conjunto recibo independente do servidor de nuvem. HTTP 200/`ok` demonstra alcance e saúde declarada dos endpoints, sem comprovar entrega autenticada de ferramentas de ponta a ponta.

Os campos de runtime da captura inicial de metadata vieram nulos. A versão foi confirmada pela CLI e por `get_device_info` local; o readback posterior trouxe o heartbeat novo e o modo persistente. O autostart permanece desabilitado. Este registro não concede aceite de restauração, Windows, recuperação sob falhas ou lançamento público.

## Rastreabilidade

O [resumo JSON](linux-native-summary.json) contém checks independentes, recibos selecionados e SHA-256 das evidências e da fixture executada. A origem que também contém o fechamento Windows foi usada somente em sua seção Linux.

A exportação não contém configuração privada, hashes do arquivo de configuração, credenciais, comandos ou saídas brutas, IDs de dispositivo, URL do endpoint ou dados de sessão.
