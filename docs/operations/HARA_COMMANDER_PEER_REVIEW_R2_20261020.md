# HARA Commander — revisão independente R2: cobrança e expiração

Revisor: Valky. Coleta e reprodução: 2026-10-20 18:58–19:00 UTC.
Frente examinada: `codex/commander-prelaunch-fixes-20261020` no clone do Núcleo.
Base do snapshot: `1943a269b4361e78a73a588e10bc2bd89f251166`.

## Primeiro: avanço real e revisão anterior incorporada

`d7b3ad5` + `a73124b` incorporaram o aviso R1: o pacote v4 não é promovido como equivalente ao Linux atual; a drenagem pós-exit recebe regressão real e o candidato exige assinatura oficial. O `PROGRESS.md` distingue fonte, teste e PROD. Isso é correto. Esta R2 não pede reabrir/reverter essas correções.

## Método e limites desta rodada

- Copiei SOMENTE fontes/testes/migrações selecionados para um diretório temporário exclusivo; nenhum arquivo do produto foi editado pelo revisor.
- Snapshot: `/tmp/hara-commander-peer-r2-20261020-dh1paucj`.
- `SNAPSHOT.json` registra HEAD, timestamp e hashes; nenhuma fonte mudou durante a cópia nem durante os testes.
- `billing.mjs` SHA-256: `c50ee6b7c001b50bfd39a1f1e6cdba586536e793c5d77bf7603ab4af5a3ed67d`.
- `worker.js` SHA-256: `ee036e2bcfba43e291cb3b131cb49de88c2948454e8a75c21b7b1db2ce4dc2cc`.
- Testes: SQLite `:memory:`, eventos sintéticos assinados com segredo de fixture, mock de Stripe e rede bloqueada no harness. Nenhuma chave real foi lida e nenhuma cobrança/Worker/D1 remoto foi alterado.
- Harness: `peer_billing_edgecases.mjs`; resultado: `peer_results.json`. Exit final **2 = seis riscos reproduzidos**, não crash do teste. Tentativas de rede real: **0**.
- Houve um erro inicial do próprio harness (migração `0003_plan_grants.sql` faltante), corrigido antes da reprodução válida. Não foi atribuído ao produto.
- O teste existente `billing_sqlite_webhook_e2e.mjs` passou, exit 0, no MESMO snapshot; o teste Python do catálogo também passou. Logo a lacuna é cobertura de cenários adicionais, não ausência de testes.
- Cinco funções examinadas são byte-a-byte iguais à base `4821692`: `claimWebhookEvent`, `processInvoicePaymentFailed`, `createBillingCheckout`, `entitlementForTenant`, `productLeaseForContext`. Não atribuir todas as falhas ao patch novo; há dívida anterior que agora precisa de cobertura.

Reprodução independente, sem serviço externo:

```bash
cd /tmp/hara-commander-peer-r2-20261020-dh1paucj
/home/sartorius/.nvm/versions/node/v24.15.0/bin/node --disable-warning=ExperimentalWarning peer_billing_edgecases.mjs
# Esperado neste snapshot: exit 2 e seis reproduced=true.
```

## R2-BILL-01 / R2-BILL-02 — eventos antigos da MESMA assinatura sobrescrevem estado novo

**Reproduzido com handler real e SQL real em memória:**

1. Assinatura ativa/recuperada; depois chega `invoice.payment_failed` mais antigo, com event ID distinto e MESMO subscription ID. O acesso volta para `SUSPENDED`.
2. Cancelamento agendado foi salvo com `valid_until_utc` futuro; depois chega snapshot `customer.subscription.updated` antigo, ainda active e sem cancelamento. O código apaga o prazo e zera `cancel_at_period_end`.

A proteção atual contra IDs de assinaturas anteriores e contra reativar REVOKED é útil, mas não cobre estes dois casos da mesma assinatura.

**Ação:** antes de aplicar um snapshot atrasado, reconciliar o estado canônico da assinatura/invoice no provedor com leitura autenticada restrita; serializar a projeção por assinatura/tenant e preservar idempotência. Em testes locais, injetar fetcher canônico com fixtures. Não “corrigir” comparando apenas `event.created`: timestamps podem coincidir, e ordem de chegada não é ordem do negócio. Não persistir payload completo com dados pessoais.

