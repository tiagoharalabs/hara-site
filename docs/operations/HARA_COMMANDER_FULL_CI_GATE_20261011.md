# Commander — validação completa automatizada, 11/10/2026

Nova automação: `hara-commander-full-offline-gate.yml`. Responde a pushes e pull requests de main e local/commander-product-current, além de execução manual. Usa a bateria completa e confere o relatório contra o SHA esperado e a lista literal dos validadores. Sem deploy, segredos de produção ou permissão de escrita: apenas contents: read.

Checkout inclui a revisão e o commit histórico assinado 08500d5c4256d25abc77a26ad377e55eadf1742a, necessário aos testes existentes. Dependências npm vêm do lockfile sem scripts de instalação. Node 24 é selecionado no cache do runner Ubuntu 24.04; sua ausência causa falha. A dependência Python cryptography é conferida/instalada no runner, não no Services. Versões efetivamente usadas são registradas; não se trata de ambiente integralmente imutável.

O verificador rejeita outro commit, suítes ausentes/duplicadas, exit code não zero, workload diferente, relatório antigo, duração inválida e alegações indevidas sobre produção. A lista de testes vem de AST, sem executar o gate. Não é assinatura criptográfica nem proteção contra controle malicioso do runner. Requer execução confiável e checkout limpo. O SHA-256 do relatório aparece no resumo.

Validação desta rodada no Services: 72/72 validadores PASS. Relatório válido aceito; 12 variações inconsistentes rejeitadas. YAML analisado e blocos shell aprovados em bash -n. A criação de um arquivo de testes unitários foi bloqueada; os 12 ensaios foram executados em memória e seus resultados preservados. A execução hospedada deve ser conferida após push; não inferi-la dos testes locais.

O workflow legado `hara-commander-scale-v2-validation.yml` permanece byte-idêntico. Sua etapa de sintaxe passou, mas seus guards pararam em validate_human_bootstrap_v2.py: procura fetch direto, enquanto o portal usa portalFetch. A tentativa de corrigir a expectativa foi bloqueada; nenhum teste foi removido. A nova automação é independente e não encerra essa falha legada. A evidência workflow-local-validation.json preserva o resultado não aprovado.

Concorrência cancela apenas validações anteriores deste workflow/ref, não agentes ou deploys. Nenhuma alteração de runtime, preço, banco, frota ou produção. A aprovação dos testes não certifica carga real, custo ou versões em produção.

Evidências: docs/evidence/commander-ci-proof-20261011/. O gate local conserva o HEAD-base 48f68c8; código runtime permaneceu inalterado. Publicação, execução hospedada e implantação devem ser confirmadas separadamente.
