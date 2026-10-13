# H.A.R.A. Commander — carga real de 1.000 Agents

Estado: PREPARED_NOT_EXECUTED. O plano foi preparado sem carga. Depois da revisão, criou-se uma VM própria60GiB/8CPU/24GiB, com cloud-init/SSH/user-systemd e preflight nativos aprovados; ainda0Agents/0tenants. Os 72 checks PASS são guardas locais, não homologação de mil clientes.

## Critérios

| Gate | Evidência real necessária | Estado |
| --- | --- | --- |
| REAL_1000_SHORT | Mil tenants, mil processos conectados, recibo de cada Agent, rampa100→250→500→1000 e20min contínuos | Pendente |
| REAL_1000_24H | Os mesmos mil Agents por24h, Free/Pro próprios, replay, recuperação e métricas Worker/D1/DO | Pendente |
| BACKEND_72H |72h de estabilidade; o resultado deve informar quantos Agents estiveram ligados | Pendente |

A referência comercial docs/operations/HARA_COMMANDER_COMMERCIAL_1000_HARDENING_20261011.md exige mil tenants/Agents por24h. Um soak com dois Agents e um teste curto com mil são evidências distintas; sua soma não cumpre esse requisito. Contas SQLite e GETs health também não substituem processos reais.

Novo escopo autorizado: distribuir os mil processos em Núcleo e frota Linux, com CPU física<=25% e memória<=40% da disponibilidade atual porhost, piso4GiB (Núcleo16GiB). Proposta inicial:250VM+300SentD+300SentB+100Ninja+50Services, sem inflação seA/C entrarem. O plano singleVM está preservado como histórico e não será lançado em bulk.

Esta proposta mede Event V2 DEV com fixtures QA pré-criadas. Não certifica mil logins humanos OAuth, mil comandos simultâneos nem todos os transportes públicos. É preciso vincular o resultado ao backend, Agent e caminho de distribuição exatos. Stripe não faz parte desta carga.

## Recursos

O ramp real100 aprovou100/100, p95=2331,18ms, p99=3564,85ms, RSS=4.183.265.280bytes. O run longo falhou depois: isso não é prova de continuidade. Fonte: ../real-dev-soak/ramp-proof.json.

Services possui32,9GB de RAM total. Extrapolar o RSS dos cem Agents resulta41,83GB para mil; não cabe em Services. Essa extrapolação serve apenas ao planejamento.

Snapshot04:07:58Z: Núcleo possui89.815.076.864bytes disponíveis e16 CPUs, carga1m4,20. Uma VM60GiB deixa25.390.567.424bytes disponíveis naquele snapshot. Arquivos: nucleo-resources.json, services-resources.json e host-resource-preflight.json. Revalidar com idade<=120s antes de qualquer criação.

Candidato próprio: commander-capacity1000-20261013,60GiB/8vCPU/24GiB de disco, autostartOFF. Host exige60GiB+16GiB disponíveis, disco>=32GiB e carga<65% das CPUs. Guest exige4GiB de margem, carga<70% de oito CPUs e memória prevista para a próxima etapa: maior entre56MiB e1,35×RSSp99 por Agent. Checar recursos a cada5s, sem contar swap como capacidade.

Cgroup exclusivo: MemoryHigh52GiB, MemoryMax56GiB, CPUQuota600% no plano original; a VM própria recebeu teto global400% em04:30Z (25% das16CPU físicas), e o perfil do supervisor será ainda menor se necessário, TasksMax8192, LimitNOFILE8192, Restart=no, KillMode=mixed. Deadline2h no teste curto ou25h no teste24h. Não alterar limites globais ou outras VMs.

Imagem Ubuntu24.04 oficial no Núcleo: /tmp_hara/commander-linux-clean-20261012/base/noble-server-cloudimg-amd64.img,625612288bytes, SHA2566a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2. Revalidar e converter para qcow2 standalone. Criar UUID/MAC/cloud-init/chaveSSH/knownhosts próprios. A receita create_linux54_qa_vm.py possui guardas da outra VM; não executá-la para esta carga.

