# Paradox — handoff público do site unificado

```text
STATE=GIT_HANDOFF_READY_NO_DEPLOY
PLATFORM_PR=tiagoharalabs/hara-platform#97
PLATFORM_HEAD_AT_HANDOFF=ac2dd8f2b0e7deaa3e2ab6f3c70c7b7f800a3c13
HARA_SITE_BASE_MAIN=ca35c89e2fe712538f31deb36280b1475553cb70
CANONICAL_PRODUCT=PARADOX
TARGET=ONE_SITE_ONE_UI_SHELL
```

Esta branch não redesenha nem implanta o site. Ela substitui a governança Torre V10 que permaneceu aberta e entrega a superfície V12 para a próxima etapa:

1. reler em modo read-only o runtime Paradox, assets e rotas;
2. rebasear somente os componentes atuais de Drift Control, Observabilidade e Doc Controls;
3. convergir a raiz e `/observabilidade/` em um shell único, mantendo compatibilidade;
4. validar sanitização, responsividade, acessibilidade e frescor;
5. solicitar decisão separada de merge/deployment e publicar receipt de readback.

Paradox não é control plane. Hara Services governa; Observer presencia; Storage preserva; o site apresenta.
