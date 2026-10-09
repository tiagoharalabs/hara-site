# H.A.R.A. Commander — arquitetura comercial Cloud-first e submissão pública

Data: 2026-10-09 | Branch canônica: `local/commander-product-current`

## Decisão de produto

O fluxo principal de distribuição é **o mesmo modelo comercial do Remote Desktop Commander**:

```
ChatGPT (plugin H.A.R.A. Commander, capivara dourada)
  -> MCP HTTPS público `commander.haralabs.com.br/api/mcp?profile=simple`
  -> autenticação HARA Identity OAuth + autorização por tenant e device + limites
  -> transporte comercial do H.A.R.A. Commander via Cloudflare
  -> Agent na máquina do cliente -> execução e confirmação local
  -> resultado pelo mesmo Gateway ao ChatGPT
```

**Todas as chamadas do plugin público passam pelo Gateway da H.A.R.A.** Os argumentos e os resultados transitam por esse Gateway. O sistema do cliente executa as ações; o HARA Services administrativo *não* é o proxy do MCP comercial. O cliente não precisa criar uma chave OpenAI Platform nem configurar um túnel da OpenAI. A integração ao ChatGPT exige autenticação OAuth normal e, enquanto o plugin não for publicado, uma conexão MCP personalizada por URL.

O Commander Direct (Secure MCP Tunnel da OpenAI, privado por workspace) permanece como **opção avançada Linux**, sem ser um pré-requisito do lançamento comercial.

## Privacidade — declaração precisa e verificável

- No modo Cloud, dados dos comandos **transitam** pela Cloudflare e não devem ser descritos como exclusivamente locais ou como inacessíveis à H.A.R.A.
- O fallback de fila durável atualmente **persiste `payload_json` e `result_json` em D1**, para executar/retornar a solicitação mesmo diante de indisponibilidade temporária. O TTL nominal de chamada é **50 segundos**. A rotina de manutenção é acionada em cron (`17 * * * *`); por isso, a efetiva redação pode ocorrer mais tarde, sem garantia de apagar exatamente aos 50 s. Após a redação, permanecem marcadores SHA-256, metadados e eventuais logs de infraestrutura conforme a política aplicável.
- Há um canal transitório Event V2 quando as condições de conexão permitem, que não precisa gravar os conteúdos de tool calls em D1. Isso **não** autoriza prometer zero persistência em todos os caminhos.
- O sistema mantém metadados operacionais e contagem de transações. A política comercial não deve alegar que a H.A.R.A. não processa ou não vê conteúdo transmitido pelo Gateway.
- Não enviar comandos/arquivos para treinamento de IA H.A.R.A.; analítica de aprendizado é limitada a sinais derivados e sem conteúdo, conforme o contrato existente.
- O Agent mantém autorizações locais; uma solicitação Cloud não ignora uma recusa ou política de segurança do usuário.

## Mudanças realizadas na fonte candidata

- `apps/commander/public/install/linux.sh`: **OUTBOUND_RELAY** padrão de novos clientes; DIRECT requer seleção explícita. Bloqueio de autostart Direct em transporte Cloud; `update` baixa `tunnel-client` apenas quando necessário; instrução pós-instalação informa URL comercial + OAuth.
- `apps/commander/public/index.html` + `app.js`: onboarding Cloud-first, modo Direct avançado e revelação explícita do trânsito de conteúdo pelo Gateway. Seleção de transporte Linux no comando gerado; Direct não oferecido no Windows.
- `apps/commander/plugin-submission/plugin.json`, `mcp.json` e `assets/{logo,icon}.png`: **rascunho de submissão**, com identidade H.A.R.A. Labs e capivara, endpoint comercial único, cinco casos positivos e três negativos de revisão. Nenhuma chave/reviewer password no repositório.
- `apps/commander/scripts/validate_cloud_launch_contract.py`: testa separação Cloud/Direct, identidade, endpoint, pacote, logo e o aviso de retenção transitória de conteúdo.
- Preservados `validate_prod_static.py`, `validate_linux_tunnel_start_modes.py`, `validate_local_tunnel_control_plane.py`, `validate_customer_privacy_noc_contract.py` e testes Node MCP.

## Publicação segura

A versão 0.3.41 do Agent/instaladores continua a única **release estável assinada** em produção. A fonte 0.3.43 é candidata e ainda não pode ser promovida para distribuição sem resolver a divergência legítima entre a chave privada de assinatura e a JWK pública fixada. **Não** desabilitar assinatura nem trocar âncora de confiança sem autorização formal.

