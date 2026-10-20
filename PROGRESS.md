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

- Fonte candidata atualizada após as melhorias de busca/listagem: `/tmp/commander-prelaunch-source-candidate-20261020-2125z`, manifesto SHA-256 `45e172a3e232fc445506923d58a881e85b836f7a6f8e5ddb20f5ce333fb3467e`, estado `AWAITING_OFFICIAL_SIGNATURE`. Linux atual `0.3.43` (SHA-256 `cbd1b6c9a979ef8484f241135967173be435139fbbb0401d136e813d62a899ba`) + Windows/instaladores comerciais v4 (`0.3.43`) + UI atual da branch (`index.html` SHA-256 `a82ad3ad28b43fe89282870aaabb23764632db07f5380a10726ea8d423b3c366`; `app.js` SHA-256 `754d21728dcdd4bf529147df5a4be59cf530ae6719d58c9f5164c06711d5bccb`). O Linux e o manifesto do candidato foram relidos por SHA; o arquivo `CANDIDATE_STATUS.json` declara `signature_present=false` e `private_key_read=false`. Sem assinatura, o verificador de publicação o rejeita. As montagens anteriores, inclusive `2104z`, `2112z` e `2117z`, foram superadas como candidatas e preservadas apenas como rastros locais.
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

## Histórico e retenção D1 — 20/10/2026

**Corrigido no código:** migração aditiva `0039` guarda total vitalício por tenant/usuário e contagem horária somente dos oito dias recentes. O histórico de sete dias combina essas contagens com a fração da hora inicial lida pelo índice existente; usa uma leitura D1 e conserva a precisão no limite de sete dias. O job horário remove no máximo 500 chamadas terminais com mais de 90 dias, apenas quando o uso pago está liquidado, e até 5.000 agregados horários vencidos. A migração adicional `0040` arquiva um marcador criptográfico mínimo antes de apagar uma conclusão `COMPLETED`/`FAILED`; o Worker só compacta essas chamadas depois da redação do payload e resultado. Reenvio posterior do resultado exato recebe aceite idempotente sem cobrar de novo. Linha sem liquidação e resultado ainda não redigido ficam preservados. Não há trigger de DELETE no histórico D1 que devolva franquia. `0039`/`0040` não foram aplicadas no D1 remoto.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `node apps/commander/scripts/test_device_call_history_retention.mjs` | 0 | backfill, limite exato de sete dias, prova pendente e conteúdo bruto preservados, arquivo de recibo mínimo, inserção posterior, replay da migração e isolamento de sujeito em SQLite |
| `node apps/commander/scripts/test_device_call_usage_settlement.mjs` | 0 | reenvio exato após arquivamento aceito, resultado divergente recusado e cota sem segunda cobrança |
| `python3 -B apps/commander/scripts/validate_portal_read_capacity.py` | 0 | 1.000/10.000 contas, resultados iguais, plano indexado e uma leitura D1 simulada; não mede Cloudflare hospedada |
| `node --check apps/commander/src/worker.js` | 0 | sintaxe |
| `git diff --check` | 0 | whitespace |

**Estados:** corrigido no código: sim; testado local: sim; testado DEV: não; publicado PROD: não. O stage deve aplicar `0039` e `0040` juntos antes do Worker novo. Escala/migração D1 hospedada e consumo histórico permanecem bloqueios de promoção.

## Orientação operacional recebida — 20/10/2026

Li `docs/operations/HARA_COMMANDER_PRIMARY_OPERATIONAL_POLICY_20261020.md` (SHA-256 `0f7f5b7ed96bea25f082e3d7e7ae6dad8f4fa4921281dc9b73ae423f05837dc6`) e `docs/operations/HARA_COMMANDER_FUNCTIONAL_IMPROVEMENTS_20261020.md`. A decisão expressa de Tiago foi recebida novamente nesta sessão: Commander é o MCP principal da frota e ele é o primeiro usuário intensivo. Desktop Commander deixou de ser dependência disponível; não o usar, reconectar ou renovar como fallback sem autorização. Os números de 10.000 transações contratadas e aproximadamente 80.000 usos são relato do proprietário, sem auditoria de conta, período ou benchmark de throughput. Não mudam o modelo comercial do HARA: R$ 80/mês, cinco computadores ativos por organização, um milhão de chamadas funcionais compartilhadas por mês, 5.000 de avaliação total e Founder/Internal separado; não há limite inventado de usuários. O foco local é benefício observável nas ferramentas existentes, confiabilidade R4, fila/PTY R3, sessões, limites de resposta e identidade. O uso do Commander ativo continua preservado; nenhuma mudança de Agent em execução, canário ou deploy foi autorizada. Não alterei os documentos de origem nem incluí os recibos externos deste turno nos commits.

## Compactação TenantQuota e regressões R4/R3 — 20/10/2026

