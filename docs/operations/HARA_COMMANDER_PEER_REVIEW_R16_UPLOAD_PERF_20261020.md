# HARA Commander — R16 / gate de upload de release e SLO de latência

**Data:** 20/10/2026 (BRT), revisão independente da frente Codex. **Somente H.A.R.A. Commander.** Nenhum Wrangler, Cloudflare, Agent ou segredo produtivo foi acionado nesta reprodução.

## Estado para liberar produto sem retrabalho

- O código do Codex já publicou `53af168` (estágio confere com árvore Git) e `b99f97c` (upload verifica estágio assinado/digest antes e depois de invocar Wrangler). Os testes existentes `test_versioned_prod_upload_preflight.py` e `test_versioned_prod_release_preflight.py`, reexecutados **num clone isolado de b99f97c**, passaram **8 e 13 casos**, ambos exit 0.
- O candidato congelado da R15 é `commercial-0.3.43-v5-terminal-drain-unsigned-a13b4d2.tar.gz`, SHA `3ade217145e32899da47bedb43272897ee020e44658ae2b197b0eda61880970d`. Os 4 assets e pins para JWK v2 estão coerentes, mas **a assinatura comercial oficial v5 ainda não existe**.
- Não reabrir R10–R15 já encerradas (pre-enrollment, ACK recuperável, validação Linux Fedora x86/Ubuntu ARM, CAS, pacote congelado). O novo objetivo é **garantia real de bytes durante upload + prova de performance da release instalada**.

## R16-P1 — janela temporal de troca/restauração de asset durante upload

**Fonte exata:** `apps/commander/scripts/commander_versioned_prod_upload.py`, commit congelado `b99f97c2f7bf128390c750b89d22991f08443ef8`. `upload_version()` chama `checked_stage` antes de `run_wrangler_upload(stage,...)` e novamente depois da conclusão. Entretanto passa ao uploader **a mesma pasta mutável**. Se outro processo com permissão de escrita trocar temporariamente um asset na janela de leitura e restaurá-lo antes da pós-verificação, **ambas as verificações passam**; o que o uploader leu não fica provado pelo SHA do stage.

**Prova nova, reproduzida:** `peer_upload_toctou.py` usa `stage()` real com bundle histórico v4 **assinado, exclusivamente como fixture**, e `upload_version()` real, substituindo somente `run_wrangler_upload` por um leitor local simulado. Este modifica temporariamente `index.html`, lê os bytes alterados, restaura a fonte e retorna exit 0. Resultado observado:

- pré-verificação `VERIFIED_NOT_UPLOADED` com digest real `e3f5ce730a7a640d71c41c062315497d20b6fc292f1188c0885d88d8f6653448`;
- SHA-256 do `index.html` aprovado: `a82ad3ad28b43fe89282870aaabb23764632db07f5380a10726ea8d423b3c366`;
- SHA dos **bytes lidos pelo fake upload:** `4cf3c8f8354594f70f52a9fcc8294b174a696b471def27c0bc5338d96b353df2`;
- pós-verificação continua vendo bytes originais, e código retorna **`UPLOADED_VERSION_READBACK_REQUIRED`**;
- controle positivo: alteração que **permanece** até pós-verificação foi corretamente rejeitada como `SIGNED_UPLOAD_OUTCOME_UNKNOWN:STAGE_CHANGED`.

**Exit 2 do teste = janela de concorrência reproduzida, não teste de aceite PASS.** Nenhuma rede/Cloudflare foi usada. **Não há evidência de exploit nem de release incorreta realmente enviada em produção.** O cenário requer outro escritor com acesso à pasta privada do staging. Pode ocorrer em processos do mesmo usuário se vários publicadores/ações de build operarem em paralelo.

**Correção recomendada para o Codex (sem duplicar o código dele):** serializar publicação com lock por release/stage e garantir upload de **snapshot de conteúdo estável** exclusivamente controlado pelo uploader; aferir digest exato no ponto de leitura e confirmar o **conteúdo da versão Cloudflare enviada** antes de liberar a promoção de tráfego. `chmod -R a-w` é defesa auxiliar, não exclusão forte de outros processos do mesmo usuário. Comparar SHA antes e depois da transferência é insuficiente para provar bytes intermediários. Ao perder ACK de Wrangler, manter `OUTCOME_UNKNOWN` sem retry cego.

**Critério mínimo:** fixture onde outro processo tenta substituir `index.html` durante o upload **não pode gerar sucesso atribuível ao SHA antigo**; deve bloquear o escritor, usar snapshot estável ou marcar o resultado como não verificado; provar arquivo publicado por hash e version ID. Não introduzir deploy sem assinatura; preservar rollback.

## Baseline de desempenho agora (não benchmark)

Pelo próprio HARA Commander, janela **24h** mais recente: **4.525 chamadas; 4.462 concluídas, 60 falhas, três cancelamentos; sucesso bruto reportado 98,6%; média fila 982 ms, execução 869 ms, total 1.851 ms; 88,6% abaixo de 3 s.** Parte das falhas pode ser esperada por cenários negativos; **não reinterpretar automaticamente como indisponibilidade 1,4%**.

Últimas **100** chamadas da telemetria (amostra enviesada pelo trabalho atual): Services/Event V2 62, fila p95 **2.186 ms**, total p95 **5.065 ms**; Núcleo/Event V2 36, fila p95 **688 ms**, total p95 **1.646 ms**; duas outras chamadas Event V2. Esses percentis usam a amostra retornada, **não representam p95 exato das 4.525 chamadas**. A diferença pode refletir ferramentas, distribuição de demanda, fila e carga atual, não isoladamente hardware.

**Gate comercial adicional sugerido:** definir alvos de SLO por método/transporte e por organização, distinguir falha do cliente/política de falha operacional do serviço, medir p50/p95/p99 e fila vs execução em QA/canário. Validar especialmente upload/reconexão, relay Windows e Event V2 com microcarga controlada; preservar 5 dispositivos e quota 1M/mês em concorrência. Não lançar sem estabelecer teto de atraso e reversão, mas não inventar números de performance homologada.

## Arquivos e handoff

- `docs/evidence/commander-peer-review-r16-upload-20261020/peer_upload_toctou.py`
- `.../r16-upload-toctou-results.json`
- `.../README.md` e `.../SHA256SUMS`

O teste deve rodar em **clone isolado do commit b99f97c** que contenha `apps/commander`; no Núcleo o ambiente QA foi `/tmp/hara-commander-r16-upload-20261020`. Não apontar para checkout do Codex, não baixar secrets e não executar `--execute` contra Wrangler. O relatório é orientativo para o Codex que permanece único proprietário dos patches; sua branch não foi modificada. **Release comercial sem assinatura segue HOLD**, com Storage/Observer ainda sem Agent principal.
