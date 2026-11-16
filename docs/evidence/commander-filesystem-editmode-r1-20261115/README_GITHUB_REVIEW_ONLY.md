# H.A.R.A. Commander — revisão GitHub da correção 0.3.84

**Escopo: revisão de fonte e QA; não é release, instalador publicado, aprovação comercial nem deploy.**

Esta branch foi criada **sobre o HEAD real do GitHub `hara-site/main`**, `d2ff871ece53415cb1646ce27c81af3f56fa04db`, sem alterar a árvore pré-existente. Ela copia somente evidências, patch de correção e cinco scripts de validação da branch local custodiada `local/commander-editmode-source-integrated-r2-20261115`, commit `1059fa86142e5fcfa362ae36ccee3f43db55ba7b`. Nenhum Agent público ou instalador foi substituído.

## Por que esta reconciliação existe

O GitHub `main` ainda contém os artefatos públicos de Agent `0.3.11`; a fonte efetiva corrigida partiu da versão local `0.3.83`. Essas histórias **não são uma cadeia de fast-forward**. A branch de revisão preserva o `main` remoto como ancestral, evitando force-push, merge direto de release ou publicação comercial acidental.

## Provas incluídas na revisão

- `agent_0383_filesystem_edit_mode_r2.patch` representa a correção do `filesystem.edit` para preservar modo POSIX, owner, grupo, ACL e xattrs quando o Agent é editado.
- `QA_SOURCE_INTEGRATION_R2.json` documenta o SHA exato da fonte Linux integrada: `4d1de56697329b2936778351a4988092e355d8a0d8a6f6cf17cce57880275733`.
- `QA_PRIVATE_SIGNED_0384.json` documenta a assinatura privada v2 de 0.3.84, com manifesto SHA-256 `b0350ec8dc9f2b995742cf07df91df8ad5aaa324a9948b16753f178cef2820fe`.
- `QA_OFFLINE_CONTAINER_CANARY_0384.json` documenta 8/8 verificações no contêiner offline e rollback de arquivo.
- `QA_WINDOWS_NATIVE_0384.json` documenta validação RSA-3072, parser Windows, versão e rollback temporário em VM nativa isolada.
- `QA_LINUX_NATIVE_INSTALLER_SERVICE_0384.json` documenta serviço `systemd --user`, rollback de .84 para .83, e recusa segura do instalador oficial `update` sem matrícula, RC5 `DEVICE_NOT_ENROLLED`.
- Scripts `sign_private_commander_0384_v2.py` e `validate_*0384*.py` são referências para revisão; a execução do primeiro **exige autoridade de chave privada ausente desta branch**.

## Limites que o reviewer deve preservar

A assinatura RSA é um artefato de QA privada, não autorização para publicação. **Não executar os scripts sobre usuários ou Agents produtivos; não usar branch para substituir `apps/commander/public/agent` ou executar HARA Identity comercial.** O fluxo de instalação positiva com pareamento, admissão comercial, aceite de tarefa Windows, Worker/D1/DO e leitura remota de código continuam frentes separadas. A exceção da ausência da árvore 0.3.83 no `main` é mantida como divergência explícita, não ocultada.

O publicador semanal deve emitir `PASS_REMOTE_EXACT_REF` sobre o commit desta branch de revisão. Só então fica comprovada a publicação de código e QA no GitHub. O código de release 0.3.84 permanece em custódia privada local até a homologação integral.

**Autoridade operacional:** H.A.R.A. Commander Primary. H.A.R.A. Commander Baseline não modificado.
