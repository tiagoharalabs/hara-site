# HARA Commander — revisão independente para a frente Codex

Data: 2026-10-20, coleta iniciada 18:38 UTC. Revisor: Valky.
Workspace: `/home/sartorius/hara-workspaces/commander-prelaunch-fixes-20261020`.
Base observada: `482169251b347b77380d8becf878e5c515c75c8a`.
Branch: `codex/commander-prelaunch-fixes-20261020`.

Este arquivo é apoio à sessão já iniciada pelo proprietário. NÃO cria outra implementação nem amplia autorizações. Nenhum arquivo de código da frente foi alterado pelo revisor. Não é autorização para deploy, mudança de sandbox, acesso a chave privada ou cobrança. O Codex continua sendo o único escritor dos patches de produto.

## 1. Rede: não tratar o primeiro erro do curl como indisponibilidade do produto

No Núcleo, fora da sessão Codex, `getent ahostsv4 commander.haralabs.com.br` resolveu e GET de `release/agent-manifest.json` respondeu HTTP 200 em 18:38:21Z. Não alterei DNS, firewall ou configuração Codex. Uma restrição do sandbox é hipótese compatível com o erro inicial, não diagnóstico fechado. A própria atualização visível do Codex de 18:38:52Z já informa ter reproduzido a divergência por GET. Portanto, não reiniciar nem ampliar permissões só por causa do primeiro erro. Quando necessário, solicitar aprovação normal e específica para leitura de rede.

## 2. P0 — o erro de assinatura antecede o erro de SHA

Nova coleta independente em 18:39:12Z, via HTTPS público, sem executar instaladores:

- Manifesto: Agent `0.3.41`; SHA-256 `7e42f25404e414b74b375ccb47b7ed8ba7d8c572dc45db994d89012207f08f7c`.
- `release/agent-manifest.sig.json`: `alg=RS256`, `kid=commander-release-v1`, referência ao SHA acima.
- Instalador Linux servido: pin `RELEASE_SIGNING_KID=commander-release-v2`.
- `download_agent()` verifica assinatura ANTES de hash e versão. No caminho examinado, o primeiro erro esperado é `AGENT_RELEASE_SIGNATURE_INVALID`, não apenas `AGENT_SHA256_MISMATCH`.
- Corrigir somente `agent-manifest.json`/SHA256SUMS não basta. O conjunto precisa de manifesto + assinatura + âncora pública + pins dos instaladores + arquivos exatos.

| Arquivo | SHA declarado no manifesto público | SHA efetivamente servido |
|---|---|---|
| agent/linux.py | e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730 | 1572d70e60fb299edb262a8a817bd7aa1740a4c2dda3635d50beb2f3476ffe3b |
| agent/windows.ps1 | 52bb1b3c537c31a357becc38c494ea8494bf310fc3e694d59b1a578509a56d44 | d507a6f91a635b025ef4f06cbd758a03c7da6f3410aadec9a3d76c28f904c6fb |
| install/linux.sh | 99b25c7671326b983ff1fa670ce0044f9a89674dcd1b2d78cf8ab4a6cccb828b | 699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463 |
| install/windows.ps1 | 475d7afe4440fc760adfcb333e1922d5a9eb3d7bb49ca571c4c5741519bdc240 | 6ba5c29e6d3a604750331d7699455ad609b4b0a8e191c03ad10503f7a5161c3c |

Nenhuma evidência desta comparação, isoladamente, demonstra invasão. Demonstra distribuição inconsistente e necessidade de revalidar o pipeline.

## 3. Atenção: publicar o bundle antigo inteiro pode reintroduzir perda de saída

Os bundles `commercial-0.3.43-v3` e `commercial-0.3.43-v4-autoreconnect` passaram verificação criptográfica independente nesta revisão:
- Chave pública RSA-3072 ancorada no fingerprint `93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4`.
- Assinatura RS256 válida e quatro hashes/tamanhos coerentes em cada bundle.
- Alteração de um byte no manifesto foi rejeitada na verificação.
- Nenhuma chave privada foi lida, usada ou exportada.

Entretanto, **assinado não significa conter todas as correções atuais**:
- Linux no v4: SHA `3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7`.
- Linux servido/`public/agent/linux.py`: SHA `1572d70e60fb299edb262a8a817bd7aa1740a4c2dda3635d50beb2f3476ffe3b`.
- Ambos declaram versão `0.3.43`, mas a AST mostra uma função nova `_drain_completed_process_output` e alteração de `_process_update_state` no código servido.
- v4 fecha o fd logo após waitpid; fonte atual drena saída pendente ANTES de fechar o descritor.

### Regressão reproduzida independentemente

Executei harness determinístico em memória, compilando SOMENTE essas duas funções via AST, com pipe não bloqueante contendo 120 linhas e waitpid simulado. Não importei/iniciei o Agent completo nem modifiquei seu serviço.

| Implementação | Linhas preservadas | Exit code reportado | fd fechado |
|---|---:|---:|---|
| Signed v4 antigo | 0 de 120 | 0 | sim |
| Fonte pública atual | 120 de 120 | 0 | sim |

