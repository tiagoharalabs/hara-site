# H.A.R.A. Site — política V12 de publicação do Paradox

```text
AUTHORITY=TORRE_CONTROLE_HARA_V12
PRODUCT=PARADOX
FRONT=HARA_PARADOX_UNIFIED_DRIFT_OBSERVABILITY_DOC_CONTROLS_FRONT_V1
CANONICAL_REPOSITORY=tiagoharalabs/hara-site
DIRECT_MAIN_PUSH=DENY
FORCE_PUSH=DENY
AUTO_MERGE=DENY
RAW_EVIDENCE_PUBLICATION=DENY
RUNTIME_AUTHORITY=FALSE
```

Toda alteração do site segue: binding exato de `main` → branch não-main → escopo de arquivos declarado → verificação de conteúdo público e segredo → validação estática/build → PR draft → revisão → decisão explícita de integração → deployment → readback → receipt.

O site é uma projeção sanitizada e read-only. Nenhum botão, endpoint ou script pode decidir, despachar, reivindicar fila, alterar desired state ou executar remediação sem um futuro contrato de ação assinado pelo Hara Services e autorização soberana separada.

O modelo de produto é um Paradox, um repositório, uma implantação e um shell principal. Rotas de compatibilidade podem existir durante a transição, mas não criam outra autoridade.
