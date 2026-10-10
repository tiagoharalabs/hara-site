# H.A.R.A. Commander — limite Free definitivo de 10.000 chamadas/mês

**Checkpoint de 10/10/2026 — última decisão do proprietário, posterior à aprovação temporária de 15.000.**

O plano comercial **Free**, código interno `TRIAL`, deve permitir **10.000 chamadas governadas por mês-calendário**. O Pro/Standard mantém `period_kind=NONE` sem limite mensal. Não confundir essas chamadas do produto com HTTP requests/polling do Worker Cloudflare.

## Migrações, dados e consistência

- Migrações `0021_commercial_terms_20261005.sql` (10.000) e `0031_free_15000_20261010.sql` (15.000) são **históricas e imutáveis**; nunca editar migração já executada.
- A nova `0032_free_10000_revert_20261010.sql` revoga somente o excesso temporário: `TRIAL`/`Free` volta a `unit_limit=10000`, `CALENDAR_MONTH`.
- A migração `0032` foi aplicada em **D1 DEV e PROD**. Após aplicação, ambas retornaram em consultas reais `TRIAL=10000` e `STANDARD=NULL`; o Pro não mudou.
- Se um tenant Free já consumiu mais de 10.000 chamadas no ciclo atual durante a janela de 15.000, a execução passa a seguir o limite de 10.000. Não apagar contadores ou recibos para mascarar excedentes. Revisar eventuais casos individuais por governança comercial.

## Distribuição e portal

- O portal comercial apresenta Free 10.000 em `public/index.html` e `public/app.js`, incluindo rótulos, contador e fallback visual.
- O Worker PROD deve publicar o mesmo site com cache key `20261010-free10k1`. Os quatro arquivos comerciais assinados `agent/linux.py`, `agent/windows.ps1`, `install/linux.sh`, `install/windows.ps1` **NÃO precisam mudar**: manter a release 0.3.43 RSA-v2 e sua assinatura correspondente. Não gerar binários novos só para alterar a quota de banco e textos do portal.
- Testes `validate_billing_v1.py`, `validate_prod_static.py` e `commander_prelaunch_offline_gate.py` incluem a migração 0032 e a consistência da quota final.
- Preservar rollback do Worker anterior e comprovar os hashes de todos os assets (HTML pode ter beacon Cloudflare injetado; comparar normalizando somente o beacon conhecido).

A decisão **10.000** prevalece sobre todos os históricos mencionando **15.000**; Stripe/Pro continuam separados, assim como a política de conexão manual do Agent.