**Corrigido no código:** cada DO ativo verifica retenção no máximo uma vez por dia quando não há backlog, ou a cada cinco minutos quando um lote de 1.000 foi cheio. A consulta é indexada e remove `DENIED` antigos, `RELEASED` apenas após liquidação comprovada sem execução, e `COMMITTED` de mês pago já encerrado após 90 dias. Reservas ainda abertas, liberações apenas por TTL e `COMMITTED` de Trial `LIFETIME` ficam no ledger. A trigger de DELETE versão 2 mantém o consumo `COMMITTED` no agregado `period_usage`; outra trigger move o vínculo e recibo para uma tabela menor na mesma operação atômica. Reserva com ID aposentado é recusada; repetição do mesmo recibo `COMMITTED` ou liberação `RELEASED` mantém resposta idempotente. A tabela de recibos aposentados cresce com o histórico e requer política futura de capacidade, sem descarte silencioso. Um DO sem tráfego não é compactado até a próxima consulta, pois não foi criado fan-out periódico por tenant.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `node apps/commander/scripts/test_approval_async_quota_ttl.mjs` | 0 | 20 cenários; trigger v1→v2, lote 2 simulado, plano indexado, Trial preservado, liberações pendentes preservadas, recibo aposentado idempotente e consumo pago estável |
| `node apps/commander/scripts/test_device_call_usage_settlement.mjs` | 0 | conclusão sem cliente, falha DO/retry e recibo idempotente |
| `node apps/commander/scripts/test_quota_1000_local_workload.mjs` | 0 | 1.000 DOs SQLite isolados; 44.504 asserções; não mede Cloudflare |
| `python3 -B apps/commander/scripts/validate_tenant_quota_storage_efficiency.py` | 0 | índice de expiração e leitura O(1) do agregado no caminho comum |
| `node apps/commander/scripts/test_approval_async_storage.mjs` | 0 | 30 cenários de leitura/settlement/concorrência em SQLite |
| `python3 -B apps/commander/scripts/validate_result_delivery_outbox.py` | 0 | novo caso de disco cheio após mutação: resultado `UNKNOWN`, sem reexecução nem falsa negação |
| `python3 -B apps/commander/scripts/validate_process_continuous_drain.py` | 0 | novo caso determinístico de desaparecimento `/proc`, erro de permissão preservado, 256 KiB, Unicode, memória e revogação de descendente |

**Estados:** corrigido no código: sim; testado local: sim; testado DEV: não; publicado PROD: não. A [documentação atual da Cloudflare](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/) confirma `sql.exec()` síncrono e armazenamento transacional; a validação acima usa SQLite local, não Cloudflare hospedada. Capacidade da tabela aposentada e custo da compactação em DO hospedado permanecem pontos de observação antes de promover a política de retenção.

## R5 recebida — uso real das funções existentes

Li `docs/operations/HARA_COMMANDER_DOGFOOD_R5_FUNCTIONS_20261020.md` após fechar os commits de retenção. A revisão observou no Commander Founder ativo: paginação simples, CAS/ambiguidade de edição e busca funcionando; resultado one-shot de oito linhas com `max_lines=3` foi truncado sem recuperação pelo `run_id`. Registrou também a diferença entre funções de hash/rollback no código e as 24 ferramentas disponíveis naquele conector, sem atribuir a causa ao backend. A prova é de uso Founder na frota, não de instalação comercial limpa, Windows, 1 milhão de chamadas ou DEV hospedado deste candidato. Os Agents em execução não foram alterados.

O commit documental de origem `27005547a048d5f6c2b61308f46726f8b324da03` foi confirmado via `git ls-remote origin refs/heads/local/commander-functions-r5-review-20261020` (exit 0). Seu objeto ainda não está neste clone; reconciliei apenas os três Markdown já entregues aqui, com hashes SHA-256 `0f7f5b7ed96bea25f082e3d7e7ae6dad8f4fa4921281dc9b73ae423f05837dc6` (política primária), `04f05e02938bdc2e1775a0d22aa940e5ef2d8b4353310344a602e93888b44c68` (melhorias funcionais) e `08a44ed9b2d7dae10cccc3689bcd8fde571f1842b52983c826d98f4d6c4f3a38` (R5), sem tocar na branch da revisão nem copiar evidências brutas. Os recibos JSON externos continuam sem commit. Versão assinada e canário seguem pendentes.

