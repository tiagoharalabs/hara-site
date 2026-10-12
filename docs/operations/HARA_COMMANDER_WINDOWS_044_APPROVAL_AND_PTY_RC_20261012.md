# H.A.R.A. Commander — Windows 0.3.44-v4 RC (11/10/2026, horario de Sao Paulo)

## Estado e limites

Release candidata assinada **0.3.44-v4 RC**, destinada somente à VM `commander-win11` para homologação. **Não foi publicada no instalador comercial, não foi instalada nesta etapa na identidade registrada e não foi habilitada a aprovação automática.** A versão pública 0.3.43-v3 permanece a fonte de produção e os Agents Linux Founder 0.3.46 seguem intocados.

## Funcionalidades novas

- ASK_EVERY_ACTION continua o padrão, mas agora apresenta uma solicitação no console local do operador em vez de recusar permanentemente. O Agent grava pedido temporário com nonce, request_id, SHA-256 dos argumentos e expiração de 22 s, somente no perfil do usuário. A sessão local deve ter PID e horário de início válidos; um humano deve digitar o desafio para aquela ação. Respostas sem nonce/hash/identidade corretos, expiradas, negadas ou sem sessão são recusadas. O fluxo **não modifica** device.json nem troca para PERSISTENT_TRUSTED/SESSION_TRUSTED.
- Sessões gerenciadas em PowerShell 5.1 via subprocesso .NET e I/O assíncrona: start, output, interact, kill, sessions, com limites de 8 processos ativos, 5.000 linhas/2 MiB por sessão e retenção de 15 minutos após encerramento. Interagir, iniciar e encerrar processos exigem confirmação individual. **Sessões ainda não persistem através de restart do Agent**.
- Escrita de arquivos por substituição atômica com backup transitório, proteção optimistic concurrency SHA-256, recusa de leaf reparse point e limpeza dos arquivos temporários.

## Provas já feitas

- Windows 11 real na VM: seis arquivos de laboratório SHA-256 idênticos à origem, parser PowerShell 5.1 sem erros, Agent candidato `--self-test` PASS, incluindo recusa fail-closed de três operações sem sessão.
- Sessão .NET real na VM: 120/120 linhas pós-exit, duas instruções na mesma sessão, exit 0; ensaio de 7.000 linhas com retenção limitada a 5.000, truncamento informado e última linha preservada.
- Escrita num diretório descartável (sem device.json real): arquivo novo, troca atômica com SHA correto, SHA antigo negado, conteúdo original preservado, PASS.
- Fonte Worker sob regressão real: 37/37 contratos de ferramentas e gates Windows .43 vs .44.
- Fonte de segurança: 20 verificações PASS para nonce, hash, aprovação explícita, prazo, recusa, retenção, CAS e grants.
- Pacote RC `apps/commander/release-bundles/commercial-0.3.44-v4-rc` criptograficamente assinado RS256/RSA3072; manifesto de quatro arquivos autenticados; Linux Agent/instalador iguais byte a byte ao comercial v3. Release v3 imutável preservada.
- Gate offline principal **87/87 PASS** com 1.000 tentativas/24 threads nos cenários internos. Isso não certifica mil clientes reais nem aprovação Windows positiva.
- Nenhuma alteração em Stripe, tenant, banco de dados ou políticas de máquina durante a preparação e ensaios do pacote.

## Pendências antes de publicar v4

1. CI GitHub do SHA exato do RC deve ficar verde.
2. Instalar v4 apenas na VM com backup de v3 e checagem de configuração byte-idêntica.
3. O usuário da VM abre o console local e **aprova de fato** uma chamada mutante e nega outra. Conferir por MCP comercial escrita, execução e recibos. Um texto enviado ao chat não substitui esse gesto porque ASK_EVERY_ACTION é uma política local.
4. Testar iniciar/interagir/ler/encerrar sessão de terminal pelo MCP comercial e saída completa após exit, inclusive em reinício controlado do Agent. Rejeição em janela 22 s e ausência de alterações após timeout.
5. DEV antes de PROD para Worker com tool gate apenas Windows >=0.3.44; produção v0.3.43 não deve ganhar ferramentas não suportadas.
6. Atualização Windows pública somente depois de todos os gates, com rollback e canários; Windows Event V2 WebSocket ainda é RC separado.

Windows `0.3.43` operacional permanece conectado no MCP em modo OUTBOUND_RELAY. A release v4 não reduz a política de segurança para fazer os testes passarem.
