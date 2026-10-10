# H.A.R.A. Commander — distribuição comercial 0.3.43 (assinatura v2)

Conjunto de oito arquivos públicos assinados por RSA-3072, com identidade `commander-release-v2` e manifesto que contém o SHA-256 dos dois Agents e dos dois instaladores. **Nenhuma chave privada está neste diretório.**

O instalador comercial usa `ASK_EVERY_ACTION`, inicia o Agent apenas para a verificação inicial e não habilita autostart ao reiniciar ou ao fazer login. O usuário inicia a sessão pelo terminal local e a encerra manualmente.

A release pública anterior v0.3.41 fica preservada na tag `hara-commander-signed-agent-v0.3.41`, com assinatura e arquivos originais. **Não combine** instalador v1 com manifesto/Agent v2, nem execute um HEAD não assinado.

A distribuição Git não altera automaticamente o Worker Cloudflare. A publicação exige deploy versionado, verificação criptográfica e readback SHA dos assets. Para rollback na Cloudflare, restaurar a versão Worker anterior; para recuperar os arquivos históricos v1, utilizar a tag correspondente.

A instalação Windows está em fase beta: falta prova nativa no Windows PowerShell 5.1 e de autorização por ação para mutações. Não declarar paridade Linux/Windows de ações sensíveis sem homologação.
