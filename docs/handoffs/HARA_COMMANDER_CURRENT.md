# H.A.R.A. Commander — CURRENT (10/10/2026, após rollout 7/7)

**DECISÃO MAIS RECENTE DE PREÇO/QUOTA — FREE=10.000 chamadas governadas/mês.** O dono revogou a autorização temporária de 15.000. D1 DEV e PROD estão em 10.000 via migração `0032_free_10000_revert_20261010.sql`. Pro permanece ilimitado. Cloudflare PROD `hara-commander` **43421f6f-5bee-4fe6-9bc4-982a3e10d019 a 100%**, readback de 10/10 assets assinados e portal JS/HTML 10.000 PASS; rollback `8c3eec1b-8783-4aff-868f-7f558e1d9db5`. O conteúdo histórico abaixo sobre 15.000 está SUPERADO. Ver `docs/operations/HARA_COMMANDER_FREE_10K_REVERSION_20261010.md`.

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
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` ainda PENDING em PROD. **Checkout pago NÃO ATIVO.** Catálogo Free = 15.000 chamadas governadas/mês (migração PROD 0031 confirmada em 10/10); Standard Pro = R$80/mês (ilimitado no catálogo), não comprovadamente faturado.
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

## 10/10/2026 — Nova release comercial assinada, Free 15.000, portal start/stop

A migração `0031_free_15000_20261010.sql` foi aplicada no **D1 DEV e PROD**, com readback exato: `TRIAL` = 15.000 chamadas governadas/mês; `STANDARD` = ilimitado. Stripe PROD ainda sem checkout. O site candidato agora mostra Free 15.000 e comandos copiados de `start`/`stop` fixos abaixo do instalador Linux/Windows.

A chave privada v1 não corresponde ao público pinado e não deve ser usada. A autoridade de assinatura **v2 existente** assinou a distribuição comercial `0.3.43` usando RSA-3072. Arquivos públicos íntegros: `apps/commander/release-bundles/commercial-0.3.43-v2/` (4 assets + manifesto, assinatura, JWK público, SHA256SUMS). Nenhuma chave privada no Git. Teste E2E do **pacote assinado exato** em simulador Linux PASS, incluindo instalação sem autostart, upgrade parado, reenrolamento e desinstalação. Windows: política estática PASS; homologação PowerShell real pendente.

Canário Cloudflare DEV `hara-commander-dev-v2` versão `5e17d990-bf6f-43f4-b65f-3a9aa140eb88` com 9/9 assets byte-idênticos ao pacote, health 200. PROD versão candidata *carregada sem deploy* `8c3eec1b-8783-4aff-868f-7f558e1d9db5`, com nomes de secrets de autenticação e MCP presentes; rollback PROD v1 `29e556f3-86af-476d-ba01-a764c3acb6a0`. **Não afirmar PROD v2 ativa antes do readback 100% e 10/10 hashes.**

Documento detalhado: `docs/operations/HARA_COMMANDER_SIGNED_COMMERCIAL_V2_PUBLICATION_20261010.md`. A release assinada anterior continua disponível via tag `hara-commander-signed-agent-v0.3.41`; não misturar chaves/manifestos. Storage segue em HOLD; frota Founder V2 0.3.44 intacta. Gate offline 53/53 PASS, incluindo SQL concorrente e novo catalogo.

## PRODUÇÃO ATUALIZADA — checkpoint final 10/10/2026

**Última verdade prevalece sobre históricos anteriores:** Cloudflare Worker **PROD** `hara-commander` versão `8c3eec1b-8783-4aff-868f-7f558e1d9db5` está em **100%**, com assets comerciais assinados 0.3.43 v2 (chave `commander-release-v2`). `validate_signed_commercial_v2_bundle.py --live` 10/10 assets PASS, SHA após normalização exata do beacon HTML Cloudflare. `validate_prod_runtime_drift.py --expect-assets current` CURRENT PASS. Website e downloads públicos agora entregam nova política **start manual, sem autostart**. Comandos copiar/iniciar/parar ficam sob cada instalador. Free/TRIAL 15.000/mês aplicado no D1 PROD/DEV e readback PASS, Pro ilimitado; Stripe checkout ainda OFF.

Comercial MCP pós-deploy `ping` Núcleo A e Sentinela D PASS em Agent Founder 0.3.44 Event V2; não mudar Founder. Rollback Worker PROD `29e556f3-86af-476d-ba01-a764c3acb6a0`, tag legado assinada `hara-commander-signed-agent-v0.3.41`; novo backup assinado tag GitHub `hara-commander-commercial-v0.3.43-signed-v2` (commit `d7e5f128...`). Manifesto público v2 tem kid v2; não combinar assets v1. Windows ainda BETA sem prova nativa PS 5.1; permitir download não equivale a homologar mutação. Multi-tenant stress/Stripe e OpenAI plugin listing são gates separados.

Relatório e procedimento: `docs/operations/HARA_COMMANDER_SIGNED_COMMERCIAL_V2_PUBLICATION_20261010.md`. Verificador antigo `verify_commander_public_artifacts.py --check` preserva assinatura v1 no Git; `--live` deve usar validador comercial v2, nunca tratar a v1 histórica como atual. Storage protegido segue HOLD `092f35af...`.

## 10/10/2026 — Minimalismo da tela Computadores

Novo refinamento autorizado da UI no portal público (sem alterar cores/identidade): cada linha mostra só nome, sistema, último contato e estado real; Agent/arquitetura/transporte/autorização ficam no menu de detalhes com ações secundárias. O grande guia de onboarding está recolhido por padrão; os botões de diagnóstico e procedimentos de autorização/revogação são preservados. Uma lease local válida não implica máquina online. O total de chamadas Free continua 10.000/mês.

Fonte e contrato: docs/operations/HARA_COMMANDER_DEVICES_MINIMALIST_UI_20261010.md. Gate offline 54/54 PASS, DEV Worker versão 636d9e2f-883c-4a0d-96e1-8280ee2ee4ad com SHA exato 11/11 e health 200. Bundle assinado comercial v0.3.43 e agentes Founder v0.3.44 não foram tocados. Registrar versão PROD depois da promoção e readback.
