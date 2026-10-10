# H.A.R.A. Commander — CURRENT (10/10/2026, após rollout 7/7)

**Antes de qualquer mutação ou decisão: ler primeiro**
`docs/handoffs/HARA_COMMANDER_FLEET_EVENT_V2_HANDOFF_20261010.md`.
**Para billing/Stripe:** `docs/operations/HARA_COMMANDER_STRIPE_TEST_ONE_COMMAND_ACTIVATION_20261010.md`.

**Única branch autoritativa de produto:** `local/commander-product-current`.
Worktree Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`.
Repo GitHub: `tiagoharalabs/hara-site`.

## Estado atual comprovado
- **Frota Linux Founder 7/7** em Agent **0.3.44 assinado per-device** e **EVENT_V2 WebSocket**, com `H_A_R_A__Commander.get_device_info` e `ping` comerciais PASS: `nucleo-a`, `sentinela-a`, `sentinela-b`, `sentinela-c`, `sentinela-d`, `ninja-blue`, `services`.
- V2 `active+enabled`, v1 0.3.41 `inactive+disabled` mas preservada para rollback; watchdog/timer ativo em todos. Nenhum reboot nem failover forçado foi realizado. Windows permanece offline/revogado/não homologado em Event V2.
- Worker PROD Cloudflare `hara-commander` versão `29e556f3-86af-476d-ba01-a764c3acb6a0` (100%) no último readback. Allowlist original Núcleo mais seis Founder configurados em **secret** `DEVICE_EVENT_V2_ADDITIONAL_DEVICE_IDS`; sem wildcard, sem liberar outros tenants.
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` ainda PENDING em PROD. **Checkout pago NÃO ATIVO.** Catálogo Free = 10.000 chamadas governadas/mês; Standard Pro = R$80/mês (ilimitado no catálogo), não comprovadamente faturado.
- **Stripe TEST automation preparada:** `stripe_test_activation_wizard.py --check/--apply` (a segunda exige chave `sk_test_` introduzida privadamente no Services). Cria/reutiliza produto/Price BRL80, webhook assinado, Portal e configura quatro DEV Worker secrets; o assistente não recebeu/instalou nenhuma chave Stripe. Teste integrado SQLite e teste offline do wizard PASS. **Worker DEV publicado** na versão `490c38bf-5ef0-4b55-a33a-2dc6d0c6ad6c` 100%, DEV health 200, sem segredos Stripe; PROD mantido na versão anterior. Restam test Checkout real e live rollout governado.
- **Correção SSH Stripe 10/10:** erro `CLOUDFLARE_DEV_SECRET_LIST_UNAVAILABLE` foi causado por Wrangler sem Node no PATH em SSH non-login (`/usr/bin/env: node: No such file or directory`). O wizard agora resolve Node instalado via NVM sem carregar perfis nem tocar no PATH global. `--check` validado com SSH normal e `ssh -tt` Núcleo→Services e com PATH limitado, sem chaves, pagamentos ou alterações de Cloudflare. O operador, já em Services, deve executar o `--apply` manualmente e digitar `sk_test_` apenas no terminal.
- Métrica anterior Cloudflare de canário Núcleo −20,7% polling, −19,7% requisições Worker entre duas janelas equivalentes; **não transferir esse percentual à frota 7/7 nem à economia de fatura sem nova medição**.
- **Storage diverge de GitHub/local**: `092f35afc52827d6c5584f0401e9f60eaeb3d985`; `STORAGE_RECONCILIATION=HOLD`. Não forçar refs ou burlar hooks.
- O handoff anterior `HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md` e o arquivo de preparação `HARA_COMMANDER_EVENT_V2_FOUNDER_FLEET_STAGE_20261010.md` são **históricos**, não a verdade atual de deploy.

