# HARA Commander — R13 | Cadastro perdido após commit e resposta não entregue

Data: 20/10/2026, QA independente pela Valky via **H.A.R.A. Commander**. O proprietário solicitou apoio intensivo à frente Codex. O trabalho fica numa branch isolada: não editar `apps/commander`, `PROGRESS.md` nem índice Git do executor.

## Síntese

**P0 antes de novos pareamentos e do lançamento comercial:** o instalador já antecipa corretamente a validação criptográfica da release (R11), mas uma nova classe de erro continua possível *depois* do cadastro: o servidor grava o dispositivo e consome o token de pareamento, porém uma operação posterior falha ou a resposta de rede se perde. O cliente fica sem token do dispositivo, não consegue revogá-lo automaticamente e o mesmo pareamento não pode ser repetido com segurança.

Esta é uma reprodução isolada do caminho real, NÃO um incidente comprovado em D1 PROD. Não executar mais cadastros reais em Storage/Observer para reproduzir a falha. Preserve a frota recém-estabilizada: sete Agents Linux 0.3.54, VM Windows 0.3.53; o produto público continua em HOLD por release não assinado/inconsistente.

## O que já funciona — não refazer

Extraí `1d8b183564f1d8498c0b71ae7e35e924787e8010` em `/tmp/hara-commander-r13-pre-enroll-rgqgez92/source`, sobrepondo **cópias** dos oito arquivos WIP do instalador/gate, com SHA-256 em `snapshot.json` e sem modificar o checkout do Codex. Reexecutei:

| Suíte | Exit | Resultado |
| --- | --- | --- |
| `test_linux_r11_pre_enroll.py` | 0 | Seis cenários: manifesto v1/v2 incompatível, asset Linux ou Windows alterado e versão alterada deixam **zero POSTs de inscrição**; release válida alcança o mock |
| `test_live_release_integrity_gate.py` | 0 | Nove verificações offline, assinatura/pin/sha divergentes corretamente negados |
| `verify_live_release_integrity.py --live` | 2 | **HOLD esperado em produção**: assinatura v1, pin Linux servido v2 e quatro assets com digest incompatível |

Nenhum instalador remoto/Cloudflare PROD foi executado; as suítes usam mock localhost, chave efêmera QA, release pública em GET read-only e HOME/XDG temporários. **Exit 2 do gate público significa bloqueio correto, não uma suíte aprovada.**

## R13-P0-ENROLL-POSTCOMMIT — prova usando Worker real + SQL/migrações

`peer_worker_postcommit.mjs` executa **a função `enrollDevice()` extraída de `apps/commander/src/worker.js` e as três consultas SQL reais de `device-enrollment.mjs`**, com as 40 migrações SQLite da base. A única falha simulada acontece na `INSERT OR IGNORE INTO commander_device_selections` **depois** que o batch transacional de inserir dispositivo e consumir token já retornou sucesso.

Resultado registrado:

- O servidor de fixture lança `QA_SELECTION_WRITE_UNAVAILABLE_AFTER_COMMIT` e **não entrega `device_token` ao chamador**.
- O banco da fixture mantém **1 dispositivo ACTIVE**, com o token de pareamento **consumido** e nenhuma linha de seleção.
- Repetir o mesmo pareamento devolve `DEVICE_PAIRING_INVALID`. Não existe neste fluxo um identificador idempotente que permita ao cliente obter a credencial original no segundo pedido.
- Controle positivo com outro sujeito/pareamento: resposta `ACTIVE`, novo token entregue e seleção criada corretamente.
- **Não houve D1 hospedado, conexão externa nem cobrança.**

O ponto exato da fonte: `enrollDevice` chama `env.PRODUCT_DB.batch([insert,consume])`; **fora** desse batch chama `SELECT tenant_id,... FROM commander_devices` e `INSERT OR IGNORE INTO commander_device_selections`. Se um desses dois passos posteriores falhar, a transação principal já foi confirmada. A segunda SQL de seleção é parte da experiência de dispositivo inicial, mas atualmente tem sucesso obrigatório para devolver o novo token.

**Correção mínima do ramo de DB:** incluir readback/seleção na mesma transação quando possível, ou tratar seleção como operação reconciliável pós-commit e retornar o token ao cliente de maneira durável/segura. O primeiro passo NÃO resolve sozinho queda de conexão **após** commit e antes da resposta. Não apenas engolir exceções se isso quebrar isolamento/seleção.

**Correção robusta da janela de entrega:** introduzir intento de instalação idempotente e recuperação autenticada, com vínculo a pairing, tenant, dispositivo e credencial gerada pelo próprio cliente ou recibo recuperável sob criptografia/política de retenção. O Worker hoje guarda **somente hash** da credencial gerada pelo servidor: não pode recriar o token depois que a resposta se perde. Não habilitar replay arbitrário de pairing tokens consumidos, não armazenar tokens em claro no D1 e não liberar consentimentos/tenants para resolver o problema.

