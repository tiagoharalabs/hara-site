# Commander — conectar, parear e atualizar

## Comportamento pedido

O ponto de entrada é **Conectar HARA Commander**:

1. Se a instalação tem um vínculo válido, reutilizar esse vínculo e verificar a atualização.
2. Se a instalação não está pareada, orientar o login no portal e pedir o código gerado pelo usuário. Validar o novo vínculo e atualizar quando houver uma versão mais recente verificada.
3. Não pedir outro código por falha de rede ou por falha na descoberta de atualizações.
4. Preservar uma conexão válida se a atualização não puder ser verificada. Não fazer downgrade nem trocar silenciosamente de origem/conta.

Os dois controladores estão instalados como auxiliares de QA nas VMs existentes da Sentinela B. Os instaladores candidatos incorporam o controlador e o novo caminho de pareamento de uma instalação existente. Estes instaladores são fontes separadas, ainda sem uma nova assinatura de release.

## Estrutura

- [Linux](linux/README.md): controlador, instalador candidato, gerador determinístico e testes.
- [Windows](windows/README.md): controlador, transação de pareamento preservando a instalação, instalador candidato, gerador e testes em PowerShell 5.1.
- Evidência operacional: `docs/evidence/commander-commercial-056-20261023/continuation-20261027/connect-flow-20261028/`.

A versão assinada 0.3.56 permanece imutável. A incorporação destes instaladores ao produto distribuído exige uma versão nova, com os quatro artefatos e o manifesto coerentes.

## Resultado nas VMs existentes

| VM em qemu:///system | Vínculo observado | Verificação real do controlador |
| --- | --- | --- |
| hara-review-win11-restoretest-20261024 | Produção; pareamento 0.3.56 concluído em 28/10/2026 às 13:37, Brasília | Às 14:10 reconheceu vínculo válido, confirmou conexão e não pediu token. Atualização suspensa por assinatura do catálogo antigo. |
| hara-review-linux | Desenvolvimento; 0.3.56, heartbeat autenticado HTTP 200 | Às 13:58 preservou o vínculo e recusou downgrade para o catálogo 0.3.54. Não pediu token. |

Os registros distinguem instalação pareada, atualização pendente e erro de conexão. O Ubuntu continua no ambiente de desenvolvimento; esta alteração não o migra para a conta reviewer em produção.

## Limite de entrega

Os controles de integridade permanecem ativos. O catálogo público observado anuncia 0.3.41 e usa a assinatura histórica v1, enquanto os clientes 0.3.56 verificam v2. O catálogo de desenvolvimento anuncia 0.3.54. Estes fatos impedem tratar a atualização real para uma versão nova como concluída.

Os testes isolados dos novos caminhos não substituem o pareamento real de uma instalação sem vínculo nem a atualização real para uma nova candidata assinada. Consulte os relatórios por plataforma e os recibos operacionais. A entrega desta fonte e dos auxiliares de QA não representa publicação pública do produto.