**Nova auditoria de produto e stress em 10/10:** ler também `docs/operations/HARA_COMMANDER_PRELAUNCH_SECURITY_STRESS_AUDIT_20261010.md`. As **31 funções do Agent são suficientes como primitivas do MVP**, mas o perfil simples ChatGPT tinha 24 métodos; **27 métodos estão preparados somente em código-fonte candidato** (inclui preimages, rollback e recibos), sem deploy público. A suíte offline de pré-lançamento **47/47 PASS** executou até **1.000 tentativas concorrentes / 24 threads** por cenário contra SQL exato do Worker em SQLite isolado: fila 16, idempotência 1, cross-tenant 0 e claim 16 únicos. Correções candidatas: limite RAM/sessões, quota de backups 256 MiB/4.096 entradas, `ASK_EVERY_ACTION` como padrão para novos instaladores, risco destrutivo honesto em MCP, `list_directory.offset` corrigido, regressões OIDC e integridade de v1. **Nenhuma dessas correções de agente foi implantada em release assinada**, e os 3 métodos MCP também não estão ativos no PROD. Não tratar 47/47 como teste real de 1.000 clientes Cloudflare.

**Próximos gates P0:** assinar/testar release externa com hardening e default seguro; Stripe real checkout+webhook/idempotência; segundo tenant real e isolamento; homologação da franquia Free (fim do limite, concorrência, replay); stress DEV 24h com teardown e failover; instalar e dar suporte sem mutações sem aprovação. **P1:** Windows Event V2 ou beta Linux-only, cold boot/failover, métricas 24h por host e Cloudflare faturado, observabilidade `last_seen`/`agent_version`, Storage/CI. Ver handoff completo para provas e rollback.

**Não confundir ferramentas:** `H_A_R_A__Commander` é o MCP comercial; `H_A_R_A__Commander_Baseline` é superfície Services/admin. Verificar novamente com plugin comercial ao iniciar novo chat.

## 10/10/2026 — Política comercial manual-on-demand, publicação e contingência

**Contrato decidido:** ao instalar Linux/Windows, o Agent inicia uma única vez para teste/atestado, mas o instalador **não habilita autostart no próximo reboot/login**. O cliente usa `hara-commander start` no Linux ou `hara-commander-agent.ps1 start` no Windows para abrir uma sessão ativa; `stop` encerra. `ASK_EVERY_ACTION` é padrão seguro; não há seletor de autorização persistente ou autostart na página comercial. Técnico pode optar em Linux por serviço persistente explicitamente via sistema operacional. O MCP STDIO local `hara-commander mcp` é distinto do Agent Cloud.

**Comprovação de publicação de assets:** Cloudflare PROD serve `https://commander.haralabs.com.br/install/linux.sh` e `install/windows.ps1` com HTTP 200, arquivos de release **v0.3.41 assinado antigo** e autostart ainda presente (Linux `enable --now`, Windows `AtLogOn`). Publicação é via Wrangler Worker `hara-commander`, `assets.directory=public`; `git push` isolado não a altera. Novo fluxo está SOMENTE nos arquivos candidatos em Git até nova assinatura e deploy versionado.

**Contingência GitHub real:** tag **`hara-commander-signed-agent-v0.3.41`** criada e publicada, apontando para SHA exata `08500d5c4256d25abc77a26ad377e55eadf1742a` com tag readback PASS. `verify_commander_public_artifacts.py --check/--live` verificou assinatura RSA v1 e seis arquivos byte-idênticos Git↔Cloudflare, incluindo manifesto. Nunca montar distribuição comercial nova combinando candidate HEAD com manifesto v0.3.41.

**Storage:** `origin` commit `092f35af...` está divergente; fontes de instaladores/agents NÃO correspondem ao manifesto assinado legado no Storage. `HOLD`, não usar Storage como fallback assinado nem fazer force-push.

**Alterações exclusivamente candidatas:** Linux systemd disabled+start uma vez, `Restart=on-failure`, CLI start/stop controla unit, status mostra `AUTOSTART`, update e reenroll preservam estado parado; Windows Task Scheduler sem trigger, CLI manual start/stop, update preserva off; portal `ASK_EVERY_ACTION` e `TUNNEL_AUTOSTART=OFF` fixos, sem escolha de autostart no site. Harness Linux com assinatura efêmera e mock localhost passou todos os passos de ciclo de vida. Windows precisa homologação real; não atualizar Founder V2 0.3.44 inadvertidamente.

**Documento autoritativo:** `docs/operations/HARA_COMMANDER_MANUAL_START_DISTRIBUTION_AUDIT_20261010.md`. **GATE PARA PROD:** nova release assinada completa + testes de reboot Linux/Windows, canário Cloudflare DEV e readback de hashes antes de substituir a v0.3.41 no domínio público.
