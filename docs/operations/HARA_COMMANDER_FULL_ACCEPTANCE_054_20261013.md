# H.A.R.A. Commander — aceitação funcional .54R2 e continuação de estresse

Checkpoint 20261013T064138Z: teste real160calls/120PASS/40DEVICE_OFFLINE(SentD/Windows); seis máquinas20/20PASS. Novo pacote experimental corrige drift de liveness .46; canárioSentC com fontes/config verificadas, expansão em curso. Escala1000/24h pendente. Safe-tail encerrou05:58:53UTC; backend003/observerLinux53 continuam. OAuthWrangler expirado sob renovação existente. Evidência: capacity-1000/fleet-direct-burst-160-20261013T0621Z.json.

Checkpoint: 13/10/2026, São Paulo. Continuação autorizada pelo proprietário; ferramentas DIRECT H.A.R.A. Commander e infraestrutura própria governada.

Windows e Linux .54R2 concluíram seus ciclos funcionais reais em DEV. A homologação completa continua pendente de duração, escala, medições de custo/falhas controladas e critérios comerciais externos. O [checklist atual](../handoffs/HARA_COMMANDER_CURRENT.md) reúne os fechamentos; entradas históricas não substituem esse checklist.

## Pacote e publicação

| Item | Identificação |
| --- | --- |
| Bundle imutável | commercial-0.3.54-v14-rc-r2 |
| Manifesto SHA256 | e1c7c23de1b4313093e2d8c52be1ec52f6419f72d5ef59d675c7e5a279b1a13d |
| Linux Agent SHA256 | 62e1a836ef92fc8b72638fd116a6f0097fcf9e9f0ef0f4259ca8e0f6712b4229 |
| Windows Agent SHA256 | fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62 |
| DEV Worker /100% | 6f6e68e3-0777-4fb3-820d-a288ca5f7fab |
| PROD Worker /100% | 70564d5b-bf87-42dd-837e-717d3615ecad |
| Distribuição PROD | .43; promoção .54 pendente |
| Gate integrado deste checkpoint | 133/133 PASS; alterações posteriores do planner têm teste próprio |

O Windows preserva started_at quando o heartbeat omite o parâmetro. A falha reproduzida na53, a correção nativa de34 casos e o ciclo54 ficam separados. O primeiro coletor54 esperava heartbeat em25 segundos, embora a fonte configure60; sua falha foi preservada, e uma leitura posterior comprovou startup atualizado e preservado com o mesmo operador.

No Linux, managed start passa max_lines, o wrapper encaminha todos os argumentos e migra somente corpos históricos reconhecidos. A primeira54R1 reteve uma assertiva interna antiga; R2 corrigiu apenas a assertiva e acrescentou cobertura dos três roteamentos. Os bundles53 e54R1 ficaram imutáveis.

## Provas funcionais

Windows: instalação limpa normal HTTPS, assinatura/hashes/self-test, DPAPI no usuário QA, tarefa Interactive/Limited com boot manual, CLI start com operador/PID real, OAuth QA2 normal e MCP/recibo/quota, atualização ativa com heartbeat posterior, atualização parada, assinatura adulterada recusada, uninstall/revogação, tarefa/processos/porta ausentes e teardown do clone próprio. [Resumo e recibos](../evidence/commander-full-acceptance-20261012/windows-clean/windows-054-r2-acceptance-summary.json).

Linux: baseline53 real em VM limpa, upgrade54,13 checks core, rollback por falha QA controlada,25 checks MCP, uninstall; instalação54 limpa,13 core, revogação pelo portal, re-enroll com credencial anterior rejeitada,26 checks MCP e uninstall. Saída PTY20+100=120 exatamente uma vez, Unicode/CAS, sessão pelo wrapper público, ASK restaurado. [Resumo das12 fases](../evidence/commander-full-acceptance-20261012/linux-clean/linux54/native-054-r2-lifecycle-summary.json).

