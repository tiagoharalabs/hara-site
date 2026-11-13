# H.A.R.A. Commander — correção P0 da janela de autorização no enqueue 0043

**Data:** 13/11/2026. **Branch:** `local/commander-0043-enqueue-auth-fence-20261113`. **Base:** `6f3d62bf76835690ff06d074277b2f7cce891526`.

## Falha real reproduzida

`enqueueDeviceCall` validava a identidade, o entitlement e o grant em `mcpProductContext`, mas depois aguardava `resolveCustomerTargetDevice` e `resolveCallUsageMode`. A operação D1 `INSERT OR IGNORE` verificava o dispositivo e a capacidade da fila, **não a autorização 0043 no momento da inserção**. Em SQLite com a migration canônica, revoguei o entitlement durante o `await` da resolução de uso: a chamada ainda foi admitida, e o teste falhou com `Missing expected rejection`.

O `claimNextDeviceCall` já contava com `callAuthorizationFence` antes de devolver o payload; esta prova anterior não demonstrou execução de Agent indevida. O defeito demonstrado era **a possibilidade de persistir uma chamada PENDING com credenciais/autorização já revogadas**.

## Correção na fonte do produto

Na função existente `enqueueDeviceCall`, o `INSERT OR IGNORE ... SELECT` recebeu um `AND EXISTS` com linha sintética `auth_call` e **a própria função `callAuthorizationFence("auth_call")`**, reaproveitando o contrato de autorização da migration 0043. Os sete campos necessários são vinculados como parâmetros do D1, sem texto arbitrário de usuário no SQL.

A revalidação ocorre **dentro da mesma declaração SQL que cria a chamada**, e não em outra leitura assíncrona sujeita à corrida. A falha de autorização impede o `INSERT` e não cria novo `PENDING`, nem aciona o Agent. O contrato de idempotência, limite de fila, perfil de aprovação e a barreira existente no `claim` foram mantidos.

## Provas executadas

- **Antes do patch:** o novo teste de revogação de entitlement durante `resolveCallUsageMode` falhou no produto anterior como `Missing expected rejection`.
- **Depois do patch:** `test_approval_async_queue_claim_0043_candidate_20261112.mjs` **26/26 PASS** — cenários de enfileiramento, concorrência, idempotência, Windows approval e sete cenários de autorização tardia: entitlement, identity binding, usuário, plano, grant, expiração e issuer OIDC.
- `test_p0_dispatch_authorization_0043_undelivered_20261112.mjs` **29/29 PASS** — função real de claim, 0043 21→22 colunas, revogações, scrub, falha D1, incerteza de execução e proteção contra duplo dispatch.
- Teste histórico com SHA fixado à versão `777cce...` foi **preservado** como prova histórica; não foi reclassificado como falha atual. Os casos das duas suites não devem ser somados como testes únicos sem análise de sobreposição.
- `validate_0043_atomic_enqueue_20261113.py`: reexecução reproduzível das duas suites e build completo do Worker com Wrangler **`deploy --dry-run` PASS**, sem chamadas ao provedor.
- `audit_0043_atomic_enqueue_20261113.py`: auditoria independente de fonte, migration, testes, hashes e limites, estado `ATOMIC_0043_ENQUEUE_AUTHORIZATION_INDEPENDENT_PASS`.

## Integridade

- Fonte Worker candidata: `c9f4c48e553de133598982018a3fbc19f6fcf9165dfd9ddf1609620da61e8dbc`.
- Migration 0043 original, inalterada: `7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3`.
- Bundle do dry-run: `64e6aaf456d75b1f65f421be7847c57a0c463494235f016eaf11c04b63c0d8df`.
- Recibo QA: `ATOMIC_0043_ENQUEUE_QA.json` SHA-256 `64618c6f9851e30bce70877eee7511f130d4dcd5b4bce897fe1561fa2a901542`.
- Auditoria: `INDEPENDENT_ATOMIC_ENQUEUE_READBACK.json` SHA-256 `ecdf3579eac399680cb471300695b1f3c026581998c3521879eb5bc4082bdd34`.

## Limites e próximos impeditivos

O patch está na **fonte candidata privada**, sem deploy do Worker comercial ou aplicação da migration 0043 em PROD. Nenhum cliente, Agent, segredo, quota real, Stripe ou App OpenAI foi alterado; as operações D1 da QA rodaram em SQLite local sintético.

**P0 global permanece NO-GO:** inventário das instâncias Durable Objects efetivamente ativas e suas gerações/epochs; duas janelas completas de drenagem WSS/RPC/alarmes/filas; snapshots D1/DO/quota/outbox; consumer comercial real da fila e recuperação forward-only sem liberação ou execução duplicada. A homologação E2E das FileTools/Reviewer também continua separada. Não usar rollback ao Worker antigo.

**Resultado:** a janela de enfileiramento com autorização revogada foi corrigida e testada; `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` permanece como trava da comercialização.

## Patch revisável

O diff exato das alterações de Worker e das duas suítes da candidata está em `SOURCE_0043_ATOMIC_ENQUEUE.patch` (SHA-256 `c31162037ee0afc4ea807c42386cf2b78b9532e5d95bb4bf5424928e978cec97`). Ele é derivado da comparação entre `6f3d62bf76835690ff06d074277b2f7cce891526` e o commit de correção `d46b31bfd8a2b81094057c255be9b81d9737f285` e não contém credenciais. Aplicá-lo ao `main` do GitHub Web ou a um Worker hospedado sem reconciliar a linhagem de fonte e seus gates seria incorreto.