**R5-F01 corrigida no código Linux e testada localmente:** `process_run` mantém somente resultados terminados com linhas ainda não entregues, por até uma hora ou até o limite de oito resultados. A memória por sessão continua limitada a 2 MiB; os tombstones de expiração/evicção têm limite 128 e duram até 24h. A resposta inclui `run_id`/`session_id`, `next_offset`, base, truncamento e prazo de retenção; informa que a capacidade pode encurtá-lo. `read_process_output` recupera páginas pelo mesmo identificador, sem executar o comando novamente. Resultado pequeno continua one-shot e não ocupa sessão. Se o kill por timeout não tiver confirmação, a sessão permanece gerenciável com `termination_uncertain=true`, em vez de perder o PID. O caso de oito linhas/3 por página foi reproduzido antes (exit 1, `session_retained=false`) e passou depois (exit 0) com contador local igual a um. **Windows ainda usa o caminho one-shot anterior; paridade Windows precisa patch/teste próprio antes de alegar o mesmo benefício comercial.**

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/validate_process_oneshot_pagination.py` | 0 | 8 linhas em 3 páginas, efeito único, saída pequena não retida, expiração distinta e limite de resultados/tombstones |
| `python3 -B apps/commander/scripts/validate_process_terminal_drain.py` | 0 | 19/19 PTY pós-exit |
| `python3 -B apps/commander/scripts/validate_process_continuous_drain.py` | 0 | 256 KiB, Unicode, vários MiB, memória/descendente e corrida `/proc` |
| `python3 -B apps/commander/public/agent/linux.py --self-test` | 0 | contrato local Linux preservado |
| `python3 -B apps/commander/scripts/validate_device_installers.py` | 0 | jornada de instalação isolada e validações existentes |
| `python3 -B apps/commander/scripts/build_commander_commercial_terminal_drain_candidate.py --check` | 0 | cinco regressões Linux exigidas no construtor; candidato permanece sem assinatura |
| `python3 -B apps/commander/scripts/test_signed_distribution_stage.py` | 0 | 12 testes de seleção/manifesto/assinatura/adulteração |
| `python3 -B apps/commander/scripts/stage_signed_commercial_assets.py --check` | 1 | HOLD esperado: `SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE` |

**Estados:** corrigido no código: Linux sim, Windows pendente; testado local: Linux sim, inclusive bytes copiados para candidato `2022z`; testado DEV: não; instalado em canário: não; publicado PROD: não. O candidato novo possui manifesto coerente mas sem assinatura; não é um release publicável.

## R6 recebida — conclusão tardia e resultado público ponta a ponta

Li `docs/operations/HARA_COMMANDER_PEER_REVIEW_R6_END_TO_END_20261020.md` e a reprodução independente. O revisor comprovou que uma transmissão inicial perdida depois da execução local deixava READY após 51 s, e que o JSON interno de leituras com 4/10 arquivos era cortado na projeção pública. Revalidei o harness em cópia temporária, com Agent/Worker/SQLite reais, identidade e relógio sintéticos e sem rede externa. A cópia temporária aguarda 2,1 s entre tentativas para respeitar o novo backoff; os scripts originais do revisor não foram modificados. A prova local atual saiu 0: conclusão tardia entregue uma vez, outbox ACKED, novo claim permitido, ACK perdido recuperado e JSON interno parseável nos três tamanhos.

**Corrigido no código:** resultado autenticado de chamada já reclamada pode ser aceito depois do prazo de 50 s, inclusive se a limpeza a marcou EXPIRED; o prazo original permanece e a resposta marca `completed_after_deadline`. Chamada nunca reclamada, recibo divergente e resultado diferente continuam recusados. A liquidação da cota acompanha a conclusão idempotente. O Agent mantém o corpo READY em SQLite, aplica backoff transitório limitado a 300 s e põe respostas HTTP definitivas em quarentena, visíveis por `outbox status` e `doctor`; `outbox retry CALL_ID` reenvia o mesmo resultado somente após ação local explícita. Polling e Event V2 deixam de reclamar nova tarefa enquanto houver resultado pendente; a quarentena tem código próprio. Nenhuma ação mutante é reexecutada na recuperação.

**Projeção pública:** JSON de resultado até 128 KiB em bytes UTF-8 chega intacto aos perfis MCP simples/completo; conteúdo acima desse orçamento vira JSON válido com sinal de truncamento e offsets de continuação, enquanto texto puro permanece limitado. A regressão combina leitura real do Agent (1/4/10 arquivos) com projeção e envelope MCP e compara SHA do stdout entregue. Resultado one-shot Linux também passa a dividir linhas longas por orçamento em bytes para que o `run_id` e `next_offset` cheguem ao cliente.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| Harness R6 temporário `peer_end_to_end.py` sobre esta branch | 0 | dois achados `reproduced=false`, ACK perdido, atraso de 51 s, uma mutação, zero rede |
| `node apps/commander/scripts/test_device_call_usage_settlement.mjs` | 0 | conclusão tardia reclamada, expiração por manutenção, chamada não reclamada, idempotência e cota |
| `python3 -B apps/commander/scripts/validate_result_delivery_outbox.py` | 0 | backoff, quarentena, status sem payload, doctor degradado, retry exato, reinício e disco cheio |
| `python3 -B apps/commander/scripts/validate_event_v2_durable_batch_continuation.py` | 0 | pendência e quarentena bloqueiam claim com causas distintas; lotes 0/1/8/9/12/16 |
| `node apps/commander/scripts/test_public_result_projection.mjs` | 0 | JSON, offsets, Unicode e fronteiras 65.535/65.536/65.537 |
| `python3 -B apps/commander/scripts/validate_result_envelope_budget.py` | 0 | leitura real até envelope MCP, SHA igual em 1/4/10 arquivos |
| `python3 -B apps/commander/scripts/validate_process_oneshot_pagination.py` | 0 | linhas longas paginadas, sem repetição de comando |
| Construtor do candidato `--check`; testes de distribuição assinada | 0; 0 | bytes Linux verificados; 12 testes de seleção/assinatura |
| Stage assinado corrente `--check` | 1 | HOLD esperado por falta de assinatura oficial |

**Estados:** corrigido no código: sim (`cdb0208`, `ddbd0cc`); testado local: sim; testado DEV: não; publicado PROD: não. A identidade no harness é substituta, não prova de autorização Cloudflare. Quarentena exige avaliação do operador antes do reenvio, sem limpar o READY. O candidato `2022z` foi superado pelo `2104z` após as mudanças de R3/R7 e a divulgação do trânsito Cloud.

## R3 — sessões e autenticação opaca

**Sessões corrigidas no código (`c254758`, `862ca44`):** `process.run` agora define `PAGER`, `GIT_PAGER` e `PSQL_PAGER` apenas no ambiente do subprocesso one-shot, sem alterar o shell interativo nem o ambiente do Agent. O claim durável passa o `subject_id` ao Agent e a sessão retém identificador do sujeito e `request_id`; `process.sessions` expõe ocupação, capacidade, último acesso do cliente, segundos ociosos e sessões que exigem revisão do dono após 30 min. O aviso é registrado ao atingir 12/16 sessões ativas. Falha de gravação do aviso aparece no retorno/status com código seguro; o teste de instaladores detectou e impediu uma captura silenciosa. A política é de **revisão e encerramento explícito pelo dono via `process.kill`**, sem matar automaticamente um job longo que pode estar autorizado. Não foi executada limpeza nos 13 processos observados pela revisão em Services; Agents ativos não foram modificados.

**Autenticação corrigida no código (`0063c41`):** discovery e JWKS coalescem requisições simultâneas; token opaco igual compartilha apenas introspection/userinfo **em voo**, com remoção imediata após resposta. A cada chamada posterior, o token é validado de novo para respeitar revogação, sem cache durável de credencial. As consultas ao IdP têm `AbortSignal` e prazo de aplicação de 3 s, inclusive se o mock ignorar abort. Falha do provedor retorna 503 com `Retry-After: 5`; token inativo ou rejeitado pelo userinfo permanece 401. O Worker registra latência/categoria sem token, sujeito ou segredo, com amostragem de 1% nos sucessos. O teste com mocks observou 25 introspections + 25 userinfos em 25 chamadas sequenciais e 1 + 1 em 10 simultâneas do mesmo token; tokens diferentes não compartilham. A [documentação Cloudflare de APIs Web](https://developers.cloudflare.com/workers/runtime-apis/web-standards/) confirma `AbortController`/`AbortSignal` no runtime, mas o comportamento hospedado ainda requer DEV.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/validate_process_session_policy.py` | 0 | PTY real, pager one-shot, shell interativo, dono, alerta de capacidade, falha de armazenamento visível e job longo preservado |
| `node apps/commander/scripts/test_approval_async_queue_claim.mjs` | 0 | 19 cenários, sujeito vinculado ao claim; fixture SQL atualizada para `usage_settled_at_utc` |
| `node apps/commander/scripts/test_hara_identity_customer_auth_pressure.mjs` | 0 | 25 sequenciais, 10 concorrentes, tokens distintos, revogação, 401/503 e timeout de 3 s; zero rede real |
| `node apps/commander/scripts/test_hara_identity_customer_mcp.mjs`; `test_oidc_discovery.mjs`; `test_oidc_transport.mjs` | 0; 0; 0 | contrato de issuer/audience/scope e endpoints HTTPS preservado; teste de discovery passa a usar issuer único por caso para não mascarar falha via cache |
| `python3 -B apps/commander/scripts/validate_device_installers.py` | 0 | validação e autoteste Linux isolados, fora do sandbox para socket 127.0.0.1 |
| `python3 -B apps/commander/scripts/commander_linux_clean_lifecycle.py --execute` | 0 | instalação, update, reenrolamento e remoção locais, fora do sandbox para loopback; sem Agent real |
| `python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py` | 1 | **138/139 PASS** fora do sandbox; único FAIL é `stage_signed_commercial_assets.py`, HOLD esperado sem assinatura oficial |
| `python3 -B apps/commander/scripts/build_commander_commercial_terminal_drain_candidate.py --output /tmp/commander-prelaunch-source-candidate-20261020-2104z` | 0 | candidato sem assinatura, Linux SHA, manifesto e UI acima; rollback v4 separado |

