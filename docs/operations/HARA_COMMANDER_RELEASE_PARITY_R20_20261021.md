# H.A.R.A. Commander — R20 | Fleet, release train e paridade Linux/Windows

**21/10/2026, 17h06–17h20 UTC.** Revisão pelo HARA Commander (Núcleo A e Services, Sentinelas A/B/C/D e Ninja Blue por MCP, Storage e Observer via SSH read-only). Objetivo: não permitir lançar instaladores desatualizados nem declarar homogeneidade falsa. **Nenhum Agent foi trocado, nenhum computador acordado, Windows VM permaneceu shut off, nenhuma publicação Cloudflare foi executada.**

## Resultado objetivo

**Frota Linux interna: versão/protocolo/funções homogêneos, mas dois builds do loop Event V2. Instalação Windows/Linux comercial mais recente: NÃO.**

| Dimensão | Comprovação R20 | Aceite |
| --- | --- | --- |
| Núcleo, Services, Sentinela A/B/C/D, Ninja Blue | **7/7 `ping` PASS**, versão `0.3.54` | PASS |
| Catálogo Linux | **7/7 `get_config` exatamente o mesmo conjunto de 31 funções**, `PERSISTENT_TRUSTED` | PASS |
| Operações reais Linux | **7/7 read_file, 7/7 process.run** com exit0 e recibos HARA | PASS |
| Integridade do Agent Linux | **7/7 assinaturas RSA v2 verificadas**, 7 manifests ligados a devices únicos, 7/7 hashes declarados íntegros, user service v2 active/enabled, legacy inactive/disabled | PASS |
| Binários compartilhados Linux | `candidate/event_v2_full_agent.py` SHA `8a533885af73e46cca7140f150a15aab0ff7e0619d54647b5ab22056e798f774` em **7/7**; `public/agent/linux.py` SHA `9f27d636fa8d0b2f012bdee08dfa5996eb15d896a0da9a8dd0ba1c8b0394c58c` em **7/7** | PASS |
| Loop Event V2 | Variante SHA `cd9ae709...`: Núcleo/Services/Sentinela B; variante `f1a7d9fc...`: Sentinelas A/C/D/Ninja Blue | **HOLD de build exato** até equivalência qualificada |
| Windows VM | `commander-win11` **shut off**, registro 0.3.53 offline, não foi inicializada | HOLD runtime |
| Fonte Windows mais recente | Candidata `windows_agent_055.ps1` versão `0.3.55`, SHA `f44caf3f8af2b35e57a4066df65fadabf4c7eeceb969c853f62312bd18fb22ba`, testes de fonte/instalador PASS; sem assinatura e sem instalação | HOLD publicação |
| Worker — capacidades | Linux 0.3.54 **31**; Windows instalado 0.3.53 **19**; Windows 0.3.55 candidato **22**, sendo 3 funções recuperadas; diferenças restantes explicitadas em `capability-matrix.json` | HOLD paridade funcional ampla |
| Linux comercial 0.3.55 | **Não existe fonte candidata 0.3.55 identificada no checkout**, nem pacote comercial equivalente assinado | HOLD |
| V5 comercial atual | **0.3.43** Linux e Windows, assinatura RS256 oficial válida, 160/160 testes offline R19; diferente do 0.3.54 Founder e do 0.3.55 candidato Windows | PASS assinatura, **HOLD versão de atualização** |
| Site público | Quatro probes via Núcleo/Services/Storage/Observer mostram manifesto **0.3.41**, assinatura `commander-release-v1`, e Agent/installer Linux com os mesmos hashes antigos; 4 arquivos não correspondem ao manifesto assinado | **HOLD instalação pública** |
| Storage e Observer | Sem Agent principal cadastrado; Fedora43/x86_64 e Ubuntu22/aarch64 já passaram verificações offline do release v5 assinado, não foram instalados | HOLD inscrição real |

**Apenas número igual não implica build igual.** As duas variantes de loop fazem parte de manifests RSA assinados e ligados à identidade local de cada host. Não copiar arquivos entre dispositivos e não reembalar/sinalizar 0.3.54 como 0.3.55 sem nova homologação e assinatura por autoridade competente. A origem/necessidade da diferença requer revisão do Codex; o fato de ambas oferecerem 31 funções e passarem operações não prova que sejam semanticamente equivalentes.

## Descoberta de paridade Windows por fonte Worker real

`analyze_cross_platform_capabilities.mjs` extrai as funções de compatibilidade do próprio `src/worker.js`, sem rede, e compara os catálogos:
- Linux 0.3.54: 31 funções
- Windows 0.3.53: 19
- Windows 0.3.55: 22
- 21 funções presentes em ambos os catálogos mais recentes; Windows 0.3.55 adicionou `hara.files.edit`, `hara.files.read_many`, `hara.files.search`.
- No Windows 0.3.55 faltam `hara.files.copy/delete/diff/hash/move/preimages.list/rollback`, `hara.system.resources/uptime` e `hara.workspace.inspect`; há `hara.functions.invoke` apenas no catálogo Windows. **Não prometer 31/31** até implementação, decisão de funções opcionais e testes reais.

