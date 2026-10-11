# H.A.R.A. Commander — Hotfix comercial Windows 0.3.43-v3

**Data:** 11/10/2026 · **Status:** correção de atualização comprovada em Windows 11; conexão MCP Windows ainda em HOLD.

## Defeito e solução

No pacote comercial 0.3.43-v2, o atualizador gravava o novo Agent como `hara-commander-agent.ps1.update`. O PowerShell 5.1 recusa `-File` para esse sufixo, gerando `AGENT_SELF_TEST_FAILED` antes da substituição. A cópia assinada com nome `hara-commander-agent.update.ps1` passou no mesmo autoteste.

A fonte canônica `apps/commander/public/install/windows.ps1` foi corrigida para usar `$Agent + ".update.ps1"`. A nova distribuição imutável `apps/commander/release-bundles/commercial-0.3.43-v3` foi assinada com a chave custodiada v2 (RS256/3072), sem exportação de chave. **Os Agents Linux/Windows e o instalador Linux são byte a byte iguais à versão v2; apenas o instalador Windows mudou**. O pacote v2 continua intacto.

## Prova no Windows real, sem nova identidade

VM `commander-win11` no Núcleo A, Windows 11 Pro e PowerShell 5.1. O instalador v3 foi enviado ao Windows, conferido por SHA-256 e parser. A atualização ocorreu como o usuário efetivamente conectado, através de uma tarefa temporária do Windows com logon interativo, sem senha e sem operar como SYSTEM dentro do script de instalação.

**Resultados:** atualização do Agent **0.3.14 → 0.3.43 PASS**, hash do Agent comercial assinado PASS, configuração da identidade **idêntica byte a byte**, tarefa do Agent manteve estado `Ready`, cópia de segurança da versão antiga preservada e nenhum pareamento repetido. Chave e token não foram exibidos.

O catálogo do produto passou a registrar a versão 0.3.43 para `HARA_WIN11`, mas o dispositivo ainda apareceu **OFFLINE**. Um teste manual da tarefa existente mostrou `Running`, sem sessão local de operador reconhecida; a tarefa foi parada novamente e retornou a `Ready`. A tarefa antiga contém gatilho `AtLogOn`, herdado do 0.3.14. Nenhum gatilho foi alterado nesta correção. **Não declarar paridade Windows de ponta a ponta nem fluxo Event V2 comercial antes da conexão e dos comandos reais.**

## Ensaios de regressão

- Fonte e manifesto comerciais 0.3.43-v3: `validate_signed_commercial_v3_bundle.py`, assinatura e SHA verificados.
- Staging canônico do Worker: `stage_signed_commercial_assets.py --check` PASS com v3.
- Gate offline geral: **84/84 PASS**. Histórico v2 também validado.
- Pacote 0.3.43-v3 assinado com hash do instalador Windows: `d0f6d7e3a79a87e439a6275ebf60b2918ad5ccdbc28666ce18288644f3d595b9`.
- Evidência JSON: `docs/evidence/commander-windows-updater-v3-20261011/acceptance.json`.

## Próximos gates

1. CI hospedado do exato commit contendo o release v3.
2. Deploy DEV usando o stage comercial assinado, leitura exata dos oito assets e saúde/autenticação.
3. Deploy PROD somente após DEV PASS, seguido de leitura exata e preflight assinado no Windows.
4. O usuário da VM inicia a sessão de operador **por ação local**; o H.A.R.A. valida presença e comandos de leitura/escrita sem depender do Desktop.
5. Separadamente: revisão do trigger legado de login e homologação Event V2 Windows em release próprio; não introduzir mudança oculta de política no hotfix.

Stripe, conta bancária, preços, tokens de usuário e demais máquinas Founder não foram modificados neste hotfix.

## Fechamento de DEV e PROD após homologação

O GitHub Actions passou no commit `a1d5f7276780e1b9f1ec60e8fd8c36e0ab150675` (run **38185936537**, 84/84 validadores offline).

**DEV:** Worker `aaa289cc-7e8e-490c-9a25-c7c9bd763b9d` em 100%; saúde e autenticação aprovadas; 9/9 arquivos públicos idênticos ao stage assinado.

**PROD:** Worker `e5544ad6-b1a4-47ac-bf09-78874ca0bc4a` em 100%; anterior `7d148653-fc93-4cd6-94cc-07c3d26b52c5` registrado para rollback. Auditoria `CURRENT`, saúde/autenticação PASS, 9/9 arquivos exatos, manifesto e assinatura incluídos. O instalador Windows público apresenta SHA-256 `d0f6d7e3a79a87e439a6275ebf60b2918ad5ccdbc28666ce18288644f3d595b9`.

O Windows 11 da VM baixou o novo instalador diretamente de PROD e aprovou o preflight RS256, versão do Agent 0.3.43 e Task Scheduler. A frota Founder Linux continua 7/7 online em 0.3.46.

**Limite ainda aberto:** `HARA_WIN11` permanece OFFLINE no MCP. A tarefa legada contém gatilho AtLogOn e foi devolvida ao estado Ready, sem alterar o registro, a identidade ou o token. Há um novo atalho `HARA Commander - CONECTAR MANUALMENTE.cmd` no Desktop da VM, verificado por SHA, mas ainda não executado pelo usuário. A conexão Windows e as operações pelo MCP dependem dessa sessão autorizada localmente. Nenhuma mudança no Stripe, no D1 ou em aplicações CSOTN foi feita nesta entrega.
