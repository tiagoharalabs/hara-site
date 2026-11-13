# H.A.R.A. Commander — correção de contrato de observação do Cron QA

**Data:** 13/11/2026. **Estado técnico:** `QA_MARKER_CONTRACT_26_PASS_HOSTED_CRON_STILL_HOLD`.

## Regra de trabalho
A baseline foi documentada e commitada antes de criar a correção, na branch `local/commander-expiry-cron-observer-fix-20261113` a partir de `00438dbfbb21f901ca31ca857fdfc5286767d724`.

## Problema comprovado
No observador da frente paralela `commander-0043-expiry-hosted-qa-20261113`, a leitura `content_redacted` compara o comprimento do marcador de `HARA_REDACTED_SHA256:` com **64 caracteres hexadecimais**. O Worker original gera SHA-256 **base64url sem padding, com 43 caracteres** e os dois bits finais canônicos zerados. O leitor antigo reportaria incorretamente `false` para um marcador válido.

O relatório hospedado anterior contém **zero recibos de Cron**, chamada QA ainda `EXECUTING` e Cron desativado pelo provedor. Corrigir o marcador **não transforma esse resultado em PASS** e não explica sozinho a ausência de execução nativa.

## Correção construída e validadas
- Nova função pura `expiry_cron_readback_contract_20261113.mjs`: valida base64url SHA-256 canônico e avalia dois recibos, quota, expiração, idempotência, estado da chamada, desativação de Cron e invariância comercial.
- Nova suíte `test_expiry_cron_readback_contract_20261113.mjs`: **26/26 testes PASS**, com marcadores válidos, hex64, padding, truncamento, alteração de bits finais, zero/um/três recibos, falta de quota e efeitos duplicados.
- Auditoria `validate_expiry_cron_observer_20261113.py`: confrontou a fonte real do observador antigo, o recibo QA anterior de zero Cron e o recibo de desativação. Estado `QA_MARKER_CONTRACT_26_PASS_HOSTED_CRON_STILL_HOLD`.
- Patch revisável `QA_HOSTED_OBSERVER_BASE64URL43_FIX.patch` corrige exclusivamente a validação do marcador na fonte de QA antiga; **não foi aplicado à worktree paralela nem a qualquer Worker Cloudflare**.

## Limite e próxima correção
Não foi criado deploy, agenda, D1, Agent, Stripe ou modificação de produção. O Worker's hosted QA anterior continua **HOLD sem dois recibos nativos**. Para fechar: revisão do patch pelo owner do worktree QA, verificar se gatilho nativo e binding D1/DO estão corretos, produzir testemunho hospedado real, desativar Cron e colher readback final. Manter `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN`.

**Revisão comercial, migration PROD e FileTools não autorizadas por esta entrega.**