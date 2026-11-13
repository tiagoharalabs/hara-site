# H.A.R.A. Commander — Teste da cobertura por instância nas três Durable Objects reais

**Data:** 13/11/2026. **Branch privada:** `local/commander-do-manifest-runtime-qa-20261113`. **Base:** `dcfe17937a314431a71c2634a0b8fed0ac61187d`.

## Entrega e resultado

- **11/11 cenários reais do Worker em workerd/Miniflare PASS**, com `TenantQuota`, `DeviceChannel` e `SecurityRateLimit` originais, D1/DO SQLite isolados e fontes pinadas por SHA.
- **22/22 negativas** de evidência e manifesto recusadas: falta de ator, classe trocada, epoch e geração divergentes, nonce repetido, janela de tempo insuficiente, callback/presença/WSS/alarmes pendentes, alteração de unidades protegidas e alegação indevida de quiescência global.
- **4 instâncias sintéticas conhecidas:** 2 `TenantQuota`, 1 `DeviceChannel` e 1 `SecurityRateLimit`, observadas sob o mesmo epoch. A cerca persistiu após reinício real do runtime local.
- **2 unidades de quota protegidas** permaneceram íntegras; `DeviceChannel` recusou novo efeito após fence; `SecurityRateLimit` não concedeu nova permissão após fence.
- Duas observações locais têm **8 nonces distintos** e intervalo positivo medido no recibo (centenas de milissegundos). Elas **não equivalem** às duas janelas globais temporizadas exigidas para produção.
- Um **quinto DO propositalmente não registrado** continuou recebendo efeitos de teste. Isso demonstra por execução que completar somente um manifesto conhecido NÃO prova cobertura de todas as instâncias.

**Estado final:** `REAL_PRODUCT_DO_MANIFEST_11_AND_22_NEGATIVES_PASS_GLOBAL_HOLD` (auditoria independente), `commercial_cutover_authorized=false`.

## Artefatos versionados

- `apps/commander/qa/p0-manifest-runtime/manifest-gate.mjs`: verificador puro do manifesto conhecido e dos testemunhos por epoch, geração, nonce, estado de canal e unidade protegida; não é orquestrador, endpoint nem serviço novo.
- `apps/commander/scripts/test_p0_real_do_manifest_20261113.mjs`: ensaio das três classes originais dentro do workerd; possui regressões e caso negativo da instância não registrada.
- `apps/commander/scripts/run_p0_real_do_manifest_20261113.py`: faz build do Worker original por Wrangler **`--dry-run`**, testa em diretório temporário com egress bloqueado, apaga o armazenamento e grava recibo write-once.
- `apps/commander/scripts/validate_p0_real_do_manifest_20261113.py`: readback independente de fontes e resultados.
- `docs/evidence/commander-p0-real-do-manifest-20261113/REAL_DO_MANIFEST_WORKERD_QA.json`: recibo completo com hash do Worker compilado, casos PASS e limites.
- `docs/evidence/commander-p0-real-do-manifest-20261113/INDEPENDENT_DO_MANIFEST_READBACK.json`: auditoria independente e SHA dos artefatos.

## Fontes e isolamento

Worker candidato `worker.js` SHA-256 `9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260`.

Migration 0043 SHA-256 `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3` (não aplicada em PROD).

**Não foram alterados:** Worker candidato, migration, Agent, FileTools, D1 Cloudflare comercial ou QA, recursos Stripe, permissões, App OpenAI, GitHub `main` ou repositório canônico. O teste NÃO contactou Cloudflare; usou Workerd local com software real e dados sintéticos, sem credenciais e sem tráfego externo.

## Estado hospedado anterior a preservar

O readback autenticado anterior confirmou 72 DOs persistidos comerciais e 4 de QA (seis namespaces), Worker comercial `12fe1bb3-4c8c-4a37-9793-54bb4525556e` a 100%, D1 comercial com 21 colunas e D1 QA com 22, e Cron temporário de reparação removido. Essas contagens ainda não abrangem todas as instâncias ativas sem storage.

## Próxima aceitação P0 necessária

1. Desenvolver e autenticar registro **exaustivo das instâncias ativas**, com geração e epoch por instância das três classes, sem vazar nomes/IDs em relatórios.
2. Executar em **Cloudflare QA hospedado** duas janelas independentes, de duração apropriada e com observações de WSS, alarmes, RPCs, Queue, efeitos e reservas por objeto; tratar qualquer ator ausente como HOLD.
3. Vincular snapshots D1/DO/quota/outbox e consumer real da fila 0043 à mesma geração e testar recuperação compatível/retorno forward-only.
4. Só então propor migration 0043 e atualização de FileTools em DEVELOPMENT, sem rollback para o Worker legado.

**Critério comercial:** `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` permanece; a nova prova NÃO libera produção.