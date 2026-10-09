# H.A.R.A. Commander — cliente MCP local com OpenAI Secure MCP Tunnel

Data: 2026-10-09
Frente canônica: `local/commander-product-current`
Objetivo: **ChatGPT/OpenAI -> OpenAI Secure MCP Tunnel -> tunnel-client na máquina do cliente -> hara-commander mcp local**.
NÃO usar `HARA_SERVICES` como relay operacional de tool calls.

## Constatação no Núcleo A

- Instalado e assinado: `hara-commander` 0.3.41; MCP STDIO inicializa, lista **24 ferramentas**.
- Cliente oficial do túnel da OpenAI: `~/.local/share/hara-commander/tunnel-client`, v0.0.15. Antes da instalação, arquivo baixado do release oficial, com ZIP SHA-256 verificado; executável atual SHA-256 `286769f6b1b1837e89896b4684a3ec59c919f860fa2bc159442e3839b6468711`.
- A API da OpenAI é alcançável via HTTPS, TLS validado. O MCP local não exige portas de entrada.
- O helper para configurar o túnel do cliente está instalado em `~/.local/bin/hara-commander-openai-bridge`, mode 0700, SHA-256 `00bcad20b3435b37f5c860cb85131ed4706c911b8e5cbd367e1e9abd47a6f2dc`.
- O serviço systemd do usuário `~/.config/systemd/user/hara-commander-openai-tunnel.service` foi preparado (0600), `LoadState=loaded`, `is-enabled=disabled` e `is-active=inactive`.
- O serviço aponta para o **tunnel-client local**, que depois de configurado chama `/home/sartorius/.local/bin/hara-commander mcp` por STDIO.
- Sem criar fake tunnel_id, sem inventar chave, sem alterar a instalação assinada.
- Teste fail-closed: `hara-commander-openai-bridge start` sem perfil retorna `OPENAI_TUNNEL_ID_NOT_CONFIGURED` (exit 2); Agent anterior continua ativo e intacto.
- Teste offline do bootstrap: `python3 apps/commander/scripts/validate_local_openai_bridge_bootstrap.py`, **PASS**. Não leu nem utilizou o token do dispositivo nem instalou o Agent de novo.

## Finalização real: identidade OpenAI (ação pessoal obrigatória)

**ChatGPT/HARA Identity OAuth não gera automaticamente uma chave de OpenAI Platform.**
São recursos administrativos diferentes. O estado atual verificado no Núcleo:
- `~/.config/tunnel-client/hara-commander.yaml`: AUSENTE.
- `~/.config/hara-commander/openai-tunnel.env`: AUSENTE.
- Nenhum tunnel_id real foi encontrado.
- Nenhuma conexão de túnel OpenAI ativa foi alegada ou simulada.

O proprietário da organização/workspace deve:
1. Criar ou selecionar um túnel em https://platform.openai.com/settings/organization/tunnels, com associação à organização Platform e ao workspace ChatGPT correto; requer permissão **Tunnels Read + Manage**.
2. Criar uma runtime API key em https://platform.openai.com/settings/organization/api-keys, concedida no escopo que permite **Tunnels Read + Use**.
3. Informar tunnel_id e chave **apenas no terminal local**, não no chat:
   `hara-commander-openai-bridge configure`
   O script pede o tunnel_id e oculta a entrada da chave. Escreve o env em 0600 e configura um perfil STDIO `hara-commander` em 0600. Não transmite segredos à HARA Cloud.
4. Verificar `hara-commander-openai-bridge doctor`. Se PASS, `hara-commander-openai-bridge start` para iniciar manualmente; opcional `hara-commander-openai-bridge autostart on` para iniciar pelo systemd user após login.
5. No ChatGPT Plugins, `Add custom MCP server`, escolher **Tunnel**, selecionar a entrada de túnel criada ou informar `tunnel_id`; concluir autorização e habilitar a conexão na conversa. Definir nome **H.A.R.A. Commander** e ícone da capivara como metadado visual do plugin, se a interface oferecer essa opção.
6. Executar de dentro do ChatGPT `device.info` / `ping`, confrontar recibo e autoridade. **Somente esse teste real prova o trajeto do produto.**

Documentação oficial: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

## Cuidados de produto

