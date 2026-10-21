# H.A.R.A. Commander — R25 | QA independente de histórico R23 e readback do Worker

**Data:** 21/10/2026 (BRT). **Origem:** handoff R24 commit `8696fa6f616124eb1e47c33306a5f082f3696e99`. **Canal:** branch de revisão; NÃO é release, homologação, merge na `main` ou deploy.

## Contexto preservado

- R18: auditoria de proveniência do Worker e outras verificações; commit `6b4d9ab892610bc6018a2d29dacd7a7caee57d1c`.
- R22: Windows Founder `0.3.55` canário assinado e histórico sob demanda; commit `25923b3419adbdaad46166ecf44d654c8ec577be`.
- R23: snapshot WIP Linux/Windows e fixtures preservados pelo R24; **nenhum Agent foi atualizado para R23**.
- `main` e Cloudflare não foram alterados por esta QA. A worktree ativa do Codex `commander-prelaunch-fixes-20261020` permaneceu intocada.

## Resultados reproduzidos

| Área | Evidência | Leitura de aceite |
| --- | --- | --- |
| Linux R23 | Reexecução de `python3 -B apps/commander/scripts/test_linux_r23_history.py` no checkout R24 isolado, no Núcleo A: `Ran 7 tests ... OK`, **exit 0** | **7/7 PASS** em fixtures sintéticos |
| Windows fixture R23 | Executado na VM `HARA_WIN11` em diretório `%TEMP%`; origem `windows_history_30d_fixture.ps1`, SHA-256 `d6c90a10100bb56f229ac625b4108f6e5d35fd5e07d811036188e63ba00a4097`, conferido no destino | **17 marcadores PASS**: janela 30 dias, paginação, cursor, redaction, console EOF, novos eventos, clear descartável e recibos |
| Windows não-admin | `windows_nonadmin_guard.ps1` em sessão Windows não elevada: `R23_WINDOWS_NON_ADMIN_CLEAR_DENIED=PASS` | Bloqueio não-admin **PASS** |
| Catálogo Windows | H.A.R.A. Commander `get_config`: 19 ferramentas com Agent `0.3.55`; `files.read_many` e `files.search` retornam `UNKNOWN_FUNCTION_ID` | **HOLD Worker/catálogo**, sem reinstalar Agent |
| Catálogo Linux | Services `0.3.54` anuncia 31 ferramentas; `files.read_many` de `/etc/os-release` PASS | Controle comparativo PASS |
| Integridade local | R24 worktree conferida limpa; Codex ativo conservou modificação já existente em `docs/operations/HARA_COMMANDER_PEER_REVIEW_R2_20261020.md` | Nenhum checkout/reset/clean/cherry-pick |
| Limpeza de QA | Os dois scripts de teste Windows foram removidos de `%TEMP%`; diretório descartável `HARA_HISTORY_R23_*` não permaneceu | Nenhum dado real de histórico foi limpo |

**Ressalva obrigatória:** no Windows, a sessão gerenciada criada pelo Commander permaneceu `RUNNING` depois de imprimir os últimos PASS. O wrapper observado era `powershell.exe -NoLogo -NoProfile -NonInteractive -Command -`. As duas sessões QA foram encerradas explicitamente e confirmadas `EXITED`, sem tocar na sessão preexistente. **Não afirmar exit 0 automático para a suíte Windows** até qualificar o ciclo de vida de `process.run`/`process.start`.

## Recibos de execução / readback

- Linux R23 suite: `b215e190a2f3b145203b5adbd997c2e67e01c287164263154b3f22e0a7863b87`.
- Windows fixture SHA readback: `87c5e7658bf466df263768b77f5f19a260f4543595ed23544420c4ed4f4fcd1b`.
- Windows fixture 17 markers: `aa27f61a60d1d6e9ce2da036187a556ce3ee4e8322fd5116e84b152690685fd5`.
- Windows não-admin: `976de34c243ac62742b4f9fb2bec3298501ad289b41a9a370ba8a9e5483f5b41`.
- Windows sessões QA encerradas: `999a2848ae0e3fb5fefd3e7ce0766dffc2e06942bc05b259516a8b6b13e24189`.
- Windows scripts temporários removidos: `6b2c08a3de28fa88985d9e626c69f5f7f311078d5bc622a9a7cb09d092108a09`.

## Próxima ordem de trabalho

1. **P0 R23 — QA faltante:** adicionar caso `at_utc` futuro (consultas hoje usam limite inferior de 30 dias, não limite superior) e teste de borda temporal; confirmar comportamento de PowerShell com execução não interativa e saída natural; avaliar ACLs, reparse points e bloqueios quando o Agent/sessão estão ativos. Reexecutar fixtures e gerar candidato successor versionado e assinado, não instalar R23 diretamente.
2. **P0 Worker Cloudflare:** fixar commit SHA + hash do entrypoint Worker e dependências/import graph ao snapshot imutável, reproduzir `versions upload` com projeto inteiro congelado e `version readback`. Nunca promover/upload PROD apenas porque assets públicos foram validados. Somente após autorização específica, smoke canário e rollback comprovado.
3. **P0 paridade:** 22 funções Windows esperadas no código revisado versus 19 hospedadas; teste `read_many`, `search` e `edit` em canário isolado, mantendo `ASK_EVERY_ACTION` onde requerido.
4. **P1 release train:** conservar Linux Founder 0.3.54 / Linux comercial 0.3.43 / Windows Founder 0.3.55 até homologar versões sucessoras por arquitetura, identidade, assinatura, SLO e rollback.

**Gate R25:** QA de histórico sintético avançou, mas **R23 permanece WIP** e **Worker permanece HOLD**. Nada foi publicado em PROD ou na `main`. A evidência aqui não autoriza limpeza administrativa, merge, rollout ou downgrade.
