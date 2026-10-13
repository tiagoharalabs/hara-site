# H.A.R.A. Commander — efeitos reais, Windows 0.3.52 privado e escala local

Frente iniciada em 12/10/2026; fechamento em 13/10 UTC (12/10 em São Paulo). Trabalho pelo plugin direto H.A.R.A. Commander.

A correção de efeitos do Windows está em um pacote privado assinado 0.3.52, com 520/520 verificações nativas aprovadas. A VM em operação continua em 0.3.51: uma sessão gerenciada de outra frente permanece ativa e foi preservada. O pacote privado não foi promovido para a distribuição pública.

## Comportamento corrigido

O Windows marcava `mutation_performed=false` mesmo depois de executar processos ou escrever arquivos. Agora informa `true` somente após o helper concluir a operação; criar um diretório já existente e encerrar um processo já terminado informam `false`. A autorização continua anterior à operação, inclusive quando o resultado é um no-op.

O Worker preserva valores booleanos e informa `null` quando o Agent não fornece uma informação válida. A projeção anterior transformava informação ausente, nula ou inválida em `false`. A recuperação de chamadas passa a preservar `PROCESS_EXECUTION` e `FILESYSTEM_MUTATION`, sem publicar conteúdo, enfileirar outra execução ou cobrar uso adicional. Metadados históricos que já foram reduzidos a `null` permanecem históricos; não foram reconstruídos por inferência.

## Evidências executadas

| Validação | Resultado |
|---|---:|
| Efeitos reais, arquivos/CAS, processos e sessão revogada no PS5.1 | 120/120 |
| Janela de aprovação e vínculos de sessão/consumidor | 227/227 |
| Entrada gerenciada | 11/11 |
| Inicialização do operador | 68/68 |
| Comandos Unicode | 11/11 |
| JSON UTF-8 em HTTP local | 30/30 |
| Retomada de console | 27/27 |
| Recusa nos helpers e dispatch completos | 26/26 |
| Total nativo da fonte final 0.3.52 | **520/520** |
| Projeção Worker e replay com SQLite real | **30/30** |
| Gate prelaunch integrado | **121/121** |

Os fixtures importam a fonte por AST e usam arquivos/processos próprios. A prova de janela usa relógio controlado; não representa uma espera humana real de 15 minutos. A aprovação humana positiva pelo MCP da 0.3.49 e a homologação funcional real da 0.3.51 continuam registradas nas evidências anteriores.

A fonte Windows anterior falhou na nova regressão de criação de diretório depois de efetivamente criá-lo; a candidata passou. Duas regressões do Worker foram reproduzidas contra a fonte anterior. O primeiro gate integrado foi 119/121 porque dois validadores ainda exigiam literalmente a versão 0.3.51. Seus pins foram atualizados para 0.3.52, mantendo os demais critérios; a repetição completa passou.

## Pacote privado e runtime

Bundle: `apps/commander/release-bundles/commercial-0.3.52-v12-rc`.

| Artefato | SHA-256 |
|---|---|
| Windows 0.3.52, 98.717 bytes | `817325667ea552136efa10d807148fa4dc6d035aca24046c884f444a4fb61ebc` |
| Manifesto | `fd019aa722ea865781bab0ba2ee2d5e9483fec35fa6ae590fb74a33a4d88262b` |
| Envelope de assinatura | `cc0420eb4eaca686774d0206be38e75a956c693292bc663d7a434cde7b802039` |
| Instalador Windows | `7560c58b11200d1768ceba3162f5253bc0173b051f9ea3e9ebb6a323a89a31fa` |

Assinatura RS256/RSA3072 pela autoridade existente `commander-release-v2`. A janela de aprovação permanece em 900 segundos; transporte UTF-8, proteção SHA-256, privacidade, instalador canônico e bytes Linux foram preservados. A chave privada não foi exportada nem publicada. Os validadores históricos 0.3.51 agora verificam a fonte congelada correspondente, e os validadores 0.3.52 verificam a candidata atual.

A VM atual mantém `SESSION_TRUSTED`, conforme configuração encontrada, sem alteração de consentimento. A instalação da 0.3.52 está em HOLD enquanto a sessão `HARA-PROC-aa74d04499a3456fb0d6b9affd6d6850` de outra frente estiver ativa. Após drenagem, ainda é necessário instalar o canário assinado e repetir pelo MCP real os campos de efeito, no-op e replay. As 520 provas nativas não são declaradas como esse rollout.

## Servidor em produção e otimização

Worker publicado em 13/10/2026 às 00:12:47 UTC (12/10 às 21:12 em São Paulo), versão `99a19edb-d2cf-4806-8c98-861e4513a2f7` a 100%. Apenas os dois módulos de metadados mudaram. Os 15 assets públicos, incluindo os oito arquivos assinados da distribuição 0.3.43, foram conferidos antes e depois; health 200 com JSON UTF-8. Não houve nova migração.

Um novo `hostname` na VM pelo MCP real retornou exit0 e recibo `a64abf077d84a5a6a4bc27a313868872ab662850a94d16a6b3f59027638516f0`. A recuperação da chamada `HARA-CALL-4a0e98bd-2578-4293-b131-a3af7291ced3` preservou `PROCESS_EXECUTION` e o mesmo recibo, com conteúdo redigido, zero novas chamadas e zero unidades adicionais. O campo de efeito continua refletindo a resposta da 0.3.51; sua correção depende do canário 0.3.52 ainda não instalado.

A validação histórica do pacote privado eliminou invocações recursivas duplicadas, mantendo a cadeia completa v3/Windows44–51 e os controles próprios da 52. No teste local, as 13 guardas caíram de 55,272s para 27,800s; o validador de assinatura caiu de 18,530s para 9,338s. Ambas passaram após a otimização. O gate completo também verifica v2 separadamente. O gate local 121/121 precedeu esta deduplicação; o CI hospedado deve confirmar o tree final.

## Escala e frota

O novo teste extrai a classe `TenantQuota` do Worker e executa 1.000 bancos SQLite independentes simultâneos: 39.499 chamadas, 115.999 instruções SQL, 44.504 assertivas, 5.000 recibos preservados e cleanup 1.000/1.000. Foram detectadas duas alterações deliberadamente incorretas. Este resultado local não certifica 1.000 clientes autenticados em nuvem.

O próximo aceite comercial exige um segundo tenant DEV autenticado com dispositivo próprio, recibos e acesso cruzado recusado. Continuam pendentes o soak de 1.000 tenants/Agents por pelo menos 24h e as métricas de erro, p95 e custo em nuvem. Detalhes em [relatório de escala](HARA_COMMANDER_SCALE_LOCAL_WORKLOAD_AND_ACCEPTANCE_GAPS_20261012.md).

Consultas novas comprovaram acesso aos sete Linux: seis em 0.3.46/EVENT_V2; `sentinela-b` está efetivamente em 0.3.41/OUTBOUND_RELAY, tanto no runtime quanto no arquivo instalado. A causa da divergência histórica não foi comprovada. O inventário `ONLINE` admite uma janela de presença de sete horas para EVENT_V2; as consultas atuais de dispositivo forneceram prova independente de acesso.

Evidências próprias: `docs/evidence/commander-win52-product-validation-20261012-root/`, `docs/evidence/commander-win52-actual-effect-20261012/`, `docs/evidence/commander-relay-effect-metadata-20261012/` e `docs/evidence/commander-scale-local-workload-20261012/`.
