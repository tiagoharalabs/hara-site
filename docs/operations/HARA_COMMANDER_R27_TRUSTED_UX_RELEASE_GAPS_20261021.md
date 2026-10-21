# H.A.R.A. Commander R27 — confiança única e fechamento de release 9 Linux + Windows

**Data:** 21/10/2026 (BRT). **Escopo:** revisão independente do modelo de autorização e código de UX no **candidato Linux R23**, não instalado; ênfase em reduzir aprovações repetitivas sem desativar RBAC ou recibos. **Estado:** revisão, sem promoção ou deploy.

## Requisito do proprietário

> Depois de vincular um dispositivo e permitir os escopos necessários, o usuário não deve ser interrompido para autorizar cada comando. A autorização contínua deve ser uma escolha explícita, revogável e auditada; mudanças de privilégios e outras operações críticas preservam proteção adicional.

**Hoje, o produto já suporta três políticas:**
- `ASK_EVERY_ACTION`: aprovação local individual para mutações e comandos; padrão do instalador comercial 0.3.43.
- `SESSION_TRUSTED`: dispensa confirmação de cada comando enquanto houver sessão local ativa. Atual no Windows 0.3.55.
- `PERSISTENT_TRUSTED`: comandos governados aprovados pelo trust do dispositivo, inclusive sem console aberto. Atual nas sete Linux Founder 0.3.54.

O modo `PERSISTENT_TRUSTED` **não deve ser ligado silenciosamente por instalador ou por chamada remota**. No onboarding final, oferecer autorização explícita *uma vez*, com escopos/usuário/tenant/dispositivo visíveis, registro e revogação imediata. Confirmações repetidas por comando não são a experiência-padrão pretendida para dispositivos confiáveis. RBAC/grants, restrições de ferramentas e rollback permanecem indispensáveis.

## Readback real — 21/10/2026

| Device | Plataforma | Versão | Approval | Catálogo MCP |
|---|---|---|---|---|
| nucleo-a | Linux x86_64, **OFFLINE na consulta** | 0.3.54 | PERSISTENT_TRUSTED | 31 |
| services, sentinela-a/b/c/d, ninja-blue | Linux x86_64 | 0.3.54 | PERSISTENT_TRUSTED | 31 |
| storage | Linux Fedora43 x86_64 | 0.3.43 | ASK_EVERY_ACTION | 31 |
| observer | Linux Ubuntu22 Tegra ARM64 | 0.3.43 | ASK_EVERY_ACTION | 31 |
| HARA_WIN11 | Windows 11 x64 | 0.3.55 | SESSION_TRUSTED | **19 hospedadas, 22 esperadas** |

**São 9 instalações Linux, não 7**; no instante desta auditoria, 8/9 Linux apareciam online, porque `nucleo-a` estava offline. Nem um teste de sete casos nem sete Founder são evidência de 9/9 homologadas.

No `0.3.43` **instalado nos dois servidores**, o comando local `hara-commander approval-mode always` já está implementado e troca o perfil sem reinstalar o Agent. A alteração pode exigir reinicialização da sessão e readback de heartbeat. **Não foi executado**, porque o acesso pelo Commander aos dois hosts exige a política atual `ASK_EVERY_ACTION` e tentou `process.run` com `LOCAL_OPERATOR_APPROVAL_TIMEOUT` (R26). Não contornar a política usando shells secundários para elevar confiança.

## Código realizado em R27

Base: revisão isolada `review/commander-r27-trusted-ux-20261021`; parent R26 `94b7955483d852221460808944be5a261e568590`.