## Oferta e orçamento

Manter os Agents anteriores ligados em cada etapa. Concorrência de criação/enrollment2 e de comandos20. Cada ciclo completo faz saúde, device.info com recibo e replay do mesmo request_id. Medir carga oferecida e atendida; mil conexões com vinte comandos concorrentes não significam mil comandos simultâneos.

| Limite | Curto |24h |
| --- | ---: | ---: |
| HTTP de aplicação + comandos D1 planejados |13.948 |43.948 |
| Reserva exclusiva de teardown |1.024 |1.024 |
| Teto |20.000 |60.000 |
| UpgradesWSS iniciais |1.000 |1.000 |
| ReconexõesWSS adicionais |200 |200 |

O teste24h prevê dez ciclos completos por Agent distribuídos durante24h reais, além de rampa, piloto e final. O candidato usa950TRIAL/Free e50STANDARD/Pro próprios, sem checkout. Alterar somente entitlements criados pelo journal desse run. Mutações limitadas a arquivo QA exclusivo, com sessão local autorizada; replay/CAS deve verificar nenhuma execução ou cobrança adicional.

O contador de aplicação exclui PING/PONG, liveness/telemetriaWSS, RPCs internos e statementsD1 executados dentro das rotas. Medir separadamente. Sem isso, custo fica UNMEASURED; limite de comandos não é fatura.

Interromper avanço em erro inesperado, troca de versão, mistura de tenants, falha de recibo, perda de Agent, dupla execução/débito ou limite de recurso. SLO: p95<=6s, p99<=12s. Reconexão:30s medidos, com janela explícita. Não repetir operações cujo resultado permaneça desconhecido.

## Implementação e cleanup

O helper commander_real_1000_capacity_plan.py gera plano e verifica recursos; não lança carga. O runner atual commander_full_acceptance_real_dev_soak.py tem MAX_AGENTS100 e RSS máximo6GiB: não basta passar outro argumento. Controlador separado e manager da VM ainda precisam ser implementados e submetidos a smoke real com dois Agents.

Credenciais Cloudflare/canaryMCP e criação de fixtures ficam em Services. Manager da VM recebe somente credenciais individuais de seus dispositivos e fontes congeladas; XDG isolado por Agent. Saída pública limitada a PID/starttime/hash/status e recibos. Antes de cada mutação, journal privado0600/parent0700 registra IDs exatos e estados parciais para recuperação.

Cleanup exige PID+starttime+comando+UID, nunca kill genérico. D1 usa IDs exatos do journal, nunca LIKE ou janela de horário. Confirmar zero processos e rows próprios, revogar credenciais, remover runtime e somente a VM própria. Preservar outros runs e falhas históricas.

Root deve revisar a composição e coordenar com os testes54 e soak003 antes de criar a VM; o usuário já autorizou continuar os testes. Preparação não constitui teste executado.

## CLI e evidência

No worktree /tmp_hara/commander-win50-utf8-20261012:

```bash
python3 -B apps/commander/scripts/test_real_1000_capacity_plan.py
python3 -B apps/commander/scripts/commander_real_1000_capacity_plan.py --mode short
python3 -B apps/commander/scripts/commander_real_1000_capacity_plan.py --mode soak24
python3 -B apps/commander/scripts/commander_real_1000_capacity_plan.py --collect-local Services
```

--backend-version exige UUID real completo. Planos preparados deixaram esse campo null; não inventar versão. --host-resources valida JSON recente. Guest preflight só ocorre após VM própria.

preparation-regression.json registra hashes e72checks offline. short-plan.json e soak24-plan.json registram bulk_load_started=false e gates reaisfalse. Nenhum arquivo deste diretório deve ser citado como homologação concluída.

Compatibilidade fontes assinadas54 +quatro módulosEventV2: parse/import nativos PASS emSentB Py3.10.12/UID1002 eNinja Py3.14.7/UID1000. Controller/manager ainda precisam de prova nativa após freeze; ver native-python-310-314-source-compat.json.
