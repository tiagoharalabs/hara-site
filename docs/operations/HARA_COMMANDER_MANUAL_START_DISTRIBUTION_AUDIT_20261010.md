# H.A.R.A. Commander — auditoria de instaladores, startup manual e contingência Git
**10/10/2026 · linha canônica `local/commander-product-current` · PROD preservado**

## Decisão de produto

**Instalar → iniciar uma vez → validar → sem autostart no próximo boot/login.** Conexão Cloud não deve ficar pendurada indefinidamente no computador do cliente. Após um reboot, o computador está **offline por decisão do usuário**; o ChatGPT não tem como ligar sozinho uma máquina desligada ou um Agent parado.

O cliente técnico usa `hara-commander start` para habilitar o Agent e abrir a sessão local, ou `hara-commander mcp` para o modo local STDIO sob demanda. Encerrar com Ctrl+C/ `hara-commander stop` revoga a sessão. O produto **não** deve oferecer um checkbox de "iniciar automaticamente" no onboarding público. Persistência é uma operação técnica explícita, de responsabilidade do administrador da máquina.

**Não confundir:** a conexão WebSocket do Agent comercial ao Worker Cloudflare não é o processo MCP STDIO local. Iniciar o MCP local sob demanda já é possível; um Agent Cloud offline retorna indisponível às chamadas do ChatGPT até o cliente iniciar o processo localmente.

## Onde os arquivos estão publicados, com provas reais

| Superfície | Readback e papel | Política confirmada |
|---|---|---|
| **Cloudflare PROD** `https://commander.haralabs.com.br/install/linux.sh` | HTTP 200, SHA256 `99b25c7671326b983ff1fa670ce0044f9a89674dcd1b2d78cf8ab4a6cccb828b` | **ANTIGA**: `systemctl --user enable --now`, inicia no login/boot |
| **Cloudflare PROD** `https://commander.haralabs.com.br/install/windows.ps1` | HTTP 200, SHA256 `475d7afe4440fc760adfcb333e1922d5a9eb3d7bb49ca571c4c5741519bdc240` | **ANTIGA**: tarefa `AtLogOn` |
| **Cloudflare PROD** `agent/linux.py` / `agent/windows.ps1` | SHA256 `e1f44e46...` / `52bb1b3c...` | Release pública 0.3.41 |
| **Cloudflare PROD** `release/agent-manifest.json` e `agent-manifest.sig.json` | SHA256 `7e42f254...` / `b755f0fd...` | Manifesto v0.3.41; **RSA RS256 verificado** com chave pública pinada |
| **GitHub, contingência imutável** | **Tag** `hara-commander-signed-agent-v0.3.41` | GitHub tag, commit exato `08500d5c4256d25abc77a26ad377e55eadf1742a`; todos os seis assets byte-idênticos à Cloudflare; GitHub exact readback **PASS** |
| **GitHub branch de desenvolvimento** | `local/commander-product-current` | Contém código candidato e manifesto legado; **não** baixar HEAD como release assinada de cliente |
| **Storage Git protegido** | `092f35afc52827d6c5584f0401e9f60eaeb3d985` | Fonte dos instaladores **diverge** dos hashes do manifesto v0.3.41; **NÃO serve de contingência instalável**. `HOLD`, sem force push |
| **Cloudflare DEV** | URL `hara-commander-dev-v2...workers.dev/install/linux.sh` respondeu 403 | Não é fonte de instalador público alternativo |

**Origem de publicação:** o Cloudflare Worker `hara-commander` usa Wrangler `assets.directory="public"` e domínio personalizado `commander.haralabs.com.br`. **Enviar commits ao GitHub não instala assets na Cloudflare**. A promoção ocorre via pipeline de release/deploy do Worker, não via Git puro.

**Prova reproduzível de contingência:** `python3 -B apps/commander/scripts/verify_commander_public_artifacts.py --check` valida tag/base Git e assinatura RSA; `--live` lê os seis assets Cloudflare e exige SHA exato. Não lê tokens nem modifica PROD. A tag imutável está no GitHub, mas restaura o **comportamento antigo de autostart** — somente para recuperação da antiga release, nunca para anunciar a nova política comercial manual.

## Ajustes implementados exclusivamente no código candidato

### Linux

