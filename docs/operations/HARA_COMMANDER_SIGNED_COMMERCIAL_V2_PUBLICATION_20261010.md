# H.A.R.A. Commander — publicação comercial assinada v2 (10/10/2026)

## Mudança autorizada pelo proprietário

- Cliente comercial instala o Agent com início único para atestação; **sem autostart** em boot/login. Para sessões futuras, usa `hara-commander start` (Linux) ou o `start` do Agent PowerShell; botão Copiar iniciar/parar fica imediatamente abaixo do comando de instalação do portal.
- `ASK_EVERY_ACTION` é o padrão de autorização do novo cliente. A opção de persistência não aparece no instalador/site; somente técnicos podem fazê-la manualmente no sistema operacional.
- Lease Direct de autorização permanece em **6 horas**, com código de autorização one-time de 10 minutos; isso **não** corresponde ao tempo que o Agent fica conectado. O modo Cloud não exige lease Direct.
- O usuário escolheu **15.000 chamadas governadas por mês** no Free/Trial; Pro continua ilimitado no catálogo e Stripe permanece sem checkout real.

## Quota aplicada e verificada

A migração `apps/commander/migrations/0031_free_15000_20261010.sql` preserva historicamente a 0021 e altera SOMENTE a linha `TRIAL`/`Free`. Foi executada no Cloudflare D1 **DEV e PROD** em 10/10/2026. Exact readback de ambas:
- `TRIAL`: `CALENDAR_MONTH`, `unit_limit=15000`, `ACTIVE`;
- `STANDARD`: `NONE`, `unit_limit=NULL`, `ACTIVE`.

Nenhuma configuração Stripe foi criada. O gate `billing_prod_activation_preflight.py --live` confirmou `TRIAL_LIVE_ALIGNED=TRUE`, `STANDARD_LIVE_UNLIMITED=TRUE` e `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`. Diferenciar chamadas governadas (quota do plano) de requests HTTP Cloudflare.

## Cadeia de confiança

A chave privada v1 em Services **não** corresponde ao módulo público legado; não é possível reassinar a v0.3.41 com essa chave. Portanto a nova versão comercial v0.3.43 foi assinada com a autoridade existente `commander-release-v2`, RSA-3072, cuja chave privada permanece exclusivamente no diretório 0600 do Services. O manifesto mantém o schema do instalador v1 mas recebe `kid=commander-release-v2`; os **dois instaladores pinam a chave pública v2**, verificam assinatura/arquivos e recusam alteração.

Pacote somente público guardado em `apps/commander/release-bundles/commercial-0.3.43-v2/`: 2 installers, 2 Agents, manifesto, assinatura, JWK público e SHA256SUMS; nenhuma chave secreta. Validador `validate_signed_commercial_v2_bundle.py` deve validar RSA, SHA de todos os arquivos, pinagem nos instaladores e política sem autostart.

**Rollback independente:** assinatura e arquivos da v0.3.41 permanecem imutáveis na tag GitHub `hara-commander-signed-agent-v0.3.41`; Worker PROD anteriormente ativo `29e556f3-86af-476d-ba01-a764c3acb6a0`. Atenção: restaurar a release antiga restaura também o *comportamento antigo de autostart*. Nunca mesclar manifesto v1 com binaries v2.

## Provas DEV e release staging

- Staging de distribuição: `/tmp_hara/commander-public-commercial-v2-20261010`, verificado por `build_commander_commercial_signed_v2.py verify --stage ...` e testes criptográficos.
- Teste real do **pacote já assinado** via servidor local mock, systemctl falso e diretórios temporários: `commander_linux_clean_lifecycle.py --execute --signed-stage /tmp_hara/commander-public-commercial-v2-20261010` — PASS para instalação, boot policy, atualização parada/ativa, reenrollment, rollback, desinstalação.
- Cloudflare **DEV** Worker `hara-commander-dev-v2` versão `5e17d990-bf6f-43f4-b65f-3a9aa140eb88`, página e assets lidos de URL externa: **9 de 9 arquivos byte-idênticos** ao staging, HTTP health 200.
- Cloudflare PROD: nova versão **carregada mas não promovida no começo deste documento**, ID `8c3eec1b-8783-4aff-868f-7f558e1d9db5`. Os 7 nomes de secrets existentes foram confirmados na nova versão, inclusive AUTH_CLIENT_SECRET, MCP_PRODUCT_TOKEN, PRODUCT_LEASE_PRIVATE_JWK e as variáveis do Identity. Worker PROD antigo continuava 100% na versão `29e556f3...` durante o pré-flight.

## Limitações e cautelas comerciais

1. O GitHub **não instala automaticamente** um Worker; somente a promoção versionada dos assets muda o site público. Após promoção verificar SHA exato dos 10 endpoints `install/*`, `agent/*`, `release/*` e `index.html/app.js`, Worker health e D1 Free=15.000. Rotas existentes precisam permanecer iguais.
2. **Cliente Windows ainda não homologado em Windows PowerShell 5.1 real**. O Agent PowerShell em modo `ASK_EVERY_ACTION` nega algumas mutações por segurança; documentar como beta limitado, não prometer paridade de escrita. O teste Windows foi estático e o Linux foi testado em harness isolado, sem reboot de máquina real.
3. A frota Founder usa `EVENT_V2` assinado 0.3.44, serviços particulares e configurações persistentes; **não alterar** serviços/frota Founder durante a promoção dos assets públicos.
4. Uma v1 instalada pode tentar atualizar utilizando um instalador com nova chave v2; a rotação de confiança deve ser explicitamente aceita por quem baixou pelo canal HTTPS. Preservar a versão Worker anterior para rollback e tag Git antiga para resgate.
5. Atualizações manuais de máquinas previamente configuradas com autostart **não mudam automaticamente** a preferência existente: o novo padrão se aplica sobretudo a instalações comerciais novas. Administradores antigos precisam desligar sua persistência local conforme política.

## Runbook de promoção

Validação source (Services):
```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py --stress 1000 --threads 24
python3 -B apps/commander/scripts/validate_signed_commercial_v2_bundle.py
```

Promoção controlada somente com verificação prévia das configurações, secrets e capacidade de rollback:
```bash
./node_modules/.bin/wrangler versions view 8c3eec1b-8783-4aff-868f-7f558e1d9db5 -c apps/commander/wrangler.jsonc
./node_modules/.bin/wrangler deployments list -c apps/commander/wrangler.jsonc
./node_modules/.bin/wrangler versions deploy 8c3eec1b-8783-4aff-868f-7f558e1d9db5@100% -c apps/commander/wrangler.jsonc --message "Commercial signed v2 manual-on-demand" --yes
./node_modules/.bin/wrangler triggers deploy -c apps/commander/wrangler.jsonc
python3 -B apps/commander/scripts/validate_signed_commercial_v2_bundle.py --live
```

Se a promoção ou readback falhar, usar o rollback aprovado `29e556f3-86af-476d-ba01-a764c3acb6a0@100%` e confirmar health e identidade do Worker. Não fazer alterações D1 desnecessárias no rollback da página.

**O registro final de deploy e status público deve ser acrescentado após readback real.**