**Aceite:** recovery + failure antigo não suspende; cancelamento atual + active antigo não apaga deadline; versões duplicadas e eventos na mesma timestamp convergem; falha da consulta ao provedor fica explícita e recuperável, sem liberar acesso sem base.

Referência primária consultada em 20/10/2026: Stripe `https://docs.stripe.com/webhooks`, seções Event ordering / Handle duplicate events. A documentação não garante ordenação e recomenda não depender de `created` para ordenar/deduplicar snapshots.

## R2-BILL-03 — evento abandonado em PROCESSING nunca é recuperado

**Reprodução:** semear evento PROCESSING com `received_at_utc` antigo, como após morte do Worker entre claim e conclusão. Três reentregas válidas retornam `ok=true, duplicate=true, result_code=EVENT_IN_PROGRESS`. O registro continua PROCESSING e o entitlement pago não existe.

`claimWebhookEvent()` só reclama RECEIVED/FAILED. Não há lease/expiry/fencing nem recuperação do PROCESSING nesta via. O endpoint Worker envolve esse retorno em `json(...)`, portanto a resposta normal é de sucesso sem provar aplicação nem enfileiramento recuperável.

**Ação:** claim com prazo e identificador de dono; recuperação atômica após expiração; fence contra conclusão atrasada do dono anterior. Ou inbox durável + executor/reconciliação que garanta retomada. Duplicata concluída pode ser 2xx; evento apenas abandonado não pode ser tratado como concluído. Não basta trocar PROCESSING para FAILED indiscriminadamente enquanto o primeiro executor ainda pode agir.

**Aceite:** falhas após claim e após atualização parcial recuperam entitlement exatamente uma vez; retry não fica preso; processo antigo não sobrescreve recuperação; alerta operacional para claim órfão. A simulação foi de estado persistido equivalente a crash, não morte de Worker real.

## R2-BILL-04 — duas tentativas simultâneas criam dois checkouts

**Reprodução:** `Promise.all` com duas chamadas `createBillingCheckout` do mesmo tenant sem assinatura ainda. Obtive duas chamadas ao mock do provedor e dois `checkout_session_id` distintos; nenhum `Idempotency-Key` enviado.

O guard de assinatura ativa só funciona depois do webhook. Antes disso, clique duplo, duas abas ou retry após timeout podem abrir duas oportunidades de compra.

**Ação:** registrar tentativa de compra pendente por tenant/plano de forma atômica; reutilizar sessão ainda válida; usar chave idempotente estável por TENTATIVA no provedor; recuperar timeout ambíguo antes de criar outra sessão. Não usar chave eterna por tenant, pois impediria compras legítimas futuras. Cobrança em si NÃO foi testada nem ocorreu.

**Aceite:** duas requisições concorrentes → uma tentativa comercial; timeout/retry retorna a sessão existente; sessão vencida permite nova tentativa; assinatura nova não é alterada por webhook de tentativa anterior.

## R2-BILL-05 — fluxo pago pode expirar Founder/Internal

**Reprodução:** tenant sintético com entitlement FOUNDER_INTERNAL ativo; webhook subscription.created STANDARD torna o Founder `EXPIRED`, pois `syncPaidEntitlement` expira todos os outros ACTIVE do tenant.

**Ação:** proteger explicitamente a isenção Founder no checkout E na sincronização de eventos. Não confiar somente em esconder o botão. Preservar política de prioridade/seleção de entitlement; não gerar ambiguidade entre duas authorities.

**Aceite:** Founder permanece ativo/ilimitado e sem dependência Stripe após qualquer evento comercial, inclusive pagamento/cancelamento. Nenhum Founder real foi modificado.

## R2-LEASE-06 — prazo pago não chega à emissão de licença local

**Reprodução de funções reais extraídas, não de endpoint público:**

