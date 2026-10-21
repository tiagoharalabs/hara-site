# H.A.R.A. Commander — R19 | Release comercial v5 assinado e homologado offline

**21/10/2026 — revisão e execução via H.A.R.A. Commander (Núcleo A), com Services/Storage/Observer por SSH autenticado.** Escopo original: fechar o P0 de distribuição comercial sem o Codex. Não acordar as demais máquinas e não sobrescrever worktrees ativos.

## Estado verdadeiro

**Pacote v5: `SIGNED_OFFLINE_VERIFIED`; estágio de publicação: `PASS`; cloud PROD: ainda NÃO publicado.** Não chamar o ponto 1 de encerrado na web até readback dos endpoints e uma instalação comercial limpa. O gate de assinatura antes pendente foi resolvido com a autoridade v2 oficialmente custodiada no Services, sem exportar a chave privada nem assinar um manifesto diferente do congelado.

### Hashes imutáveis e chaves

- Fonte unsigned congelada do Codex: `apps/commander/candidate/commercial-0.3.43-v5-terminal-drain-unsigned-a13b4d2.tar.gz`, SHA-256 `3ade217145e32899da47bedb43272897ee020e44658ae2b197b0eda61880970d`.
- Manifesto original do release `0.3.43`: SHA-256 `2ec2b3ccddc0fbc5edb577c926315358dbcb558812d3492ec9a68894038ff381`.
- Assinatura oficial RSA-3072/RS256, `kid=commander-release-v2`: SHA-256 do arquivo público `6286b3ce8c453602b4b17ffa0b9ea547239cf8b5341cdc10aaf9e09aa56addcb`.
- Fingerprint do trust anchor público v2: `93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`.
- Signed eight-file archive da distribuição: SHA-256 `08ad0115c440a64911c305aa383f8baf14137cce40c96835fb58d4dae0d7a7f5`.
- Os 7 arquivos originais da distribuição permaneceram idênticos ao tar congelado; apenas `release/agent-manifest.sig.json` foi acrescentado. Quatro assets (Linux/Windows Agent e instalador) conferidos byte a byte com o manifesto.
- A chave privada permaneceu no Services em `~/.config/hara-commander-release/v2/`, com proprietário `sartorius`, permissão `0600`. Foi usada localmente pelo processo de assinatura, sem saída de `d,p,q`, sem SCP/exportação de JWK privado.

## Processo de assinatura — evidência, não publicação

O script `apps/commander/scripts/commander_sign_frozen_v5_services.py` fixa o SHA do tar, o SHA do manifesto e a raiz de confiança. Recusa arquivo alterado, diretório de assinatura existente, trust root incompatível, modo inseguro da chave ou assinatura pré-existente. O `prepare` usou tar imutável e saiu `PREPARED_UNSIGNED`. O `sign` no Services saiu `SIGNED_OFFLINE_VERIFIED`, seguido de `verify` independente. O pacote continua preservado no Services sob:

`/tmp_hara/hara-commander-v5-official-signed-20261021/`

O bundle **somente público** (8 arquivos) foi copiado de volta para a **branch isolada de revisão**, na pasta:

`apps/commander/release-bundles/commercial-0.3.43-v5-terminal-drain/`

`verify_signed_distribution.verify_bundle` retornou `RS256_RSA3072_VALID` e `stage_signed_commercial_assets.py --check` saiu `0` com `COMMANDER_SIGNED_ASSET_STAGE=PASS`.

## Provas reais de portabilidade assinada

Os testes executados diretamente em hosts reais usam somente o bundle **público** e o verificador do produto, com arquivos temporários, sem cadastro nem instalação:

| Host | Runtime | RSA-3072/RS256 | Quatro hashes | Sintaxe Linux |
| --- | --- | --- | --- | --- |
| **Storage** | Fedora 43 / x86_64 / Python 3.14.4 | PASS | 4/4 | Bash/Python PASS |
| **Observer** | Ubuntu 22.04 / aarch64 / Python 3.10.12 | PASS | 4/4 | Bash/Python PASS |

Evidências `storage-signed-verify.json` e `observer-signed-verify.json`. As 24 regressões anteriores de pré-cadastro/lost ACK nos hosts (R14) foram homologadas em fixture local; **nenhum clean install real foi realizado**.

Nove regressões funcionais do Agent Linux **0.3.43 v5 congelado** passaram (drenagem pós-exit, saída contínua, paginação one-shot, sessões, outbox, envelope, CAS, relay burst, montagem/recursos). Estas corrigem o limite funcional da v4 histórica; **não recomendar rollback comercial automático para v4**.

## Worker compilado e proveniência R18/R17

