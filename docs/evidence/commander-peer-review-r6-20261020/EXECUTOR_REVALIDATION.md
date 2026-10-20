# R6 — revalidação do executor na branch atual

Em 20/10/2026, executei o harness independente de `90a03a170961d188b1b507536a7f925c2484a91b` em uma pasta temporária, sem rede, listener, credenciais ou alteração de Agent em execução. Os oito arquivos cobertos por `SHA256SUMS` foram importados sem edição e conferidos com `sha256sum -c` (exit 0). A revisão Markdown já tinha os mesmos bytes neste clone.

O harness original presume retry imediato. Na branch atual, uma falha transitória de entrega ativa backoff local de 2 segundos. Sem aguardar, o harness sai 1 na asserção do controle de ACK perdido, antes de testar os dois achados; isso não representa a regressão R6. Modifiquei **somente a cópia temporária** de `peer_end_to_end.py`: acrescentei `import time` e `time.sleep(2.1)` imediatamente antes de cada `flush_completion_outbox()` que segue `advance(seconds=51)`. O script original e seus hashes permanecem intactos. Usei a mesma adaptação para os dois códigos-fonte.

| Fonte sob o mesmo harness adaptado | Exit | Outbox após envio inicial perdido | Leitura pública de 4/10 arquivos |
| --- | ---: | --- | --- |
| `97a35d9bde706db66e4c3a5645cefce083dc08c6`, extraído em `/tmp` | 2 | `DEVICE_CALL_EXPIRED`, depois `NOT_EXECUTING`; READY=1; nenhum novo claim | JSON interno inválido após corte em 65.536 caracteres |
| HEAD `d81aafcca5db21005c7d785c6b4db70e631f5a91`, código do clone | 0 | aceite tardio, ACKED, pendentes=0, execução=1, novo claim tentado | JSON válido em 1/4/10; `structuredContent` igual à projeção; recibo preservado |

Relatórios: `executor-before-97a35d9.json` (SHA-256 `52c023608f221a679514af19dcc0036af5aa53e614b134bbcace79fb6ddd3a10`) e `executor-after-current.json` (SHA-256 `7aebe0418b86c41adbe10c6a8760be4c6b70ab7bf125191a8f013b6f86454fe6`). A chave `source_head` nula é comportamento do harness ao receber `HARA_PEER_SOURCE`; os quatro hashes em `source_sha256` identificam os bytes avaliados. O cabeçalho acima identifica o commit de cada fonte.

As suítes do produto no HEAD também saíram 0: `test_device_call_usage_settlement.mjs`, `validate_result_delivery_outbox.py`, `validate_event_v2_durable_batch_continuation.py`, `validate_result_envelope_budget.py` e `test_public_result_projection.mjs`. A integração usa identidade e relógio sintéticos com SQLite local; não comprova Cloudflare hospedada, SDK HTTP, canário comercial ou PROD. Os fixes de código já estavam nos commits `cdb0208` e `ddbd0cc`; esta revalidação não alterou o produto.
