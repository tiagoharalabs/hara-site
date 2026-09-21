# H.A.R.A Labs — Site Institucional Premium

Pacote estático do site institucional H.A.R.A. A publicação externa é integrada à Cloudflare; mudanças no `main` podem produzir efeito de deploy e, por isso, o caminho normal de alteração é sempre branch → pull request revisado → merge.

## Estrutura

- `index.html`
- `styles.css`
- `assets/images/`

## Identidade visual canônica

- fonte aprovada: `brand/hara-capybara-flat-matte-source.png`
- derivado web/Commander: `assets/images/hara-brand-flat-matte.png` + cópia em `public/`
- app/plugin square: `hara-mark-square.png` / `hara-mark-square.webp`
- favicons `16`, `32`, `192` e `512` derivados da mesma fonte
- política: flat/matte, não espelhado, marca integral visível e `object-fit: contain` nas superfícies de branding

Os arquivos `hara-logo-premium.*` permanecem apenas como legado não ativo; não são a identidade primária.

## Publicação governada

`DIRECT_MAIN_PUSH=DENY`  
`FORCE_PUSH=DENY`  
`GENERIC_GIT_ADD_A=DENY`  
`AUTO_MERGE=DENY`

Não use `git push` diretamente para `main` como fluxo normal e não use staging genérico de todo o repositório. Alterações devem ser limitadas aos paths intencionais, publicadas em branch própria e revisadas por pull request antes do merge.

O workflow `HARA Site Main Provenance Guard` verifica a proveniência de cada push em `main` e falha se o commit não estiver associado a um pull request mergeado. Esse guard é detecção/adjudicação pós-push e **não substitui branch protection/ruleset nativo do GitHub**. Portanto, não trate a existência do workflow como prova de que `main` está preventivamente protegido.

A configuração exata de branch protection/ruleset e a integração externa de deploy devem ser resolvidas por readback atual antes de qualquer afirmação de proteção preventiva.

## Ambientes DEV / PROD

O fluxo canônico do site é DEV -> PROD.

DEV é o ambiente local de engenharia e revisão visual. PROD é o estado mergeado em `main` e comprovado ao vivo em `haralabs.com.br` / `www.haralabs.com.br`.

O Git não mantém uma árvore `dev/` nem snapshots de preview como estado durável. Branches de PR são transporte temporário para revisão; o estado persistente do produto no repositório representa PROD.

Contrato completo: `docs/workflows/HARA_SITE_ENVIRONMENT_PROMOTION_V2.md`.