**Estados:** corrigido no código: sim para sessões e custo/deadline da autenticação; testado local: sim, inclusive gate 138/139; testado DEV: não; publicado PROD: não. O gate inicial no sandbox saiu 128/139 por fixtures defasadas e bloqueio de sockets/subprocessos; as cinco fixtures foram reconciliadas e os testes de loopback passaram fora dele. O gate final permaneceu exit 1 pela assinatura ausente. Coalescência reduz picos do mesmo token, mas não elimina as duas consultas sequenciais por chamada; cache de introspection além do voo exige contrato explícito de revogação. Alertas de capacidade ainda dependem de release e observação nos Agents, sem limpeza automática da frota.

## Jornada comercial, pacote MCP e promoção — verificação local

Conferi o ZIP de revisão existente `apps/commander/plugin-submission/hara-commander-capivara-v0.2.0-review.zip` antes de qualquer edição: SHA-256 `40c5a69ed30b7ed626fe725b1eb2841d423e3e3ef772b49120aad228f606c483`; `validate_commander_submission_package.py` confirmou `SOURCE_PACKAGE_PASS`, 33 ferramentas, cinco casos positivos e três negativos, com ZIP igual à fonte. `mcp.json` usa apenas `https://commander.haralabs.com.br/api/mcp?profile=simple` com recurso OAuth `https://commander.haralabs.com.br/api/mcp`, separado do MCP interno `mcp.haralabs.com.br/mcp`. Não alterei o ZIP. Os comentários mais recentes de hara-platform #851 ainda pedem decisão do proprietário sobre `functions.list/describe/invoke` e hints antes da submissão; credencial de revisor, vídeo, verificação de domínio/negócio, scan e aprovação pública continuam sem prova. Hara-platform #1000 confirma o canal outbound do Agent e telemetria só de metadados; não autoriza rotear conteúdo de cliente pelo Services.