- Instalação registra um unit de usuário e executa `systemctl --user disable` + `systemctl --user start` para **atestar startup inicial sem habilitar no boot**; aborta se continuar habilitado.
- Unit com `Restart=on-failure` para recuperar erro enquanto a sessão foi voluntariamente iniciada, **não** `Restart=always` e não enabled no login/boot.
- `hara-commander start` exige terminal local, inicia o unit inativo (verbo/nome fixos, sem shell arbitrário) e abre o console de aprovação. Ao fechar, **para a unidade somente se esse comando a iniciou e se ela não estiver habilitada**; respeita uma unidade já ativa e um opt-in avançado.
- `hara-commander stop` revoga sessão e para unit; `status` imprime presença ativa e `AUTOSTART=ON/OFF`.
- Instalar, atualizar parado, atualizar ativo, re-enrolar e desinstalar foram provados em harness isolado com systemctl falso, conta local temporária, mock API HTTP loopback e manifesto assinado **por chave RSA efêmera de teste**. Chave efêmera não é chave de produção nem substitui release assinada.
- Atualizar um Agent inativo **não cria conexão**. Re-enrolar um inativo faz atestado temporário e para novamente. Agent ativo continua ativo durante update/reenroll.

### Windows

- Instalador cria a tarefa agendada **sem nenhum trigger `AtLogOn`/`AtStartup`**, verifica essa ausência e inicia a tarefa uma vez para atestação.
- Script instalado `hara-commander-agent.ps1 start` inicia a tarefa manualmente e abre o console; ao encerrá-lo, para a tarefa que o comando iniciou se ela continuar sem triggers. `stop` revoga a sessão e para a tarefa.
- `status` imprime se há trigger (autostart), e um update preserva o estado parado do cliente.
- **Windows ainda requer teste real em Windows PowerShell 5.1, tarefa agendada, reboot e homologação de autorização por ação.** A implementação Windows de autorização `ASK_EVERY_ACTION` ainda recusa certas mutações como fail-closed; não anunciar Windows com paridade Linux de operações sensíveis antes de prova end-to-end.

### Portal / onboarding

- `public/index.html` e `public/app.js` foram sanitizados: `ASK_EVERY_ACTION` fixo para novos clientes; `HARA_COMMANDER_TUNNEL_AUTOSTART=OFF` fixo; sem seletor de `PERSISTENT_TRUSTED` ou checkbox de autostart na página; caminhos Cloud e Direct continuam distintos.
- O portal ensina conexão manual, parada local e o fato de que não há reconexão automática após reboot. O JS ganha cache key `20261010-manualstart1`.
- **Opção técnica avançada, fora do onboarding:** um administrador Linux pode deliberadamente mudar o modo de autorização e usar `systemctl --user enable --now hara-commander-agent.service`. Esse comando aumenta o tempo de exposição da máquina e pode ficar conectado durante todo login; não deve ser o default e não é oferecido no site. Tarefas Windows podem receber trigger manualmente no Task Scheduler por administrador, sujeito ao próprio controle local.

## Validação e gating

- `validate_manual_on_demand_commercial.py` testa Linux start/stop, TTY obrigatório, lista fixa de comandos, exceção/limpeza e assinaturas estáticas de política Windows.
- `commander_linux_clean_lifecycle.py --execute` **PASS** após assinatura efêmera e simulações de instalação, parada, atualização, início manual, re-enrolamento e desinstalação.
- `validate_prod_static.py`, `validate_bootstrap_supply_chain.py`, `validate_linux_tunnel_start_modes.py` agora validam a UX manual por padrão; o teste de supply chain compara **somente a release v1 assinada** à sua versão histórica, não confunde fontes candidatas e manifesto antigo.
- `commander_prelaunch_offline_gate.py` inclui essas provas e SQL stress isolado (1.000 tentativas / 24 threads); **não executa stress Cloudflare PROD**.
- `apps/commander/candidate/install_linux_rc.sh` / `install_windows_rc.ps1` são **instaladores experimentais de canário Event V2**, separados do onboarding público e não alterados pela política deste lançamento. A frota Founder 0.3.44 e seus watchdogs permanecem intocados.

## O que impede promoção para clientes agora

1. **Assinar pacote comercial novo** contendo Agent Linux, Agent Windows, instaladores Linux/Windows e manifesto/assinatura **todos consistentes**. A chave antiga da release v1 está pinada em instaladores já distribuídos; seguir governança de rotação de chave e compatibilidade do upgrade. Não sobrescrever v1 seletivamente.
2. Testar em computador Linux limpo com reboot real, reconexão manual, offline verdadeiro, `ASK_EVERY_ACTION`, rollback e upgrade. Para anunciar Windows, fazer o mesmo em Windows PowerShell 5.1 real.
3. Testar canário Cloudflare **DEV primeiro**, UI/instalador/Agent/manifesto assinados, e publicar em PROD por rollout versionado com readback SHA de todos os assets. Cache de assets/página precisa refletir a mesma versão.
4. Não confundir "site público disponível" com "plugin OpenAI listado/aprovado"; publicação de app ainda tem gates separados.

**Status final desta auditoria:** segurança manual corrigida no **código candidato e Git**, tag imutável antiga publicada como contingência, Cloudflare PROD ainda entrega v0.3.41 com autostart e aguarda nova release assinada. **Nenhuma mutação Cloudflare PROD, Storage Git protegido, frota Founder ou cobrança ocorreu.**
