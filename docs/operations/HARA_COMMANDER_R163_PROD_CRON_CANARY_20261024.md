# H.A.R.A. Commander #163 — PROD cron Storage-only (24/10/2026)

**Execução:** autorizada pelo proprietário; produção, alteração exclusivamente do agendamento do Worker `hara-commander` via Wrangler `triggers deploy` com configuração mínima sem routes/assets/bindings. **Não** houve novo deploy de código, alteração do D1 produtivo, alteração de Agent, VM, release ou segredo.

**Preflight:** versão de código ativa `8b6d44ce-dd16-4dbb-aa1a-114153c53851` (100%). No `wrangler versions view --json`, `COMMANDER_RECOVERY_ALERTS_ENABLED=true`; whitelist contém exatamente a matrícula ativa do Storage (Agent 0.3.54, `PERSISTENT_TRUSTED`, `OUTBOUND_RELAY`). Todos os outros dispositivos excluídos. A matrícula antiga do Storage permanece revogada. `/api/health` HTTP 200. O D1 já continha `commander_device_recovery_events`, mas tinha zero eventos.

**Causa:** a versão ativa implementava `event.cron === "* * * * *"`, porém só estava publicado o cron horário `17 * * * *`. Logo, faltava a invocação periódica de 1 minuto em PROD.

**Correção aplicada:** Cloudflare confirmou `Deployed hara-commander triggers` com **ambos** `17 * * * *` e `* * * * *`. Pós-alteração, `/api/health` respondeu 200, a versão em 100% continuou `8b6d44ce-dd16-4dbb-aa1a-114153c53851`, a flag e whitelist foram reconfirmadas na versão remota e no D1 (uma única matrícula Storage). Não houve republicação de código; o domínio comercial continuou acessível.

**Fonte:** commit `cf4bfd6fced85d5dc857a4a80c2b7e7497e78f90` mantém as duas agendas em `apps/commander/wrangler.jsonc`. Esse arquivo, intencionalmente, **não** inclui os vars de ativação e allowlist: um deploy novo só será habilitado quando autorizado. Perfil de triggers-only versionado em `apps/commander/scripts/wrangler-triggers-only-prod-r163.jsonc`.

**QA:** contrato 30/30 PASS (incluindo perfil de triggers-only), DOM 3/3 PASS, seleção sintética de 20.000 dispositivos PASS (não é teste integral de transporte Event V2), regressão Node 45/45 PASS. O teste histórico de regressão R14 só isenta a alteração intencional no cron e compara todas as demais configurações.

## Reversão controlada

No Services, via H.A.R.A. Commander, após conferir o estado e a autorização:

```bash
NODE=/home/sartorius/.nvm/versions/node/v24.15.0/bin/node
WR=/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules/wrangler/bin/wrangler.js
CFG=/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-recovery-alerts-r1-20261024/apps/commander/scripts/wrangler-triggers-only-prod-r163.jsonc

# Voltar somente à agenda horária, preservando código e domínio:
"$NODE" "$WR" triggers deploy --config "$CFG" --triggers "17 * * * *"

# Após revisão/aceite, reaplicar ambas as agendas:
"$NODE" "$WR" triggers deploy --config "$CFG"
```

Depois de qualquer operação, verificar retorno do Wrangler, versão de código 100%, bindings/allowlist e saúde HTTP 200. A agenda por minuto tem consumo recorrente de Worker/D1; acompanhar e desabilitar caso gere regressões.

## Escopo e pendências

O Storage estava **saudável** e continua no Agent **0.3.54**; não induzimos falha nem fabricamos incidente. Portanto o D1 PROD segue sem evento natural confirmado nesta observação, embora o canário DEV separado tenha provado detecção em 125,903 s e recuperação em até 2,029 s.

A outbox do candidato Agent 0.3.56 permanece fora de PROD, aguardando Valk, assinatura, pin e admissão. A entrega HTTPS independente comprovada é de QA, **não** prova que uma pessoa recebeu e-mail/push. Escala Event V2/20k e liveness da frota continuam gates distintos da issue #163.
