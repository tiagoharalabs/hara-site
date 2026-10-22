# H.A.R.A. Commander — revisão de autorização persistente, conexão e histórico

**Data do levantamento:** 21/10/2026 (BRT)  
**Natureza:** descoberta / requisitos / proposta — **SOMENTE DOCUMENTAÇÃO, SEM IMPLEMENTAÇÃO**.  
**Origem:** solicitação do proprietário, painel PROD em `commander.haralabs.com.br/#devices` e leituras somente leitura do código local do Commander no Núcleo A e Services.  
**Autoridade comercial:** Commander **produto** `https://commander.haralabs.com.br/api/mcp?profile=simple`, nunca confundir com Commander Baseline/MCP interno.  
**Estado:** `REQUIREMENTS_CAPTURED / DESIGN_PROPOSED / OWNER_REVIEW_REQUIRED / NO_RUNTIME_MUTATION`.

## 1. Comportamento solicitado pelo proprietário

> A autorização de uso não deve expirar por seis horas, 12 horas nem 24 horas se o dispositivo foi validado pelo HARA Identity e seu vínculo continua autorizado. Deve permanecer até a revogação do proprietário. A **conexão** não deve ser considerada ativa se cair ou se o operador a encerrar. O histórico deve ser opcional e o usuário deve poder limpar a visualização, inclusive de dispositivos revogados.

**Distinções contratuais obrigatórias:**

1. **HARA Identity / OAuth:** autenticação de pessoa/cliente e emissão/validação de credenciais de login; tokens continuam com expiração própria e não devem virar tokens eternos.
2. **Autorização durável do dispositivo:** concessão explícita do proprietário, vinculada a tenant, subject/role, Device ID, escopo e versão de política. Estado `AUTHORIZED_UNTIL_REVOKED`, sem expiração arbitrária de seis horas. Não equivale a sessão ativa.
3. **Lease técnica assinada:** acesso temporário de produto, assinatura e quotas, com `exp` e renovação governada **sem novo código de pareamento** enquanto a autorização durável estiver válida e o HARA Identity/tenant estiverem autorizados. Uma lease expirada não deve permitir execução offline.
4. **Conexão / sessão de operador:** estados separados `CONNECTED`, `OFFLINE`, `DISCONNECTED_BY_OPERATOR`, `REVOKED`. Ao cair o WebSocket ou sessão, bloquear novas execuções imediatamente. Encerramento voluntário cancela a sessão e **proíbe auto-retomada silenciosa**. Para queda involuntária, uma eventual reconexão automática é outro controle explícito, com novo handshake e revalidação, nunca baseada apenas num token antigo.
5. **Política de aprovação de comandos:** `ASK_EVERY_ACTION`, `SESSION_TRUSTED`, `PERSISTENT_TRUSTED` são preferências distintas de autorização de acesso: não convertê-las automaticamente em `PERSISTENT_TRUSTED`. "Permitir tudo" no plugin ChatGPT não substitui a escolha local de permissão do computador.
6. **Histórico:** sessão nova do MCP começa sem despejar registros passados; a seção Histórico pode mostrar registros quando solicitada. Limpeza do histórico visual e eliminação permanente de dados elegíveis são ações diferentes, cada qual com escopo, confirmação e auditoria apropriados.

## 2. Código realmente consultado — baseline local, não garantia de PROD

| Local observado | Git | Atenção |
|---|---|---|
| Núcleo A: `/home/sartorius/hara-worktrees/commander/incident-20261021-v2-presence` | `fix/commander-v2-presence-20261021`, HEAD `19ccf2fe9db83e311f8828f9525017432fd97d2f`, **limpo** | Essa frente pertence ao Codex; não tocar no checkout nem assumir que foi publicada. |
| Services: `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current` | `local/commander-product-current`, HEAD `f9f90078c5a8c4de914dd290e12607b8ecc8772c`, **com alterações anteriores** | Preservar staging e autoria do Codex, especialmente os quatro arquivos Windows modificados. |
| GitHub `hara-site/main` | `b2b34ca4b14fc3a13aa5368a7da8b73b1342bf65` no readback | Main não é necessariamente o código que roda em PROD; exigir reconciliação da versão Worker antes de qualquer rollout. |

**Achados de código nas duas árvores locais:**