O contrato de jornada Cloud detectou uma lacuna real: a nota inicial e a nota dinâmica do portal não divulgavam igualmente que o conteúdo transita pelo Gateway e pode permanecer temporariamente na fila. Ambas agora exibem esse fato, e `validate_cloud_launch_contract.py` exige a divulgação nas duas fontes. Isto esclarece a escolha do cliente sem alterar o transporte. A jornada Linux limpa passou localmente com fixture isolada; a validação do instalador também passou. O Windows `0.3.52-v12-rc` tem assinatura RS256 verificada e testes de seleção/imutabilidade locais, mas é RC separado, não substituto silencioso do Windows comercial `0.3.43` no candidato. Não há `pwsh` nem aceite de instalação Windows limpa e roundtrip autenticado neste host. O instalador Event V2 Windows RC continua DEV-only e sua própria validação declara `WINDOWS_RUNTIME_PROVEN=FALSE`.

O assistente Stripe TEST continua só com mocks: chave LIVE negada, preço `BRL 8000/month`, webhook e portal simulados, ordem de secrets e redação aprovadas. Corrigi o teste de fallback Node para simular ausência no PATH sem depender da instalação NVM específica deste host; o código de ativação não mudou. A conta Stripe TEST e a prova de checkout, webhook assinado e cancelamento reais dependem do proprietário. A franquia única continua por mês-calendário, enquanto Stripe governa período pago; a decisão de produto permanece pendente antes de migrar clientes.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/validate_cloud_launch_contract.py` | 0 | rota comercial, OAuth, Cloud padrão e divulgação na UI inicial/dinâmica; teste estático, não OAuth hospedado |
| `python3 -B apps/commander/scripts/validate_prod_static.py` | 0 | UI e configuração estáticas |
| `python3 -B apps/commander/scripts/validate_commander_submission_package.py` | 0 | `SOURCE_PACKAGE_PASS`; pacote não submetido |
| `python3 -B apps/commander/scripts/validate_stripe_test_wizard.py` | 0 | mocks, preço, chave LIVE negada, Node em PATH/fallback; zero Stripe real |
| `python3 -B apps/commander/scripts/validate_signed_windows_052_v12_rc.py` | 0 | assinatura RC válida, sem prova runtime Windows |
| `python3 -B apps/commander/scripts/test_windows_052_release_guards.py` | 0 | 13 guardas de fonte/imutabilidade, sem assinatura nova ou deploy |
| `python3 -B apps/commander/scripts/validate_event_v2_windows_rc_install.py` | 0 | RC instalável em DEV por contrato estático; runtime não provado |
| `python3 -B apps/commander/scripts/commander_commercial_readiness_gate.py --require COMMERCIAL_BETA` | 2 | HOLD: distribuição comercial assinada e segundo tenant autenticado ainda sem evidência deste candidato |
| `python3 -B apps/commander/scripts/build_commander_commercial_terminal_drain_candidate.py --check` | 0 | fonte coerente e sem assinatura |
| `python3 -B apps/commander/scripts/test_signed_distribution_stage.py` | 0 | 12 regressões de seleção, hash, assinatura e drenagem |
| `python3 -B apps/commander/scripts/stage_signed_commercial_assets.py --check` | 1 | HOLD: `SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE` |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py` | 1 | 140/141 PASS fora do sandbox; único FAIL é o staging sem assinatura oficial. Inclui agora contrato Cloud e wizard Stripe TEST; a execução precedeu o commit `fa92a66` do próprio gate, sem alterar os testes executados |

**Estados:** corrigido no código: divulgação Cloud (`e369b70`), fixture Stripe (`73c3dd2`) e gate ampliado (`fa92a66`); testado local: sim para fonte, mocks e Linux; testado DEV: não para este candidato; publicado PROD: não. A prova Founder e o ZIP fonte não substituem cliente comercial limpo. Próxima promoção exige assinatura oficial do candidato, readback de bytes/versão e rollback, migrações `0036`–`0040` em DEV autorizado com auditoria dos agregados históricos, dois tenants reais isolados, Windows limpo, Stripe TEST autorizado, decisão de mês-calendário e aprovação específica antes de PROD. Nenhuma dessas ações remotas foi executada nesta sessão.

