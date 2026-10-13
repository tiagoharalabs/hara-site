# H.A.R.A. Commander — escala: teste executável e pendências reais

Data: 12/10/2026. Base auditada: `0f918c302318663ee068d31da5df7688acdded9b`. O teste foi disparado pelo MCP direto **H.A.R.A. Commander**, no Services.

O novo teste executa a classe `TenantQuota` extraída do Worker de produção, com 1.000 bancos SQLite locais independentes abertos ao mesmo tempo. Comprova o comportamento de quota, recibos e expiração em uma carga reproduzível. A homologação de 1.000 clientes autenticados em nuvem continua pendente.

## Resultado medido

| Prova local | Resultado |
|---|---:|
| Objetos de quota independentes abertos simultaneamente | 1.000 |
| Chamadas aos métodos reais da classe | 39.499 |
| Instruções SQL executadas | 115.999 |
| Assertivas verificadas | 44.504 |
| Recibos de commit preservados após replay | 5.000 |
| Recusas sem consumir unidades | 1.500 |
| Reservas liberadas sem reembolso duplicado | 3.000 |
| Bancos fechados ao final | 1.000/1.000 |
| Duração local | 3.211,109 ms |
| RSS observado no processo de teste | 221.646.848 bytes |

O mesmo ID de pedido foi reutilizado deliberadamente em objetos distintos. O teste verificou contas separadas, conflitos por sujeito/função/período, replay terminal, 500 pedidos recusados no objeto ruidoso sem alterar os saldos dos demais, preservação da reserva aos 15 minutos e liberação no limite exato de 30 minutos. O limite de 30 minutos é a reserva de quota do relay; a aprovação humana do produto permanece em 15 minutos.

Duas alterações deliberadamente incorretas, aplicadas apenas em diretórios temporários, foram detectadas pelo novo teste: commit que cobra duas unidades e remoção da guarda do sujeito na liquidação. Esses diretórios foram removidos. O Worker e os Agents em execução não foram alterados por esta frente.

As regressões existentes também passaram: 16 cenários de quota/TTL, cinco cenários de retenção com a função real do Worker e as consultas exatas de sessão/retenção em conjuntos de 1.000 e 10.000 tenants sintéticos. A consulta conservou 10.000 sessões ativas diante de 210.000 sessões totais e usou índices; a limpeza manteve seu limite de 100 registros por instrução. Os tempos SQLite são diagnósticos locais, sem representação de latência D1 ou SLO comercial.

## O que falta para a homologação comercial

| Condição exigida pelo gate | Evidência ainda necessária |
|---|---|
| Segundo tenant | Identidade autenticada separada, dispositivo próprio e recibos; tentativas de acesso entre tenants recusadas |
| Distribuição atual | Instalador/Agent comercial assinado correspondente ao código promovido; hoje a distribuição pública é 0.3.43, enquanto a VM usa o canário privado 0.3.51 |
| Windows completo | Instalação e desinstalação limpas, roundtrip autenticado, reconexão/replay, paridade de arquivos/processos e operação sem o aplicativo desktop Commander |
| Soak de escala | Pelo menos 1.000 tenants distintos e 1.000 Agents simultâneos autenticados durante 24 horas |
| Correção sob falhas | Isolamento, quotas, reconexão sem duplicação de efeitos, recibos e limpeza verificada |
| Medições em nuvem | Erro entre 0% e 0,5%; p95 maior que zero e até 6.000 ms; custo real Worker/D1/DO registrado |
| Comercial geral | Homologações independentes de Stripe TEST e revisão/identidade do provedor |

A ausência do JSON específico de aceite Windows no gate não invalida as provas reais 0.3.51 já publicadas: esse contrato adicional exige instalação/desinstalação e outros critérios que não podem ser inferidos de um comando que passou. Nenhum ajuste de Stripe foi executado nesta frente.

A auditoria examinou 220 arquivos JSON de evidência de até 512 KiB e não encontrou o schema de soak autenticado de 1.000 clientes. O gate opcional atual mantém `COMMERCIAL_BETA` e `GENERAL_AVAILABILITY` em HOLD e contém duas condições comerciais fixadas em falso até sua futura integração com evidência real. Ele não integra o gate prelaunch atual. A configuração canônica não declara um ambiente Wrangler DEV separado e Event V2 continua restrito ao canário.

O próximo aceite real é **um segundo tenant DEV autenticado e isolado**, com recibos de operações úteis e acesso cruzado negado. A rampa prevista segue 10–100 tenants, 250 conexões Event V2 e, depois, 1.000 Agents/tenants por 24h; as correções devem ser seguidas por soak de 72h. O ambiente, identidades, quotas e coleta de custos precisam ser distintos da produção antes dessa carga.

## Execução e evidências

Com Node.js 24 ou superior, na raiz do repositório:

```sh
node apps/commander/scripts/test_quota_1000_local_workload.mjs
```

Evidências curadas em `docs/evidence/commander-scale-local-workload-20261012/`: carga de 1.000 objetos, regressões, prova dos dois erros detectados e auditoria do gate. Todas referem-se ao SHA e aos hashes de fonte registrados nos JSON. Não houve criação de identidades cloud, cobrança, rollout, upgrade de Agent ou carga em produção nesta frente.
