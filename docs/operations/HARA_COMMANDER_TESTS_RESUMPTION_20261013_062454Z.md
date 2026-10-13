# Commander Testes — retomada de 13/10/2026

Captura UTC: 2026-10-13T06:24:54.857Z. Base local: `e2606d9f6aa643f521e025794e68ac060e83f8a5`, branch `local/commander-product-current`. Owner de aceite Windows: hara-site#240; coordenação: hara-site#310.

O fluxo básico do Windows 0.3.51 já possui homologação pelo MCP real. A homologação comercial completa permanece aberta. Esta rodada recuperou os handoffs atuais e fez consultas/execuções de diagnóstico pelo plugin H.A.R.A. Commander; não repetiu os 520 testes nativos nem o gate integrado anteriormente aprovados.

## Estado observado

| Alvo / escopo | Evidência desta rodada |
|---|---|
| Windows HARA_WIN11 | 0.3.51, SESSION_TRUSTED, OUTBOUND_RELAY; identificação, arquivos e execução remota responderam |
| Windows, estado ao final | OFFLINE; list_sessions recusado com DEVICE_OFFLINE. A sessão de outra frente não foi declarada encerrada por inferência |
| Núcleo A | device.info PASS; 0.3.46, PERSISTENT_TRUSTED, EVENT_V2; processo de diagnóstico exit 0 |
| Services | device.info PASS; 0.3.46, PERSISTENT_TRUSTED, EVENT_V2 |
| Sentinela C | device.info PASS; 0.3.46, PERSISTENT_TRUSTED, EVENT_V2 |
| Sentinela B | device.info PASS; 0.3.41, PERSISTENT_TRUSTED, OUTBOUND_RELAY; divergência de versão confirmada |
| Sentinela D | Catálogo OFFLINE; isso não prova que o computador ou o jogo estão desligados |

No Windows, a execução de Get-Command hara-commander terminou com exit 1: o comando não está no PATH da sessão remota. A existência desse alias não foi confirmada como requisito do instalador; esta observação não é classificada como defeito. O Agent instalado foi localizado em AppData/Local/HARA Commander e o runtime-status não apresentava código de erro na leitura.

As respostas de descoberta/configuração usam autoridade HARA_SERVICES; as operações consultadas identificam execução HARA_COMMANDER_AGENT e customer_services_relay=false. Esta rodada não revalidou a URL cloud do MCP ou OAuth. Não foram usados Desktop Commander nem o plugin Baseline.

## Provas anteriores aplicáveis

- [Handoff Windows 0.3.51](../handoffs/HARA_COMMANDER_WINDOWS_051_HANDOFF_20261012.md): execução/escrita UTF-8, CAS, terminal e entrada Unicode pelo MCP real; sem aprovação individual em SESSION_TRUSTED.
- [Windows privado 0.3.52](HARA_COMMANDER_WINDOWS_052_EFFECT_METADATA_AND_SCALE_20261012.md): 520/520 nativas, 30/30 de Worker/replay e 121/121 do gate integrado, pacote assinado e staging nativo conferidos. Falta instalação e aceite dos efeitos pelo MCP real.
- [Escala e lacunas](HARA_COMMANDER_SCALE_LOCAL_WORKLOAD_AND_ACCEPTANCE_GAPS_20261012.md): carga SQLite local aprovada; segundo tenant autenticado e 1.000 tenants/Agents por 24 horas em nuvem continuam pendentes.

A distribuição pública 0.3.43 é o último estado documentado, não uma nova consulta ao download público nesta rodada. A correção privada 0.3.52 não foi instalada nem promovida por esta retomada.

## Ordem de continuidade

1. Resolver a disponibilidade atual do Windows e conferir o owner da sessão gerenciada existente. OFFLINE não autoriza assumir drenagem ou finalizar processos de outra frente.
2. Após admissão e drenagem comprovadas, instalar o canário privado assinado 0.3.52 com preimage/rollback; verificar por MCP real efeito verdadeiro, no-op falso, CAS e replay sem nova execução.
3. Concluir instalação/reinstalação/desinstalação limpas, roundtrip autenticado, reconexão e paridade de processos em ambientes isolados. ConPTY/stdin de aplicativos arbitrários são critérios próprios.
4. Conciliar a versão efetiva da Sentinela B com a release Linux admitida; não declarar frota uniforme 0.3.46.
5. Fechar separadamente segundo tenant autenticado, Stripe TEST, rampa/soak em DEV, métricas e distribuição comercial correspondente. Não inferir aceite comercial de testes locais.

Recibos e estados desta rodada: [JSON de evidências](../evidence/commander-tests-resumption-20261013/readback.json).

Foram preservados os sete caminhos dirty/untracked encontrados na árvore canônica. Esta rodada não reiniciou Agents, não mudou sessões/perfis, não fez instalação/desinstalação, não alterou gameplay e não executou carga cloud ou cobrança.