- `apps/commander/src/worker.js`: `PRODUCT_LEASE_TTL_SECONDS = 6 * 60 * 60`; a lease RS256 assinada recebe `valid_until_utc`. No fluxo `LOCAL_TUNNEL`, `deviceProductLease()` exige um novo `authorization_code` de uso único antes da lease e grava `local_authorized_until_utc = valid_until_utc`.
- `DEVICE_AUTHORIZATION_CODE_TTL_SECONDS = 10 * 60`: código de uso único expira em dez minutos; **não modificar apenas porque a permissão durável será persistente**.
- `apps/commander/public/app.js` e `index.html`: literalmente `Autorizar por 6h`, `Renovar autorização (6h)`, `Autorização local por 6 horas` e `Código válido por 10 minutos · lease válida por 6 horas`. `deviceReadiness()` exige lease válida para declarar `LOCAL_TUNNEL` pronto.
- `apps/commander/public/agent/linux.py`: `PRODUCT_LEASE_REFRESH_SECONDS = 4 * 60 * 60`; `verify_product_lease_token()` rejeita lease com `exp-iat > PRODUCT_LEASE_REFRESH_SECONDS + 3h` (**limite de sete horas**). Mudar a lease do Worker diretamente para 24 horas quebraria o Agent existente. Assinatura, aud/iss, Device ID e escopo devem continuar validados.
- `apps/commander/src/product-lease.mjs`: token assinado RS256 com `iat`, `exp`, `jti`, `iss`, `aud` e lease incorporada. Manter expiração e verificação criptográfica no token técnico.
- `apps/commander/src/auth.js`: portal HARA Identity com `SESSION_SECONDS = 8h`, sessão degradada 30 minutos e toque de presença 30 minutos. **Login do portal não é licença permanente do dispositivo**; não expandir cookie para 24h como substituto da autorização durável.
- `apps/commander/src/worker.js`: `deviceOnline()` para Event V2 usa idade de `last_seen_at_utc` em janela de sete horas; `LOCAL_TUNNEL` retorna falso nessa função porque existe um caminho direto distinto. Uma autorização persistente **não deve ampliar** o indicador ONLINE nem ressuscitar socket morto.
- `apps/commander/src/worker.js`: `listDevices()` inclui ACTIVE e REVOKED; `revokePortalDevice()` marca `REVOKED`, remove seleções e cancela chamadas pendentes. A revogação de cliente também tem `revokeDeviceSelf()`; falta especificar neutralização de lease direta já emitida para uma sessão ainda aberta.
- `apps/commander/public/app.js`: abas `Ativos`/`Histórico` separadas; no Histórico, os dispositivos revogados continuam visíveis. Não foi encontrado endpoint de limpeza `/api/portal/devices/history/clear` no Worker consultado.
- `apps/commander/src/worker.js` preserva histórico detalhado preferencialmente **local**, agregados/snapshots sanitizados e fallback legado de chamadas no cloud. NÃO tratar limpeza da lista de dispositivos revogados como exclusão de todo o histórico de execução.

**Ponto de arquitetura:** presença Event V2 é frente própria (`hara-site#163`). O bug de reconexão/last_seen preparado no commit local `19ccf2f` continua condicionado a canário, versão Worker PROD exata, rollback e provas de LIVENESS; não misturar sua correção com mudança de autorização.

## 3. Contrato proposto — autorização persistente

**Estado durável canônico (proposta, não schema aplicado):** autorização por `tenant_id + device_id + grant_id`, `granted_by_subject_id`, escopos, `granted_at_utc`, `revoked_at_utc`, `authorization_epoch`, `last_verified_at_utc`. Nunca persistir token em claro como fonte de verdade. O Device ID sozinho ou a existência de token de enrollment não bastam para autorizar execução.

**Transição inicial:** OWNER autenticado via HARA Identity + dispositivo pareado válido + confirmação inequívoca do consentimento -> `GRANTED`. O código de bootstrap continua one-time/10 minutos. Requisições subsequentes de lease consultam a autorização durável, tenant/usuário ativos, modo e políticas antes de renovar credencial técnica. Fluxo independente para `EVENT_V2` e `LOCAL_TUNNEL` deve manter equivalência de segurança.

**Revogação:** portal ou ação local pode revogar. No servidor, revogação deve invalidar autorização, novas emissões de lease, chamadas em fila e reconexões; um controle por `authorization_epoch`/geração de permissão deve barrar tokens antigos mesmo se assinados e não expirados. Na conexão direta, sem acesso confiável ao servidor, **falhar fechado para novas chamadas**, para não criar uma janela de 6h de comando após a revogação. A revogação de acesso é distinta de `Desconectar`.

**Conexão:**
- `CONNECTED`: canal realmente autenticado e comprovadamente roteável, com frescor técnico e observabilidade independente de TTL da autorização.
- `OFFLINE_NETWORK`: conexão perdida, nenhuma chamada nova executável, autorização durável permanece registrada mas **não é uma sessão ativa**.
- `DISCONNECTED_BY_OPERATOR`: sessão encerrada pelo operador; `AUTO_RECONNECT` não pode restabelecer execução sem nova ação explícita do operador.
- `REVOKED`: credencial inabilitada; não reativar usando refresh, histórico, cookie ou novo socket. Reenrollment requer fluxo autorizado distinto.

**Decisão UX a preservar:** o proprietário rejeita a exigência de reautorizar a cada seis horas. Nenhuma proposta de autenticação persistente deve eliminar a possibilidade de revogar, de encerrar a conexão nem os limites de permissões locais.

## 4. Histórico e dispositivos revogados

