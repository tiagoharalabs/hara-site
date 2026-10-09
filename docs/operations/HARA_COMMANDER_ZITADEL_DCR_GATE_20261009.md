# H.A.R.A. Commander — diagnóstico DCR real no ZITADEL / HARA Identity (2026-10-09)

## Decisão e bloqueio único da autenticação inicial do ChatGPT

Produto público: `https://commander.haralabs.com.br/api/mcp?profile=simple` (Cloudflare customer MCP; **não** MCP administrativo HARA Services).
Autenticação: HARA Identity / ZITADEL 4.17.3, OAuth Authorization Code + PKCE S256, registration mode DCR conforme pacote `apps/commander/plugin-submission/mcp.json`.

**Evidência live em 2026-10-09:**

- MCP protegido: `GET /api/mcp?profile=simple` não autenticado -> HTTP 401 (PASS).
- PRM: `GET /.well-known/oauth-protected-resource/api/mcp` -> 200, aponta para `https://auth.haralabs.com.br`, resource `https://commander.haralabs.com.br/api/mcp` (PASS).
- OIDC da Identity: issuer/auth/token e PKCE S256 válidos; `registration_endpoint` anunciado.
- **RFC 8414**: `GET https://auth.haralabs.com.br/.well-known/oauth-authorization-server` -> 200, mas **não** anuncia `registration_endpoint` e informa `client_id_metadata_document_supported=false`.
- **Gateway real**: contêiner `hara-identity-zitadel-dcr-gateway-1` versão `v0.2.0`, HEALTHY, porém `mode=closed`; registro no `POST /oauth/v2/register` retorna **404**, como política fail-closed, quando testado com user-agent definido (um primeiro teste sem user-agent teve 403 transitório; readback repetido confirmou 404).
- Compose live no Storage: `HARA_DCR_GATEWAY_MODE: closed` e `HARA_DCR_REGISTRATION_ADVERTISED: "false"`.
- Validador da frente Identity `validate_mcp_oauth_metadata_live.py --expect-cimd disabled --expect-dcr disabled`: PASS.
- Validadores e simulações do guard `test_mcp_dcr_gateway.mjs` e `validate_mcp_dcr_promotion.py`: PASS.
- Teste novo no Commander: `python3 apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect closed`: PASS, com `CHATGPT_DCR_REGISTRATION=BLOCKED_BY_CURRENT_CONFIGURATION`. Quando exigido `--expect guarded --require-ready`, falha intencionalmente (não está pronto).

**Conclusão:** o ZITADEL **não precisa de um novo gerador de token**. A infraestrutura de registro público dinâmico **existe, mas não foi promovida do modo closed para guarded**. Descoberta OIDC anunciar `registration_endpoint` não substitui uma verificação real de POST e não prova que um cliente ChatGPT foi registrado.

## Promoção governada já implementada pela frente de Identity

O script canônico existente está no worktree isolado de Identity:
`/srv/hara/repos/local-git-gateway/worktrees/hara-site/identity-dcr-refresh-20261008/apps/identity-login/scripts/promote_mcp_dcr_guarded.py`
(branch `local/identity-dcr-refresh-20261008`, commit de referência `b13d1c9`).

Procedimento **somente no host Identity/Storage com autenticação de proprietário autorizada**, fora do chat:

1. Confirmar preimage CLOSED, backend ZITADEL DCR desabilitado, RFC8414 DCR não anunciado, imagens DCR v0.2.0 e metadata v1.1.0 com health PASS.
2. Usar o PAT administrativo de proprietário do ZITADEL via **arquivo privado protegido**, com `--pat-file`; jamais expor, criar token falso ou colar aqui. Compose canônico: `/srv/hara/identity/compose/compose.yml`.
3. Executar primeiro **sem** `--execute` (dry-run de preflight) e só então `--execute` dentro de uma janela de mudança autorizada.
4. O mecanismo existente habilita DCR backend, muda gateway `closed -> guarded`, anuncia DCR no RFC8414, valida readback público e registra preimage/rollback; em falha tenta restaurar compose e política anterior.
5. Depois do sucesso:
   `python3 apps/commander/scripts/commander_cloud_oauth_live_readiness.py --expect guarded --require-ready` deve passar e o POST inválido deve receber `400 invalid_client_metadata` (não cadastrar cliente nessa prova negativa).
