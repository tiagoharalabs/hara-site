# H.A.R.A. Commander — baseline pré-mudança: diagnóstico do Cron QA de expiração

**Data:** 13/11/2026. **Branch:** `local/commander-expiry-cron-observer-fix-20261113`. **Base:** `00438dbfbb21f901ca31ca857fdfc5286767d724`.

## Estado observado ANTES de corrigir o observador

Existe uma frente separada `commander-0043-expiry-hosted-qa-20261113` com Worker QA exclusivo `hara-commander-0043-expiry-qa-20261113`, D1 QA próprio, sem rotas públicas nem acesso a Agents. **Não interferir nesse worktree, que contém arquivos não commitados de outra frente.**

Recibos pré-existentes indicam uma tentativa de Cron nativo em QA com **zero recibos de execução**, chamada sintética ainda `EXECUTING` e payload não redigido. O Cron QA foi desligado e confirmado com `schedules=[]`; PROD permaneceu na versão comercial anterior. Não transformar isso em teste hospedado PASS.

**Defeito específico reproduzível de diagnóstico:** o observador `observe_0043_expiry_qa_20261113.py` usa `len(marker)==len("HARA_REDACTED_SHA256:")+64`, porém a implementação original de `sha256()` do Worker gera **base64url sem padding (43 caracteres)** para 32 bytes. Logo, um payload corretamente redigido seria reportado incorretamente como não redigido. Isso **não explica sozinho** por que a execução do Cron não produziu recibos.

## Plano seguro de correção

Adicionar ao produto uma função **pura, sem rede e somente de QA**, que valide marcador de SHA-256 base64url em formato canônico, recuse hex64/padding/truncamento, e classifique recibos nativos: zero recibos = `HOLD_CRON_NOT_OBSERVED`, um recibo = `HOLD_SECOND_NATIVE_CRON_MISSING`, dois recibos coerentes = PASS somente quando state, quota e metadados batem. Qualquer indeterminação deve permanecer HOLD.

Testar os contratos com exemplos sintéticos e adulterações; preservar o antigo worktree de QA, sem deploy ou reativação de Cron. Gerar recibo write-once e commit Services → Storage. Publicar código de QA em PR draft sobre main sem afetar o código do Worker. A homologação comercial continuará `LEDGER_RECOVERY_COMPATIBILITY_UNPROVEN` até testemunhos hospedados conclusivos.

**Proibido nesta fase:** alterar QA Worker hospedado que outra frente usa, criar nova agenda, tocar D1 PROD, quota real, Agents, Stripe, secrets, reviewer ou App OpenAI.