O cliente QA2 usou login regular OAuth/PKCE, callback normal com criação orgânica do Trial, pairing/select pelo portal e chamadas MCP. Device info consumiu uma unidade1→2 e o recibo foi recuperado por leitura. Após uninstall, o portal mostrou REVOKED/offline, active_count0 e online_count0. Dois usuários QA, quatro sessões, bearers, cliente DCR descartável e os dois tenants DEV próprios foram removidos após as provas. O cliente real do portal e políticas globais permaneceram íntegros. [OAuth](../evidence/commander-full-acceptance-20261012/real-oauth/REAL_OAUTH_QA.md).

## Duração e diagnóstico

O run002 terminou após1155,971s com INTERNAL_ERROR no probe de saúde, enquanto os dois Agents continuavam vivos/conectados. A causa500 original permanece desconhecida. O diagnóstico posterior20min passou; os novos testes retêm IDs de requisição, onda PENDING antes de dispatch, falha antes do cleanup, HTTP status, CF-Ray e UUID de incidente. Não existem retries que convertam falha em PASS.

O DEV54 inclui diagnóstico limitado a DEV: classe/categoria de erro, hash da mensagem e frames permitidos sem URLs/payloads/cookies. A coleta tail retém apenas o schema validado; seu início posterior ao run gera uma lacuna explícita de cobertura. Os efeitos públicos do catch e o comportamento PROD foram testados.

| Execução | Início UTC | Próximos marcos |
| --- | --- | --- |
| CLI/Linux53 real, VM própria | 13/10 01:50:08 | 24h:14/10 01:50:08UTC =13/10 22:50:08BRT |
| Backend003, dois Agents QA | 13/10 03:56:15 | 24h:14/10 00:56:15BRT;72h:16/10 00:56:15BRT |
| Backend003 piloto | 20min completos PASS | Duração24/72h em aberto |

O observador Linux53 assumia CLOUD_QUOTA exclusivo. A renovação normal do lease antes do deploy54 emitiu LOCAL_BUDGET, e a operação29 concluiu PASS com débito local COMMITTED1. As falhas do observador e as provas D1/local foram preservadas. A substituição do observador mantém início, deadline,200 enqueues totais e Agent/sessão originais; cobertura e segmentos devem ser lidos nos arquivos próprios.

Unidades Services: hara-commander-acceptance-soak-20261013-003.service e hara-commander-dev-safe-tail-20261013-003.service. Fontes do run003 estão congeladas em /tmp_hara/commander-soak003-frozen-20261013, com credenciais na custódia existente. O estado vivo fica em real-dev-soak/soak-20261013-root-003; snapshots datados são os checkpoints publicáveis.

## Estresse autorizado em toda a frota

O proprietário autorizou Núcleo, Sentinelas, Ninja Blue e todas as máquinas da frota em13/10 01:25BRT. O inventário DIRECT confirmou cinco Agents disponíveis e três candidatos offline sob diagnóstico. Aquecimento:50/50 device.info reais, cinco máquinas, concorrência5,50 recibos distintos, p954542ms e p995181ms. Esse é o aquecimento da frota.

A distribuição proposta de1.000 processos/tenants DEV é250 na VM própria Núcleo,300 SentD,300 SentB,100 Ninja e50 Services, com redistribuição sem aumentar o total se SentA/C entrarem. CPU até25% por máquina, memória conforme disponibilidade fresca e pisos, cgroups próprios, credenciais por dispositivo0600 e administração Cloudflare apenas Services. Compatibilidade das fontes congeladas em Python3.10/SentB e3.14/Ninja foi exercitada nativamente.

A VM Núcleo é própria,60GiB/8CPU/24GiB, sem autostart; UUID c8bcefb4-3f25-41b0-a07a-58c0d7956662. A rampa será100→250→500→1000, com IDs, recibos, quotas, reconexão e cleanup. O ensaio de dois Agents e a implementação distribuída têm seus próprios checkpoints. Não existe resultado real1k24h neste documento.

[Plano, recursos, warmup e ensaios](../evidence/commander-full-acceptance-20261012/capacity-1000/README.md).

Stripe TEST e revisão pública OpenAI são gates comerciais externos. O escopo de72h completo também exige falhas de rede/Agent/Worker e CPU/D1/DO/custo medidos; o run003 de dois Agents não encerra sozinho esse escopo. [Critérios canônicos](HARA_COMMANDER_COMMERCIAL_1000_HARDENING_20261011.md).
