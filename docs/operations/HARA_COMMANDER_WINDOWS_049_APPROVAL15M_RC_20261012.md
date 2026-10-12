# H.A.R.A. Commander — Windows 0.3.49, aprovação de 15 minutos

Data: 2026-10-12. Candidata privada assinada; aplicação na VM e comprovação humana
pelo MCP seguem o procedimento controlado do laboratório.

## Comportamento

Cada ação mutante continua exigindo aprovação humana individual. A constante
central `ApprovalTimeoutSeconds=900` oferece até **15 minutos** por pedido.
A interface deriva os minutos dessa constante e instrui a digitar a frase
completa `APROVAR <código de oito caracteres>` e pressionar Enter para enviar.
`APROVAR` sozinho, código incorreto e Enter vazio não concedem autorização.

A espera continua não bloqueando a leitura de teclas. Preserva texto parcial
até o prazo, revalida o pedido no Enter e na publicação e rejeita respostas no
instante exato da expiração ou depois dele. Ctrl+C e revogação da sessão
continuam interrompendo a autorização. A política permanece `ASK_EVERY_ACTION`;
o prazo maior não transforma a sessão em autorização permanente.

## Pendências, concorrência e liveness

Uma solicitação com prazo futuro continua ocupando seu slot durante todos os
900 segundos. A idade de dois minutos do arquivo não pode apagar esse pedido.
A limpeza exige expiração demonstrada, metadados válidos e rechecagem do hash
do arquivo; o par de resposta usa nonce, request, digest, owner e consumer
correspondentes. Metadados inválidos mantêm o slot ocupado. Uma resposta órfã
válida só entra no fallback de idade após pelo menos 900 segundos.

O consumer autenticado mantém o heartbeat durante a espera, na cadência
existente de 60 segundos. Esse caminho envia somente heartbeat: não busca
outra ação e não aceita consentimento a partir da resposta da rede.
Falha de heartbeat não concede aprovação nem avança o instante do último
heartbeat bem-sucedido. Uma resposta local válida é consumida antes de tentar
heartbeat; os últimos cinco segundos não são usados para essa chamada de rede.

A compatibilidade completa dos 15 minutos também depende do prazo e do
acompanhamento assíncrono no Worker/MCP. Esses componentes têm evidências e
validação próprias; os testes do Agent não substituem a comprovação ponta a
ponta nem a aprovação humana real.

## Identidade da fonte e validação

Fonte final:
`7b51d2f243228f27aaf742086fe012c73bc17cd8c180a4f9abbcb1e2c51f3080`.

- Guard estático: **17/17 PASS**.
- Fixture nativo PS5.1 de 900 segundos, com clock controlado: **227/227 PASS**
  na fonte final. Nenhum teste aguardou quinze minutos reais.
- Inclui limite antes/no instante/depois, texto parcial e Enter, recusa,
  bindings de owner/consumer/nonce/digest, pendência viva aos 600 segundos,
  limpeza após 900 segundos e heartbeat com sucesso/falha.
- Regressões anteriores: **111 + 26 + 27 + 68 PASS** na fonte
  `1e32e2c23476a2c8390111d4b9a57e877dbb3dd80426929a75bfb647da33274a`.
- A passagem para a fonte final altera exclusivamente um literal de
  `Write-Host` em `Read-LocalApprovalResponse`, para esclarecer Enter.
  Os corpos das demais funções permanecem iguais; o fixture de 227 checks
  e o parser foram executados novamente no hash final.
- Source .48 e bundles anteriores preservados.

Evidências:
[commander-win49-approval15m-20261012](../evidence/commander-win49-approval15m-20261012/).

Os fixtures usam funções reais extraídas por AST, perfil e input sintéticos
e fronteiras de rede controladas. Não comprovam buffer físico de teclado,
consentimento humano real, execução mutante pelo MCP ou escala real de clientes.

## Integração e estado de implantação

Status: **LIVE_PENDING — ainda não instalada**. RC49-v9 assinada com autoridadev2 existente; manifesto d0f375fd95e1e7842abb566359cd8edf2f14c4d10853e844cf2c425d0f9d6124, assinatura SHA1352fb54ed1e30d59fbd7c7daf374ef65f1b4f30df3acca4452b2a6d88344cf1. Assinatura/trustpin/bytes/parser foram verificados também em PS5.1 real. O bundle anterior e Linux são byte-idênticos.

Fonte e backend estão integrados na worktree final. Backend55checks PASS; **gate integrado105/105 PASS**, exit0/37,602s/peak_child_RSS143692KiB/stderr vazio. A execução104/105 foi preservada; o validador SQL passou a verificar os29 binds reais de enqueue/5 de claim, schema35 e os cenários existentes, mais a corrida900s, sem alterar o Workerd147. Relatório offline-final-gate.json SHA3a6ae220eb1d734ad9965da95ca32b7c906939f07cc87b8cc40136ae035a365a. Symlink temporário de dependências removido. Rollout do backend concluído e confirmado por readback: migração35 aplicada/zero pendentes, versão338e2b88-eae9-41b1-868d-947098fe68a3 em100%, health/auth e12/12 assets/8signed43 PASS. O canário49 está em preparação controlada; instalação ainda não comprovada nesta atualização. Runtime Windows continua48; aceite humano permanece pendente. Downloads públicos43-v3 foram consultados por HTTPS e Agent/install/manifest são byte-idênticos ao bundle histórico; deploybackend precisa montar seus assets a partir desse bundle, sem usar os defaults brutos do repo.


## Recibos reais do backend

production-validation.json SHAefdae1d9603121d4d4c2a4ab049b4ddca57eb64b383d6e901c3552930939bdd5 confirma a implantação, migração e duas leituras Linux diretas. A primeira tentativa de deploy foi interrompida pelo timeout10s do cliente; reconciliação confirmou nenhum upload/deploy, mantendo a migração aplicada. A tentativa gerenciada posterior passou com compiled identity match e100%. O snapshot de TimeTravel anterior35 foi preservado. Reverter runtime600s exige drenar/conciliar chamadas900s, conforme o recibo; migração aditiva permanece.

ControleRootR2 às20:25:14.458Z registra20 chamadas terminais e nova listagem de sessões0. Usar windows49-root-fresh-cutover-control-r2.json SHAd0604f8d670822bf6023c77317a2ae0f64e86e406afde72fbf0c816dfe0b23be como prechecagem histórica desta etapa; o controle anterior foi preservado, sem assumir freshness depois desse instante. Backend real não prova aprovação humana Windows. Agent49 e aceite positivo continuam pendentes até recibos do canário/execução.
