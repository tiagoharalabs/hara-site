# H.A.R.A. Commander — handoff GitHub R24 para próximo chat

**Data de corte:** 21/10/2026 (BRT). **Repositório:** [tiagoharalabs/hara-site](https://github.com/tiagoharalabs/hara-site). Este documento existe numa branch de revisão; **não** representa merge na `main`, aprovação comercial, atualização de Cloudflare ou deploy de novos Agents.

## Onde buscar tudo que já foi feito

| Frente publicada no GitHub | Branch | Commit exato | Conteúdo |
| --- | --- | --- | --- |
| R11–R18, auditorias e reproduções | [review/commander-peer-audit-r18-20261021](https://github.com/tiagoharalabs/hara-site/tree/review/commander-peer-audit-r18-20261021) | `6b4d9ab892610bc6018a2d29dacd7a7caee57d1c` | R11 assinatura/download; R12 rollout Sentinela A; R13 idempotência; R14 compatibilidade Linux; R15 pacote imutável; R16 TOCTOU/upload e latência; R17 códigos de erro MCP; R18 proveniência do Worker |
| R19–R22 e atualização Windows | [review/commander-windows-history-r22-20261021](https://github.com/tiagoharalabs/hara-site/tree/review/commander-windows-history-r22-20261021) | `25923b3419adbdaad46166ecf44d654c8ec577be` | v5 assinado e 160/160 offline; matrizes R20; Storage/Observer R21; Windows 0.3.55 canário assinado, UX histórico e testes R22 |
| **Este handoff + backup R23 WIP** | [review/commander-handoff-r24-20261021](https://github.com/tiagoharalabs/hara-site/tree/review/commander-handoff-r24-20261021) | veja HEAD da branch | Este arquivo + fontes de histórico Linux/Windows R23 congeladas **como rascunho**. Não homologadas para deploy |

**Importante:** GitHub `main` permanece intocada. Não aplicar merge automático das três branches. São entregas de revisão, com testes de produto e artefatos públicos assinados, mas também contêm canários Founder ligados a uma identidade específica; não são releases comerciais prontos. Não publicar versões nem copiar tokens/configurações entre hosts.

## Estado observado no hardware e publicação

- **Linux Founder:** sete Agents `0.3.54` Event V2 (Núcleo A, Services, Sentinelas A/B/C/D, Ninja Blue), 31 funções iguais; R20 verificou pings, leitura, execução e RSA em 7/7. Persistem **duas variantes assinadas do loop Event V2**; a versão nominal é igual, mas builds não idênticos.
- **Linux comercial:** Storage Fedora43 x86_64 e Observer Ubuntu22 ARM64, **0.3.43**, `OUTBOUND_RELAY`, `ASK_EVERY_ACTION`, 31 funções; instalação real, MFA/identidade própria e leitures/ping testados na R21.
- **Windows VM:** `HARA_WIN11` Windows 11, Agent canário Founder **0.3.55** instalado em 21/10 a partir de manifesto **RSA v2** assinado para essa VM, mesma identidade, tarefa do Agent Running e backup da `0.3.53` verificado. R22 `ping`, `device.info`, Unicode, CAS, PowerShell com exit code, paginação de stdout e leitura 4/4 passaram. Não reinstalar nem rebaixar.
- **Worker MCP hospedado:** ainda anuncia **19 ferramentas Windows** mesmo com Agent `0.3.55` (Worker de código revisado prevê 22). `read_many` e `search` retornaram `UNKNOWN_FUNCTION_ID`; `edit` retornou `AGENT_UPGRADE_REQUIRED`. A correção exige **qualificar/implantar Worker com version readback**, não repetir update do Agent.
- **Download público:** em 21/10 R21, o site `https://commander.haralabs.com.br` entregou **0.3.43, RSA v2, quatro assets com hashes válidos**. **Mas** o manifesto público SHA `53c0cbc2...` não é o manifesto SHA `2ec2b3cc...` do pacote assinado de revisão R19: 3/4 arquivos variam. Não chamar o pacote publicado de exatamente R19 sem reconciliação de proveniência. Também não chamar o 0.3.43 de última versão Linux/Windows.
- **Homogeneidade de frota ainda não concluída:** existem 0.3.43/0.3.54/0.3.55 em canais diferentes. O gate R20 retorna HOLD até ter build homologado, assinaturas, capacidades e dados de runtime por plataforma.

## História do console: requisito explícito do proprietário

**UX desejada em todas as plataformas:** abrir `hara-commander start` com **console ao vivo vazio**, exibindo somente novos eventos; preservar histórico local e mostrar **comando por solicitação explícita**, com filtros aos **últimos 30 dias** e paginação; `history clear` só para administrador/superusuário local, com confirmação forte e recibo, sem reset/destruição silenciosa de evidências.

- **Windows R22 já instalado:** inicia novo console em EOF, lê linhas novas incrementalmente; `hara-commander history [limit [before_id]]` permite consulta paginada SQLite, sem argumentos privados. **Para a janela antiga do operador carregar a nova UX, o usuário deve fazer `Ctrl+C` e abrir `hara-commander start` novamente.** Não fechar sessão sem comando do proprietário.
- **R23 Linux e Windows — WIP não implantado:** congelados neste branch sob `apps/commander/candidate/linux_agent_history_r23.py` e `windows_agent_history_r23.ps1`; fixtures sob `docs/evidence/commander-history-r23-20261021/`. Linux **7/7 testes sintéticos PASS** em cópia/snapshot; Windows R23 exige QA independente de filtro 30 dias, administrador e proteção contra apagar histórico com sessão ativa. **Nenhuma limpeza de histórico foi realizada.**
- **Nunca executar `history clear` como parte de teste automático ou sem usuário administrador presente.** Preservar sessão atual, recibos e isolamento de tenant/dispositivo.

## Prioridades para a próxima frente, em ordem

1. **P0 — aceitar e integrar R23:** revisar e executar fixture Windows R23 em ambiente TEMP isolado; testar últimos 30 dias com limites, paginação e privacidade. Testar `history clear` somente com mocks/fixtures para garantir superuser/TTY/confirmação forte, sem apagar qualquer histórico real. Concluir comandos `help` e UX Linux; nova assinatura/versionamento antes de instalar/atualizar.
2. **P0 — Worker hospedado e catálogo Windows:** conferir versão e dependências reais Cloudflare, criar candidate imutável, smoke test canário independente, obter autorização antes do upload/deployment, depois readback Worker+assets; liberar 22 funções esperadas para Windows 0.3.55 sem reinstalar Agent. Não desativar approval / `ASK_EVERY_ACTION`.
3. **P0 — release train comum, sem downgrade:** construir Windows/Linux comerciais consistentes numa release sucessora com manifesto, digest por plataforma, origem e capacidades declaradas, assinatura v2 oficial, rollback. Qualificar versões Founder distintas e as duas variantes de loop. Não baixar Linux 0.3.54 ou Windows 0.3.55 para 0.3.43 apenas por aparência de uniformidade.
4. **P1 — desempenho:** o `OUTBOUND_RELAY` Windows R22 teve fila de **1,9–6,7 segundos** em microburst 4/4, execução ~0,7–0,8 s. Qualificar percentis por transporte e método, distinguir erros esperados de falhas operacionais. Não deduzir p95 global desse ensaio.
5. **P1 — aceitação comercial:** reinstalação/upgrade segura de Windows e Linux x86/ARM, segundo tenant independente, SELinux/lifecycle, monitoramento de sessão/retentativas, performance e segurança, Stripe/billing se aplicável; somente após gates assinado/readback/rollback.

## Localização dos worktrees no Núcleo e cuidados

- **Codex ativo (não modificar sem coordenação):** `/home/sartorius/hara-workspaces/commander-prelaunch-fixes-20261020`, branch `codex/commander-prelaunch-fixes-20261020`, último HEAD conferido `3a9131785cf74ed5303b7474b4c2cf2d5ebd61a6`; possuía arquivos modificados/não rastreados de trabalho contínuo. Não fazer `git clean`, reset, cherry-pick ou checkout nessa pasta.
- **Revisão R11–R18:** `/home/sartorius/hara-workspaces/commander-dogfood-r5-review-20261020`, commit `6b4d9ab`, branch limpa antes da sincronização.
- **Revisão R22 / R23 original:** `/home/sartorius/hara-workspaces/commander-distribution-p1-20261021`, branch R23 aberta com **arquivos originalmente não rastreados**. R23 foi copiado byte a byte para esta branch de handoff com SHA-256 em `docs/evidence/commander-history-r23-20261021/WIP_SNAPSHOT.json`, sem interferir no diretório original.
- **Este snapshot e handoff:** `/home/sartorius/hara-workspaces/commander-github-handoff-r24-20261021`. Branch independente criada a partir do commit R22; usar este README para localizar R23 sem confiar na memória do chat.
- **Git local Services:** gateway `/srv/hara/repos/local-git-gateway/working/hara-site.git`; branches de revisão anteriores também têm readback SHA. Para sincronização final com GitHub usar refs de revisão e checar SHAs; não alterar a `main`.

## Condição para considerar encerrado

Código/manifesto/version **iguais aos bytes publicados**, instalação e update reais em cada plataforma, testes funcionais e performance dentro dos SLOs, opções de histórico e limpeza aprovadas, rollback operacional e atestação por hashes. **Nem R22 nem R23 autorizam automaticamente upload/deploy PROD.**

O histórico/código foi salvo no GitHub para continuidade em outro chat; a publicação GitHub **não equivale a** atualização da Cloudflare ou da frota.
