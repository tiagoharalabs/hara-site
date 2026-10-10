# H.A.R.A. Commander — autorização formal para rotação de assinatura (2026-10-09)

## Decisão do proprietário

Em 09/10/2026, o proprietário autorizou **rotação formal da chave de assinatura e sua extensão gradual à frota**. Isso autoriza planejar uma nova cadeia de confiança, mas não suspende verificação criptográfica, isolamento de clientes, autorização local, contingência, assinaturas válidas ou requisitos de qualificação. A autorização não significa que todas as máquinas estejam tecnicamente prontas para receber o mesmo Agent.

## Estado factual nesta rodada

- **PROD:** o Worker `215ab34e-78ad-4002-a4d6-7e26e3a71f94` inclui `DEVICE_CHANNEL` com `acceptWebSocket`, migração v3, flag Event V2 ligada e allowlist exclusiva de `nucleo-a`.
- **Cliente comercial:** Agent assinado 0.3.41 continua usando `OUTBOUND_RELAY`, com polling de infraestrutura. Nenhuma redução real do polling de produção foi demonstrada.
- **DEV:** o canário Event V2 havia concluído operações e reconexão via WebSocket; seu processo isolado foi encerrado após a prova. O Agent comercial continuou ativo.
- **Source candidate:** `candidate/event_v2_full_agent.py` contempla os 32 identificadores de ferramenta, reusando o executor do Agent existente. Autotestes de consulta, recibos e autorização local passaram. Não está assinado como release comercial.
- **Chave antiga:** a única chave RSA privada localizada no caminho de custódia do Services (permissões 0600) **não corresponde** ao módulo da chave pública `commander-release-v1` pinada no instalador oficial. O Storage não apresentou outra candidata nos caminhos de custódia verificados.
- **Bloqueio operacional:** o acesso remoto bloqueou tanto a tentativa de executar o script de geração da chave v2 quanto a tentativa de escrever o launcher comercial; não foram contornados. **Nenhuma chave v2 foi gerada, nenhuma assinatura nova foi emitida e nenhum Agent de produção foi substituído nesta rodada.**
- O arquivo `scripts/rotate_signing_key_v2_once.py` é **fonte de preparação não executada**, para um operador autorizado revisar antes do uso. Sua existência no repositório não equivale à rotação efetiva.

## Migração compatível com clientes existentes

**Não sobrescrever** `/release/agent-manifest.json`, `/release/agent-manifest.sig.json`, `/release/release-signing-public.jwk`, `/agent/linux.py`, `/agent/windows.ps1`, nem `/install/linux.sh`/`windows.ps1` enquanto a antiga chave v1 continuar pinada nos instaladores em circulação. Um agente v1 não consegue verificar uma nova assinatura da chave v2 automaticamente.

Proposta de trilha v2 independente e verificável:
1. Gerar sob custódia autorizada uma chave RSA nova, com identificação distinta `commander-release-v2`, armazenando **somente o público** no código e o privado em diretório protegido 0700 com arquivo 0600. Conferir fingerprint e prova de posse assinada, sem expor o privado no log.
2. Publicar os artefatos v2, manifest v2, assinatura v2 e instalador v2 sob URLs **versionadas separadas** do v1. O instalador v2 precisa ter o **novo público fixado**, validar assinatura RS256 e SHA256 de cada módulo, e recusar arquivos ou caminhos fora da lista autorizada.
3. Fazer migração explícita, nunca atualização silenciosa: o usuário/administrador confirma a rotação, preserva o Agent v1, valida o v2 e então troca **um único processo por dispositivo** sob supervisão do systemd.
4. Se falhar handshake, comando, autenticação, autorização, quota ou recibo após o corte, desativar o v2 e reiniciar o Agent **v1 assinado e original**, mantendo a configuração e identidade do cliente, sem reset do D1. A chave v1 continua válida para a rota v1.
5. Só divulgar v2 para clientes novos após testes de Linux/Windows, matrizes tenant A/B, revogação, limite Free, processo e arquivo com autorização humana e medição de custo Cloudflare.

## Ordem de implantação autorizada e segurança

- Núcleo A: primeiro e único canário de PROD para Event V2. Verificar `ping` e `get_device_info` via plugin comercial com recibo SHA256 correlacionado à D1 PROD, comando de arquivo e processo permitido, revogação e reconexão; aferir contagem de requisições do Agent com janela comparável.
- Sentinelas A/B/C/D e Ninja Blue: promover **sequencialmente**, após expansão explícita da allowlist na Cloudflare, release assinada e teste de canário completo em cada plataforma. Máquina offline nunca deve ser declarada migrada.
- Não iniciar simultaneamente os serviços antigo e novo para o mesmo dispositivo. Não divulgar chaves de device, tokens, valores de assinatura ou conteúdo do usuário para Git/telemetria.
- Guardar métricas `HTTP polls/h`, WebSocket connections, DO duration, Worker invocations, D1 reads/writes, uso cobrável versus informativo e taxa de reconexão.
- A redução de polling só deve ser declarada após o Agent assinado efetivamente estar em `EVENT_V2` em PROD, e comparada com os dados anteriores.

## Gate de execução pendente

A política de segurança da ferramenta remota bloqueou a mutação criptográfica, apesar da autorização do proprietário. O operador humano precisará executar a cerimônia de rotação via canal de administração autorizado, ou habilitar explicitamente um fluxo de aprovação que permita a operação sem burlar esse bloqueio. O script preparatório deve ser revisado e testado antes disso.

**Estado canônico:** ROTATION_APPROVED; V2_KEY_NOT_CREATED; V2_RELEASE_NOT_SIGNED; PROD_AGENT_0.3.41_PRESERVED; PROD_EVENT_V2_SERVER_AVAILABLE; PROD_POLLING_REDUCTION_PENDING.
