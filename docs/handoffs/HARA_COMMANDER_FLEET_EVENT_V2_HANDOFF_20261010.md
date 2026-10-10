# H.A.R.A. Commander — CURRENT: Frota Linux Founder em Event V2
**Checkpoint operacional de 10/10/2026, BRT, após migração da frota inteira.**

> Este documento SUBSTITUI, quanto ao estado vivo dos Agents e Worker, o handoff `HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md` e a preparação `HARA_COMMANDER_EVENT_V2_FOUNDER_FLEET_STAGE_20261010.md`. Não ignorar os gates comerciais pendentes. Seguir APENAS `local/commander-product-current`; não abrir branches paralelas de produto.

## 1. Resultado verificado no produto comercial

**Todas as sete máquinas Linux Founder que estavam online foram efetivamente migradas para H.A.R.A. Commander Agent 0.3.44 + EVENT_V2, e comprovadas por `mcp__H_A_R_A__Commander__get_device_info` com `operational_authority=HARA_COMMANDER`, `execution_authority=HARA_COMMANDER_AGENT`, `customer_services_relay=false` e recibo SHA-256.** O ping comercial também passou em cada máquina na rodada. Não confundir esta prova com `H_A_R_A__Commander_Baseline`/Services.

| Máquina | Agente atual | Transporte | Comercial E2E | v1/rollback |
|---|---|---|---|---|
| nucleo-a | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |
| sentinela-a | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |
| sentinela-b | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |
| sentinela-c | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |
| sentinela-d | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |
| ninja-blue | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |
| services | 0.3.44 | EVENT_V2 | PASS | 0.3.41 preservado |

- Nas sete máquinas, serviço de usuário `hara-commander-agent-v2.service` = **active + enabled**, serviço anterior `hara-commander-agent.service` = **inactive + disabled**, `hara-commander-v2-guard.timer` = **active**. Readback individual com hostname após o grace confirmou **`EVENT_V2_GUARD_HEALTH=PASS` em 7/7**, com **`NRestarts=0` em 7/7**. Não houve reboot ou failover deliberado.
- Registros históricos HARA_WIN11: um OFFLINE, outros REVOKED. Não atualizar contas de máquinas revogadas/offline nem declarar Windows Event V2 homologado.
- O Services é tanto host de infraestrutura quanto um computador cliente Founder no produto; **a migração foi apenas da unidade de usuário do Agent**, sem mutar o backend Services nem os projetos H.A.R.A. paralelos.

## 2. Cloudflare PROD e autoridade

- O cliente comercial usa `https://commander.haralabs.com.br/api/mcp?profile=simple` via HARA Identity/OAuth, Cloudflare Worker, Durable Object `DeviceChannel`, Agent no dispositivo, D1 e recibos. O caminho não é um túnel privado direto da OpenAI.
- Worker PROD `hara-commander`: versão atual após última configuração da allowlist **`29e556f3-86af-476d-ba01-a764c3acb6a0` com tráfego 100%**, lida em `wrangler deployments list --json`. Antes deste rollout, o Worker ativo era `215ab34e-78ad-4002-a4d6-7e26e3a71f94`.
- `DEVICE_EVENT_V2_ENABLED=true`, `DeviceChannel` DO v3 hibernável, `DEVICE_EVENT_V2_CANARY_DEVICE_ID` autoriza Núcleo A. **Nova allowlist segura** `DEVICE_EVENT_V2_ADDITIONAL_DEVICE_IDS` foi configurada como **secret** do Worker com as outras seis máquinas Founder; listagem dos nomes de secrets confirmou presença, e o teste comercial real provou os seis dispositivos aceitos.
- O Worker exige dispositivo autenticado + ID na allowlist; no teste de fonte `validate_event_v2_fleet_allowlist.mjs`, cliente desconhecido, entrada inválida, curinga e IDs duplicados foram negados antes do DO. Ausência do secret volta ao único canário original. **Não liberar todos os tenants** nem mover IDs internos para `wrangler.jsonc` público.
- A implantação usou `build_prod_signed_event_v2_stage.py`: os quatro assets públicos de 0.3.41 mantêm hashes da assinatura original. O código do Worker mudou, **mas o instalador público e release v1 não foram substituídos**.
- `DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED` NÃO foi habilitado em PROD. Telemetria de `last_seen` deve ser revisada: há indício anterior de leitura defasada mesmo quando transações comerciais por Event V2 concluíram; não declarar heartbeat de presença resolvido apenas pela atualização.

## 3. Releases, custódia, instalação e retorno

