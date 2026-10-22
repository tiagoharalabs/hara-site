# H.A.R.A. Commander — reconciliação de entregas: confiança durável e histórico (R2)

**Data:** 21/10/2026 BRT (22/10 UTC)  
**Natureza desta revisão:** documentação e reconciliação **somente**. **ZERO alterações em runtime, bancos, Agents, instaladores, Worker PROD ou worktrees ativos** nesta etapa.  
**Continuação de:** [levantamento original](./HARA_COMMANDER_PERSISTENT_AUTHORIZATION_AND_HISTORY_REVIEW_20261021.md), commit documental `2b8c6e551d809c5c1324d146a103355ea1ec240d`. O documento original permanece como fotografia de requisitos de 21/10; este complemento registra implementação candidata posterior.

## 1. Readback: o que foi realmente entregue

| Linha | Estado verificado | Escopo / custódia |
|---|---|---|
| Requisitos e diagnóstico | **PUBLICADO GitHub (docs only)** | Branch `docs/commander-persistent-identity-history-20261021` |
| Código de autorização durável e histórico | **CANDIDATA LOCAL + GIT STORAGE, NÃO PUBLICADO NO PRODUTO** | Services `local/commander-durable-trust-20261022-r1`, commit `ea83525b6bc99a42f8c301517167dc8f352bb868`; `ls-remote origin` no Storage retornou SHA idêntico; checkout limpo |
| Código em execução em PROD | **ANTERIOR À CANDIDATA** | `GET /api/health` retornou 200. `/app.js` publicado SHA256 `badbac26a0128dbfa05809f65cb2ba1fe1ac671104b4171d6defaf93710ee27e` ainda contém “Autorizar por 6h” e “Renovar autorização (6h)” |
| Manifesto estável Linux público | **0.3.43** | `GET /release/agent-manifest.json`: `agent_version=0.3.43`, `channel=stable`; não confundir com instalação Founder |
| Frota privada | **10/10 ONLINE no snapshot** | Services, Núcleo A, Sentinelas A–D, Ninja Blue, Observer e Storage em Linux 0.3.54; Windows 11 em 0.3.55; não confundir disponibilidade atual com QA da implementação candidata |
| H.A.R.A. Identity público | **METADATA DISPONÍVEL** | Issuer `https://auth.haralabs.com.br`, metadados anunciam `authorization_code` e `refresh_token`. Metadados NÃO demonstram fluxo de rotação/recuperação de credencial de dispositivo |

**Sem equivalência automática entre Git local, Git do Storage, GitHub Web, deploy DEV e PROD.** A referência ao commit de código no Storage não significa que esteja na branch documental do GitHub, na `main`, na versão pública assinada, ou num Cloudflare Worker implantado.

## 2. Matriz requisito × candidata × lacuna

