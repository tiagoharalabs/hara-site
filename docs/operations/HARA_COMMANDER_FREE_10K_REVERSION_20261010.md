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

## Resultado comprovado em produção — 10/10/2026

- **D1 PROD e DEV**: `TRIAL=10000` com período `CALENDAR_MONTH`, `STANDARD=NULL` (ilimitado), exact readback PASS.
- **Cloudflare DEV**: `hara-commander-dev-v2`, versão `46ae1490-6a31-439c-8b8c-937531bd550e`, interface Free 10.000. Conferidos 6/6 arquivos de prova incluindo quatro assets de instalação/assinatura.
- **Cloudflare PROD**: `hara-commander`, versão `43421f6f-5bee-4fe6-9bc4-982a3e10d019` em **100%**, com cron e domínio sincronizados. Rollback imediato preservado na versão `8c3eec1b-8783-4aff-868f-7f558e1d9db5`.
- **Readback público independente**: `validate_signed_commercial_v2_bundle.py --live` PASS **10/10 hashes** (HTML normalizado apenas quanto ao beacon Cloudflare), `commander_prod_deployment_readback.py --expect-version ...` PASS, site `/index.html` e `/app.js` mostram 10.000 e não 15.000, endpoint e runtime saudáveis.
- **Gate offline**: 53/53 verificações PASS, incluindo billing e concorrência SQLite com 32 migrações reconhecidas.
- **Instaladores assinados**: v0.3.43 RSA v2 byte-idênticos aos anteriores, `manual start` preservado. Nenhuma atualização ou reinício de Agent Founder causada pela mudança de quota.
- O Stripe permanece sem checkout pago ativo; código Free no catálogo continua `TRIAL` somente por compatibilidade, e o Pro não foi alterado.
