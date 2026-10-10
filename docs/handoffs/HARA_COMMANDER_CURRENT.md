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
- Métrica anterior Cloudflare de canário Núcleo −20,7% polling, −19,7% requisições Worker entre duas janelas equivalentes; **não transferir esse percentual à frota 7/7 nem à economia de fatura sem nova medição**.
- **Storage diverge de GitHub/local**: `092f35afc52827d6c5584f0401e9f60eaeb3d985`; `STORAGE_RECONCILIATION=HOLD`. Não forçar refs ou burlar hooks.
- O handoff anterior `HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md` e o arquivo de preparação `HARA_COMMANDER_EVENT_V2_FOUNDER_FLEET_STAGE_20261010.md` são **históricos**, não a verdade atual de deploy.

**Próximos gates P0:** Stripe real checkout+webhook/idempotência; segundo tenant real e isolamento, homologação da franquia Free (fim do limite, concorrência, replay), roteiros de suporte/instalação externa. **P1:** Windows Event V2, cold boot/failover, métricas 24h por host e Cloudflare faturado, observabilidade `last_seen`, Storage/CI. Ver handoff completo para provas e rollback.

**Não confundir ferramentas:** `H_A_R_A__Commander` é o MCP comercial; `H_A_R_A__Commander_Baseline` é superfície Services/admin. Verificar novamente com plugin comercial ao iniciar novo chat.