6. **Homologação E2E real, separada:** registrar cliente OAuth do ChatGPT na interface de Plugins, completar consentimento do usuário e PKCE, obter token que o MCP aceite com issuer/audience/scope corretos, executar `ping` e `get_device_info` no Núcleo pelo MCP comercial, verificar recibo sem HARA Services Baseline.
7. Executar casos de isolamento/permissões e coletar vídeo/credenciais de conta DEMO em campo privado antes de submissão à OpenAI.

**Não realizado em 2026-10-09:** promoção DCR PROD, criação de cliente OAuth real, consentimento no ChatGPT, troca de token, submissão ou aprovação do plugin. O escopo desta rodada foi descoberta, prova negativa e gate automatizado, sem acesso a PAT administrativo.

## Riscos e limites

- DCR habilita registro público de clientes OAuth sob validação/rate-limiting; é mudança global da política de segurança do ZITADEL. Não habilitar diretamente o backend nem mudar arquivos compose manualmente contornando o guard e rollback.
- O plugin é distribuído pelo MCP comercial da Cloudflare. O Gateway vê/trafega comandos e respostas; fallback D1 persiste temporariamente conteúdo (TTL nominal 50 s, com redação assíncrona). Não prometer trânsito 100% direto pela OpenAI nessa modalidade.
- A versão assinada de Agent público é 0.3.41 em sete máquinas; assinatura da candidata 0.3.43 continua uma frente separada.
- O endereço para o proprietário completar cadastro/publicação do plugin, após gate OAuth, é https://chatgpt.com/plugins; a OpenAI exige verificação do desenvolvedor e revisão do MCP.

## Verificação adicional em 2026-10-09 — credencial REAL existente, promoção bloqueada pela ferramenta

A pedido do fundador, foi confirmado que **o PAT de proprietário existe** no host Storage, no caminho canônico `/srv/hara/identity/secrets/identity-owner.pat`, com proprietário root e modo 0600. Não foi lido, exibido ou transferido. O usuário `sartorius` tem acesso de execução a `sudo -n python3 --version` no Storage, porém **o comando canônico de preflight que referencia o PAT foi recusado pelas configurações de segurança do conector**, antes da execução. Não procurar outro método de bypass.

A rotina `promote_mcp_dcr_guarded.py` da frente `local/identity-dcr-refresh-20261008` foi copiada para `/tmp/hara-dcr-guarded-canonical-20261009.py` no Storage, sem quaisquer segredos, e conferida por SHA-256:
`1edf9837bba41e1beecd6bae02917558e67d7d293c9fed0fcf327fc8ceb03984`.
`--self-test` PASS. **Dry-run com PAT não executado, `--execute` não executado.**

O administrador do Storage pode usar o console local legítimo e a rotina já preparada para executar **primeiro preflight sem `--execute`**, depois **promoção com `--execute`** somente se o preflight passar. Argumentos canônicos já suportados pelo script: `--pat-file /srv/hara/identity/secrets/identity-owner.pat --compose-file /srv/hara/identity/compose/compose.yml`. O próprio script contempla backup do compose, readback do guard e rollback no caso de falha.

Readback final: `HARA_DCR_GATEWAY_MODE: closed`, `HARA_DCR_REGISTRATION_ADVERTISED: "false"`, runtime health mode `closed`. **Não afirmar que o DCR foi promovido nem que o plugin está homologado.** Após promoção pela via autorizada, rodar o teste `commander_cloud_oauth_live_readiness.py --expect guarded --require-ready`, depois consentimento OAuth real do ChatGPT, chamadas MCP comerciais e testes da submissão.