A aba `Histórico` no portal já apresenta dispositivos `REVOKED`; no snapshot, havia oito cadastros históricos e dez ativos. O produto precisa oferecer duas ações com significado explícito:

- `Limpar lista de dispositivos revogados` e `Remover do meu histórico`: ocultação persistente dos itens selecionados **somente no escopo autorizado do usuário/tenant**; sem reativação, sem reinicialização e sem excluir os tombstones necessários para impedir reutilização de credenciais.
- `Limpar histórico de execuções`: administrar separadamente o histórico de dados local do Agent, dados elegíveis do portal e a retenção de metadados; oferecer confirmação, contagem, escopo, exportação opcional, política de retenção e recibo. Registros obrigatórios antifraude/auditoria não podem desaparecer sem política documental e base legal adequadas.

**Modelo de implementação a avaliar:** tombstone/visibilidade por usuário ou tenant em tabela isolada (ex.: `commander_device_history_visibility`) com `hidden_at_utc`, `hidden_by_subject_id` e origem da ação; listar apenas os itens visíveis. Evitar `DELETE FROM commander_devices` indiscriminado: `commander_device_calls`, orçamentos/telemetria e relatórios usam FKs; em alguns schemas há `ON DELETE CASCADE`. Uma exclusão física cascata é **inadequada** para um simples botão de "Limpar histórico".

Acesso à aba `Histórico` é opcional; não despejar eventos de sessões anteriores na abertura do MCP/console. Novos eventos devem aparecer sem duplicação e os anteriores somente por consulta explícita. Cuidado com as necessidades de acesso/supervisão e auditoria do proprietário.

## 5. Frentes, prioridade e provas exigidas (sem intervenção agora)

| Frente | Prioridade | Owner sugerido | Trabalho a planejar |
|---|---|---|---|
| Separar permissão durável de product lease `6h` | P0 produto | `hara-site#310` + segurança `#189` | Contrato com Identity, modelo de dados, renovação e revogação, migração backward-compatible |
| Connection close / revogação imediata / reconnect | P0 segurança | `#189` + Event V2 `#163` | EPOCH/revocation, estado da sessão, cancelamento, sem auto-retomada após STOP |
| UI autorização persistente e estados claros | P1 UX | `hara-site#310` | Remover texto `6h` só após backend/Agent; apresentar `Autorizado até revogar` e estados `Conectado/Offline/Encerrado` |
| Limpeza da lista de revogados | P1 UX/privacy | `#310` + `#189` | Ocultação com isolamento multi-tenant e tombstone preservado |
| Limpeza do histórico de execuções | P1 privacy | `#310` + `#189` | Política local/cloud, retenção, confirmação, escopo e testes de privacidade |
| Compatibilidade Windows | P1 homologação | `hara-site#240` | Preservar 0.3.55, handshake e terminologia compatíveis, sem downgrade |
| Estabilidade de presença Event V2 | P0 paralelo, não confundir com autorização | `hara-site#163` | LIVENESS, last_seen, DO/WSS e rollback independente |

**Critérios de aceite antes de disponibilizar ao cliente:** provar autorização além de 6/8/12/24h sem pedir novo código; renovar lease técnica automaticamente sem ampliar arbitrariamente sua validade; negar uso após revogação (inclusive lease já emitida); queda da rede gera OFFLINE e bloqueia execução; STOP local não reabre silenciosamente; tenant B não pode reusar grant/histórico de A; HARA Identity desativado bloqueia novo uso; histórico revogado fica oculto após limpeza voluntária e não ressuscita após login; auditoria mínima e recibos permanecem; migração e rollback não prejudicam Agents existentes e não alteram unidades de cobrança.

**Não basta:** mudar o rótulo do botão, trocar `PRODUCT_LEASE_TTL_SECONDS` de 6 para 24 horas, mudar `SESSION_SECONDS` para 24h, ampliar `deviceOnline()` para 24 horas, ou apagar fisicamente todas as linhas `REVOKED`.

## 6. Gates de implantação e limites desta revisão

- Conferir PROD Worker atual com ID de deployment, bindings, schema D1, assinatura e capacidade; `main` e worktrees locais **não** equivalem automaticamente a PROD.
- Exigir revisão de segurança para credenciais persistentes e revogação instantânea; instrumentar testes sintéticos 0/6/12/24h e E2E Windows/Linux com HARA Identity, incluindo D1 e regressão de quotas.
- Autorizar somente em branch do owner com diff, CI, plano de rollback e aceitação formal. Este documento **não** é autorização para deploy, restart, sudo, migração ou modificação de instalações.
- Manter patch Event V2 `19ccf2f` na fila própria; não fazer cherry-pick na frente de UX, nem reabrir frentes fechadas.

**Alterações de runtime feitas durante este levantamento:** **ZERO**.  
**Entrega esperada nesta branch:** este registro documental, revisável pelo Codex e proprietários das issues — nenhuma alteração funcional.