## R13-P1-ENROLL-RESPONSE — mock end-to-end do instalador Linux

`peer_malformed_enrollment.py` reaproveita a fixture oficial assinada de `test_linux_r11_pre_enroll.py`, mas substitui apenas a resposta do servidor *após* o POST. Executa o instalador WIP real em PTY com HOME/XDG temporários, assinatura RSA QA e token sintético (nunca gravado nas evidências). O servidor falso registra dispositivo em memória e marca pairing consumido. Quatro casos:

| Falha imposta após inscrição simulada | Cliente sai com erro? | Cadastro QA permanece? | Revoke automático? |
| --- | --- | --- | --- |
| HTTP 200 sem `device_token` | Sim; `unbound variable` | Sim | Não |
| HTTP 200 sem `device_id` | Sim; `unbound variable` | Sim | Não |
| HTTP 200 com JSON inválido | Sim; `unbound variable` | Sim | Não |
| Servidor simula commit e **fecha conexão sem resposta** | `curl` exit 52 | Sim; retry do mesmo pairing negado (HTTP 409 no mock) | Não |

O caso HTTP 200 malformado **não é alegação de resposta normal do Worker atual** — seu `enrollDevice` retorna todos os campos quando conclui. Ele é teste defensivo do contrato HTTP. O caso de resposta perdida é um cenário plausível de transporte depois do commit. No mock, `server_created_registration=true` significa **registro simulado em memória**, não D1 real.

O erro extra de Bash nasce de `readarray -t VALUES < <(python3 ...)`: o status de saída do Python na substituição de processo não é propagado como falha de `readarray`. A atribuição subsequente lê um elemento ausente sob `set -u`. Nesse ponto `INSTALL_ENROLLED` ainda não está `TRUE`, então o rollback não tenta revogar. Quando a resposta/token falta, a revogação por `revoke-self` é impossível, independentemente de uma mensagem melhor.

Recomendação: validar JSON e tipos/identificadores de forma atômica com propagação do exit code, sem `readarray` sobre pipeline ocultando erro; devolver `ENROLLMENT_ACK_UNKNOWN`/reconciliação segura quando o estado remoto não puder ser conhecido. A UI deve comunicar ao operador como recuperar a instalação sem consumir indefinidamente o limite de cinco dispositivos. Alinhar Linux e Windows, mantendo o token fora dos logs.

## Aceite que falta para chamar o instalador de confiável

1. `server_selection_failure_after_device_commit`: zero dispositivos órfãos **ou** resposta/reconciliação recuperável, sem duplicar inscrição; estado concreto em SQLite + Worker.
2. `server_commit_then_connection_lost`: repetir a mesma intenção sob credencial/idempotency key permite resultado equivalente/recuperação autenticada, **sem** reutilizar pairing token livremente. Exigir que o servidor revogue/proteja registros não recuperáveis por prazo explícito.
3. HTTP 200/201 inválido, truncado, sem device ID/token, 401/503 e timeout: erro tipado, nenhum `unbound variable` e nenhum token/payload privado vazado.
4. D1 emulado + Cloudflare DEV homologado em tenant comercial de teste e tenant vizinho, limite de cinco dispositivos, revogação, perda de ACK e concorrência. Não afirmar PROD porque SQLite/local/mock passou.
5. Preservar os seis testes R11 que já passaram, o gate público fail-closed e a assinatura oficial obrigatória. **Não instalar Storage/Observer** enquanto a distribuição pública continuar com kid v1/v2/hashes divergentes.

## Evidência e limites operacionais

`docs/evidence/commander-peer-review-r13-20261020/` contém os dois scripts de reprodução, respostas sanitizadas, snapshot dos oito arquivos WIP e três testes existentes, README e SHA256SUMS. Os scripts usam **somente** localhost/tempfile/SQLite em memória; não chamam o app público salvo no Linux do usuário, não enviam token real e não escrevem no checkout Codex.

Os scripts saem **2 quando reproduzem o defeito** — nunca interpretá-los como teste de aceitação PASS. O pacote histórico de fonte congelada para esta coleta estava em `/tmp/hara-commander-r13-pre-enroll-rgqgez92/source`. Se os arquivos WIP mudarem, executar em nova cópia QA com `HARA_PEER_SOURCE` apontando ao código analisado e guardar o novo SHA, preservando esta evidência.

Nenhum Agent da frota foi reiniciado, nenhuma instalação remota foi tentada, nenhum dispositivo adicional foi realmente inscrito, nenhum deploy, assinatura ou segredo foi usado. O Codex continua sendo o único autor das fontes produtivas do HARA Commander.
