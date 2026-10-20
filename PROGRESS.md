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

- Fonte candidata atualizada após correções R4 de entrega e tamanho: `/tmp/commander-drain-source-candidate-20261020-1943z`, manifesto SHA-256 `261734daef7125ce6afd08c429afa52c0603b2256af103aff1b061538b527d57`, estado `AWAITING_OFFICIAL_SIGNATURE`. Linux atual `0.3.43` (SHA-256 `9115666c3f7ab350bff4fd4ba63f4feb5bf63c6947fd7e1dff45ad3c3e7539d9`) + Windows/instaladores comerciais v4 + UI comercial da branch. Sem assinatura; o verificador de publicação a rejeita. As montagens anteriores foram superadas como candidatas e preservadas apenas como rastros locais.
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

## Cinco computadores por organização — candidato local

**Corrigido no código:** o `INSERT ... SELECT` de inscrição consulta o limite do plano e conta computadores `ACTIVE` da mesma organização dentro da instrução de escrita. O batch D1 consome o token somente se o dispositivo foi inserido; no sexto computador, retorna `DEVICE_LIMIT_REACHED` (HTTP 409) e mantém o pareamento sem consumo. A revogação libera a vaga, o registro revogado permanece, e Founder/Internal conserva limite nulo. O índice aditivo de `0036` cobre a contagem por tenant/estado.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `node apps/commander/scripts/test_device_enrollment_limit.mjs` | 0 | quinto/sexto, token não consumido, revogação/substituição, isolamento entre tenants, Founder e dois escritores concorrentes em SQLite |
| `python3 -B apps/commander/scripts/validate_pairing_supersession.py` | 0 | token mais recente e supersessão preservados |
| `python3 -B apps/commander/scripts/validate_device_lifecycle_races.py` | 0 | corridas de revogação/chamada preexistentes preservadas |
| `node --check apps/commander/src/worker.js` | 0 | sintaxe |
| `python3 -B apps/commander/scripts/validate_device_installers.py` | 0 | instaladores, manifesto, ponte MCP local e revogação; teste de loopback executado após bloqueio do socket pelo sandbox |

**Estados:** corrigido no código: sim; testado local: sim (SQLite, sem Cloudflare); testado DEV: não; publicado PROD: não. A aplicação remota de `0036` e a corrida em D1 real continuam pendentes de autorização/ambiente.

## Event V2 — wake e qualificação comercial local

Na comparação com `origin/local/commander-event-v2-pong-deadline-20261013`, a base QA contava sockets substituídos como wake entregue. O filtro agora exige attachment atual e ignora uma falha de envio para continuar até outro socket vivo. `test_event_v2_notify_delivery.mjs` saiu 0; `validate_event_v2_wiring.py`, `validate_event_v2_presence_reconnect.py` (34/34), `validate_event_v2_websocket_client.py`, `validate_event_v2_clean_shutdown.py`, `validate_event_v2_fleet_allowlist.mjs` e `validate_event_v2_productization.py` saíram 0. Detalhes em `docs/operations/HARA_COMMANDER_COMMERCIAL_EVENT_V2_ACCEPTANCE_20261020.md`.

**Estados:** corrigido no código: filtro de wake; testado local: sim; testado DEV: não; publicado PROD: não. O Agent comercial limpo ainda não é Event V2 assinado. Founder não foi contado como canário comercial.

## Revisão independente R2 — billing, checkout e licença local

Recebida `docs/operations/HARA_COMMANDER_PEER_REVIEW_R2_20261020.md`, com snapshot e seis reproduções em `docs/evidence/commander-peer-review-r2-20261020/`. Várias funções afetadas já existiam na base QA; a revisão foi tratada como lacuna pré-lançamento, sem atribuir indevidamente uma regressão nova.