| Requisito do proprietário | Implementação candidata observada | O que ainda falta provar |
|---|---|---|
| Autorização persistente até revogar | `src/device-local-trust.mjs` e migração `0037` usam `local_persistent_trust_at_utc` para autorização direta concedida após código de uso único e modo `PERSISTENT_TRUSTED`. Registros legados permanecem `NULL` até consentimento | H.A.R.A. Identity E2E com dono autenticado; binding formal de quem concedeu, escopo, versão/grant epoch e alteração de permissões |
| Leases técnicas continuam curtas e renováveis | Worker mantém RS256 de 6h; `deviceProductLease()` permite refresh LOCAL_TUNNEL sem novo código quando trust ativo. Candidato Linux 0.3.54 agenda refresh antes do `exp`, com backoff | DEV hosted, compatibilidade Agent/Worker, clock skew, reboot/reconnect real, tráfego/custo, falhas de identidade |
| Código para confirmar o primeiro acesso | Código one-time do portal vinculado ao Device ID, TTL 10min. UI troca “Autorizar por 6h” por confirmação de acesso | Rejeitar replay e cross-tenant em DEV real; mostrar claramente que o código NÃO substitui a credencial durável do dispositivo |
| Reconexão após queda involuntária | A credencial do Agent é preservada; lógica candidata não exige novo pairing para renovar lease válida | Presença real e LIVENESS Event V2 `#163`, prova de status OFFLINE imediato e de reconexão segura com novo handshake |
| Encerramento voluntário é respeitado | A candidata mantém status direto distinto de Cloud e não reivindica ONLINE sem atestação | Testar STOP e proibição de auto-retomada silenciosa após reboot, socket superseded e unidades Windows/Linux |
| Revogação bloqueia comandos | Worker limpa o trust ao marcar REVOKED; LOCAL_TUNNEL candidato faz `POST /api/device/access-check` antes de cada execução, rejeita rede indisponível/token inválido (fail closed). Botão revogar passa a exigir resposta `REVOKED` e janela de confirmação 15s | Revogação real de device sintético DEV: token antigo rejeitado, lease pendente não utilizável, socket morto, race/in-flight e revogação em todos os transportes |
| Histórico de dispositivos revogados pode sumir | Migração `0038`: `device_history_hidden_at_utc` no registro; owner/admin oculta REVOKED na listagem do próprio tenant; chamadas/recibos mantidos | DEV D1, UI Brave, reconciliação por role e auditoria de quem ocultou, política de retenção e restore |
| Histórico de execuções limpo sob escolha | **NÃO IMPLEMENTADO na candidata**. Não confundir com ocultação da lista de revogados | Definir retenção/limpeza local e Cloud separadamente, sem apagar antifraude/auditoria nem recarregar histórico automaticamente |
| Recuperar/rotacionar credencial após invasão | **NÃO IMPLEMENTADO**. Autorização direta não é rotação de `HARA_DEVICE_TOKEN` | Fluxo separado HARA Identity + confirmação no Agent, token substituto atômico, invalidação do antigo, receipts, rollback sem reabrir credencial roubada |

## 3. Evidência de testes disponível — não ampliar o alcance

A branch de código isolada possui resultados de QA reportados:

- `test_device_local_trust.mjs`: **14/14** cenários, incluindo 6, 8, 12 e 24h **simulados**; NÃO é soak real de 24h.
- `test_durable_device_lifecycle.mjs`: **17/17** casos com funções reais extraídas do Worker em fixture sem dispositivo real, código único, renovação, cross-tenant e token REVOKED recusado.
- `test_local_agent_trust_guards.py`: **4/4** cenários de agendamento e **7/7** fail-closed para Agent candidato; testes de status, offline e erros HTTP sem credenciais reais.
- `test_revoked_history_visibility.py`: SQLite isolado, isolamento por tenant, sem `DELETE`, idempotência, preservação dos registros de auditoria e de dispositivos ativos.
- Node `--check` para três arquivos JS no Observer: PASS; candidato Linux com `--self-test` em ambiente isolado, versão lógica 0.3.54: PASS.
- Fonte foi commitada e sincronizada no Storage, sem modificar `commander-product-current` ou o checkout ativo do Codex.

**NÃO provado:** migrations 0037/0038 no D1 DEV real, HARA Identity + refresh/rotacionamento end-to-end, Windows 0.3.55 com novo protocolo, revogação hospedada, automação STOP/reconnect em rede real, custo/latência por chamada, assinatura/instalador de release da candidata, CI completo e smoke PROD.

## 4. Riscos de integração: blockers de gate, não de documentação