- `entitlementForTenant()` retornou entitlement ACTIVE cujo `valid_until_utc` já havia passado há uma hora: query ignora `valid_from_utc` / `valid_until_utc`.
- `productLeaseForContext()` recebeu contexto com término pago em um minuto, mas emitiu objeto de licença com validade de seis horas.
- `deviceProductLease()` nem transmite as datas do entitlement no contexto. A nova gravação correta de cancelamento no Billing ainda não basta para fazer todos os caminhos respeitarem o prazo.

**Ação:** resolver entitlement com janela temporal e vinculação corretas; passar os limites para o contexto; limitar lease a `min(TTL, fim do período aplicável, validade do entitlement)`. Bloquear renovação após vencimento e explicitar comportamento offline/revogação. Evitar renovar autorização por 6h depois do fim pago; não enfraquecer Direct/Cloud/Local Budget.

**Aceite:** não emitir lease para entitlement expirado/futuro, licença nunca ultrapassa fim pago e não se renova após cancelamento efetivo; durante o período pago, acesso permanece. O harness NÃO assinou nem utilizou uma licença e não prova bypass E2E de todos os guards.

## Prioridades e continuidade

Tratar como gates antes de receber clientes pagantes: reconciliação de eventos, recuperação de crash, unicidade de checkout e expiração consistente. Founder é uma regressão contratual a proteger também.

O limite de cinco PCs está em implementação em outra parte do mesmo worktree. Esta nota não declara pronto ou defeituoso o WIP que ainda não foi testado. Reexecutar os cenários contra os hashes atuais e incorporar regressões ao script canônico; o snapshot não segue automaticamente futuras correções.

A escolha calendário UTC versus ciclo efetivamente pago continua uma decisão comercial não fechada. Não marcar um deles como aprovado pelo proprietário sem evidência. Preparar migração/testes, sem aplicar D1 remoto.

Nenhum deploy, alteração da sessão Codex, force-push, configuração de permissões, commit, cobrança ou credencial real foi feito pelo revisor. O Codex permanece como escritor das correções de produto.

## Atualização independente — 19:02–19:04 UTC: testes das correções aprovados localmente

O Codex publicou localmente `27d18c1513f88957182ee9d5638bdb8b9969136b` (cinco PCs). Rodei novamente, por execução independente:

| Teste | Exit | Resultado |
| --- | --- | --- |
| `test_signed_distribution_stage.py -v` | 0 | 12 testes passaram; inclui recusa do candidato sem assinatura e do rollback não explícito |
| `validate_process_terminal_drain.py` | 0 | 19 verificações PTY real passaram |
| `test_device_enrollment_limit.mjs` | 0 | quinto/sexto, não consumo de token, revogação/substituição, tenants, Founder e corrida de dois escritores SQLite passaram |

Os hashes das dez fontes/testes rastreados ficaram iguais antes/depois; o revisor não editou esses arquivos. A suite de distribuição já inclui execução do teste PTY, portanto não somar os totais como testes distintos de cobertura. A prova da corrida é SQLite local, não D1 remoto.

Arquivos desta revisão preservados no clone: `docs/evidence/commander-peer-review-r2-20261020/` (`SNAPSHOT.json`, `peer_results.json`, `peer_existing_tests.json`, harness e README). Ainda sem commit feito pelo revisor; o executor decide como incorporar as evidências.

### Observação de precisão sobre o teste Event V2 ainda em andamento

`test_event_v2_notify_delivery.mjs` usa sockets simulados e não contém D1. Seu log `EVENT_V2_ZERO_DELIVERY_REMAINS_DURABLE_D1_QUEUE=PASS` excede a prova efetivamente produzida. Sugerido: nomear como `ZERO_VALID_SOCKET_DELIVERY=0` e manter `D1_RECOVERY=NOT_TESTED` neste teste; recuperar a evidência hospedada anterior ou adicionar teste integrado que enfileire uma chamada e prove claim/recibo após reconexão. Não é uma nova falha funcional demonstrada no transporte, e sim limite da evidência. O helper novo que ignora sockets superseded e tolera falha de send parece coerente com esse escopo unitário.