**Corrigido no código:** webhooks de assinatura e falha de pagamento consultam a assinatura atual da Stripe antes de projetar estado; leituras indisponíveis ficam recuperáveis. A projeção por tenant possui claim exclusivo e fencing. A migração aditiva `0037` dá prazo/fencing ao claim de webhook e registra uma tentativa de Checkout por tenant. Concorrência abre uma sessão; timeout repete a mesma tentativa com a mesma `Idempotency-Key` e parâmetros; após a janela segura de 23h sem reconciliação a compra fica em HOLD. Founder/Internal não entra em Checkout pago nem perde seu entitlement em eventos comerciais; tem prioridade na seleção de entitlement. Consulta e licença locais respeitam `valid_from_utc`/`valid_until_utc`, limitando a lease ao prazo pago.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `node apps/commander/scripts/billing_sqlite_webhook_e2e.mjs` | 0 | falha antiga após recuperação, atualização antiga após cancelamento agendado, consulta indisponível/retry, claim órfão, claim ativo retryable, projeção concorrente/fenced e Founder; zero Stripe real |
| `node apps/commander/scripts/test_billing_checkout_attempts.mjs` | 0 | uma chamada ao mock em dois checkouts simultâneos, retry com mesma chave/corpo, nova tentativa após sessão vencida, webhook de tentativa antiga ignorado |
| `node apps/commander/scripts/test_paid_entitlement_expiry.mjs` | 0 | entitlement vencido/futuro negado, prioridade Founder e prazo da lease limitado ao fim pago |
| `node apps/commander/scripts/billing_v1_selftest.mjs` | 0 | contrato de Checkout/Portal com SQL real em memória |
| `node apps/commander/scripts/test_no_stripe_technical_mode.mjs` | 0 | 13/13, zero chamadas Stripe |
| `python3 -B apps/commander/scripts/validate_billing_v1.py` | 0 | migração `0037`, catálogo, contratos e preflight |
| `git diff --check` | 0 | sem erros de whitespace |

**Estados:** corrigido no código: seis cenários R2; testado local: SQLite e Stripe mock; testado DEV: não; publicado PROD: não. A prova local de claim não substitui D1/Worker concorrente hospedado. `0037` não foi aplicada remotamente. Nenhuma conta Stripe TEST autorizada está disponível, e não houve cobrança real. A decisão de mês-calendário versus ciclo Stripe e o baseline histórico Trial continuam pendentes. O teste de wake Event V2 passou a declarar apenas entrega a socket simulado; persistência/recuperação D1 exige outra prova integrada.

## Gate amplo, autoteste Linux e revisão R3 — 20/10/2026

O gate offline amplo inicial saiu **1** com 122/129 PASS e sete falhas, sem afrouxamento: staging sem assinatura oficial (HOLD esperado), jornada Linux e instaladores, dois testes de UI com termos antigos, telemetria e versão que exigiram subprocesso Python fora do sandbox. Os dois testes de UI foram atualizados para os termos aprovados e passaram (exit 0); telemetria 40/40 e versão 28/28 passaram fora do sandbox (exit 0). A jornada Linux e `validate_device_installers.py` falharam também fora do sandbox por uma fixture de autoteste: `workspace.inspect` subia até o marcador `.git` de `/tmp`, contrariando uma suposição do próprio teste. A fonte Linux agora cria um marcador de projeto próprio na fixture. `validate_agent_selftest_workspace_boundary.py` reproduz o pai marcado e passou (exit 0); autoteste Linux, instalação/atualização/remoção isolada e validação dos instaladores passaram (exit 0). O teste de instaladores usa `XDG_DATA_HOME` e `XDG_CONFIG_HOME` temporários para não gravar preimages no HOME. O candidato foi remontado sem assinatura, com novo hash acima. A execução inicial 122/129 não foi reclassificada como PASS; o gate completo precisa ser repetido após os patches.

**R3 recebida e lida:** `docs/operations/HARA_COMMANDER_PEER_REVIEW_R3_FLEET_20261020.md`; evidências locais em `docs/evidence/commander-peer-review-r3-fleet-20261020/`. A revisão reproduziu fila Event V2 que para após o lote de oito e child com 256 KiB de stdout que só progride após leitura; observou 13/16 sessões Services ocupadas e fan-out de token opaco para o IdP com mocks. Inclui diferenças de build sob a mesma versão e limitações de HA, sem prova de falta de hardware. Prioridade desta frente: regressões de fila e drenagem contínua, depois sessões e custo/autorização de autenticação, preservando a ordem comercial e a retenção ainda pendente. Não houve mudança nos Agents em execução. Os arquivos brutos de frota da R3 permanecem apenas no clone para revisão de privacidade antes de eventual commit; não são recibo de DEV comercial nem autorização de PROD.

**R3-QUEUE-01 corrigida no código e testada localmente:** Event V2 continua a reconciliação em lotes de no máximo oito enquanto o lote vier cheio; entre lotes, uma sondagem breve de prontidão do socket permite processar fechamento/evento, sem timeout curto sobre leitura parcial de frame. Após lote curto ou fila vazia, volta ao keepalive normal, sem polling HTTP ocioso. O novo teste reproduziu a falha antes do patch (exit 1 para 8 pendências) e passou depois (exit 0) para 0/1/8/9/12/16 chamadas, revogação entre lotes, ausência de replay e frame TCP parcial. `validate_event_v2_websocket_client.py`, `validate_event_v2_presence_reconnect.py` e `validate_event_v2_local_telemetry.py` passaram (exit 0). O subteste com `socketpair` exigiu execução local fora do sandbox, pois `sendall` foi bloqueado ali com EPERM; não usou rede externa. **Testado DEV: não; publicado PROD: não.**