## Revisão independente R7 — admissão concorrente de processos

Li `docs/operations/HARA_COMMANDER_PEER_REVIEW_R7_20261020.md` no clone. A revisão distinguiu corretamente uma corrida induzida dentro da mesma instância Python da alcançabilidade pelo transporte comercial atual; não há prova de incidente em PROD. No instante desta leitura, `docs/evidence/commander-peer-review-r7-20261020/` citado pelo Markdown não estava presente no clone, então reproduzi a condição com regressão própria, sem depender da fixture ausente. A primeira execução do teste com a fonte anterior saiu **1**: duas chamadas simultâneas foram aceitas para capacidade um.

**Corrigido no código (`c486bd1`):** `process_start` reserva a vaga sob lock antes do fork, sem manter o lock durante o fork. A reserva conta tanto no teto ativo (16) quanto no teto retido, é transferida para a sessão registrada e é liberada em falha. Falha antes da resposta encerra o child criado, fecha o PTY e retira uma sessão sem identificador entregue ao cliente. O coletor termina ao receber o sinal local de parada. A regressão força duas entradas com limite um e vinte com limite 16, falha de fork, falha de início do coletor e falha de leitura após fork real. Não foram encerradas as 13 sessões RUNNING observadas no Services nem alterado Agent ativo. Este controle é **por processo Agent**, não uma cota distribuída entre processos ou dispositivos.

| Teste local | Exit | Evidência |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/validate_process_session_policy.py` antes da correção | 1 | duas sessões aceitas com limite um; corrida reproduzida com fork simulado |
| Mesmo teste depois de `c486bd1` | 0 | 1/2 e 16/20 aceites, reserva liberada nos erros, child real encerrado, pager/owner/revisão preservados |
| `python3 -B apps/commander/public/agent/linux.py --self-test` | 0 | contrato local do Agent preservado |
| `python3 -B apps/commander/scripts/validate_process_continuous_drain.py` | 0 | drenagem contínua, Unicode, truncamento, kill/revogação preservados |
| `python3 -B apps/commander/scripts/build_commander_commercial_terminal_drain_candidate.py --check` | 0 | novo SHA Linux ancorado, candidato ainda sem assinatura |
| `python3 -B apps/commander/scripts/test_signed_distribution_stage.py` | 0 | 12 regressões de distribuição/assinatura |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py` | 1 | 140/141 PASS com `source_head=c486bd1`; único FAIL é o HOLD de assinatura oficial; lifecycle e instalador Linux passaram |

A revisão também observou dispositivos Event V2 com `last_seen_at_utc` antigo que responderam a ping recente; idade de `last_seen` não prova desconexão. A observação não demonstra falha de roteamento ou de presença neste candidato. A semântica de cadastro, checkpoint e ping deve ser qualificada em DEV antes de alterar o estado exibido ao cliente. Diferenças de build na frota e HA de Identity permanecem nos limites da R3 e não foram confundidas com aceite comercial.

**Estados:** corrigido no código: admissão por instância; testado local: sim; testado DEV: não; canário comercial: não; publicado PROD: não. O candidato `2104z` preservava a correção e foi superado pelas fontes `2112z` e `2117z`, ainda sem assinatura oficial. A revisão R7 e a telemetria de frota não autorizam intervenção nos Agents em execução.

## Paridade de uso diário — paginação de arquivos e handoff funcional

**Gap e correção (`abefe75`):** a leitura paginada Linux retornava offsets sem pista barata de que os bytes do arquivo haviam mudado. A regressão inicial falhou (exit 1, ausência de `file_revision_hint`). `filesystem.read` e cada item de `filesystem.read_many` agora expõem uma pista SHA-256 **dos metadados** de dispositivo, inode, tamanho, mtime e ctime. Essa pista não é hash do conteúdo, assinatura, CAS ou snapshot. Se o arquivo muda durante a leitura, o resultado marca `file_changed_during_read=true`, `continuation_safe=false`, remove `next_offset` e indica `restart_offset=0`. Se os metadados mudam entre páginas, as pistas diferem para que o cliente reinicie. O sinal de mudança sobrevive inclusive a uma tentativa interna de reduzir a resposta ao orçamento de 96 KiB. O teste público confirma os campos no envelope MCP simples/completo sem alterar o ZIP de submissão.

**Gap e correção (`47d04ac`):** `read_multiple_files` informava `FAILED` por item, mas faltava um resumo para distinguir lote parcial de lote totalmente bem-sucedido. A regressão falhou antes (exit 1, ausência de `successful_count`) e passou depois. O resultado agora acrescenta `successful_count`, `failed_count`, `deferred_count` e `overall_status=PASS|PARTIAL|FAILED`; uma mudança detectada durante leitura produz `PARTIAL`, mesmo se o item devolveu linhas. A contagem entra no cálculo do orçamento serializado, e a projeção MCP simples/completo a conserva. Nenhum campo antigo foi retirado e nenhum erro por item foi escondido.

