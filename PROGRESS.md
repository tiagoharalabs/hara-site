# HARA Commander — correções pré-lançamento

Branch exclusiva: `codex/commander-prelaunch-fixes-20261020`
Base QA: `482169251b347b77380d8becf878e5c515c75c8a`
Escopo de execução: clone local, testes isolados, sem deploy ou migração remota.

## Distribuição pública — 20/10/2026

GETs HTTPS somente leitura em `https://commander.haralabs.com.br` reproduziram o incidente. O manifesto público declara `0.3.41`; ambos os Agents servidos declaram `0.3.43`. Seu manifesto possui assinatura RS256 **criptograficamente válida para a chave pública v1**, mas nenhum dos quatro arquivos servidos corresponde aos bytes e SHA-256 declarados. O instalador Linux servido fixa a chave v2 e rejeitaria a assinatura v1 antes mesmo de verificar os hashes; o instalador Windows servido fixa v1, mas falharia na verificação do Agent. Nenhum instalador foi executado.

| Arquivo | Bytes declarados | Bytes GET | SHA-256 GET |
| --- | ---: | ---: | --- |
| `agent/linux.py` | 163048 | 220422 | `1572d70e60fb299edb262a8a817bd7aa1740a4c2dda3635d50beb2f3476ffe3b` |
| `agent/windows.ps1` | 56752 | 60233 | `d507a6f91a635b025ef4f06cbd758a03c7da6f3410aadec9a3d76c28f904c6fb` |
| `install/linux.sh` | 28595 | 37180 | `699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463` |
| `install/windows.ps1` | 22321 | 23604 | `6ba5c29e6d3a604750331d7699455ad609b4b0a8e191c03ad10503f7a5161c3` |

**Causa localizada no código:** `wrangler.jsonc` apontava `assets.directory` para `public/`, que contém fontes de desenvolvimento e manifesto v1 antigo. O staging comercial estava fixo em v3, embora o instalador Linux comercial assinado mais recente estivesse em v4. A combinação exata de comandos que gerou o deploy público misto ainda precisa de readback da publicação; a configuração antiga permitia essa classe de erro.

**Correção no código:** configs PROD e DEV exigem `--assets` com staging explícito; o `--dry-run` sem override falha no diretório sentinela. Verificador novo exige chave v2 ancorada, assinatura RS256 válida, quatro arquivos exatos, hashes/tamanhos, `SHA256SUMS`, pins e versões dos Agents. `build_release_manifest.py` recusa sobrescrever manifesto assinado sem nova assinatura. O staging exige bundle corrente qualificado e bloqueia os bundles históricos salvo como rollback identificado.

**Regressão funcional descoberta:** Linux assinado v4 perde saída de processo após `waitpid`; o Agent Linux fonte atual preserva a drenagem. O teste PTY real passa 19/19 na fonte atual e falha em `120_lines_available` no v4. Portanto o v4 **não é candidato equivalente**. O novo bundle corrente `commercial-0.3.43-v5-terminal-drain` só poderá ser aceito após assinatura oficial e validação completa. O Windows `0.3.52-v12-rc` permanece separado: assinatura e hashes válidos, mas o manifesto global `0.3.52` não corresponde ao Linux `0.3.43`; ele não foi promovido como comercial.

**Artefatos locais preparados, sem publicação:**

- Fonte candidata atualizada: `/tmp/commander-drain-source-candidate-20261020-1858z`, manifesto SHA-256 `6742a7ac8256e5e35e3c2d16e51d3c3647def7a61dddf39350def15078914b39`, estado `AWAITING_OFFICIAL_SIGNATURE`. Linux atual `0.3.43` + Windows/instaladores comerciais v4 + UI comercial da branch. Sem assinatura; o verificador de publicação a rejeita. A montagem anterior de 18:46 não inclui a UI nova.
- Referência de rollback: `/tmp/commander-signed-v4-rollback-20261020-1846z`, assinatura v2 válida e estado explícito `ROLLBACK_ONLY_KNOWN_PROCESS_DRAIN_REGRESSION`. Não representa promoção segura do fix de drenagem.
- Antes de qualquer promoção, obter version ID PROD atual e rollback real por readback, assinar oficialmente o v5 no fluxo autorizado, verificar assinatura/bytes/PTY e pedir aprovação específica. Nenhum upload foi feito.