1. `apps/commander/candidate/linux_agent_history_r23.py`: o console passa a descrever corretamente o modo persistente. `Ctrl+C` fecha sua janela de visualização, **não revoga** a confiança persistente. Orienta o comando de revogação.
2. `set_approval_mode('always')`: em um dispositivo que ainda não é persistente, exige TTY e frase exata `CONFIAR NESTE DISPOSITIVO` antes de elevar confiança. A operação não ocorre em stdin não interativo; alteração para `ask` (revogação) não exige repetir consentimento. Recusa `device.env` quando é symlink.
3. `apps/commander/scripts/test_linux_r27_trust.py`: 9 testes sintéticos, cobrindo autorização, redaction/UX, negativa headless, recusa sem frase, idempotência, revogação e bypass **apenas de prompts repetidos** em SESSION/PERSISTENT, sem desligar grants.

**Provas no Services, em scratch descartável separado de Codex/PROD:**
- Suite R23 de histórico Linux: **7/7 PASS**, exit0.
- Suite R27 de confiança: **9/9 PASS**, exit0.
- Syntax AST da fonte Linux R27: **PASS**, exit0.
- Recibo de execução combinada `81ba192b6bfe7278c95289c29cc49491fefa1b876de565d1f33008b407d3f72f`.
- Nenhum Agent foi atualizado, banco de histórico real apagado, política alterada nos hosts, Worker implantado ou código em `main` editado.

**Limite de segurança:** TTY + confirmação textual é um gate local de UX, não prova de MFA, criptografia de consentimento ou resistência a um invasor que já possua controle do usuário do SO. O release comercial ainda requer fluxo de trust do dispositivo, autenticação forte, autorização por escopo, revogação, credenciais/identidade não exportáveis quando possível e testes adversariais.

## O que falta para todos terem a última release operacional

1. **Criar a release sucessora única:** provisoriamente 0.3.56 (ou posterior após integração), não renomear 0.3.43/0.3.54. Integrar histórico R23 Linux/Windows, contrato R27 de confiança, e outros fixes já aceitos. Fonte Windows 0.3.55 Founder é canário, não pacote comercial geral. As duas variantes Event V2 0.3.54 requerem equivalência ou reconciliação.
2. **Concluir o Worker hospedado:** ele ainda anuncia 19 funções Windows, embora a fonte revisada espere 22; `files.search/read_many` retornam `UNKNOWN_FUNCTION_ID`. Fazer bundle imutável do Worker e seu grafo, smoke/version readback e só implantar após autorização específica.
3. **Assinar instaladores e Agents sucessores por plataforma:** Fedora43 x86_64 (Storage), Ubuntu22 Python3.10/aarch64 (Observer), demais Linux x86_64 e Windows x64; manifesto RS256 v2 com digests/build/capability declarado, prova anti-downgrade, transporte compatível e rollback.
4. **Integrar onboarding de autorização única Windows/Linux:** dono escolhe dispositivo confiável no cadastro, escopos concedidos e duração; nenhum prompt por comando admitido. A elevação exige consentimento efetivo local/portal; revogação deve interromper novas execuções e preservar recibos. Testar sem sessão ativa, pós-reboot e após revogação.
5. **Canários reais:** Storage e Observer 0.3.43→sucessora, preservando `device.env`, IDs, `OUTBOUND_RELAY`, configuração e histórico. Depois expandir Founder em ondas e Windows. Validar **9/9 Linux e 1/1 Windows** com versão+SHA+funções+ping/execução/recibo e rollback. O `nucleo-a` precisa estar acessível para teste online.
6. **Portal público:** somente depois de gates satisfeitos atualizar download 0.3.43 para a versão realmente assinada, verificando CDN/Worker/versão em múltiplos hosts. `git push` não equivale a promoção PROD.
7. **Antes do GA comercial:** segundo tenant isolado, segurança de autorização, estresse/soak/SLO por arquitetura/transporte, faturamento e outros gates de lançamento. Não bloquear o laboratório inteiro por Stripe, mas não chamar release de GA antes.

**Resultado R27:** pequena correção real + 16 testes PASS; aprovação repetitiva pode ser eliminada no modelo atual ao optar por confiança persistente, mas isso ainda não foi ativado no Storage/Observer. Release sucessora/Worker/deploy seguem **HOLD**.