**R3-PTY-02 corrigida no código e testada localmente:** coletor limitado por sessão ativa drena PTY mesmo sem leitura do cliente, compartilha lock com leituras interativas, preserva caracteres UTF-8 divididos e mantém os limites de memória/linhas anteriores. A regressão real falhou antes do patch (exit 1, child bloqueado), depois passou (exit 0) para 256 KiB, vários MiB/truncamento, Unicode, kill e revogação com descendente. A regressão pós-exit 19/19, orçamento de memória, autoteste Linux e `validate_device_installers.py` passaram (exit 0). O construtor do candidato e o staging assinado exigem agora ambos os testes PTY; `build_commander_commercial_terminal_drain_candidate.py --check` e os 12 testes de distribuição passaram (exit 0). A fonte candidata foi remontada com os bytes exatos e testada de novo (ambas as regressões exit 0). **Testado DEV: não; publicado PROD: não; assinatura oficial pendente.**

**R4 recebida para correção seguinte:** `docs/operations/HARA_COMMANDER_PEER_REVIEW_R4_DELIVERY_QUOTA_20261020.md` reproduz localmente resposta de mutação rebaixada para `DENIED` após falha de envio, envelopes `read_many` maiores que o limite do Worker e reserva de cota liberada quando o cliente some após conclusão. Não houve incidente PROD comprovado. Prioridade imediata: preservar conclusão/recibo e impedir reexecução cega da mutação; depois orçamento serializado e liquidação da cota. Evidências brutas da R4 permanecem no clone, sem commit ou uso de credenciais reais.

**R4-DELIVERY-01 e RESULT-SIZE-02 corrigidas no código e testadas localmente:** SQLite local grava a intenção antes da execução e o corpo exato antes da transmissão; resultado pronto é reenviado de forma idempotente sem reexecutar, inclusive após reinício. Intenção interrompida retorna `UNKNOWN`/`mutation_performed=null`, nunca garantia falsa de ausência de mutação. Resposta de aceite só libera o conteúdo local após `ok=true`; tombstone ACKED é retido por uma hora e pendências ficam limitadas a 256, sem descarte silencioso. O Agent suspende novos claims quando há resultado pendente, tanto no polling clássico quanto no Event V2. A regressão real falhou antes (exit 1, segunda conclusão falsa); agora passou (exit 0) para ACK perdido, reinício, duplicata, intenção interrompida e falhas repetidas. O teste de envelope falhou antes (exit 1, 603.461 bytes em 10 arquivos) e passou depois (exit 0) para 1/4/10 arquivos, controle JSON e fronteira de bytes; linhas não devolvidas conservam `next_offset` por arquivo. O payload de escrita agora rejeita UTF-8 acima de 65.536 bytes antes do enqueue, e a descrição MCP expõe esse limite; `validate_device_tool_contract.mjs`, `test_customer_mcp_simple_profile.mjs`, `validate_canonical_functions_hardening.py` e `validate_device_installers.py` passaram (exit 0). O construtor e o stage assinado passam a exigir as quatro regressões Linux; `--check` passou (exit 0). **Testado DEV: não; publicado PROD: não.** Limite restante: conclusão após expiração da chamada no servidor precisa reconciliação/aceitação específica; R4-QUOTA-03 ainda em correção.

**R4-QUOTA-03 corrigida no código e testada localmente:** migração nova `0038` marca a liquidação D1/DO, sem reescrever migração aplicada. `completeDeviceCall` liquida todo resultado normal autenticado antes de responder; repetição do mesmo resultado é idempotente. O job horário reconcilia até 200 resultados com prova ainda pendentes e preserva o conteúdo até a liquidação. `TenantQuota` aceita recibo válido de conclusão após vencimento da reserva e restaura a unidade no período original; falha sem execução comprovada libera a reserva. Trigger de DELETE versão 2 deixa consumo COMMITTED no agregado durante compactação e ainda desconta RESERVED removido. O teste novo falhou antes (exit 1) e passou (exit 0) para cliente ausente, falha DO após D1, reentrega, recuperação sem reentrega após TTL e negação sem execução. `test_approval_async_quota_ttl.mjs` (17 cenários), `test_approval_async_storage.mjs` (30), `test_quota_1000_local_workload.mjs` (1.000 objetos), `validate_tenant_quota_storage_efficiency.py` e `validate_quota_reservation_ttl.py` passaram (exit 0). **Testado DEV: não; publicado PROD: não; `0038` não aplicada remotamente.** Agregados históricos já descontados por DELETE não são reconstituíveis a partir das linhas ausentes e exigem auditoria antes da promoção.
