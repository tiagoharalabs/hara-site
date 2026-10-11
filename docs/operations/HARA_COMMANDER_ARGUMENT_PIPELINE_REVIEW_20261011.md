# Commander — revisão da cadeia de argumentos, 11/10/2026

## Resultado e escopo

Base observada: `local/commander-product-current`, commit `aa4a90b228993c9fde4715ccb03e0c7967a437cc`. Foi criado e executado no Services um teste de integração local entre o handler MCP real, as funções de adaptação extraídas do Worker e o contrato canônico de ferramentas. Nenhum comando de dispositivo, rede externa, Cloudflare ou banco de produção é invocado pelo teste.

**A correção do Worker NÃO está aplicada ao produto.** A tentativa de gravá-la por execução remota foi bloqueada pela ferramenta, e não foi tentada outra rota para alterar esse Worker. A candidata foi testada somente como uma transformação da string de código dentro do processo de teste.

## Causas encontradas no fonte

1. `customerMcpDevicePayload` reconstruía `hara.files.write`, `hara.files.edit` e `hara.files.delete` sem `expected_sha256`. O perfil simples e o contrato canônico já suportam esse campo; o adaptador intermediário o descartava. Isso explica uma perda concreta no fonte, consistente com os recibos anteriores que retornaram `precondition_checked=false`. Não foi verificada uma correção em produção.
2. O mesmo adaptador descartava `offset` para `hara.files.search` e `hara.files.list`. Assim, chamadas com posições de continuação diferentes chegavam ao contrato sem essa distinção.
3. `legacyInvokePayload` também não incluía o offset na lista de argumentos de busca/listagem. A candidata preserva posições e preenche os valores padrão anteriores somente quando necessários para alcançar o argumento de offset.

A candidata preserva parâmetros opcionais, encaminha valores inválidos para rejeição pelo contrato em vez de eliminá-los e não modifica texto de comando, limites existentes, seleção de máquina, grants, autenticação ou permissões. Preservar o hash permite que ele participe do payload usado na identificação da requisição. Não é prova de compare-and-swap atômico entre processos no sistema de arquivos.

## Testes executados

Arquivo: `apps/commander/scripts/test_customer_argument_pipeline.mjs`.

- Execução padrão, contra fonte não alterado: **38 casos; 16 PASS, 22 FAIL**.
- Execução `--candidate`, com correções apenas em memória: **38 PASS, 0 FAIL**.
- A execução padrão deve continuar falhando enquanto o adaptador do produto permanecer sem correção. Não ignorar essas falhas nem declarar homologação com base apenas no modo candidato.
- Não houve integração desse teste ao gate geral nesta rodada. A tentativa de reexecutar a bateria geral foi bloqueada; não atribuir a estas mudanças um novo PASS dos 68 validadores.

Os testes cobrem hash opcional e obrigatório quando fornecido, normalização do hash, rejeição de valores inválidos, distinção entre precondições, offsets 0/17/10000, posições fora dos limites, continuação legada, preservação de conteúdo e ausência de mudança em comandos/processos.

SHA Worker original: `54753d72f0ba108d6a97351c35b767f8c171ac95438ad3c67c3d073bc5add71e`.
SHA da string candidata integral testada: `46fc3d42c4b0bc0fb5fb661f88b16d5c05c7f7c008d295067638aa06480b127d`.
SHA do teste gravado: `9695a72fab2458af090ded53e36e360bae061c546f61b38971d2f54f2c5f6826`.

Relatórios no Services:
- `/tmp_hara/commander-argument-pipeline-before-20261011.json`.
- `/tmp_hara/commander-argument-pipeline-candidate-20261011.json`.
- `/tmp_hara/commander-activity-full-source-20261011.json` — as correções anteriores de concorrência de atividade foram verificadas agora no arquivo integral: **25/25 PASS**, Node v24.15.0, app SHA `96423032e6416a8ab288f0ce67b700b86d97cbf4051899a46c957527c4fca2b3`.

## Exemplo de console fornecido pelo proprietário

Arquivo `Texto colado(20261011-165148).txt`, SHA `68eb5acda4a90ff398a97da9e2754180d49bf7f4d0c69df33ef9336ac11b0f88`, 91.034 bytes. A anotação anterior de que não havia sido fornecido um anexo foi corrigida.

O exemplo mostra `broadcast_v1`, `device_app_version=0.2.52`, busca concluída vazia exibida como `Showing results 0--1`, processos executados em `nucleo-a` e um canal recuperado após uma tentativa. Mostra também conteúdo de imagem serializado em texto. Estes são achados do exemplo, não prova de que o mesmo transporte ou formatador pertença ao Worker Event V2 inspecionado. Não alterar reconexão, app-version ou logs de outro componente sem localizar e confirmar sua fonte.

## Pendências preservadas

Aplicação do patch ao Worker por uma superfície autorizada, execução padrão dos 38 casos após aplicação, regressão geral, DEV e promoção governada. Permanecem não comprovados: convergência das versões em produção, custo total Cloudflare, carga real de 1.000–10.000 clientes e isolamento de clientes em ambiente real. Sem deploy, migração, atualização de agentes ou mudança de preços nesta revisão.
