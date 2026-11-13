# H.A.R.A. Commander — correção da ordem de contenção WebSocket em Cloudflare QA

**Data:** 13/11/2026. **Branch:** `local/commander-p0-prefence-wss-hosted-20261113`. **Base:** `cb967b5939d26c2cde68ab89bf3e1ac46927916f`.

## Resultado hospedado novo

**`CLOUDFLARE_EXACT_DO_PREFENCE_WSS_1012_PASS`**. Worker temporário e isolado `hara-commander-p0-prefence-wss-qa-20261113`, usando o Worker do produto compilado com SHA-256 `049240c088942fe732ab25db37d8620a84cc6801008611967c09cc242fb36657` da fonte SHA-256 `9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260`.

A ordem operacional foi corrigida: **cercar a instância com código FORWARD ainda ativo antes de implantar a versão CONTAINMENT**. Uma conexão WSS hospedada recebeu o ACK nativo, foi testemunhada como `websockets=1`, e o endpoint autenticado chamou a função original `DeviceChannel.enterCutoverFence(epoch)` antes de qualquer novo deployment. O cliente recebeu **fechamento real `1012` com motivo `DO_CUTOVER_FENCED`**. O testemunho imediatamente após a cerca confirmou `websockets=0`, `local_drained=true`, nenhum alarme pendente e o mesmo epoch.

Depois da confirmação do 1012, uma versão de contenção compatível foi implantada no MESMO Worker/namespace de QA: versão `b2841d77-b68d-4609-982b-c810f0abe339` a 100%; o fence permaneceu persistente, e novas conexões WSS foram rejeitadas com **HTTP 503**.

**Fechamento verificado diretamente na Cloudflare:** `workers.dev` e previews desabilitados, zero Cron Triggers, acesso temporário eliminado. A versão comercial continuou `12fe1bb3-4c8c-4a37-9793-54bb4525556e` a 100%, sem deploy ou migration PROD. Auditoria autenticada independente: `EXACT_FORWARD_PREFENCE_WSS_1012_HOSTED_INDEPENDENT_PASS`.

## Diferença em relação ao teste anterior

O QA `commander-p0-exact-hosted-20261113` anterior tentou confirmar o encerramento WSS **depois** de trocar de versão; um cliente que recebera ACK permaneceu aberto até atingir `QA_WSS_TIMEOUT`, portanto 1012 não foi provado. A nova prova elimina essa lacuna **somente para a transição de um DO que JÁ executa o código com `enterCutoverFence`**.

## Impeditivo que continua P0

**A imagem LEGACY comercial exata** SHA-256 `32cd16b19b86fe00711c0fca1cc1102a75026cc191bb5238af5e33a3bde3828e` possui callback WebSocket mas **não contém `enterCutoverFence`**. A imagem nova contém a função. Portanto, a prova FORWARD→CONTAINMENT não resolve automaticamente a primeira transição LEGACY→código compatível: é necessário autenticar geração/epoch, estratégia de atualização, tratamento de WSS antigo e efeitos incertos nesta ponte, com inventário vivo e snapshots.

O mecanismo de atualização de Durable Objects permite coexistência temporal entre código anterior e novo; WebSockets hibernados podem sobreviver a atualizações. HTTP 503 e deployment 100% por si sós não atestam quiescência.

**Não declarar GO comercial:** ainda faltam todas as instâncias ativas, duas janelas globais temporizadas, Quota/Queue/Alarm/RPC e snapshot DO/D1/outbox consistente, recuperação forward-only, consumer comercial 0043, OAuth/Reviewer/FileTools e Stripe LIVE.

## Artefatos

- `apps/commander/qa/p0-prefence-wss-20261113/entry.mjs`: adaptador de QA autenticado, somente status, witness, fence e WSS. Nenhum endpoint de clientes, Cron ou Queue.
- `apps/commander/scripts/test_p0_prefence_wss_20261113.mjs`: cliente WSS que registra ACK, fechamento e rejeição HTTP.
- `apps/commander/scripts/run_p0_prefence_wss_hosted_20261113.py`: cria e fecha apenas o Worker QA whitelisted, usa exclusivamente D1 sintético pré-existente, destrói a chave de teste, preserva a versão comercial e gera recibo write-once.
- `apps/commander/scripts/validate_p0_prefence_wss_hosted_20261113.py`: valida recibos, hashes, versões, ingresso fechado e zero agendamentos diretamente na Cloudflare.
- `PREFENCE_WSS_CLOUDFLARE_QA.json` SHA-256 `822b33864d8fd732d000ef5dd9585a105d5562adb03635534d8b388b7664242d`.
- `INDEPENDENT_PREFENCE_WSS_READBACK.json` SHA-256 `4b61afc56a98a40cab6fec809796baee097ac34807fa0573aeaaaf54c29f79a8`.

**Escopo de mutação:** exclusivamente Worker e instâncias DO de QA recém-criados e possível atualização do estado do dispositivo sintético no D1 de QA. Nenhum cliente, Agent, credencial comercial, segredo Stripe, Worker PROD, App, migração comercial, branch `main` ou cobrança real foram afetados.

**Próximo ensaio real:** reproduzir LEGACY→bridge novo com WSS previamente conectado e estratégias explícitas de atualização, provar quiescência/contabilização de efeitos e só então usar o pré-fence comprovado antes de containment e 0043.