- Fonte do release v2: pacote Founder original 0.3.44 assinado sob `/tmp_hara/commander-event-v2-0.3.44-founder-signed-v2` no Services; chave pública v2 `kid=commander-release-v2`, RSA-3072/RS256 e fingerprint SHA256 `93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`.
- O novo empacotador `apps/commander/scripts/event_v2_founder_fleet_release.py` gera manifesto assinado **por identidade**, launcher vinculado ao dispositivo, verificador com mesmo ID e hashes exatos dos seis componentes. Pacotes temporários: `/tmp_hara/commander-event-v2-0.3.44-fleet-<nome>-signed-r3`. Chave privada v2 PERMANECE no Services, nunca em clientes/GitHub/logs.
- Caminho instalado nas seis máquinas novas: `~/.local/share/hara-commander/releases/0.3.44-fleet-event-v2`. Núcleo usa pacote independente original `~/.local/share/hara-commander/releases/0.3.44-founder-event-v2`. As unidades usam `ExecStartPre` para validar RS256 + hashes antes de iniciar, `PYTHONDONTWRITEBYTECODE=1`, `Conflicts=hara-commander-agent.service` e opt-in Event V2.
- Watchdog local `~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py` roda por `hara-commander-v2-guard.timer` (~120 s) e testa o TCP real, estado systemd e status Event V2. **Não colocar `PrivateTmp=yes` na unidade de guard**, para preservar atribuição PID em `ss -tnp`. Há grace inicial ~105s e exigência de duas falhas consecutivas antes do fallback.
- **Rollback individual, SOMENTE quando necessário:** `python3 -B ~/.local/share/hara-commander/ops/commander_event_v2_persistent_guard.py --rollback`. Para v2 antes ativa, ela para/desabilita v2, verifica que v2 não está ativa, depois habilita/inicia v1, desarma o guard. Não subir dois agentes com um token. Não tocar no D1 para rollback.
- SSH da Sentinela A: o `ssh -G` em Services definia `UserKnownHostsFile=/dev/null`, portanto `StrictHostKeyChecking=yes` não tinha uma ED25519 previamente pinada. A chave pública foi **obtida pelo Commander autenticado em `/etc/ssh/ssh_host_ed25519_key.pub`** e comparada byte a byte com `ssh-keyscan`; fingerprints coincidiram `SHA256:cWBGDChSvUAOomkbvixX9eQuyNTDGtOV/H/nA8BCpWc`. Arquivo independente restrito `~/.ssh/hara-commander-fleet-known-hosts`; somente usar A com `-o StrictHostKeyChecking=yes -o UserKnownHostsFile=~/.ssh/hara-commander-fleet-known-hosts`. Não desativar verificação de chave SSH.

## 4. Provas de teste e limites

- PASS: `validate_event_v2_wiring.py`, `validate_event_v2_websocket_client.py`, `validate_event_v2_persistent_guard.py`, `validate_multitenant_isolation.py`, `validate_prod_fail_closed.py`, `validate_prod_contracts.py`, `validate_prod_static.py`, `validate_event_v2_fleet_allowlist.mjs`, assinatura/verificação v2 por dispositivo, `wrangler deploy --dry-run`, SHA-256 de recibos e E2E real para todas as 7 máquinas.
- Núcleo original continuou respondendo após deploy Worker e atualizações do secret, assim como A/B/C/D/Ninja/Services. **Nenhum reboot/cold boot nem failover real forçado foi executado**. O guard A também passou no readback after-grace; ainda falta soak 24 horas, não chamar de SLA/custo certificado.
- Medição prévia comparável de 40 min e 4 operações comerciais/janela com só Núcleo no Event V2: fila `/api/device/calls/next` **1.756 → 1.392 (−20,7%)**; requisições Worker **2.066 → 1.658 (−19,7%)**, 0 erros em ambos os agregados. Dados medem Worker da frota, não a economia causal isolada do Núcleo; **ainda não há medição comparável após 7/7 Event V2 e nem economia na fatura comprovada**. Próxima avaliação: 1–24h, Worker requests, D1, DO duration/WebSocket, reconexões e custos reais.
- A tentativa opcional de adicionar uma guarda extra ao empacotador foi recusada por configuração de segurança de ferramenta. NÃO contornar a recusa; manter revisão de allowlist do empacotador como item de hardening antes de distribuições externas. Releases existentes foram limitados manualmente a identidades autorizadas, assinados e validados individualmente.

## 5. PROD billing: ainda NÃO pronto para cobrar