1. **Sequência de migrations:** outra frente isolada de Uso/Stripe preparou `0036_billing_period_start_20261021.sql` no commit Storage `aa324294c159cdd47de0cad97b775cd84ea5aa62`. Esta candidata acrescenta `0037` e `0038`. Reconciliar as frentes, fonte e ordem do migrator antes de rodar qualquer D1.
2. **Concessão de trust muito simplificada:** `local_persistent_trust_at_utc` é timestamp no device, não tabela imutável de `grant_id`/subject/escopos/`authorization_epoch`. Owner da segurança (#189) precisa decidir modelagem canônica, inibição de reuso após alterações de política e auditabilidade de consentimento.
3. **Revogação offline:** check vivo por tool do LOCAL_TUNNEL fecha novos comandos quando Cloud não está acessível. Isso melhora segurança, mas aumenta latência, dependência de rede e custo. Event V2, relay e agentes Windows precisam de provas equivalentes. A revogação não encerra automaticamente comandos já em andamento sem uma política de cancelamento/lease.
4. **Status ONLINE no modo direto:** o Worker não atesta a vivacidade real de LOCAL_TUNNEL. O rótulo “Direto — status no Agent” evita declaração falsa, mas um produto acabado precisa atestação independente de sessão se prometer status ONLINE global.
5. **Credenciais duráveis comprometidas:** o registro antigo permanece válido enquanto não revogado; um código de autorização inicial não implementa rotação. Recovery deve ser owner-authenticated, com prova do dispositivo e substituição atômica.
6. **Fechamento voluntário de sessão:** um `systemctl stop` não é revogação. O produto precisa garantir STOP respeitado, sem restart oculto nem “login” silencioso, preservando pairing para start posterior.
7. **Compatibilidade:** o Agent Linux candidato é um arquivo Python modificado, ainda **não assinado** e não incluído no manifesto estável 0.3.43. Não copiar sobre os nove Agents 0.3.54 funcionais sem assinatura/rollback. Windows permanece .55 e requer contrato equivalente.

## 5. Ordem recomendada de homologação, sem executar agora

1. Owners `#310` (produto) + `#189` (segurança): reconciliar branch documental com commit de implementação e opções de escopo/grant/epoch; revisar protocol contract.
2. Reconciliação de fonte PROD exata e PR com CI, migrations 0036/0037/0038 em DEV (backup/readback); `main` não prova paridade de PROD.
3. H.A.R.A. Identity DEV real: confirmação de primeira concessão, single-use/replay, token antigo após revogação, rotação por dono, cross-tenant, owner não autenticado, downgrade de permissões.
4. Agent/Worker DEV: expiração/renovação técnica 6/8/12/24h; offline, reconnect, STOP explícito, quotas, custo e latência, rollback.
5. Compatibilidade Windows 0.3.55 e Linux 0.3.54; assinar artefato público da revisão autorizada, canário isolado e voltar versão/estado anterior em falha.
6. Só depois, aprovação formal do proprietário para alteração em PROD, deploy Cloudflare/manifesto, smoke observável com receipts e comparação de hashes.

**Critério de chegada:** “Autorizado até revogação” e conexão realmente comprovada; nenhum novo pairing apenas por vencimento da lease, mas nenhum comando autorizado depois de revogação/desconexão. Histórico opcional e escopado sem reativação, segredo vazado ou perda de auditoria.

## 6. Handoffs, autoridade e locais

- Código candidato no **Services**, worktree `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-durable-trust-20261022-r1`, SHA `ea83525b6bc99a42f8c301517167dc8f352bb868`. Git remoto do Storage `ssh://storage/srv/hara/archive/github-mirrors/working/hara-site.git` com ref `local/commander-durable-trust-20261022-r1` na mesma revisão; **não é merge GitHub Web**.
- Handoff fonte: `docs/operations/HARA_COMMANDER_DURABLE_TRUST_AND_HISTORY_R1_20261022.md` dentro da branch local. Cópia somente leitura no Núcleo: `/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_DURABLE_TRUST_R1_20261022/README.md` com SHA256 `a63d1c6c031bab2e8576486747d4c404995f9ed4a661a277a4d750683b636b83`, idêntico à fonte.
- Issues: [produto #310](https://github.com/tiagoharalabs/hara-site/issues/310), [segurança #189](https://github.com/tiagoharalabs/hara-site/issues/189), [Event V2 #163](https://github.com/tiagoharalabs/hara-site/issues/163), [Windows #240](https://github.com/tiagoharalabs/hara-site/issues/240), [coordenação Codex #1953](https://github.com/tiagoharalabs/hara-platform/issues/1953).
- Material de suporte público já em #310: comentários `6330791676` (documentação original) e `6331053534` (candidata de código). Antes de resolver, comparar também as outras frentes de Uso e instalador público para não atropelar entregas.

**Ações desta revisão R2:** investigação, comparação de documentação/Git privado/GitHub e criação de complemento documental. Não executamos nenhuma migration, revogação de dispositivo, troca de credencial, SSH com sudo, reinício, alteração de código, deploy ou mudança de configurações da frota.