### Testes e códigos de saída

| Comando / prova | Exit | Resultado |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/test_signed_distribution_stage.py` | 0 | 12 testes: manifesto antigo + Agent novo, adulteração, hashes coerentes com assinatura inválida, v12 inconsistente, staging, rollback e PTY |
| `python3 -B apps/commander/scripts/build_commander_commercial_terminal_drain_candidate.py --check` | 0 | fonte candidata íntegra, sem assinatura |
| `python3 -B apps/commander/scripts/validate_process_terminal_drain.py` | 0 | 19/19 PTY da fonte Linux atual |
| Mesmo teste com `--source .../commercial-0.3.43-v4-autoreconnect/agent/linux.py` | 1 | regressão `120_lines_available` reproduzida |
| `python3 -B apps/commander/scripts/stage_signed_commercial_assets.py --check` | 1 | HOLD intencional: `SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE` |
| Staging com `--bundle commercial-0.3.43-v4-autoreconnect --rollback-only --check` | 0 | rollback identificado com regressão conhecida |
| Wrangler `versions upload --dry-run` sem `--assets` | 1 | diretório sentinela inexistente impede upload acidental de `public/` |
| Wrangler `versions upload --dry-run --assets /tmp/commander-signed-v4-rollback-20261020-1846z` | 0 | override explícito compila e preserva bindings; somente dry-run |

**Estados:** corrigido no código: seleção/configuração/verificação; testado local: sim, com HOLD de assinatura; testado DEV: não; publicado PROD: não. O endpoint público continua inconsistente nesta sessão.

**Próximas frentes:** modelo comercial, migração nova, teto atômico de cinco computadores, Event V2 comercial, retenção e quotas, jornada limpa com mocks Stripe TEST, pacote MCP de publicação. A decisão mês-calendário versus ciclo Stripe continua pendente e não autoriza dois resets.

**Commits:** `d7b3ad5` — distribuição assinada, staging explícito, regressões e candidato de fonte. Revisão independente recebida em `docs/operations/HARA_COMMANDER_PEER_REVIEW_20261020T1840Z.md`; reproduzi localmente o defeito de drenagem antes de incorporá-lo ao gate.

## Modelo comercial — candidato local de 20/10/2026

**Corrigido no código:** migração aditiva `0036` estabelece Avaliação `LIFETIME`/5.000, HARA Commander `CALENDAR_MONTH`/1.000.000 e teto de cinco computadores em ambos; Founder/Internal permanece `NONE` ilimitado. Billing só oferece `STANDARD` por R$ 80/mês e rejeita checkout se o catálogo ainda estiver no modelo antigo. A UI reflete os termos sem limite de usuários. O webhook conserva acesso até o fim do período pago em cancelamento agendado e lê `current_period_end` no item Stripe quando presente. O cancelamento efetivo revoga o entitlement. Nenhuma chave ou conta Stripe TEST foi usada.

**Decisão registrada, pendente para promoção:** o código usa mês-calendário como único reset da franquia paga; o ciclo Stripe rege cobrança/acesso. O proprietário precisa confirmar mês-calendário versus ciclo pago antes da promoção. Não foram implementados dois resets. A migração remota exige conciliação do uso histórico de tenants Trial antes da troca para `LIFETIME`; sem baseline, um cliente existente poderia receber chamadas extras.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/test_commercial_model_20261020.py` | 0 | catálogo final e Founder em SQLite |
| `node apps/commander/scripts/test_commercial_policy_20261020.mjs` | 0 | preço, quota, plano Scale não vendável e checkout antigo negado |
| `node apps/commander/scripts/billing_sqlite_webhook_e2e.mjs` | 0 | assinatura, idempotência, suspensão, recuperação, cancelamento agendado/revertido/efetivo |
| `node apps/commander/scripts/test_no_stripe_technical_mode.mjs` | 0 | 13 cenários, zero requests Stripe reais |
| `python3 -B apps/commander/scripts/validate_billing_v1.py` | 0 | migrações e contrato de ativação |
| `python3 -B apps/commander/scripts/validate_prod_static.py` | 0 | superfície estática alinhada |

**Estados:** corrigido no código: sim; testado local: sim; testado DEV: não; publicado PROD: não. D1 remota, Stripe TEST real e Stripe LIVE não foram tocados.