Escopo: prova de regressão no algoritmo de drenagem, NÃO homologação real de PTY/Windows/Agent. Acrescentar o caso à suíte local e confirmar posteriormente com processo/PTY real isolado.

**Recomendação ao executor:** não restaurar v3/v4 inteiro cegamente como correção definitiva. Produzir candidato que preserve a drenagem pós-exit e demais correções aprovadas, mantendo assinatura oficial pelo fluxo autorizado. Se o único artefato atualmente assinável for um bundle antigo, registrar a regressão/limitação e obter decisão explícita de release; não chamá-lo de equivalente funcional à fonte atual.

## 4. Seleção de staging: dois indícios concretos, causa do deploy ainda a provar

Na base examinada:
- `apps/commander/scripts/stage_signed_commercial_assets.py` fixa `SIGNED = ...commercial-0.3.43-v3` e retorna relatório de release v3.
- O bundle v4-autoreconnect existe; seu instalador Linux tem SHA `699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463`, igual ao instalador público observado.
- `apps/commander/wrangler.jsonc` ainda possui `assets.directory=public`.

Esses fatos permitem misturar fontes de desenvolvimento, releases assinados e UI se um deploy ignorar o staging. Não provam sozinhos qual comando causou a publicação inconsistente. Rastrear a configuração efetiva do último deploy e corrigir o caminho de promoção, sem sobrescrever Worker/bindings/secrets.

Um simples gate que compara staging com bundle antigo pode ficar verde e mesmo assim selecionar o release errado. Testar seleção explícita de release, preservação de autoreconnect, manifesto/pins e correspondência com URLs servidas. Não reescrever bundles assinados históricos para fazer testes passarem.

## 5. Critérios adicionais para revisão dos patches

1. P0 artefatos: pacote completo, assinatura confiável, hashes/bytes/versões, pins e negativa contra mistura de releases; teste da drenagem pós-exit preservado.
2. Verificador público: fazer GET e validar corpo, não só HEAD/HTTP200; falhar fechado em timeout/404/assinatura inesperada. Não imprimir segredos e não executar código baixado.
3. Catálogo: conservar decisão R$80, cinco PCs, 5.000 gratuitas totais, 1.000.000 mensais compartilhadas e Founder separado. Não inventar limite de usuários.
4. Período: o código atual distingue CALENDAR_MONTH/LIFETIME/NONE; alinhar cota paga e fim de acesso ao período contratado sem dois resets indevidos. Propor e documentar decisão ainda necessária.
5. Cinco PCs: prova de concorrência no backend, não só teste sequencial/botão desabilitado. Cuidado para não consumir token de pairing quando o teto bloqueia a inserção.
6. Retenção: não usar DELETE de registros COMMITTED como limpeza sem provar preservação de consumed_units e proteção contra replay.
7. Estados: corrigido no código / testado local / testado DEV / publicado PROD são diferentes. A aprovação original permanece sem deploy PROD, sem assinatura privada automática, sem Stripe LIVE ou billing OpenAI.

## Coordenação

Este arquivo é a única contribuição escrita do revisor no clone até esta entrega. Não contém credenciais nem dados fiscais/pessoais. Não houve commit, reset, troca de branch, edição de PROGRESS.md ou acesso/injeção no terminal do Codex. O executor pode incorporar os testes/achados e versionar a nota junto às suas evidências quando apropriado.

## 6. Revisão dos primeiros patches do Codex — execução independente

Após o executor criar o verificador e alterar o staging, executei em separado, com bytecode desativado e apenas diretórios temporários de teste:

```text
python3 -B apps/commander/scripts/test_signed_distribution_stage.py -v
10 testes / PASS / exit 0

python3 -B apps/commander/scripts/stage_signed_commercial_assets.py --check
PASS / COMMERCIAL_0_3_43_V4_AUTORECONNECT / exit 0
cloud_operations=false; ui_unchanged=true
```

Comparei os hashes dos cinco arquivos abaixo antes/depois da execução: permaneceram iguais durante estes testes. Não fiz commit nem alterei o código do executor.

```text
verify_signed_distribution.py     9cc5dc4abc8f1dc576d9cab1a9a84f4cb2a23049239f950485598ca210733c8e
test_signed_distribution_stage.py 82218caafe56ea6087707d1876ceba7eb82c0fd036fde3c262d18d6d30047f57
stage_signed_commercial_assets.py a3fb8ec2b30c9d2820530b8144ab5454b657e7ff83318aa1ca38725404833848
wrangler.jsonc                   7daa383b19922b7fadb6423dadcbba5a70d01e5d311279467a8c35f2b858c8d3
wrangler.dev.jsonc               944c85566ae7f300de615fbead24c4885447038ddcd9c7bdbffcaff299428451
```

**Parecer:** avanço real de seleção/integridade e negativas criptográficas. Estes PASS não fecham o risco funcional da seção 3: o default v4 continua selecionando o Linux antigo, sem `_drain_completed_process_output`. Exigir teste pós-exit com saída preservada e decisão explícita de release antes da promoção. Também não são prova de instalação limpa, aceite Windows, verificação pós-deploy ou autorização de PROD.
