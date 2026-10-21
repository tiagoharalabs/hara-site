# H.A.R.A. Commander — R26 | Storage + Observer: upgrade solicitado, preflight e bloqueios

**Data:** 21/10/2026 (BRT). **Origem:** R25 `73a40f0994c6537ec431dc53499bdacea208a40c` e R24 `8696fa6f616124eb1e47c33306a5f082f3696e99`. **Estado:** PREFLIGHT / **HOLD**, sem upgrade, sem alteração PROD, sem downgrade, sem reinício de Agent.

## Solicitação explícita

O proprietário solicitou atualizar **Storage e Observer** para uniformizar as **nove máquinas Linux** e perguntou se o novo instalador deve ser `0.3.43` ou `0.3.54`.

**Decisão técnica proposta, não versão emitida:** **release sucessora 0.3.56** (ou posterior, conforme release manager) para o instalador comercial Linux + Windows. `0.3.43` é o download público atualmente assinado, mas está defasado. `0.3.54` já existe em builds distintos, e Windows Founder está em `0.3.55`: redistribuir `0.3.54` apenas para igualar o número não estabelece build/release parity e perderia as melhorias R23 de histórico.

## Readback factual (H.A.R.A. Commander)

| Host | Arquitetura/OS | Agent | Transporte | Política | Catálogo |
|---|---|---|---|---|---|
| Storage | Fedora 43, x86_64, Python 3.14.4 | **0.3.43** | `OUTBOUND_RELAY` | `ASK_EVERY_ACTION`, aprovação local exigida | 31 |
| Observer | Ubuntu 22.04, aarch64 Tegra, Python 3.10.12 | **0.3.43** | `OUTBOUND_RELAY` | `ASK_EVERY_ACTION`, aprovação local exigida | 31 |
| Sete Founder (R20/R24) | Linux x86_64 | **0.3.54** | `EVENT_V2` | `PERSISTENT_TRUSTED` | 31 |
| Windows Founder (R22/R25) | Windows 11 x64 | **0.3.55** | `OUTBOUND_RELAY` | `SESSION_TRUSTED` | 19 hospedadas |

Storage e Observer possuem `/home/sartorius/.local/share/hara-commander/hara-commander-agent` e unit `~/.config/systemd/user/hara-commander-agent.service`, com inscrição e identificador **próprios**. CLI `~/.local/bin/hara-commander` é symlink para o Agent; `device.env` e auditoria locais não devem ser substituídos. 31 ferramentas aparecem em ambos. Dados administrativos em `device.env` não foram lidos ou copiados.

## Tentativa de atualização via capacidade governada

Foi executada uma chamada de processo **inofensiva/diagnóstica** em cada host antes de qualquer mutação. Resultado **`DENIED/LOCAL_OPERATOR_APPROVAL_TIMEOUT` nos dois**. Não houve autorização interativa local para `process.run`; o gate de execução requer operador físico na sessão `hara-commander start` para aprovar. **Não** usar SSH como bypass deliberado de `ASK_EVERY_ACTION` nem reduzir política para instalar. Nenhum binário, unit, DB, inscrição, identidade ou versão foi alterado nesta frente.

## Pacote comercial 0.3.54 R2 — candidato localizado e validado offline

Local no Services:

```
/tmp_hara/commander-054-publish-checkpoint-20261013/apps/commander/release-bundles/commercial-0.3.54-v14-rc-r2
```

- O bundle é comercial `agent_version=0.3.54`, canal declarado `stable`, não é o pacote Founder `EVENT_V2` ligado ao device e **não está atualmente publicado como PROD**. É RC local congelada de 13/10.
- Manifesto SHA-256 `e1c7c23de1b4313093e2d8c52be1ec52f6419f72d5ef59d675c7e5a279b1a13d`.
- Linux Agent SHA-256 `62e1a836ef92fc8b72638fd116a6f0097fcf9e9f0ef0f4259ca8e0f6712b4229`.
- Signature SHA-256 `530627e5f1fe39d2582f8312fbafb32f219b9cdbdcec8777b5725aaefa73c4e8`.
- `(cd bundle && sha256sum -c release/SHA256SUMS)`: **4/4 OK**.
- `python3 -B apps/commander/scripts/validate_signed_full_054_v14_rc.py` no Services: **exit 0**, `state=PASS`, `RS256_RSA3072`, chave privada não acessada, `active_source_checked=true`, manifesto e quatro arquivos autenticados. Recibo HARA `4df6ce35eb216ecdaf914a766e2f56b880bf92e094051cc973f65ee7f445c276`.
- Documento congelado de 13/10 `docs/operations/HARA_COMMANDER_FULL_ACCEPTANCE_054_20261013.md`: ciclos funcionais Linux e Windows DEV concluídos, mas soak/escala, paridade, promoção pública e aceitação comercial em aberto.
- Esse pacote não incorpora o R23 de histórico Linux/Windows, preservado como WIP pelo R24 e avaliado parcialmente no R25. Logo, não usar `0.3.54` RC como "último instalador" para os clientes.

## Próxima execução segura (autorizada pelo pedido, condicionada aos gates técnicos)

1. **Build sucessor:** integrar UX de histórico 30 dias/console limpo no Linux e Windows, corrigir controle de `history clear` com mocks/rollback/TTY e contratar capacidades do Worker (Windows hospedado 19 vs 22 previstas). Publicação versionada nova **0.3.56** é recomendação, não release existente.
2. **Manifesto imutável:** assinatura RSA v2 e SHA de **ambos os Agents e instaladores**, origem do Worker, capacidades/arquiteturas x86_64/aarch64/x64, build por plataforma, channel, rollback, sem identidades Founder copiadas; não distribuir versões iguais com bytes divergentes sem equivalência aprovada.
3. **Canário Storage x86_64:** aprovação efetiva no console local; backup do Agent+config+unit por SHA e CAS, validar que `device.env` mantém o mesmo device_id e `ASK_EVERY_ACTION`, instalar candidato assinado sem reenrollment, systemd readback, ping, 31 funções, rollback.
4. **Canário Observer ARM64:** mesmo procedimento, rodar self-test sob **Python 3.10**, aferir autostart systemd, conexão relay e rollback sem alteração do device_id; não forçar Event V2 se não houver qualificação da combinação de transporte/política.
5. **Frota 9/9:** após os dois canários, qualificar build exato/duas variantes já instaladas nas sete Founder. Migrar em ondas com assinaturas por device. Testar nove instalações Linux, não só sete hosts ou sete testes de software.
6. **Distribuição pública:** só após pré-aceite e autorização específica, publicar instaladores novos com `version + manifest digest` corretos e readback CDN. Nunca chamar download `0.3.43` de última versão nem alegar `0.3.56` publicada antes da prova.

**Conclusão:** update Storage/Observer **não executado** por bloqueio real de consentimento local e falta de release sucessora homologada; pacote `0.3.54` localizado e validado offline; produção, chaves, inscrição, auditoria e sessões preservadas.
