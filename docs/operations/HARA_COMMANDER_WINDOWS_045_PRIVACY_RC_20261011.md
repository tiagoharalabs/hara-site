# H.A.R.A. Commander — Windows 0.3.45-v5 (candidata privada)

Estado em 11/10/2026 (America/Sao_Paulo): **release RS256 assinada; Windows 11 VM dinâmica PASS; gate local 89/89 PASS; NÃO publicada/instalada no cliente real**.

## Problema de privacidade comprovado e correção

O Agent Windows 0.3.44 registrava uma prévia de comando e caminho privado dentro do `console-events.jsonl`, apesar de declarar `payload_values_exposed=false`. Teste com marcador sintético na VM Windows 11 comprovou `command_content_persisted=true` e `private_path_persisted=true`. A correção deixa `action_summary=null` no evento persistente, mantendo metadados de ferramenta, estado e request ID. O resumo visível durante a autorização segue transitório e local para que a pessoa possa revisar a operação.

A versão 0.3.45 também melhora o resumo no pedido para `process.start`, `process.interact` e `process.kill`, sem ampliar permissões. A janela de confirmação individual foi ajustada de 22 para 30 segundos; segue com nonce por ação, hash de argumentos, sessão local válida, recusa na ausência de resposta, nunca aprovação automática.

## Evidências independentes

- Pacote `apps/commander/release-bundles/commercial-0.3.45-v5-rc` assinado RS256 RSA3072 com âncora existente e manifesto SHA-256. Windows Agent SHA256 `c370bff84b283172dcbcc40ee5f426e3b3d09b9181d3227755093d8577443dab`. Windows 0.3.44-v4, 0.3.43-v3 e Linux pré-existentes preservados; arquivos Linux byte-idênticos.
- Fonte e **binário Windows assinado** 0.3.45 transferidos à VM `commander-win11` em ambiente de laboratório separado, assinatura/hash e parser PowerShell 5.1 PASS, autoteste do Agent PASS.
- A repetição do ensaio de privacidade sobre os bytes assinados 0.3.45 confirmou **sem comandos/caminhos privados no log persistente**, mantendo metadata da ferramenta e request ID.
- Ensaio de recusa sobre os bytes assinados: **15/15** (sem sessão, negativa, nonce incorreto, expiração, limpeza, ausência de mutação), sem credenciais ou aprovação humana simulada.
- `validate_windows_045_privacy_contract.py` confirma limites e semântica de aprovação. O validador 0.3.44 antigo foi fixado ao SHA de seu pacote assinado, independentemente da fonte Windows mais nova.
- Prelaunch offline total **89/89 PASS**, sem deploy Cloudflare nem alteração de usuário real, antes da publicação desta candidata.

## Estado real e limites

O Agent **0.3.44** continua instalado e ONLINE na VM `HARA_WIN11`; o Windows público segue **0.3.43**, e o Worker PROD segue a revisão anterior, com publicação version-gated de sessões Windows >=0.3.44.

A aprovação positiva **não foi testada**: a tentativa de `hostname` no MCP real sob 0.3.44 expirou corretamente com `LOCAL_ACTION_APPROVAL_EXPIRED`. É necessário que a pessoa confirme na janela do operador da VM. Não se deve criar respostas artificiais, alterar `approval_mode` ou interpretar autorização do chat como confirmação local.

Também permanecem pendentes: transferência binária nativa entre máquinas, comportamento sob reinício de Agent com sessão interativa, homologação Windows Event V2 e 1.000 tenants autenticados em soak real.

## Próximo gate

1. GitHub CI do SHA exato 0.3.45-v5 deverá passar antes da instalação na VM.
2. Preparar pacote e backup 0.3.44 dentro da VM, sem novos tokens ou pareamento.
3. Instalar v5 somente como canário local, preservar configuração byte-idêntica e tarefa agendada.
4. Usuário local aprova um comando sintético, nega outro e confere o que foi executado; depois testar escrita, SHA/CAS e subprocesso interativo com recibos pelo MCP comercial.
5. Só após estes critérios publicar em DEV, avaliar PROD comercial e distribuir a clientes; Stripe continua independente.

Provas estruturadas: `docs/evidence/commander-win45-20261011/acceptance.json`.