Preflight read-only `python3 apps/commander/scripts/billing_prod_activation_preflight.py --live` confirmou:
- Trial Free = **10.000 operações governadas/mês**.
- Standard Pro = **R$ 80/mês** no catálogo, ilimitado. Plano SCALE NÃO ativo.
- **PENDENTES** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD`; sem billing connections/webhooks; `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`.
- O preço no catálogo não é checkout conectado nem cobrança real. Não anunciar produto final como assinatura comercialmente ativa.

## 6. Pendências priorizadas para produto final

1. **P0 Stripe:** criar/verificar produto e Price BRL autorizados, secrets de produção, endpoint webhook assinado, deduplicação/replay, checkout real supervisionado, portal, cancelamento/refund e ciclo completo de entitlement.
2. **P0 Cliente externo/segurança:** testar OAuth de segundo tenant, pairing/revogação, grants locais, isolamento cross-tenant em PROD/DEV isolado, negativa de tokens cruzados, autorizações e dados protegidos. As sete máquinas de hoje pertencem ao Founder, não a clientes independentes.
3. **P0 Quota Free real:** última operação aceita, `QUOTA_EXCEEDED` subsequente, concorrência de reservas, idempotência de replay, liberação em erro e virada mensal; Founder ilimitado NÃO homologa Free.
4. **P1 Publicação de Agent:** transformação de pacote Founder per-device para instalador/atualizador de cliente final Linux, cadeia de confiança/rotação de assinatura v2, atualização assistida, rollback automatizado e documentação de suporte. **Windows Event V2 está pendente**; registros antigos offline/revogados não foram migrados.
5. **P1 Operabilidade:** testar cold boot / `Linger` real, falha de WebSocket e fallback deliberado em janela, soak 24h, métricas por dispositivo, `last_seen`/heartbeat real e prova de que nenhum Agent duplica token após reconexão.
6. **P1 Custos:** confirmar redução de requisições de polling e custo por DO/Worker/D1 com 7/7 atualizado, Cloudflare Invoice e limites do plano. Não afirmar economia financeira antes disso.
7. **P1 Git/CI:** publicar alterações futuras pela branch canônica e readback exato; Storage divergente protegido precisa reconciliação administrativa autorizada; falta escopo GitHub `workflow` para CI novo, não contornar.
8. **P2 Lançamento:** revisão de onboarding/autenticação, renovação de sessão/token, suporte/documentação, privacidade/termos, disponibilidade, checkout UX e comunicação transparente do que foi homologado.

## 7. Git: linha única e proteção de Storage

- Repositório `tiagoharalabs/hara-site`, branch **`local/commander-product-current`**, worktree Services `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`.
- Commit publicado imediatamente antes deste documento `5d187c4c62dad95fb4be840d3a637c688325435d` — atualização de Worker, empacotador, testes e preparação. Houve `GITHUB_EXACT_READBACK=PASS`, worktree limpa.
- Ref Storage `local/commander-product-current` permanece **`092f35afc52827d6c5584f0401e9f60eaeb3d985`**, divergente por histórico de workflow GitHub recusado. **`STORAGE_RECONCILIATION=HOLD`**. Não usar `git push --force`, `git update-ref` no Storage nem alegar triple sync.
- Após publicar este documento, confirmar o NOVO SHA no GitHub via `git ls-remote` e atualizá-lo como checkpoint vigente. Não subir alterações de workflow enquanto escopo não for autorizado.

## 8. Comandos de continuidade (somente leitura)

No Services:
```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
git status -sb
git rev-parse HEAD
GIT_TERMINAL_PROMPT=0 git ls-remote --heads https://github.com/tiagoharalabs/hara-site.git local/commander-product-current
GIT_TERMINAL_PROMPT=0 git ls-remote --heads origin local/commander-product-current
./node_modules/.bin/wrangler deployments list --name hara-commander --json
./node_modules/.bin/wrangler secret list --name hara-commander
python3 apps/commander/scripts/billing_prod_activation_preflight.py --live
```
No ChatGPT, **usar somente o plugin comercial** `H_A_R_A__Commander.get_device_info(computer=<host>)` e `ping(computer=<host>)` para cada uma das sete máquinas; exigir `HARA_COMMANDER`, `EVENT_V2`, `0.3.44`, recibo válido. O mesmo plugin deve validar os testes externos quando houver segundo tenant de verdade.

**Nunca imprimir:** device token, bearer OAuth/Cloudflare/Stripe, chave RSA privada v2, conteúdo de `device.env` além de dados não secretos necessários à prova. Nunca tratar Agent 0.3.44 Founder como release pública.
