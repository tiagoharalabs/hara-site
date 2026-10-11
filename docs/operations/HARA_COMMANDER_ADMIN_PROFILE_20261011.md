# H.A.R.A. Commander — perfil administrativo ampliado, 11/10/2026

Checkpoint base: 76f7d12. Esta mudança amplia apenas o perfil MCP simples com cinco primitivas READ_ONLY já existentes no Agent/contrato: get_system_uptime, get_system_resources, inspect_workspace, hash_file e diff_files.

O produto já possuía write/edit/delete, preimages/rollback, list/search/read, processos one-shot e interativos, sessões, kill, atividade e recibos. A ampliação evita usar shell quando uma primitiva de diagnóstico ou integridade mais restrita é suficiente. Não adiciona bypass de autorização, não muda ASK_EVERY_ACTION/PERSISTENT_TRUSTED, não altera preços, CSS, agentes assinados ou armazenamento de conteúdo.

Compatibilidade Linux: system uptime/resources/workspace exigem Agent >=0.3.24; hash/diff >=0.3.23. A frota Founder online respondeu 0.3.44 nesta data. Windows legado 0.3.14 permanece fora desta homologação.

Testes: test_customer_mcp_admin_profile.mjs 5/5 PASS; test_customer_mcp_simple_profile.mjs PASS com 32 ferramentas; gate completo 73/73 PASS, 1.000 tentativas/24 threads nos cenários internos. Estes testes são locais e não certificam escala cloud.

Ações futuras de energia/configuração do sistema devem ganhar primitivas explícitas e política própria; não são incluídas automaticamente só porque start_process permite comandos governados.
