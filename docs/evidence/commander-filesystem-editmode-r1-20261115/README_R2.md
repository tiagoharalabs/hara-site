# Commander Primary — `filesystem.edit` R2: preservar modo, ACL e atributos estendidos

**Data:** 15/11/2026 · **Owner:** [hara-site #342](https://github.com/tiagoharalabs/hara-site/issues/342) · **Estado:** SOURCE QA PASS, **não instalado**.

A R1, commit `df11e6296e1d9347a866054b12d688683386c6ce`, resolveu a perda direta do modo `0755→0664` em testes isolados. A R2 adiciona retenção **fail-closed** dos atributos estendidos, inclusive ACL POSIX real, e testes de falhas intermediárias. Este pacote é a sucessora da R1, preservando os quatro arquivos originais.

**Identidades**
- Agent instalado e imutável: v0.3.83, SHA-256 `a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733`.
- Candidata R2 isolada: SHA-256 `4d1de56697329b2936778351a4988092e355d8a0d8a6f6cf17cce57880275733`.
- Patch `agent_0383_filesystem_edit_mode_r2.patch`: SHA-256 `abbac2a26f4696e02217194ad43ce2ec03b441ac198ddd6c8ba8512fb1bc2082`.

**Verificação:** em um diretório de QA isolado, copiar o Agent original exato como `agent.original.py`; confirmar seu hash e executar:

```bash
patch -s -o agent.candidate.r2.py agent.original.py < agent_0383_filesystem_edit_mode_r2.patch
sha256sum agent.candidate.r2.py
HARA_MODEFIX_SOURCE_DIR="$PWD" python3 -I -B test_modefix_r2.py
HARA_MODEFIX_SOURCE_DIR="$PWD" python3 -I -B test_modefix_acl_r2.py
XDG_DATA_HOME="$PWD/isolated-data" XDG_CONFIG_HOME="$PWD/isolated-config" python3 -I -B agent.candidate.r2.py --self-test
```

**QA concreto:** os 14 cenários de regressão executados sob root nativo passaram, incluindo grupo não primário. No namespace Commander, 13 cenários positivos e um grupo não primário indisponível. ACL POSIX real, com `system.posix_acl_access`, passou nos dois ambientes. Os cenários de negativa comprovam arquivo original intacto e temporários limpos em falha de `os.replace`, falha de cópia de xattr e mudança concorrente de atributo. `--self-test` com XDG isolado passou nas 41 ferramentas MCP. O patch se reconstrói byte a byte a partir do hash do Agent original. Os resultados e limites estão em `QA_R2.json`.

**Segurança e limites:** o código exige snapshot limitado de atributos, recusa impossibilidade de ler, restaurar ou comparar xattrs; mantém PRE/CAS SHA, verificação de modo/UID/GID, proibição de symlink, bits especiais e preimage. Não remove xattrs ou ACL silenciosamente para prosseguir. Ainda não é release: precisam integração na fonte autoritativa do produto, validação de metadados específicos de sistemas suportados, assinatura, pacote, canário, rollback e aceite nativo. Não aplicar este patch diretamente no Agent em execução, não publicar como PROD e não alterar o Baseline.
