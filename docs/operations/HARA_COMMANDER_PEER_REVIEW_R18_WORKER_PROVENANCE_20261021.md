# HARA Commander — R18 | Lacuna de proveniência do Worker durante upload comercial

Data: 21/10/2026 ~06:07 UTC, revisão independente Valky, pelo **H.A.R.A. Commander**. Escopo solicitado: leitura profunda do código e suporte de maior impacto ao Codex, usando **somente Núcleo e Services** como Agents e acesso read-only via Services a Storage/Observer. Não ligar ou acessar como Agent as Sentinelas/Ninja/VM desligadas.

## P0 — o estágio assinado protege assets web, mas não vincula o Worker JS que Wrangler empacota

O Worker do Commander tem `apps/commander/wrangler.jsonc` com `"main": "src/worker.js"`, `"assets.directory": "signed-assets-stage-required"` e `run_worker_first` em rotas API/auth. O script de upload `apps/commander/scripts/commander_versioned_prod_upload.py` (atual em `3a9131785cf74ed5303b7474b4c2cf2d5ebd61a6`) executa `wrangler versions upload --config <config> --assets <snapshot>` com **`cwd=APP` do próprio worktree**.

Os gates `stage_signed_commercial_assets.require_signed_stage()` verificam corretamente 17 arquivos `apps/commander/public/` e comparam `git rev-parse HEAD:apps/commander/public` ao `FROZEN_V5_PUBLIC_TREE`. O commit aprovado é usado como fonte da árvore web, mas **não há verificação equivalente do código `src/worker.js` e das importações empacotadas pelo Wrangler**. A correção anterior R16b protege um **snapshot privado dos assets**, não um snapshot imutável do projeto Worker completo.

### Evidência reproduzida, sem tocar na produção

Criei clone QA isolado `/tmp/hara-commander-r18-worker-drift-20261021` do commit `3a9131785cf74ed5303b7474b4c2cf2d5ebd61a6`. O script `peer_worker_code_bound.py` executa as funções reais `stage()`, `require_signed_stage()` e `upload_version()` com **bundle v4 histórico assinado somente como controle local**. Wrangler é substituído por leitor mock, sem rede.

1. Estágio assinado/assinado historicamente passa: árvore pública Git `2138ef35e0f9bee92888e1bcf7bb5212956170bd`, digest de stage `e3f5ce730a7a640d71c41c062315497d20b6fc292f1188c0885d88d8f6653448`.
2. Modifiquei **apenas a cópia QA de `apps/commander/src/worker.js`** (acrescentei uma linha sintética, restaurada no `finally`). SHA-256 Worker antes `df910bb6dfa5c710250232079be2dd4b23e8bec731a31a6ae257fd4968e0bd71`; depois `e4ac6556c6607b1d0062703eeb79494a859d3e90f11bd89c365ea14c63d98d15`.
3. `upload_version(...,execute=False)` respondeu **`VERIFIED_NOT_UPLOADED`** apesar da modificação do Worker. O mock uploader, invocado por `upload_version(...,execute=True)`, leu o Worker modificado e retornou sucesso. O script devolveu **`UPLOAD_SUBMITTED_VERSION_READBACK_REQUIRED`**.
4. A verificação de estágio não identificou a diferença, porque seu digest considera apenas os assets públicos. O Worker QA foi restaurado e o clone do Codex não foi alterado.
5. `peer_worker_code_bound.py` saiu **2 = bug de gate reproduzido**, não aceite PASS. Arquivo de resultado: `r18-worker-source-gate-results.json`.

**Escopo honesto:** a prova demonstra a aceitação da **fonte Worker não revisada na fronteira do upload local**, sob uploader fake. Não executamos o Wrangler real, não fizemos upload Cloudflare nem temos evidência de uma versão produtiva divergente. Uma alteração de `src/worker.js`/dependências pode, entretanto, alterar a versão que Wrangler empacota independentemente de uma árvore web estática assinada. Dado o objetivo comercial, tratar como **P0 de supply chain** antes de autorizar upload.

### Correção mínima e critérios de aceite para Codex

- Vincular o upload a **identidade de fonte revisada e congelada** que inclua `apps/commander/src/**`, `apps/commander/wrangler.jsonc`, imports transitivos e dependências resolvidas do bundle (incluindo lockfile/toolchain); não confiar apenas em `HEAD:apps/commander/public` ou `git status` pontual.
- Materializar um **snapshot de todo o projeto Worker** aprovado, com stage dos assets assinado, fonte JS/config e dependências fixadas; invocar Wrangler com `cwd` e `--config` desse snapshot e não do checkout ativo do Codex. Garantir serialização/imutabilidade por toda a janela de leitura do uploader, como na correção R16 para assets.
- Pré-gate deve falhar **antes de qualquer chamada Wrangler** se Worker ou config divergir do commit/hash liberado. Testar alterações transitórias do Worker durante upload: nenhum upload pode alegar versão verificada a partir de conteúdo não aprovado. O post-gate precisa manter `UPLOADED_VERSION_READBACK_REQUIRED` até a versão Cloudflare ser conferida por identificador e artefatos/smoke API compatíveis.
- Se o worker não puder ser criptograficamente validado por readback dos bytes publicados, manter `WORKER_VERSION_PROVENANCE=UNVERIFIED` e **não chamar a promoção de plenamente qualificada** só por 15 GETs de arquivos estáticos.
- Anexar plano de compatibilidade da migração D1 e autenticação/tenant, considerando que `wrangler.jsonc` aponta para PROD. Não tentar migração/assinatura/versão hospedada nesta revisão.

### Não refazer frentes encerradas

R11/R13 instaladores e recuperação de ACK, R14 portabilidade Fedora x86_64/Ubuntu ARM64 (24 casos QA), R15 congelamento do pacote público **0.3.43** (SHA `3ade217145e32899da47bedb43272897ee020e44658ae2b197b0eda61880970d`) e R16 assets/upload snapshot já passaram localmente. R17 de allowlist de erros públicos Full/Simple foi entregue como P1 separado. **R18 é lacuna distinta: proveniência do Worker em runtime, não integridade dos assets web.**

O site comercial **continua HOLD**: falta assinatura oficial v5, stage validado por custodiante, readback de versão Worker+web, canário com rollback e instalação comercial limpa em Storage/Observer. Nada foi publicado, instalado ou reiniciado por esta auditoria.

## Disponibilidade e energia observadas

- HARA Commander `ping(nucleo-a)` e `ping(services)` PASS, ambos Agent 0.3.54.
- `storage` Fedora 43/x86_64 e `observer` Ubuntu 22.04/aarch64 acessíveis via SSH read-only a partir do Services, sem Agent Commander principal nem `device.env`.
- Registry do Commander conserva entradas de máquinas desligadas e alguns checkpoints possivelmente antigos. Não inferir que Sentinela A esteja energizada apenas porque registry diz ONLINE; proprietário explicitou apenas Núcleo/Services/Storage/Observer ligados.
- Não acordar, ligar, desligar nem atualizar qualquer host nesta frente.

**Entregas:** script QA reproduzível, JSON de resultado, SHA256SUMS, relatório e fila Codex enxuta. O código de produto segue inteiramente sob autoria do Codex.
