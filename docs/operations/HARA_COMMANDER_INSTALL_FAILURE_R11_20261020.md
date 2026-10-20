# HARA Commander — R11 | Instalação falha em Storage/Observer e atualização da Sentinela A
Data: 20/10/2026. Responsável da revisão independente: Valky. **Somente HARA Commander**. Esta é uma revisão do nosso produto, não instalação concorrente.

## Resultado de prioridade máxima

**P0 — a distribuição pública não é um release criptograficamente coerente.** Uma instalação nova da versão Linux servida hoje não pode atravessar os próprios gates de autenticidade/integridade sem erro. O bloqueio independe de Storage ser Fedora 43 ou Observer ser Ubuntu 22.04.

Evidência HTTPS pública, obtida diretamente por Services, Storage, Observer e Núcleo por HARA Commander (GET sem credenciais; nada foi instalado):

- Manifesto em `/release/agent-manifest.json` SHA-256 `7e42f25404e414b74b375ccb47b7ed8ba7d8c572dc45db994d89012207f08f7c`, declara `agent_version=0.3.41`.
- Assinatura publicada é **RS256 kid `commander-release-v1`**, válida criptograficamente **somente quando verificada pela chave v1 do antigo instalador presente na fonte Git**.
- Instalador Linux **realmente servido** em `/install/linux.sh`: SHA-256 `699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463`. Ele exige **kid `commander-release-v2`**, que **não coincide** com a assinatura pública v1. A assinatura não passa no instalador real. Um arquivo local da fonte Git ainda tem pin v1, portanto verificar usando só o instalador do repositório dá um PASS enganoso para o artefato efetivamente instalado pelo usuário.
- Além desse bloqueio inicial, **quatro assets** entregues publicamente possuem SHA-256 diferente dos quatro esperados no manifesto assinado:

| Artefato | SHA-256 declarado | SHA-256 efetivamente servido | Confere? |
| --- | --- | --- | --- |
| `agent/linux.py` | `e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730` | `1572d70e60fb299edb262a8a817bd7aa1740a4c2dda3635d50beb2f3476ffe3b` | **NÃO** |
| `install/linux.sh` | `99b25c7671326b983ff1fa670ce0044f9a89674dcd1b2d78cf8ab4a6cccb828b` | `699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463` | **NÃO** |
| `agent/windows.ps1` | `52bb1b3c537c31a357becc38c494ea8494bf310fc3e694d59b1a578509a56d44` | `d507a6f91a635b025ef4f06cbd758a03c7da6f3410aadec9a3d76c28f904c6fb` | **NÃO** |
| `install/windows.ps1` | `475d7afe4440fc760adfcb333e1922d5a9eb3d7bb49ca571c4c5741519bdc240` | `6ba5c29e6d3a604750331d7699455ad609b4b0a8e191c03ad10503f7a5161c3c` | **NÃO** |

O Agent Linux servido contém a identificação `0.3.43`, diferente do manifesto `0.3.41`. O CDN respondeu HTTP 200 e `cf-cache-status: HIT` nas consultas HEAD; isso **não prova isoladamente** que cache causa o drift, sobretudo porque o repositório local contém misturas históricas de manifesto e assets. Proibir a solução simplista `curl -k`, desativar SHA/assinatura ou substituir kid só no cliente.

**Registros reais do Codex já existentes** (`PROGRESS.md` e `docs/evidence/commander-public-distribution-20261020-2306z.json`): três tentativas de Storage/Observer terminaram em `AGENT_RELEASE_SIGNATURE_INVALID` com rollback `HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=PASS`; uma quarta tentativa teve HTTP 401 antes de baixar o instalador, **não reproduzido** aqui, sem causa atribuída. A prova do revisor confirma criptograficamente o bloqueio, não precisa cadastrar mais dispositivos para repetir.

## Comparação de três distros e o Services

**Storage (Fedora Linux 43 Server):** Python 3.14.4, SELinux Enforcing, curl/systemctl/openssl/sha256sum disponíveis, `systemctl --user` e DBus saudáveis, GET público 200 em quatro endpoints, sintaxe `bash -n` do instalador e `ast.parse` do Agent público: ambos PASS. Não há `device.env`, unidade Agent, binário Agent nem CLI Commander principal instalados. Há apenas coleta de telemetria `hara-commander-telemetry-collector.*`, que **não é** o Agent MCP de cliente. **Selinux ainda precisa teste de instalação assinada em QA**; não há evidência de AVC específico ou de erro na plataforma em si.

**Observer (Ubuntu 22.04.5 LTS):** Python 3.10.12, UID do usuário sartorius 1001, curl/systemctl/openssl disponíveis, `systemctl --user` e DBus saudáveis, GET público 200, `bash -n` e `ast.parse` PASS. Também sem device.env/unidade/binário/CLI principal. UID diferente exige que instalador use `id -u` e não 1000 fixo — o script consultado já usa valor dinâmico. O HTTP 401 histórico NÃO foi reproduzido; precisa trace redigido de HTTP/Cloudflare, sem inferência de credenciais erradas.

**Services (Ubuntu 24.04):** Agent **Founder interno 0.3.54 Event V2** ativo no `hara-commander-agent-v2.service`; legacy `hara-commander-agent.service` inativo. Seu funcionamento **não comprova** que a instalação comercial do site esteja íntegra. É uma referência de funcionalidade do Agent, não um teste negativo do mecanismo público de assinatura.

## Sentinela A — upgrade necessário, mas NÃO ativar às cegas

