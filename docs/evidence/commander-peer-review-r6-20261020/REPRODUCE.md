# Reprodução R6

Sem instalação, listener, credenciais, rede externa ou alterações em Agents.
Requer Python 3 e Node com node:sqlite (Node 24.15.0 utilizado na coleta).
A suíte gera somente arquivos QA temporários e os remove; o resultado JSON
fica ao lado dos scripts. Exit 2 = achados reproduzidos, não aprovação.

Execute num clone que contenha o commit de fonte
97a35d9bde706db66e4c3a5645cefce083dc08c6. No Núcleo ele está no clone da frente:
/home/sartorius/hara-workspaces/commander-prelaunch-fixes-20261020
O commit documental de revisão não precisa ter esse commit como ancestral.
Não troque a branch do executor.

```bash
SOURCE_REPO=/home/sartorius/hara-workspaces/commander-prelaunch-fixes-20261020
EVIDENCE=/home/sartorius/hara-workspaces/commander-dogfood-r5-review-20261020/docs/evidence/commander-peer-review-r6-20261020
QA=$(mktemp -d /tmp/hara-r6-reproduce-XXXXXX)
mkdir "$QA/source"
git -C "$SOURCE_REPO" archive 97a35d9bde706db66e4c3a5645cefce083dc08c6 | tar -x -C "$QA/source"
cp "$EVIDENCE/peer_end_to_end.py" "$EVIDENCE/peer_worker_bridge.mjs" "$QA/"
cd "$QA"
HARA_PEER_NODE=/home/sartorius/.nvm/versions/node/v24.15.0/bin/node python3 -B peer_end_to_end.py
```

Para avaliar um patch novo, extraia esse commit em outra cópia QA e configure
HARA_PEER_SOURCE para a cópia, nunca sobrescrevendo a reprodução histórica.
O relatório registra hashes reais e deixa source_head nulo para fonte externa.
Este harness usa funções exatas mas substitui fronteira de autenticação;
não certifica isolamento multi-tenant, SDK HTTP ou D1 hospedado.

A primeira montagem teve erro de sintaxe da fixture do revisor; foi corrigido
antes da coleta. Não foi contabilizado como defeito do produto.
