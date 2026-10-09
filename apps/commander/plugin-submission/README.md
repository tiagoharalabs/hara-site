# H.A.R.A. Commander — pacote candidato para diretório OpenAI

**Status: DRAFT — NÃO SUBMETIDO / NÃO APROVADO.**

Conteúdo:
- `plugin.json`: metadados do plugin H.A.R.A. Commander (capivara dourada) e roteiros de revisão (cinco positivos e três negativos).
- `mcp.json`: **somente** o endpoint comercial `https://commander.haralabs.com.br/api/mcp?profile=simple`, hospedado na Cloudflare, autenticado por HARA Identity OAuth.
- `assets/logo.png` e `assets/icon.png`: cópias convertidas do arquivo de marca existente do Commander (sem gerar outra identidade visual).

Esses roteiros ainda precisam ser **executados ao vivo** num tenant de demonstração autorizado. Não utilizar contas privadas reais ou expor segredos no ZIP.

Pré-requisitos para submissão:
1. Validar URL MCP comercial com uma conexão ChatGPT distinta do conector administrativo Services (login OAuth, leitura, escrita autorizada, negação).
2. Confirmar assinatura válida do Agent distribuído (público atual: 0.3.41). Fonte candidata 0.3.43 **não assinada**.
3. Verificação de organização H.A.R.A. Labs e permissões Apps Management da OpenAI; desafio de domínio apresentado no portal de submissão.
4. Inserir credenciais de uma conta DEMO apenas no formulário privado de revisão da OpenAI.
5. Disponibilizar vídeo real demonstrando os casos de uso e verificar os resultados dos 5 casos positivos e 3 negativos.
6. Submeter e aguardar aprovação; não anunciar como publicado antes disso.

Declaração de transparência: chamadas da modalidade Cloud passam pelo Gateway Cloudflare. Na fila D1, conteúdo pode ficar temporariamente persistido; o TTL nominal é 50 segundos e a redação depende da manutenção agendada. Não afirmar 'zero armazenamento de conteúdo' nem 'sem trânsito por H.A.R.A.'.

Fonte de requisitos: https://developers.openai.com/plugins/deploy/submission

## 2026-10-09 — DCR GUARDED ativado, registro OAuth real homologado

**CURRENT GATE: `HARA_DCR_EDGE_RECONCILIATION=PASS`.** O usuário leu no Storage, com a própria credencial de proprietário, os flags reais do ZITADEL `dynamicClientRegistration.enabled=True` e `allowUnauthenticated=True`. Não recriar PAT, não reverter flags para `False/False` e não executar novamente o antigo `promote_mcp_dcr_guarded.py` que exige backend fechado.

- Nova rotina canônica `apps/identity-login/scripts/reconcile_mcp_dcr_existing_backend.py` (branch Identity `local/identity-dcr-refresh-20261008`) reconcilia **somente o Gateway público e o anúncio RFC 8414**, mantendo ZITADEL/backend intocados. Aplicada pelo Storage com root e testes de backup, rollback, fail-closed e idempotência PASS.
- Configuração PROD Storage: `HARA_DCR_GATEWAY_MODE: guarded`; `HARA_DCR_REGISTRATION_ADVERTISED: "true"`. DCR positivo: cliente OAuth temporário registrado HTTP 201, consultado HTTP 200, excluído HTTP 204; limpeza PASS. DCR negativo: `400 invalid_client_metadata`. Health do ZITADEL/login e dos dois serviços de borda PASS.
- HARA Commander público: `python3 apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect guarded --require-ready` PASS. `/api/mcp?profile=simple` sem token ainda 401. Os nomes das três configurações de audiência e introspecção aparecem no catálogo de segredos do Worker PROD (não foram revelados valores).
- Rotina atual em Storage: `/srv/hara/identity/operations/reconcile_mcp_dcr_existing_backend.py --backend-already-enabled`, que verifica `HARA_DCR_EDGE_ALREADY_GUARDED=PASS` e retorna `HARA_DCR_EDGE_EXECUTE=NO_CHANGE` sem modificar serviços.
- Candidato do plugin `apps/commander/plugin-submission/mcp.json` permanece apontando para o MCP comercial com DCR da Identity; **não é necessário Secure MCP Tunnel OpenAI por cliente**.
- **ÚNICO GATE COMERCIAL ainda pendente:** ChatGPT concluir consentimento OAuth/PKCE e entregar token de usuário aceito pelo Worker, depois ChatGPT invocar ferramenta no Agent pelo MCP **COMERCIAL** (não pelo Baseline administrativo), isolamento/permissões e revisão/publicação na OpenAI. Não afirmar que a sessão ChatGPT foi homologada, que o app está publicado nem que o Worker valida todo token real antes da prova E2E.
- Evidência autoritativa da frente de Identity: `docs/status/HARA_COMMANDER_MCP_DCR_GUARDED_LIVE_20261009.md`.