- Pop!_OS 22.04, Python 3.10.12; Agent atual **0.3.41** ONLINE, `hara-commander-agent.service` ACTIVE/ENABLED.
- Binário atual SHA-256 **`e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730`**; coincide **exatamente** com o arquivo Linux esperado pelo manifesto v1 antigo. Portanto a Sentinela A está num binário antigo coerente com a release assinada v1; não é sinal de corrupção do Agent.
- Há release Event V2 0.3.54 pré-disponibilizada em `~/.local/share/hara-commander/releases/0.3.54-event-v2-fleet-20261013-1639-r2`, com unidade `hara-commander-agent-v2.service` INACTIVE/DISABLED. Uma candidata 0.3.54 dev r2 também existe.
- Importante: o arquivo `candidate/linux_founder_event_v2.py` do release 0.3.54 em Sentinela A tem SHA `0267fe2768c59a58c24492f4bb421eb91ffb1d56543a5be3240fcd5baae94212`; arquivo do **mesmo caminho/rótulo** no Services funcional tem SHA `6f71373114c36c2d9cf6b0c3ae6566c61c20dcf95f6d4271b26b7f73353f1f24`. Isso **não prova adulteração** (são wrappers de tamanhos diferentes, potencialmente build/host-specific), mas impede considerar rótulo de versão suficiente para promover.
- A R9 mostrou 4 chamadas read-only na Sentinela A antiga com 9–16 s de espera de fila; nova fonte Codex `f682037` otimiza rajadas do relay Linux, mas **não está instalada**.
- Antes do cutover, exigir hash de todas as fontes necessárias, origem do bundle, selftest em sandbox, plano de backup/rollback da configuração individual (sem copiar token de Services), confirmação de Agent novo e ping pelo próprio Commander, e janela/consentimento para possível breve perda de acesso. **Nenhum serviço Sentinela A foi reiniciado, desabilitado ou atualizado nesta revisão.**

## Trabalho objetivo para o Codex

**P0-RELEASE-01 — Corrigir a entrega pública, não burlar a segurança.** Gerar release **única**, com assets Linux/Windows e instaladores correspondentes à versão, manifest, `kid` e assinatura RS256 **oficial**, por fluxo autorizado e com chave sob custódia. Publicar de modo consistente, idealmente release imutável versionado e atualizar ponteiro público *por último*. Antes de alterar o canal principal, ler de novo via Services, Storage e Observer e comprovar bytes e hashes. Não publicar candidate sem assinatura; não substituir arquivos soltos mantendo manifesto velho.

**P0-RELEASE-02 — Fail-fast antes de cadastrar host.** A sequência do instalador registrada pelo Codex hoje realiza enrollment e só depois baixa/verifica release. Inverter quando possível: antes de qualquer mutação de registro, obter/validar release pública e metadados de integridade; se falhar, devolver erro claro `RELEASE_SIGNATURE_KID_MISMATCH`/`RELEASE_ASSET_DIGEST_MISMATCH` e não consumir pairing/gerar dispositivo. Preservar rollback idempotente do que já for criado quando houver falha posterior. Nunca registrar credenciais em arquivos QA.

**P1-PORTABILITY-03 — Testar clean install nas três bases sem atalhos.** Fedora 43 Server com SELinux Enforcing/Python3.14/UID1000; Ubuntu 22.04 Python3.10/UID1001; Ubuntu24.04 do Services somente se for instalação comercial limpa isolada, sem mexer no Agent Founder. Verificar DBus user e lingering somente quando necessário, permissions 0600, systemd user, lifecycle/upgrade, erros de selinux AVC e remoção segura. Não classificar pacote como multi-distro apenas com `bash -n` e AST parse.

**P1-SENTINELA-A-04 — Plano de atualização reversível.** Preservar Agent funcional v1, validar a candidata 0.3.54 de A versus Services e o novo release assinado; instalar/ativar novo Agent em canário com rollback e ping, sem copiar `device.env` entre hosts nem desligar o serviço capturador da Sentinela A. Não executar cutover in-place até readback da assinatura e aprovação específica de produção.

**P1-DOWNLOAD-05 — Distinguir HTTP 401 pontual** de erro criptográfico: coletar apenas status, URL sem segredo, estágio, trace/correlation ID sanitizado, redirecionamento e versão Cloudflare; não repetir credenciais/token em tickets.

**P1-RELEASE-06 — Impedir novo drift com gate público independente.** Rodar o teste de verificação ao vivo *depois* de publicar e antes de habilitar onboarding. Verificar assinatura com a chave efetivamente pinada no instalador **servido**, não apenas com a chave do arquivo local/manifesto, e todos os 4 assets; testar vários hosts/POPs e gate fail-closed. Os testes locais de stage continuam necessários e não substituem leitura pública.

## Arquivos

`docs/evidence/commander-install-compat-r11-20261020/` contém `peer_public_release_integrity.py` e `public-integrity-results.json`. O script faz somente GET HTTPS com limite de tamanho e bloqueio a redirecionamentos, verifica matematicamente RS256 e os quatro hashes e sai **2** ao detectar distribuição inválida. **Saída 2 = achado reproduzido, não suíte aprovada.** `host-preflight.json` documenta as diferenças das distros/Services/Sentinela A sem segredos; outros arquivos de integridade em `SHA256SUMS`.

A execução em 20/10/2026 às 23:23 UTC verificou:
- assinatura antiga válida com o pin **v1** do arquivo de fonte Git: `true`;
- assinatura antiga verificada com a **chave v2 do instalador Linux servido**: `false`;
- correspondência do `kid` servido: `false`;
- correspondência dos quatro hashes servidos: `false` para todos;
- `can_pass_live_installer_release_gate=false`.

Não houve tentativa de instalação, requisição autenticada, uso de token, downgrade, reinício, Cloudflare deploy, assinatura nova ou alterações nos Agents durante esta auditoria. O Codex continua como único autor do código do Commander; esta revisão é uma entrega de diagnóstico/testes na branch documental isolada.
