# H.A.R.A. Commander — Event V2 de baixo tráfego e telemetria persistente
**Data:** 11/10/2026 | **Branch:** local/commander-product-current

## Entrega de código

- **Event V2 Linux:** contadores estritamente agregados em SQLite local (conexões, reconexões, desconexões, falhas de sessão, chamadas duráveis/transientes, falhas transientes, tentativas de liveness, PING de transporte e segundos conectados).
- **Privacidade:** nenhuma coluna ou frame guarda argumentos, saídas, paths, nomes de comandos, tokens ou conteúdo do cliente. Arquivo local privado (0600); apenas sete dias; flush por lote a cada cinco minutos, na desconexão e antes do snapshot.
- **Rede:** o resumo agregado é anexado ao LIVENESS Event V2 **já existente**, em média a cada seis horas, com jitter de ±15 min por identidade. O PING RFC6455 continua a cada 60 s de ociosidade. Não foi criado polling nem POST HTTP de telemetria.
- **Cloudflare:** DeviceChannel aceita a mensagem antiga (apenas schema/type) e a nova com metrics; rejeita campos e tipos adicionais; dispositivo e tenant vêm da conexão autenticada. Upsert D1 no mesmo batch do refresh liveness, tabela de snapshot mais recente por dispositivo e janela de sete dias.
- **Consulta:** MCP get_device_telemetry só lê dispositivos do tenant autenticado e exige COMMANDER_RECEIPT_READ; retorna null para dispositivos sem snapshot.
- **Redução de leituras:** polling de status do cliente passa a usar atrasos progressivos, preservando as verificações rápidas iniciais. Simulação de 45 s com retry_after_ms=250: 180 leituras na cadência antiga, 36 na nova (80% menos na simulação, NÃO medição da Cloudflare).

## Validação e segurança

- SQLite local: 48 casos PASS, incluindo retenção, reinício, permissões, legado e nenhuma chamada HTTP nova.
- Contrato e SQL D1 em SQLite real: 40 casos PASS, isolamento entre tenants, revogação, replay absoluto idempotente e rejeição de snapshot antigo.
- Status polling: 63 casos PASS, latência inicial e deadline preservados.
- Agent Founder 0.3.45: nova release assinada RS256 por chave v2 já autorizada, manifesto **sete arquivos**, SHA e verificador independente. Primeiro pacote Services assinado e testado. Versão 0.3.44 e assinaturas anteriores permanecem intocadas.
- Gate Commander geral: **77/77 PASS**, com ensaios concorrentes internos de 1.000 tentativas/24 threads. Não equivale a prova de escala real de usuários.
- Compatibilidade: o protocolo LIVENESS antigo continua aceito. Um Agent antigo não produzirá snapshot de telemetria nova.

## Publicação e limitações

DEV exige migração aditiva 0034 antes do novo Worker. PROD usa a mesma sequência após DEV passar. Agent 0.3.45 permanece Founder-only e precisa canário real com rollback para 0.3.44 antes de instalação em outros nós; não substitui automaticamente os instaladores comerciais Linux/Windows 0.3.43.

Os snapshots de D1 só serão preenchidos após o primeiro LIVENESS autenticado emitido pelo Agent atualizado; não inventar registros logo após o deploy. A contagem de WebSocket PING em nível de transporte não deve ser confundida com requisições Worker faturadas.

Storage permanece em HOLD por divergência. Não forçar refs nem publicar chave privada.

## Execução verificada após commit 93ebcf0

- Migração 0034 aplicada em D1 DEV e PROD. DEV Worker 15801b6f-6ec2-40e9-8508-2f1d578824df (100%) e PROD 3b926608-cff0-4dfb-947f-6ff3099cbe3f (100%), health/auth PASS. Assets comerciais assinados antigos preservados.
- Agent Founder 0.3.45 assinado (sete arquivos), instalado somente em services; verificações RSA, autoteste e MCP comercial real device.info (0.3.45) PASS. Unit V2 e timer guard active+enabled; v1 inactive. Release 0.3.44 retida para rollback e backup da unit sob /tmp_hara.
- Reinício canário controlado: SQLite local persistiu uma conexão, uma desconexão, uma chamada durável e 74 segundos conectados. Arquivo com modo 0600; conteúdo dos comandos não é armazenado.
- Pacotes 0.3.45 de Sentinela A/B/C/D e Ninja Blue foram assinados por dispositivo e verificados em stages restritos no Services, SEM instalação; Núcleo tem o pacote Founder correspondente. Hosts restantes continuam 0.3.44 até rollout governado para não interromper carga ativa.
- Snapshot cloud nos dois D1 permaneceu com zero linhas no readback após publicação: primeiro LIVENESS real (~6h) ainda pendente. Não afirmar telemetria de nuvem viva antes da primeira entrega.
- A execução GitHub CI estava falhando somente no ciclo de vida Linux: atalho hara criado pelo instalador não era removido no uninstall em host limpo. A correção remove só o wrapper marcado como gerenciado; executável de terceiros e symlink são preservados. O gate local voltou a 77/77 e o GitHub Actions do commit 1aec24c passou todas as etapas, run 38171345712, PASS. O release comercial assinado legado segue byte-idêntico; correção de fonte só será distribuída em release comercial própria.

Prova JSON sanitizada: docs/evidence/commander-telemetry-20261011/checkpoint.json.