A fonte candidata Windows 0.3.55 passou `validate_windows_r10_candidate.py` (SHA estável e base histórica 0.3.54 assinada), `test_windows_r10_capability_contract.mjs` 19/19, `validate_windows_r11_installer_candidate.py` e `validate_windows_r13_enrollment_intent.py`. São **testes de fonte offline**, não instalação de Windows 0.3.55 em VM real nem seu agente conectado.

## R20 gate novo — não vender a release antiga como a última

Novo `apps/commander/scripts/commander_release_train_parity_gate.py`, input `fleet_release_inventory.json`, modo exclusivamente offline. A versão de destino **0.3.55 é intenção PROVISÓRIA de alinhamento**, não foi selecionada/aprovada como release oficial; Codex pode escolher versão sucessora após integração.

O script verifica assinatura criptográfica REAL do bundle comercial, hashes da candidata Windows, atestados runtime Linux, coerência de source+manifest+download, paridade aprovada e disponibilidade de Linux candidato da versão-alvo. Nesta composição atual, a execução retorna corretamente **`HOLD` (exit 2)**: 6/15 gates verdadeiros e 9 bloqueios. Oito regressões unitárias `test_release_train_parity_gate.py` **8/8 PASS**: não aceita renomear pacote assinado 0.3.43 como 0.3.55, nem fonte Windows adulterada, inventário mentiroso ou credenciais/execução não comprovadas.

O gate é **candidato de aceitação** em branch de revisão, não foi acoplado ao pipeline PROD sem validação do Codex. A suíte geral R19 160/160 continua válida para a segurança OFFLINE do v5, mas **não prova que seja a versão mais recente desejada**.

## Roteiro mais curto para fechar a exigência do proprietário

1. **Codex escolhe um release train comum (0.3.55 se tecnicamente possível, ou versão sucessora).** Construir Linux comercial a partir dos recursos realmente homologados, e Windows comercial de fonte 0.3.55, sem copiar secrets/flags Founder, sem subir meramente o número. Manifesto deve conter `version + channel + build_sha + platform + capabilities_contract` por plataforma e testes de migração, inclusive upgrade/downgrade protegido.
2. **Tratar as diferenças Event V2 de A/C/D/Ninja vs Núcleo/Services/B**: explicar builds e, se intencionais, qualificar equivalência por função e runtime; se drift indevido, preparar rollout assinado por device com rollback. Não interromper serviços para alterar SHA sem essa prova.
3. **Windows real**: somente quando a VM for ligada/permitida, instalar o candidato devidamente assinado com identidade própria, testar 22 capacidades previstas, paridade declarada, erro/código de recibo, reconexão antes/depois do login, saída/continuação, fila/execução, desinstalação e rollback. Não alegar que 22 funções é igual a 31.
4. **Release estável Linux/Windows**: colocar Agents e instaladores das versões comerciais reais no MESMO manifesto oficialmente assinado; `kid/RS256`, quatro hashes, versão e build SHA conferidos, readback HTTP em múltiplas máquinas/POPs e gates fail-closed. Site público 0.3.41/v1 com assets incoerentes deve ser substituído *apenas* no fluxo versionado aprovado; upload não é promotion.
5. **Instalações e upgrade**: primeiro canário isolado Storage Fedora43/x86, depois Observer ARM64 com pareamentos próprios, depois Windows VM, e finalmente Founder Linux em ondas pequenas mantendo canal de recuperação independente; validar funcionalidade real e build/report no Commander após cada etapa.
6. **Beta**: segundo tenant isolado, custo/latência representativa, recibos e rollback; nenhuma declaração de GA antes de Windows/Stripe/OpenAI e soak aplicáveis.

**Não executado:** upgrade ativo, boot da VM, install Storage/Observer, emissão de token de cliente, nova assinatura de fontes 0.3.55, upload/deploy Cloudflare, billing ou migração. **Atualizar instaladores para a última versão não está concluído; o gate mantém HOLD até a evidência real.**

## Evidências

`docs/evidence/commander-version-parity-r20-20261021/`:
- `fleet_release_inventory.json`: 7 hosts e grupos de hash sem identidade/token privado
- `capability-matrix.json`: comparação derivada do Worker
- `release-train-gate.json`: decisão 6/15, HOLD de versão comum
- `public-{nucleo,services,storage,observer}.json`: probes públicos independentes
- `public-download-readback.json`: gate público read-only
- `SHA256SUMS`: integridade das evidências
- Verificadores em `apps/commander/scripts/commander_release_train_parity_gate.py`, `test_release_train_parity_gate.py`, `analyze_cross_platform_capabilities.mjs`

**Nota de consistência da CDN:** uma consulta preliminar apresentou metadado de `kid` v2, mas a leitura direta imediatamente posterior e os quatro hosts convergiram em `kid` v1; não é suficiente para atribuir publicação parcial. O problema comprovado e repetido é o público em `HOLD` por mismatch de versão/assinatura/artefatos. Não inferir rollout de qualquer leitura isolada.

Branch de revisão separada. Nenhum arquivo rastreado no checkout ativo do Codex foi alterado.
