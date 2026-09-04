# H.A.R.A Labs — Site Institucional Premium

Pacote estático do site institucional H.A.R.A. A publicação externa é integrada à Cloudflare; mudanças no `main` podem produzir efeito de deploy e, por isso, o caminho normal de alteração é sempre branch → pull request revisado → merge.

## Estrutura

- `index.html`
- `styles.css`
- `assets/images/`

## Imagens incluídas

- `hara-logo-premium.webp`
- `hara-logo-premium.png`
- `hara-mark-square.webp`
- `hara-mark-square.png`
- favicons em PNG

## Publicação governada

`DIRECT_MAIN_PUSH=DENY`  
`FORCE_PUSH=DENY`  
`GENERIC_GIT_ADD_A=DENY`  
`AUTO_MERGE=DENY`

Não use `git push` diretamente para `main` como fluxo normal e não use staging genérico de todo o repositório. Alterações devem ser limitadas aos paths intencionais, publicadas em branch própria e revisadas por pull request antes do merge.

O workflow `HARA Site Main Provenance Guard` verifica a proveniência de cada push em `main` e falha se o commit não estiver associado a um pull request mergeado. Esse guard é detecção/adjudicação pós-push e **não substitui branch protection/ruleset nativo do GitHub**. Portanto, não trate a existência do workflow como prova de que `main` está preventivamente protegido.

A configuração exata de branch protection/ruleset e a integração externa de deploy devem ser resolvidas por readback atual antes de qualquer afirmação de proteção preventiva.