| Função / gap observado | Commit / prova local (exit) | Fonte candidata / canário |
| --- | --- | --- |
| `read_file`, `read_multiple_files`: mudança entre páginas ou durante leitura não era sinalizada; lote parcial não tinha resumo; orçamento agregado já havia sido corrigido na R4 | `abefe75`, `47d04ac`; regressões antes 1/1, depois `validate_result_envelope_budget.py` 0 para 1/4/10 arquivos, mutação, retry, lote misto/adiado; `test_public_result_projection.mjs` 0 | Linux `2117z` sem assinatura; canário não instalado; paridade Windows não provada |
| `start_process`, `read_process_output`, `interact_with_process`: cauda pós-exit, child bloqueado e saída one-shot truncada observados nas R3/R5 | correções anteriores de drenagem/R5 e admissão `c486bd1`; PTY pós-exit 19/19, drenagem contínua, one-shot e capacidade passaram no gate atual (exit 0 por teste) | Linux `2117z` sem assinatura; canário não instalado; Windows one-shot ainda sem paridade de recuperação |
| Resultado/recibo de mutação e continuação após ACK perdido (R4/R6) | `cdb0208`, `ddbd0cc` e testes `validate_result_delivery_outbox.py`/`test_device_call_usage_settlement.mjs` exit 0 no gate | código local; sem DEV hospedado/canário; não repetir mutação em timeout |
| Fila Event V2 após oito, sessões por processo e autenticação opaca (R3/R7) | fila `72c6820`, admissão `c486bd1`, testes de lotes, sessões e Identity exit 0 no gate | código local; Cloudflare hospedada e canário comercial pendentes |
| Descoberta de hash/rollback, indicação de eco PTY e presença fresca versus cadastro (R5/R7) | gaps e aceite registrados; ZIP `SOURCE_PACKAGE_PASS` com 33 ferramentas, sem mudança publicada; não há prova de equivalência da superfície conectada de 24 ferramentas | nenhuma promoção ou canário; requer contrato do pacote, runtime Windows e validação funcional |