A fonte do Worker **não** está coberta pela assinatura dos 4 assets; a correção R18 fecha a lacuna operacional local:
- `commander_frozen_worker_source.py` extrai código `src/`, config Wrangler e package/lockfile **do commit Git fixado**, nunca do checkout vivo. Executa `npm ci --offline --ignore-scripts` e valida Wrangler 4.85.0 com lockfile imutável, diretório privado e digest da fonte.
- Nova identidade Worker após correção de privacidade R17: commit `c90907c6bd41d56411466542e01a3224538b76c1`, árvore `src` `f9afa5a4611cda6c6d87074bf8923574a9d0c6cd`, digest de arquivos materializados `b0141272657373e0598e986e32f56d5f55e1bf6238a7dd058a4e4440a3f2522f`.
- `commander_versioned_prod_upload.py` nesta branch só usa Wrangler em **snapshot privado com esse código e esses dependencies**. Conserva a regra original de `OUTCOME_UNKNOWN` após erro/timeout e não reenvia mutações automaticamente.
- **12/12 testes** de upload/status/SHA/snapshot e **61/61 regressões MCP** (Full 11, Simple 40, allowlist R17 10) passaram na branch de revisão. O `wrangler deploy --dry-run` com unsigned v5 + Worker revisado gerou `worker.js` (~1,743 MB) sem rede/prod, SHA `40696f94c52577faceb390f84345cf32ffaae02aebb0376e71645fe59853a9c4` — build local, NÃO prova da versão hospedada.
- A allowlist compartilhada em `public-mcp-error-codes.mjs` impede eco de códigos desconhecidos com aparência de credenciais nos perfis Full/Simple, preservando os códigos públicos tipados.

## Estágio pronto, upload ainda não executado

O stage completo foi criado no Núcleo e preservado em:

`/tmp_hara/hara-commander-v5-signed-stage-p1-20261021`

`stage_signed_commercial_assets.py --verify-assets` passou, com **17 arquivos públicos rastreados**, digest `4d22a2943f872d50492a2133ec9dd02aef43978c40357c93dcaa98d1a72e3c65` e Git public tree `2138ef35e0f9bee92888e1bcf7bb5212956170bd`. O wrapper de upload sem `--execute` retornou `VERIFIED_NOT_UPLOADED` / `cloud_operations=false`.

**Não executar `wrangler deploy` diretamente.** Depois de autorização explícita de upload/versionamento, usar o wrapper novo da branch revisada com stage, digest e public tree fixados. O `--execute` criará versão Cloudflare, mas **não prova seu conteúdo e não autoriza distribuição de tráfego**.

## Baseline de produção e gates faltantes

O Wrangler no Services foi consultado **somente em leitura**. Na última checagem, o deployment 100% de `hara-commander` tinha versão `99a19edb-d2cf-4806-8c98-861e4513a2f7` e deployment `65406da5-6c8e-41df-b025-89e68d8fbba4`. O comando de inventário já havia mostrado outro ID em consulta anterior; por isso **revalidar deployment atual imediatamente antes de qualquer operação mutante**. Não interpretar listagem histórica como garantia de versão atual persistente.

Último GET público independente permaneceu **HOLD**: manifesto servido 0.3.41 com assinatura `commander-release-v1`, instalador Linux exigindo v2, quatro assets divergentes do manifesto. Não houve upload nem promoção produtiva nesta frente. O site público ainda não entrega o pacote v5 assinado.

Para declarar P0 de distribuição **fechado na web**, os próximos gates são: (1) autorização de upload de versão, identificação de version ID, confirmação de código Worker e assets hospedados; (2) canário/version override ou rota DEV controlada, rollback preservado, aprovação separada para qualquer deployment 0% ou 100%; (3) readback público KID/RSA/4 SHA e 15 assets em Services/Storage/Observer; (4) instalação comercial REAL com pareamento próprio, lifecycle e rollback em x86_64 e ARM64, com prova de segurança e performance por cliente. 0% PROD não garante isolamento se o version override for público.

A VM Windows desligada não foi acordada. O Agent `0.3.43` comercial **não** equivale à versão interna Founder 0.3.54, e a versão Windows funcional 0.3.55 segue outra homologação. A beta/GA continuam separadamente bloqueadas por segundo tenant, Windows, Stripe/OpenAI/soak. Não afirmar disponibilidade geral por assinatura ou gate local.

**Preservação:** nenhum Agent, serviço, D1, Cloudflare deployment, Stripe ou energia da frota foi modificado; a única atividade sensível foi a assinatura privada sob custódia no Services e a criação de artefatos públicos de release, com a chave privada não exportada.