As mudanças da interface Cloud podem ser publicadas separadamente mediante staging com os quatro binários e manifesto/sig/SHA256SUMS **exatamente iguais aos assinados 0.3.41**, sem contaminar o release. Só anunciar deploy quando houver readback real.

## Pendências externas / antes do diretório

1. Homologar a **conexão do ChatGPT ao MCP comercial** (não o Baseline Services) com conta de cliente de teste via OAuth; ler e executar uma operação autorizada na máquina de demonstração, com recibo, isolamento e negados.
2. Verificar oficialmente a identidade da H.A.R.A. Labs na OpenAI, garantir permissões de gerenciamento e completar o desafio de domínio exigido na interface de submissão.
3. Registrar vídeo demonstrativo, criar uma conta de revisor com dados de demonstração e comprovar os 5 casos positivos e 3 negativos; os casos do pacote são **roteiros propostos**, não provas executadas.
4. Completar verificação de segurança e submissão do pacote na OpenAI. A aprovação/publicação é externa; o ícone da capivara aparecerá como identificação do plugin somente após instalação/conexão aprovada.
5. Ativar Stripe com credenciais e validação de checkout quando for comercializar planos pagos. Não bloquear testes beta gratuitos por isso.

Documentação atual: https://developers.openai.com/plugins/deploy/submission

## Evidência desta rodada

- `validate_cloud_launch_contract.py`: PASS.
- `validate_prod_static.py`: PASS.
- `validate_linux_tunnel_start_modes.py`: PASS.
- `validate_local_tunnel_control_plane.py`: PASS.
- `validate_customer_privacy_noc_contract.py`: PASS.
- `test_customer_mcp_simple_profile.mjs` e `test_customer_mcp_edge.mjs`: PASS.
- `node --check apps/commander/public/app.js` e `bash -n apps/commander/public/install/linux.sh`: PASS.
- A release signature de 0.3.43 **continua pendente**; não confundir a validade do código candidato com a publicação de um Agent assinado.

## 2026-10-09 — Zigurat / HARA Identity / OpenAI OAuth contract reconciliation

- O emissor de tokens do Zigurat/HARA Identity **já existe**; não criar novo gerador. O HARA Identity já anuncia `issuer=https://auth.haralabs.com.br`, `authorization_endpoint`, `token_endpoint`, `registration_endpoint=https://auth.haralabs.com.br/oauth/v2/register` e `code_challenge_methods_supported=["S256"]`. A descoberta OAuth protegida do MCP comercial aponta para essa autoridade.
- A autorização do usuário no Identity **não é** a assinatura criptográfica da release do Agent. A 0.3.41 está assinada e ativa; a assinatura da candidata 0.3.43 depende de custódia adequada da chave de release, separadamente do Identity.
- O rascunho de `apps/commander/plugin-submission/mcp.json` foi corrigido para declarar `extensions.com.openai.auth.type=oauth`, `client.mode=dcr`, `authorizationServerBase=https://auth.haralabs.com.br`, `resource=https://commander.haralabs.com.br/api/mcp` e `baseScopes=["openid"]`. Nenhuma chave/token de cliente foi incluída.
- `validate_cloud_launch_contract.py`: agora exige exatidão do contrato OAuth/DCR, PASS. `test_hara_identity_customer_mcp.mjs`: PASS. Verificação do OIDC público: registro e S256 anunciados.
- PONTO QUE AINDA NÃO TEM PROVA: o endpoint DCR aceitar o registro real do cliente **ChatGPT**, e a autorização PKCE devolver um token com audiência/escopo admitidos pelo MCP comercial. Um `registration_endpoint` presente no discovery NÃO constitui prova de DCR funcional. Não confundir um token HARA válido para outros clientes com o token emitido para o cliente OAuth do ChatGPT.
- Submissão/publish no diretório OpenAI: verificação empresarial, comprovação de domínio, scan de ferramentas, testes reais (5 positivos/3 negativos), vídeo e aprovação. Independente da autenticação implementada pelo Zigurat.
- Não alterar credenciais nem a implantação PROD por essa correção de pacote (somente draft). Nenhuma publicação ou aprovação OpenAI foi realizada aqui.

