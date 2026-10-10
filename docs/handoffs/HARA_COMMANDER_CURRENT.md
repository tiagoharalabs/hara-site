# H.A.R.A. Commander — CURRENT (10/10/2026)

**Início obrigatório de qualquer próxima conversa ou agente:** ler primeiro
`docs/handoffs/HARA_COMMANDER_NEXT_CHAT_HANDOFF_20261010.md`.

**Única branch autoritativa de produto:** `local/commander-product-current`.
Worktree Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`.
Repo GitHub: `tiagoharalabs/hara-site`.

**Current truth resumida:** MCP comercial H.A.R.A. Commander funciona pelo ChatGPT no `nucleo-a` com Agent Linux **0.3.44 assinado**, transporte **EVENT_V2** WebSocket hibernável, user systemd persistente e watchdog local `HEALTHY`, com v1 assinada 0.3.41 guardada para rollback. Os outros dispositivos continuam em OUTBOUND_RELAY 0.3.41. **Stripe PROD e checkout pago não estão ativos.** Free = 10 mil chamadas governadas/mês; Pro = ilimitado no catálogo.

**Cloudflare medida:** `/api/device/calls/next` 1.756→1.392 (−20,73%) e requisições Worker 2.066→1.658 (−19,75%) em duas janelas 40min com quatro operações comerciais em cada, **agregadas por Worker, não economia isolada nem fatura comprovada**.

**Governança Git crítica:** GitHub/local avançaram na linha limpa; **Storage está em ref divergente `092f35a...`** decorrente de commit com alteração `.github/workflows` recusada pelo token GH. Não forçar refs nem alegar sincronização tripla. Ver handoff completo e `docs/operations/HARA_COMMANDER_PUBLISH_SCOPE_AND_STORAGE_RECONCILIATION_20261009.md`.

Handoff histórico extenso (pode conter checkpoints superados):
`docs/handoffs/HARA_COMMANDER_PRODUCT_CURRENT_HANDOFF_20261008.md`.

**Antes de executar mutações:** verificar estado vivo do plugin **`H_A_R_A__Commander` comercial**, do Agent, PROD D1, GitHub e Storage; não confundir com `H_A_R_A__Commander_Baseline`/Services nem distribuir chave privada RSA v2.
