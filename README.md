# H.A.R.A. Paradox — site único

Este repositório contém a projeção pública sanitizada do Paradox: uma única superfície para observabilidade, drift control e doc controls.

```text
AUTHORITY=TORRE_CONTROLE_HARA_V12
CURRENT=CURRENT.json
PRODUCT=PARADOX
MODEL=ONE_PRODUCT_ONE_SITE_ONE_UI_SHELL
RUNTIME_AUTHORITY=FALSE
```

## Estado atual

A raiz institucional e a rota `/observabilidade/` vivem no mesmo repositório e deployment, mas ainda não estão convergidas em um único shell. A próxima etapa é inventário exato read-only e convergência de source; esta branch não executa deployment.

## Estrutura relevante

- `index.html` e `public/index.html`: raiz atual.
- `public/observabilidade/`: cockpit atual e snapshot sanitizado.
- `src/worker.js`: APIs públicas e entrega de assets.
- `CURRENT.json`: ponteiro de governança do site.
- `HARA_PARADOX_UNIFIED_SITE_HANDOFF.md`: sequência da frente.
- `HARA_SITE_DEPLOYMENT_POLICY.md`: política V12.

## Publicação governada

Não use push direto em `main`. Toda publicação exige branch de revisão, validação, PR draft, decisão explícita de integração, deployment readback e receipt. Secrets, topologia privada, logs brutos e evidência operacional crua não pertencem ao site público.
