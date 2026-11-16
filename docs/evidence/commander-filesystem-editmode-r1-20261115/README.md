# H.A.R.A. Commander Primary — `filesystem.edit` POSIX mode regression (source candidate)

**15/11/2026 · Issue hara-site #342 · SOURCE_ONLY · PROD UNCHANGED**

A reprodução do Agent Linux `0.3.83` mostrou que `filesystem_edit` usa `Path.write_text(); os.replace()` e perde o bit executável: `0755 → 0664`. O defeito e a reprodução original pertencem à issue #342; este pacote contém **um patch de 36 linhas**, testes isolados e evidência dos resultados. Não é instalador assinado nem release, não contém credenciais ou código integral do Agent.

## Identidades exatas

- Agent original da máquina Services: `a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733` (0.3.83)
- Candidata recomposta, **não instalada**: `d047a6454e85f3658015e1f489d00b60a1be08e431fa215e9c77b3e2f3eb5f27`
- Patch `agent_0383_filesystem_edit_mode.patch`: `8783eb732731ee30e70a9b25014453988c4a4fef4bd6a93c4c17cc7f5dfc71d2`
- Testes `test_modefix.py`; resultados em `QA.json`

## Correção e controles

A edição passa a gravar o arquivo temporário por `O_CREAT|O_EXCL|O_NOFOLLOW`, exige preimage/CAS, preserva modo/UID/GID antes do replace e confere esses atributos depois. Reprova a edição quando o owner não pode ser preservado ou o modo possui bits especiais. Registra `mode_before`, `mode_after`, `mode_preserved`, `owner_uid` e `group_gid` no retorno. Não altera política de autorização ou diretórios produtivos.

**QA no namespace Commander:** 8 casos executados PASS (incluindo a reprodução do defeito), 1 caso de grupo não primário `SKIPPED` porque GID 65534 não está mapeado. **QA no host Services nativo:** 8/8 PASS. `python3 -I -B agent.candidate.py --self-test` em XDG isolado passou com **41 ferramentas MCP**. Testes de sintaxe Python PASS. Não houve mutação do Agent em execução.

## Reprodução controlada

1. Em pasta temporária privada, copie o Agent instalado para `agent.original.py`. **Verifique o SHA original exato** acima antes de aplicar qualquer patch.
2. Reconstrua a candidata com `patch -o agent.candidate.py agent.original.py < agent_0383_filesystem_edit_mode.patch`. Confira o SHA da candidata acima.
3. Execute `HARA_MODEFIX_SOURCE_DIR=/pasta/temporaria python3 -I -B test_modefix.py` usando arquivos descartáveis.
4. Execute o `--self-test` da candidata apenas com `XDG_DATA_HOME` e `XDG_CONFIG_HOME` isolados.

## Limites de entrega

**Não** implantar este arquivo diretamente na frota. Ainda faltam validação de ACL/xattr/SELinux, prova de GID não primário, QA de falha intermediária, integração na fonte assinável do produto, pacote de release com versão nova, canário em um host, readback e rollback nativos. `filesystem.write` (modo rewrite) não está no escopo desta mudança. O owner #342 recebe fonte e QA; a publicação do código no GitHub segue a governança do Git #1913.