| Verificação desta rodada | Exit | Alcance real |
| --- | ---: | --- |
| `python3 -B apps/commander/scripts/validate_result_envelope_budget.py` | 0 | 1/4/10 arquivos, revisão entre páginas, alteração durante leitura, retry de orçamento, resumo parcial/falha/adiado, Unicode/escapes e fronteira do envelope |
| `node apps/commander/scripts/test_public_result_projection.mjs` | 0 | campos novos preservados no JSON público com paridade simples/completo |
| `node apps/commander/scripts/test_customer_mcp_simple_profile.mjs` | 0 | contrato das 33 ferramentas da fonte preservado |
| `python3 -B apps/commander/public/agent/linux.py --self-test` | 0 | autoteste do Agent local |
| `python3 -B apps/commander/scripts/build_commander_commercial_terminal_drain_candidate.py --check` | 0 | SHA Linux ancorado na fonte nova |
| `python3 -B apps/commander/scripts/test_signed_distribution_stage.py` | 0 | 12 regressões de seleção, hash, assinatura e rollback |
| `python3 -B apps/commander/scripts/validate_commander_submission_package.py` | 0 | `SOURCE_PACKAGE_PASS`; ZIP inalterado, não submetido |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py` | 1 | 140/141 PASS, `source_head=47d04ac3b7362d6359e3bd82b28493d560391cd8`; único FAIL é staging assinado em HOLD; `PROD_MUTATION=FALSE` |
| SHA da fonte Linux, cópia no candidato e manifesto relidos | 0 | Linux `c7b695c5...d605d06e` idêntico; manifesto `749b1c98...95f63fa2e`, versões 0.3.43/0.3.43 e `signature_present=false` |
| `git diff --check` | 0 | sem whitespace no patch funcional |

**Estados:** corrigido no código: pista de revisão e resumo parcial Linux, além das correções R3/R4/R5/R6/R7 já listadas; testado local: sim; testado DEV: não para este candidato; instalado em canário: não; publicado PROD: não. Windows, superfície de ferramentas do conector ativo e semântica hospedada de presença ainda exigem prova própria. A próxima promoção depende de assinatura oficial, readback, canário e rollback sem interromper o acesso atual, e aprovação específica; não houve uso de Desktop Commander, Stripe LIVE ou billing OpenAI.

## Reforço funcional recebido — busca e listagem com varredura honesta

Reli `docs/operations/HARA_COMMANDER_FUNCTIONAL_IMPROVEMENTS_20261020.md` (SHA-256 `04f05e02938bdc2e1775a0d22aa940e5ef2d8b4353310344a602e93888b44c68`) após o reforço expresso de Tiago: as ferramentas reais precisam de patch, teste, prova antes/depois e benefício observável, sem duplicar a superfície MCP. As correções R4 de recibo/resultado, orçamento e liquidação já estão no código e passaram novamente no gate offline; **R4 ainda não foi testada na Cloudflare hospedada nem publicada**. As correções R3 de fila/PTY também passaram no gate e permanecem sem instalação nova. Nenhum Agent ativo foi alterado, e Desktop Commander não foi usado.

**Atrito reproduzido antes do patch:** uma busca por nome inexistente em uma varredura sintética de 5.001 entradas parava após 5.000 e retornava `count=0`, `scan_truncated=true`, `next_offset=0`. Repetir esse offset examinaria o mesmo prefixo. Uma pasta cuja listagem foi recusada por permissão retornava `count=0` sem sinal de que a varredura falhou. Comparei a fonte `47d04ac` com `0165677` em processos isolados, usando as mesmas fixtures: após o patch, a busca retorna `scan_incomplete=true`, `incomplete_reason=SCAN_LIMIT`, `next_offset=null`; a listagem retorna `PERMISSION_DENIED`, contador 1 e `continuation_safe=false`. Ambas as comparações saíram exit 0 e não acessaram frota real.

**Correção (`0165677`):** `filesystem.search` e `filesystem.list` existentes agora distinguem página normal de varredura incompleta por limite de 5.000 arquivos, prazo de 3 s, permissão ou erro de I/O. Busca de conteúdo sinaliza também arquivos binários ou acima de 2 MiB excluídos, com contadores. Em varredura incompleta, não oferece offset de continuação que pareça seguro. Campos e paginação anteriores permanecem nos casos completos. O teste chamou também os caminhos reais `hara.files.search` e `hara.files.list` de `execute_tool` sobre arquivos locais temporários, não apenas helpers. A continuação por offset ainda pressupõe árvore estável entre chamadas; detecção de mutação profunda da árvore permanece uma lacuna, não foi alegada como resolvida.

| Função / prioridade | Gap, patch e prova | Candidato / canário |
| --- | --- | --- |
| `read_file`, `read_multiple_files` | `abefe75`, `47d04ac`: revisão entre páginas e resumo parcial; regressões 1/4/10, mutação e retry exit 0 | Linux `2125z` sem assinatura; não instalado |
| `search`, `list_directory` | `0165677`: scan cap, prazo, permissão e conteúdo excluído sem falso “nenhum resultado”; `validate_canonical_functions_hardening.py` passou exit 0 | Linux `2125z` sem assinatura; não instalado; Windows não qualificado |
| `write_file`, `edit_block`, `copy_file`, `move_file`, `delete_file` | Precondição SHA de escrita/edição/exclusão e proteção de symlink em cópia/movimento passaram no teste canônico exit 0; hash/rollback no conector ativo de 24 ferramentas ainda requer reconciliação, sem novo patch nesta rodada | Fonte local; sem canário novo |
| `start_process`, `read_process_output`, `interact_with_process`, sessões | Drenagem R3, paginação one-shot R5 e limite concorrente R7 passaram no gate exit 0 por teste; acúmulo das sessões reais não foi alterado | Linux `2125z` sem assinatura; sem canário; Windows sem prova equivalente |
| Resultado/recibo e cota R4; fila Event V2 R3 | Testes offline de outbox, settlement, 0/1/8/9/12/16, quotas e Identity passaram no gate exit 0 por teste; DEV hospedado permanece pendente | Código local; sem deploy |
| Seleção/saúde de computador | Observação de build e status passou no gate; presença fresca versus estado cadastral e equivalência do conector ativo ainda pedem reprodução/aceite | Sem patch novo, DEV ou canário |

| Verificação desta rodada | Exit | Evidência e limite |
| --- | ---: | --- |
| `validate_canonical_functions_hardening.py` antes de `0165677` | 1 | regressão nova falhou por ausência de sinal de scan incompleto |
| Mesmo teste após `0165677` | 0 | busca/listagem reais no Agent, paginação estável, scan cap, prazo, permissão, exclusão de conteúdo e CAS pré-existente |
| Comparação isolada `47d04ac`/`HEAD` de busca e listagem | 0; 0 | valores antes/depois acima, sem Agent ativo |
| Autoteste Linux; construtor do candidato `--check`; 12 testes de distribuição | 0; 0; 0 | fonte e seleção preservadas, candidato sem assinatura |
| `stage_signed_commercial_assets.py --check` | 1 | HOLD `SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE` |
| Gate offline completo após `0165677` | 1 | 140/141 PASS, `source_head=01656779b7705a1b333362f3fb4207ddffbfcbbc`; só o HOLD de assinatura; `PROD_MUTATION=FALSE` |
| SHA da fonte Linux, cópia no candidato e manifesto | 0 | Linux `cbd1b6c9...62a899ba` idêntico; manifesto `45e172a3...3fb3467e`; versões 0.3.43/0.3.43, `signature_present=false` |

**Estados:** corrigido no código: busca/listagem Linux e correções anteriores preservadas; testado local: sim, incluindo funções reais do Agent em fixture; testado DEV: não para este candidato; uso prolongado na frota: não; instalado em canário: não; publicado PROD: não. O uso diário deve fornecer próximos casos, mas esta rodada não tratou a fixture como prova de canário nem executou carga na frota. Assinatura oficial, rollback/readback, canário reservado e aprovação específica continuam necessários antes de mexer no acesso atual.