## 2026-10-09 — live OAuth/DCR blocker isolated to Identity gate (not token generator)

- Live ZITADEL/HARA Identity OIDC issuer, PKCE S256, endpoints and customer-MCP protected resource metadata: **PASS**.
- OIDC discovery advertises `registration_endpoint`, but RFC 8414 OAuth authorization server metadata **does not** advertise it; `client_id_metadata_document_supported=false`.
- Identity Storage `hara-identity-zitadel-dcr-gateway-1` is HEALTHY but **mode=closed**, compose `HARA_DCR_GATEWAY_MODE: closed`, `HARA_DCR_REGISTRATION_ADVERTISED: "false"`. A controlled invalid `POST /oauth/v2/register` is rejected HTTP **404**, consistent with closed guard.
- Existing Identity worktree `local/identity-dcr-refresh-20261008` already contains guarded DCR promotion + atomic rollback and synthetic security tests (PASS); activation requires authorized ZITADEL owner PAT via private local file and production promotion from the Identity host. **Not executed**; no PAT accessed or exposed.
- New customer-side preflight: `apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect closed` PASS; `--expect guarded --require-ready` fails closed as expected.
- Active blocker for ChatGPT consumer OAuth: **DCR not promoted**. Once governed promotion passes, configure custom MCP connection in ChatGPT with normal HARA Identity consent/PKCE and execute actual commercial tool through Cloudflare (not Services Baseline). No new token generator needed.
- Evidence/runbook: `docs/operations/HARA_COMMANDER_ZITADEL_DCR_GATE_20261009.md`. Signed 0.3.41 fleet and Cloudflare endpoint remain unchanged.

## 2026-10-09 — DCR GUARDED ativado, registro OAuth real homologado

**CURRENT GATE: `HARA_DCR_EDGE_RECONCILIATION=PASS`.** O usuário leu no Storage, com a própria credencial de proprietário, os flags reais do ZITADEL `dynamicClientRegistration.enabled=True` e `allowUnauthenticated=True`. Não recriar PAT, não reverter flags para `False/False` e não executar novamente o antigo `promote_mcp_dcr_guarded.py` que exige backend fechado.

- Nova rotina canônica `apps/identity-login/scripts/reconcile_mcp_dcr_existing_backend.py` (branch Identity `local/identity-dcr-refresh-20261008`) reconcilia **somente o Gateway público e o anúncio RFC 8414**, mantendo ZITADEL/backend intocados. Aplicada pelo Storage com root e testes de backup, rollback, fail-closed e idempotência PASS.
- Configuração PROD Storage: `HARA_DCR_GATEWAY_MODE: guarded`; `HARA_DCR_REGISTRATION_ADVERTISED: "true"`. DCR positivo: cliente OAuth temporário registrado HTTP 201, consultado HTTP 200, excluído HTTP 204; limpeza PASS. DCR negativo: `400 invalid_client_metadata`. Health do ZITADEL/login e dos dois serviços de borda PASS.
- HARA Commander público: `python3 apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect guarded --require-ready` PASS. `/api/mcp?profile=simple` sem token ainda 401. Os nomes das três configurações de audiência e introspecção aparecem no catálogo de segredos do Worker PROD (não foram revelados valores).
- Rotina atual em Storage: `/srv/hara/identity/operations/reconcile_mcp_dcr_existing_backend.py --backend-already-enabled`, que verifica `HARA_DCR_EDGE_ALREADY_GUARDED=PASS` e retorna `HARA_DCR_EDGE_EXECUTE=NO_CHANGE` sem modificar serviços.
- Candidato do plugin `apps/commander/plugin-submission/mcp.json` permanece apontando para o MCP comercial com DCR da Identity; **não é necessário Secure MCP Tunnel OpenAI por cliente**.
- **ÚNICO GATE COMERCIAL ainda pendente:** ChatGPT concluir consentimento OAuth/PKCE e entregar token de usuário aceito pelo Worker, depois ChatGPT invocar ferramenta no Agent pelo MCP **COMERCIAL** (não pelo Baseline administrativo), isolamento/permissões e revisão/publicação na OpenAI. Não afirmar que a sessão ChatGPT foi homologada, que o app está publicado nem que o Worker valida todo token real antes da prova E2E.
- Evidência autoritativa da frente de Identity: `docs/status/HARA_COMMANDER_MCP_DCR_GUARDED_LIVE_20261009.md`.
