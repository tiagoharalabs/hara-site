# H.A.R.A. Commander — baseline obrigatória antes de corrigir a fila 0043

**Data:** 13 de novembro de 2026.
**Etapa:** `PRECHANGE_RECORDED` — levantamento e custódia, **não homologação comercial**.
**Branch isolada:** `local/commander-0043-prechange-ledger-recovery-20261113`
**Commit base:** `e4b9b9e9fc134059b55922afc822e7f38e1f6970`

## 1. Evidência obtida ANTES de alterações

- Services e Storage responderam a `ping` do H.A.R.A. Commander Primary, Agent `0.3.83`.
- O worktree original `commander-0043-enqueue-auth-fence-20261113` está limpo na base acima.
- O Storage Working Mirror registra exatamente esse commit na branch base; `Storage Canonical/main` continua independente em `e739605a8abdcb617b63f5e7f97690229366cccb`.
- `apps/commander/src/worker.js` SHA-256 **`c9f4c48e553de133598982018a3fbc19f6fcf9165dfd9ddf1609620da61e8dbc`**.
- `apps/commander/migrations/0043_device_call_authorization.sql` SHA-256 **`7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3`**, sem alteração.
- `apps/commander/src/undelivered-claim-repair.mjs` SHA-256 **`83b1616f44803014ffe1caccb051aff3c338dc9bd17133cdf8396325dd541cc4`**.
- `apps/commander/src/device-channel.mjs` SHA-256 **`038025cdb9ca76fd992b828e2bdcbe623447014102f1d421469698d9380b6779`**.
- `apps/commander/src/recovery-fanout.mjs` SHA-256 **`c906934d3bedba1dddf2eee3d475e1cc16b4ebbdd016ea9bccc823c7b22b523e`**.
- Cloudflare GET autenticado: Worker comercial `hara-commander` permanece na versão **`12fe1bb3-4c8c-4a37-9793-54bb4525556e`**, 100% de tráfego (deployment criado em 09/11/2026 23:23 UTC). Leitura não executou mutations.
- A fonte candidata não está equiparada por SHA à implantação comercial. A evidência anterior indica D1 PROD 21 colunas e QA 22 após migração 0043. Essa informação de esquema é histórica até novo readback, **não um novo testemunho desta coleta**.

## 2. Separação das duas filas e das autoridades

**Fila de chamadas de dispositivos/ledger 0043:** `enqueueDeviceCall`, `claimNextDeviceCall`, `completeDeviceCall`, `acceptedCallStatus` e `undelivered-claim-repair.mjs`. A chamada PENDING/EXECUTING pertence a um tenant, sujeito, dispositivo e versão de autorização; execução pode produzir efeito irreversível no Agent. Qualquer incerteza exige retenção da reserva, redaction comprovada e reconciliação; **nenhum retry automático de efeito incerto**.

**Fila de alertas de recuperação #163:** `recovery-fanout.mjs`, `enqueueRecoveryWork`, `consumeRecoveryWork`, `recovery_delivery_outbox` e o esquema de jobs SCAN/DELIVER. Os patches anteriores eliminam falsos `COMPLETE` e ACK sem entrega na **fonte candidata**, mas isso não equivale a homologar o consumer comercial do ledger 0043. Não misturar percentuais de conclusão.

## 3. Testemunhos históricos já existentes, sem promover suas conclusões

- Em workerd/SQLite, migration 0043 original (21→22) e reparação idempotente tiveram 13/13 casos na rodada registrada em `f551046f`.
- O Cron de reparação hospedado de QA foi comprovado, com agendamento temporário desativado e 0 schedules no último readback conhecido, conforme `9725e212`.
- O ensaio hospedado integrado do Worker com Queue nativa de QA, WSS e alarmes está documentado, porém usa **adaptador de Queue QA**, não consumer comercial.
- A correção de autorização de enqueue revalida `callAuthorizationFence(auth_call)` **no INSERT atômico**, com 26 testes de enqueue e 29 de claim na fonte atual; recibo e auditoria já estão preservados em `e4b9b9e9`.
- O censo anterior de 72 objetos persistidos comerciais e 4 QA **não** prova todos os DOs vivos, gerações efetivas ou duas janelas globais de quiescência.

## 4. Hipóteses a investigar — não declarar defeitos sem reprodução

A. **Expiração de chamada EXECUTING:** a manutenção `cleanupExpiredDeviceCalls` marca calls vencidas e depois redige conteúdo; verificar se uma chamada com efeito incerto sempre preserva quota/reserva e não permite segundo dispatch.

B. **Conclusão concorrente:** `completeDeviceCall` altera estado D1 antes da liquidação de quota em DO; simular falha de D1/DO, duplicatas e revogação na fronteira, atestando recuperação idempotente e ausência de liberação prematura.

C. **Consumer comercial 0043:** identificar a implementação concreta e seu vínculo com Queue/WSS/RPC. Não inferir que `consumeRecoveryWork` entrega chamadas 0043.

D. **DO ativo + snapshots:** a enumeração de objetos com storage é um limite inferior, não manifesto exaustivo. Exigir testemunhos por instância/epoch e snapshots correlacionados de D1, DO quota, outbox e calls.

## 5. Procedimento de resolução (obrigatório)

1. **Baseline prévia:** relatório, hashes e riscos documentados em branch isolada, commit limpo e readback no Storage, ANTES de alterar fonte.
2. Criar reprodução falhando sobre a função **real**, com SQLite/migration 0043 em QA e dependências sintéticas, sem chamadas externas.
3. Aplicar correção mínima; conservar endpoint, assinatura da função, entitlements, tenancy, idempotência e estado das reservas incertas.
4. Executar testes negativos e positivos, validação independente, build Wrangler `--dry-run`, comparação de hashes e checagem de padrões de segredos.
5. Gerar recibo write-once distinguindo `PASS_LOCAL`, `PASS_HOSTED_QA`, `HOLD`, `UNKNOWN`; não transformar exceção ou evidência ausente em aprovação.
6. Commit em branch separada no Services → push para **Storage Working Mirror** → readback de SHA/arquivo/recibo no próprio Storage.
7. Publicar o diff e os documentos na branch **GitHub Web draft** correspondente. Se a origem privada não estiver no `main` Web, **não misturar a linhagem nem fazer merge automático**.
8. Somente com aceite de snapshots e recuperação compatível, e decisão documentada de owner, considerar migration PROD, deploy, FileTools DEVELOPMENT e comercialização.

## 6. Limites de autoridade

Nesta fase são permitidas leitura de Cloudflare/D1, criação de arquivos de evidência, commits locais, push para Storage e publicação de QA em GitHub Web. Testes com dados sintéticos e build seco são permitidos. **Proibido sem novo gate técnico de aceite:** migration comercial, alteração de PROD, replay/ACK de chamada real, liberação de reservas incertas, alteração de segredos, Stripe LIVE, revogação/pareamento de Reviewer ou publicação do App OpenAI.

**Estado de lançamento:** `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN / NO_GO`.

**Próxima ação técnica:** teste isolado da expiração/reconciliação e/ou consumer comercial, mantendo a migração original e as quotas produtivas intactas.