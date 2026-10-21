# HARA Commander — R15: aceite independente do v5 congelado, antes da assinatura

Data: 20/10/2026 BRT. Revisão via HARA Commander em branch isolada, sem uso de chave privada ou mudanças no produto/PROD.

## Resultado: fonte pronta para assinatura autorizada, NÃO release pronta para clientes

Verifiquei diretamente o arquivo commitado pelo Codex em `6829cd505452dbfb7d2ad20fb86b3437723c2903`:

`apps/commander/candidate/commercial-0.3.43-v5-terminal-drain-unsigned-a13b4d2.tar.gz`

- **SHA-256** `3ade217145e32899da47bedb43272897ee020e44658ae2b197b0eda61880970d` (igual ao handoff), 190.853 bytes, 27 entradas de tar.
- Arquivo imutável sem symlinks ou entradas especiais; somente arquivos/diretórios; nenhum manifesto de assinatura `agent-manifest.sig.json` dentro do artefato.
- Manifesto v1 declara `agent_version=0.3.43`, SHA-256 `2ec2b3ccddc0fbc5edb577c926315358dbcb558812d3492ec9a68894038ff381`.
- Os **quatro assets** Linux/Windows `agent` e `install` têm tamanhos e SHA-256 coincidentes com manifesto e `release/SHA256SUMS`; o `CANDIDATE_STATUS.json` confere com manifesto, fontes e hashes de UI.
- Ambos os instaladores trazem pin idêntico `kid=commander-release-v2` e `n/e` idênticos às duas JWK públicas incluídas no pacote; fingerprint `93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`. JWK não contém parâmetros RSA privados.
- `agent/linux.py` e `agent/windows.ps1` declaram 0.3.43. Candidato explicitamente `AWAITING_OFFICIAL_SIGNATURE`, `signature_present=false`, `private_key_read=false` e `production_mutation=false`.
- Verificador independente `verify_frozen_unsigned_v5.py` passou (exit 0, `READY_FOR_AUTHORIZED_SIGNATURE`), mais **cinco controles negativos**: alterações sintéticas no Agent Linux, Agent Windows, instalador, manifesto e SHA do tar causaram HOLD. Não assina material nem testa cliente hospedado.

## Decisão operacional

**O Codex não precisa reconstruir esta fonte**: entregar ao custodiante autorizado o digest exato do tar+manifesto e congelar os bytes antes de assinar. A assinatura oficial v2 deve ser aplicada ao manifesto atual **somente pelo procedimento autorizado**, seguida de build do bundle assinado, `stage_signed_commercial_assets.py --check`, readback independente dos seis endpoints públicos e canário de instalação limpa no Storage Fedora43/x86 e Observer Ubuntu22/ARM64.

**Não confundir aceite local com lançamento:** pacote v5 ainda sem assinatura, distribuição pública ainda devolve manifesto v1 contra pin v2 e 4 assets incoerentes; nenhum Cloudflare DEV/PROD foi modificado. O Windows 0.3.55 mais recente do Codex é candidato funcional separado; este v5 continua comercial 0.3.43 para ambas plataformas, com suas limitações conhecidas.

Não acessar chave privada nesta frente de peer-review, não substituir Agent Founder 0.3.54 ou VM Windows instalada, não cadastrar Storage/Observer antes de release oficial e readback. A publicação exige autorização específica e controles de rollback/canário.

Arquivos QA: `docs/evidence/commander-v5-frozen-preflight-r15-20261020/verify_frozen_unsigned_v5.py`, `frozen-release-preflight.json`, `README.md`, `SHA256SUMS`. Estes são os dados que a frente Codex pode reutilizar no handoff de assinatura sem consumo adicional de execução pesada.