- O bootstrap não troca nem desativa o Agent assinado 0.3.41 e não muda o modo de transporte atual `OUTBOUND_RELAY`. Quando o túnel estiver ativo, as chamadas feitas pelo **MCP STDIO do túnel** seguem o caminho privado da OpenAI, não o MCP dos Services.
- O Agent local 0.3.41 pode manter seu polling legado de controle em segundo plano; esse ponto é separado do caminho das chamadas pelo túnel, e a migração ao `LOCAL_TUNNEL` requer release 0.3.43 legítimo e controle de lease.
- O código-fonte do Agent 0.3.43 implementa lease de 6 horas e autostart, mas **não tem assinatura de release válida no momento**; não promover versão não assinada nem trocar a âncora de confiança silenciosamente.
- O bootstrap descrito é **uma preparação de laboratório** de serviço local usando o Agent atual assinado. A publicação comercial para clientes deve aguardar versão assinada com política de acesso revisada e E2E.
- O serviço é propositalmente fail-closed: sem perfil e runtime key, não inicia.
- O script não gera nem obtém OpenAI runtime API key; ChatGPT não disponibilizou nesta conversa ferramentas administrativas para criar credenciais de Platform em nome do usuário.

## 2026-10-09 — Direct UX / segurança (fonte candidata, ainda não publicada)

- Contrato de transporte exclusivo: OpenAI/ChatGPT -> Secure MCP Tunnel -> `tunnel-client` no cliente -> `hara-commander mcp` via STDIO. O HARA Services não encaminha essas chamadas. A Cloud HARA mantém pareamento, licenças e metadados mínimos.
- Na fonte Linux Agent **0.3.43**, o comando preferido agora é `hara-commander tunnel connect` (`tunnel configure` continua como alias). Mostra páginas oficiais para obter `tunnel_id` e chave de runtime. Chave guardada somente em arquivo local `0600`, nunca em argv, Git ou HARA Cloud.
- O `tunnel-client init` cria perfil de dados privados `0600`; `doctor` deve retornar sucesso ANTES de considerar a configuração válida. Falha limpa o perfil e o env, sem alterar o Agent. Configuração existente não é sobrescrita.
- **Fail-closed de autorização:** `tunnel start` e `tunnel autostart on` não iniciam conexão sem licença local `LOCAL_TUNNEL` válida (janela de 6 horas) E OpenAI doctor PASS. Seleção de autostart no instalador fica pendente até `hara-commander authorize`; com autorização válida, inicia automaticamente, se essa foi a escolha do cliente.
- O portal, na fonte candidata, descreve explicitamente que OpenAI Secure MCP Tunnel é privado por workspace, não é distribuição pública de plugin.
- Helper temporário `hara-commander-openai-bridge` no Núcleo recebeu validação que exige `hara-commander doctor` sinalizar licença `LOCAL_TUNNEL`, `HARA_COMMANDER_LOCAL_AUTHORIZATION=PASS` e `HARA_COMMANDER_TOOL_DATA_PLANE=LOCAL_DIRECT` antes de iniciar ou habilitar o túnel; SHA-256 do helper: `ece13b6fbad4ad93441b951d0dac87bda8e40ed05dd348e46a1fe62cd595523d`. Isso mantém o Agent assinado 0.3.41 fora da conexão direta, até release autorizado.
- Testes offline: `validate_linux_tunnel_start_modes.py` PASS, `validate_local_tunnel_control_plane.py` PASS, `validate_local_openai_bridge_bootstrap.py` PASS, `validate_local_tunnel_unit_economics.py` PASS, Agent self-test PASS, Python/Bash syntax PASS. Incluem negação antes da autorização, não vazamento de chave, rollback de configuração inválida e não sobrescrita.
- **Não é E2E com a OpenAI real**. Pendências externas: tunnel_id legítimo, chave OpenAI de runtime e associação ao workspace/permissões, e inclusão da conexão do tipo Tunnel no ChatGPT. Não criar credenciais fictícias.
- **Não é release público**. A fonte 0.3.43 continua sem assinatura válida pela cadeia do release (mismatch JWK privada/pública reportado anteriormente). Não promover o código ou trocar chave de assinatura fora do processo de custódia autorizado. O PROD permanece com Agent assinado 0.3.41.
- Documentação pública consultada em 2026-10-09: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels — Secure MCP Tunnel suporta conexões privadas, NÃO submissão/distribuição de plugin público; esse limite não pode ser removido pelo instalador HARA.
