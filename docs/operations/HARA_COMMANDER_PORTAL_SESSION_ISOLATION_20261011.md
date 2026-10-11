# H.A.R.A. Commander — isolamento de leituras entre sessões (11/10/2026)

## Problema reproduzido

Respostas atrasadas das APIs de identidade, bootstrap, dashboard, dispositivos e faturamento podiam completar depois de logout ou troca de sessão e repovoar UI/caches com informações da sessão anterior. O coordenador já invalida leituras em writes e o histórico de atividade tinha geração própria, mas o código dos outros loaders não validava que o contexto da sessão permanecia atual depois dos awaits.

Teste novo usa trechos **exatos do app.js** via VM, respostas assíncronas controladas e nenhum dado real de cliente. Antes: 3/11 PASS, 8/11 FAIL. Após correção: 14/14 PASS incluindo três corridas de billing/solicitação beta. A suíte de atividade já existente foi mantida e passou 25/25.

## Correção

- Um contador portalSessionGeneration é incrementado quando a sessão sai do contexto autenticado; `setGuestHeader()` cancela leituras pendentes do coordenador com `portalFetch.invalidate()`.
- `hydrateSessionHeader`, `loadPortalBootstrap`, `loadProductDashboard`, `loadDevices`, `loadBillingState` verificam o contador após os awaits relevantes, antes de gravar cache, atualizar DOM ou disparar novos GETs.
- Respostas 401 atrasadas não encerram uma sessão mais recente; erros antigos não mostram banners referentes a outro usuário.
- Leituras que continuam válidas, o visual aprovado, a estrutura do portal e os limites de custo continuam sem alteração.
- A proteção é **por aba** e cobre os fluxos enumerados, não promete coordenação automática entre navegadores/tabs nem substitui isolamento multitenant no servidor.

## Verificação / rollout

Script `apps/commander/scripts/test_portal_session_isolation.mjs`; integra o gate offline completo. Script preexistente `test_usage_activity_concurrency.mjs` recebeu somente stub de invalidação no VM para acompanhar a assinatura real de setGuestHeader. Nenhuma credencial de cobrança é necessária.

Os resultados locais não autorizam inferir certificação de 1.000 usuários reais. Rollout deverá manter assinaturas dos Agents e imagens estáticas intactas, atualizar apenas a versão da UI do Worker com stage comercial assinado e comprovar health/auth, versões DEV/PROD e GitHub CI.
