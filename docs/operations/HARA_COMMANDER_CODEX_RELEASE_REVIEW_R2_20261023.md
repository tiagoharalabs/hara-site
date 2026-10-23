# H.A.R.A. Commander — revisão do kit e apoio ao Codex — R2 (2026-10-23)

**State:** `HOLD_PUBLIC_RELEASE`. Este é um handoff de revisão **somente leitura e testes locais**. Não substituir o worktree WIP do Codex; não mexer nas duas VMs de revisão, em chaves, no signer, nas credenciais, em D1, na frota nem na Cloudflare.

## Fontes e owners efetivamente consultados

- Kit histórico: `docs/handoffs/HARA_COMMANDER_CURRENT_KIT_20260924.md` e `docs/status/HARA_COMMANDER_DISTRIBUTION_KIT_CURRENT_20260923.md` — **desatualizados** para versões/releases atuais. Não usar seus valores 0.3.7/0.3.2 como baseline vigente.
- Kit atual: `docs/operations/HARA_COMMANDER_LATEST_COMMERCIAL_SOURCE_GAP_20261023.md` (commit `32c874a415f2bd655d5e80fa3d95d367cc546139`), `docs/handoffs/HARA_SITE_RELEASE_FLOOR_R3_20261022.md`, `docs/handoffs/HARA_COMMANDER_INSTALLER_ANTI_ROLLBACK_R4_20261022.md`.
- Referência externa: hara-site [issue #310](https://github.com/tiagoharalabs/hara-site/issues/310) (owner comercial) e hara-site [issue #240](https://github.com/tiagoharalabs/hara-site/issues/240) (Windows aceite), [PR #321](https://github.com/tiagoharalabs/hara-site/pull/321) (draft 0.3.54 Linux).
- Worktree ativo **de outra frente Codex** em Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-public-release-repair-20261023`, branch `local/commander-public-release-repair-20261023`. Possui três arquivos WIP **untracked**: `apps/commander/scripts/commander_public_release_gate.mjs`, `test_public_release_gate.mjs` e `.github/workflows/hara-commander-public-release-guards.yml`. **Não editar/copiar sobre o WIP.**

## Prova pública mais recente

Em `2026-10-23T06:54:52Z`, o GET HTTPS ao Commander pelo Services e o gate Python somente leitura entregaram:

```text
MANIFEST_VERSION=0.3.41
LINUX_AGENT_VERSION=0.3.43
WINDOWS_AGENT_VERSION=0.3.52
MANIFEST_SIGNATURE_RS256=true (assinatura válida sobre o manifesto ANTIGO)
PUBLIC_ASSETS_SHA_AND_SIZE_MATCH=0/4
CROSS_PLATFORM_PARITY=false
PUBLIC_RELEASE_GATE=HOLD
RELEASE_GATE_EXIT=5
```

SHA público do manifesto: `7e42f25404e414b74b375ccb47b7ed8ba7d8c572dc45db994d89012207f08f7c`. Os hashes dos quatro arquivos e a RCA causal estão no handoff `docs/operations/HARA_COMMANDER_PUBLIC_SIGNED_INSTALLER_BLOCKER_R1_20261023.md` e [comentário #310](https://github.com/tiagoharalabs/hara-site/issues/310#issuecomment-6357290390).

## Revisão independente do novo gate Node da frente Codex

`node --test apps/commander/scripts/test_public_release_gate.mjs` no WIP retornou **29/29 PASS** em testes sintéticos sem release real. A conferência contra o contrato real identificou:

### 1. Bug comprovado: recusa manifesto comercial de quatro arquivos
`commander_public_release_gate.mjs` exige `manifest.files.length === PATHS[platform].length` (2). O formato atual `hara.commander-agent-release.v1` carrega **quatro** arquivos (`agent/linux.py`, `agent/windows.ps1`, `install/linux.sh`, `install/windows.ps1`).

Foi gerada uma **fixture sintética efêmera** com assinatura RSA correta, versão `0.3.55`, quatro arquivos, chave temporária com pin controlado pelo próprio teste. Resultado real em ambas as plataformas:

```text
linux   -> COMMANDER_PUBLIC_RELEASE_HOLD_PLATFORM_FILESET
windows -> COMMANDER_PUBLIC_RELEASE_HOLD_PLATFORM_FILESET
```

Reprodutor local em `~/.local/share/hara/codex-inbox/HARA_COMMANDER_CODEX_GATE_REAL_CONTRACT_REPRO_R1_20261023.mjs`. **Não é um release comercial assinado**, é um teste de contrato/forma. Incorporar fixture positiva de 4 arquivos ao teste do Codex antes de promover.

### 2. Chave de assinatura incompatível com bundle v2 existente
O gate Node fixa `KID='commander-release-v1'`, enquanto o bundle comercial histórico coerente `commercial-0.3.43-v3` tem `KID=commander-release-v2` com outra chave. O `public_bundle_gate.py` vigente usa **pin RSA público independente v2**, não JWK baixada como trust root. Resolver por uma política de chave aprovada e pinada (sem `allow any key`), preservando a identidade do signer. O documento do kit 32c874a já relatava esse defeito.

### 3. Coverage: novo workflow Node não executa na alteração dos próprios assets
A nova `.github/workflows/hara-commander-public-release-guards.yml` inclui em `pull_request.paths` **somente**:

```text
apps/commander/scripts/commander_public_release_gate.mjs
apps/commander/scripts/test_public_release_gate.mjs
.github/workflows/hara-commander-public-release-guards.yml
```

Não inclui `apps/commander/public/agent/**`, `public/install/**`, `public/release/**`, `apps/commander/release-bundles/**` nem stage/selection. O job roda somente 29 fixtures e não valida os assets reais. **Distinção importante:** o workflow Python já existente `hara-commander-release-floor.yml` cobre `apps/commander/**` e executa `stage_public_commander_assets.py --check-selection`; não confundir a falha do novo workflow com ausência total de CI.

### 4. Deploy ainda não usa diretório validado
`scripts/public_release_selection.json` tem `bundle: null`, e `scripts/public_bundle_gate.py` traz `APPROVED_PUBLIC_MANIFEST_SHA256=""`; são **HOLD intencionais**, não preencher artificialmente.

Comandos somente leitura no kit atual `commander-latest-release-reconcile-20261023`:

```text
python3 -I -B scripts/stage_public_commander_assets.py --check-selection
  -> HOLD_PUBLIC_STAGE / PUBLIC_RELEASE_NOT_SELECTED / EXIT 2

python3 -I -B scripts/test_stage_public_commander_assets.py
  -> 5 tests PASS

python3 -I -B scripts/test_public_bundle_gate.py
  -> 15 tests PASS
```

O `package.json` ainda contém `"deploy":"wrangler deploy"`; `wrangler.jsonc` lê `assets.directory: "public"` diretamente. Logo a validação do stage não é uma garantia sobre bytes que o Wrangler efetivamente sobe. Exigir um fluxo específico de release que faça: **select reviewed signed bundle → stage atomic exact assets with current UI → verify exact stage → candidate Cloudflare 0% from EXACT stage → GET/readback/hash → controlled traffic promotion + rollback**. Não reescrever o deploy geral da UI de outra frente às cegas.

## Ordem de desbloqueio que evita retrabalho

1. Release owner/admissão deve fornecer Agent Linux/Windows **comercial, atual, genérico**. Linux Founder `0.3.54` device-bound não é um pacote público; Windows `0.3.55` interno não é por si só lançamento comercial. `0.3.43-v3` é histórico. Não renumerar código antigo nem enfraquecer pisos Linux .54 / Windows .55.
2. Codex corrigir no WIP o contrato de **quatro** arquivos e seleção de chave *independentemente pinada*; incluir fixture positiva de 4 arquivos e negativos para downgrade, origem privada, assinatura e drift.
3. Codex integrar corretamente CI de ativos e stage, sem trocar a pasta raiz de UI produtiva sem guardas. Testar PowerShell nativo Windows e Linux, pares de Agent, assinatura RSA, capacidades e retenção de autorização.
4. Só depois autorizar assinatura com signer custodiado, admit/rollback, prévia 0%, promoção e leitura remota exata. Até lá `PUBLIC_RELEASE=HOLD`.
5. **VMs de revisão na Sentinela B pertencem a outra frente**, conforme ordem atual do proprietário. Não bootar, desligar, instalar Agent ou alterar redes a partir desta revisão.

## Entrega/encaminhamento

Fornecer esta análise ao owner da issue hara-site#310 e à frente Codex, sem merge no WIP. Tests local/pass aqui não equivalem a primeira instalação do cliente, liberação da OpenAI ou release pública.