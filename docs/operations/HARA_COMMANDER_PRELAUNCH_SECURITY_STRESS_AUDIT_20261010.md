# H.A.R.A. Commander — auditoria de produto, funções e carga
**10/10/2026 — frente única `local/commander-product-current` — evidência gerada em ambiente isolado**

> **Veredito:** as **31 funções canônicas do Agent** são suficientes como primitivas para um MVP comercial Linux de administração remota. **Ainda NÃO autorizar venda pública irrestrita.** O risco principal não é falta de comandos, mas segurança por padrão, confiabilidade de filas/sessões, assinatura e entrega de releases, quota multi-tenant, billing e recuperação de falhas. As correções abaixo estão no **código-fonte candidato**, e NÃO nos binários/pacotes assinados rodando em produção.

## 1. Escopo e autoridade

- Repo `tiagoharalabs/hara-site`, branch exclusiva `local/commander-product-current`; worktree Services `/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current`.
- MCP comercial certo: `H_A_R_A__Commander`. `Remote_Desktop_Commander` foi usado somente para auditoria de arquivos e testes no Services, sem confundi-lo com o fluxo comercial OpenAI → Cloudflare Worker/MCP → DO Event V2 → Agent.
- Produto ativo da frota Founder: Agent **0.3.44 EVENT_V2** em máquinas conectadas. O inventário agregado pode projetar **0.3.41** e autoridade `HARA_SERVICES` de registros legados; `get_device_info` de cada computador conectado é a prova de execução real. Corrigir essa divergência antes do lançamento público.
- Foram executados 12 pings comerciais concorrentes, distribuídos entre `nucleo-a`, `sentinela-c` e `services`; **12/12 PASS** com autoridade `HARA_COMMANDER`, Agent 0.3.44, recibo de execução. Isto é um pequeno teste de fumaça, não um teste de estresse de mil clientes.
- Não foram reiniciados hosts, reiniciados workers de produção, modificadas chaves ou quotas D1 PROD, executadas cargas GPU, alterados tokens de clientes, nem reconfigurado Stripe. Não houve deployment de novos agentes ou MCP públicos nesta auditoria.

## 2. Catálogo de comandos — suficiência do MVP

**31 funções do Agent** agrupadas em: conectividade e informações de sistema; leitura/gravação/edição/cópia/movimentação/exclusão de arquivos; comparação/hash/busca; preimages e rollback; criação/listagem/encerramento/interação em processos; execução limitada/gerenciada; funções locais, recursos/uptime/workspace e recibos.

O **perfil simples comercial atualmente publicado** tinha somente **24 métodos públicos**, ainda que o agente tivesse funções úteis adicionais. **Foi preparado, apenas no código-fonte, um novo perfil simples de 27 métodos:**
- `list_file_preimages`: localizar pontos de rollback, sem conteúdo;
- `rollback_file`: restaurar arquivo com verificação de integridade, registrado como operação destrutiva e governada;
- `get_receipt`: consultar recibo de execução sem payload sensível.

Esses três métodos não são novos mecanismos de execução no Agent: reutilizam comandos já homologados no catálogo interno. Corrigido ainda `list_directory(offset=...)` que aceitava paginação na API, mas descartava o `offset` ao encaminhar. Contrato e roteamento do perfil simples PASS.

**Não criar mais comandos apenas para aumentar o número.** Facilidades como controle específico de serviços e transferência de arquivos maiores podem ser propostas depois por telemetria real de usuários, com grants e aprovação próprios; não são pré-condição do MVP.

## 3. Defeitos e correções demonstrados

| Achado | Impacto caso ignorado | Correção aplicada no código-fonte | Prova |
|---|---|---|---|
| Saída de processo sem newline acumulava indefinidamente em `partial` | RAM excessiva no Agent | Limites: 8.192 caracteres/linha, 2 MiB para buffer de linhas | `validate_process_output_memory_budgets.py` PASS, 256 KiB newline-free truncados |
| Número de sessões/saídas de processos não limitado | Lentidão, RAM saturada após dias | Máximo 16 sessões executando, 48 no histórico, saída de sessões concluídas expira em 1 hora | Limites e prune testados sem criar processos reais |
| Preimages de arquivos ilimitados no disco | Saturação do disco por atualizações repetidas | Quota local fail-closed: 256 MiB em dados e até 4.096 versões; **sem apagar versões existentes** | `validate_preimage_storage_budget.py` PASS (quota por bytes, quantidade, integridade, symlink) |
| Instaladores Linux/Windows iniciavam com `PERSISTENT_TRUSTED` | Operações de shell sem aprovação por ação em novo cliente | Futuro instalador agora assume **`ASK_EVERY_ACTION`**; `PERSISTENT_TRUSTED` só opt-in explícito | `validate_device_installers.py` e `validate_mcp_process_risk_annotations.py` PASS |
| Metadados MCP de shell usavam `destructiveHint=false` | Clientes podem subestimar operações arbitrárias | Perfis simples e completo agora assinalam `destructiveHint=true` para comandos de processo | Testes dos dois perfis PASS |
| 24 métodos simples não expunham rollback/auditoria | Cliente sem recuperação fácil após mutação | 27 métodos candidatos, com 3 aliases de operações preexistentes | `test_customer_mcp_simple_profile.mjs` PASS |
| `list_directory` ignorava `offset` | Paginação quebrada em diretórios grandes | Encaminhamento e teste de offset | Perfil simples PASS |
| Teste OIDC reutilizava URI do JWKS com cache 5 min | Falso negativo em regressão de metadados de chave | Fixtures isoladas por JWKS URI; assinatura ruim continua recusada | `test_oidc_helpers.mjs` PASS |
| Testes de instalação comparavam 0.3.43 candidato ao manifesto 0.3.41 público | CI falhava mesmo quando cadeia de assinatura v1 era íntegra | Testes separam v1 imutável `08500d5` do candidato 0.3.43 não assinado | `validate_device_installers.py` e `validate_clean_linux_lifecycle.py` PASS |

**Limite fundamental:** a release pública v1 **0.3.41 assinada** e a Founder 0.3.44 assinada **NÃO FORAM REASSINADAS NEM IMPLANTADAS** nesta auditoria. Portanto não declarar essas correções operando nos clientes atuais. **Antes da venda, gerar release cliente nova por fluxo oficial de assinatura, verificar v1 intacta, atualizar canário de forma supervisionada e validar rollback.** Nunca publicar fontes candidatos como assets públicos sem manifesto assinado.

## 4. Concorrência e estresse realmente realizados

**SQL exato extraído de `apps/commander/src/worker.js`**, executado contra SQLite temporário com todas as **30 migrações reais**. Runner `validate_concurrent_device_queue_sql.py --attempts 1000 --threads 24`:

| Teste | Carga de tentativas | Resultado |
|---|---:|---|
| Enqueue concorrente numa máquina | 1.000 / 24 threads | Exatamente 16 aceitas, como determina o limite de fila |
| Replay do mesmo `request_id` | 1.000 / 24 threads | Exatamente 1 aceita |
| Dois tenants / tentativa cruzada | 1.000 / 24 threads | 0 chamadas indevidas |
| Captura concorrente de 16 jobs | 1.000 / 24 threads | 16 capturadas uma vez cada |
| Jobs expirados | Controlado | Impossível capturar após TTL |
| Dispositivo revogado | Controlado | Novas chamadas negadas |

Execução total de aproximadamente **5,7 segundos** no Services com carga isolada. Esse resultado valida as propriedades de concorrência destas consultas SQLite, **não** é um benchmark da Cloudflare D1 sob 1.000 clientes, nem prova de latência/99,9% de disponibilidade.

**Gate automatizado:** `apps/commander/scripts/commander_prelaunch_offline_gate.py` executou **47/47 verificações PASS**: autenticação, JWKS/OIDC, política de autorização, isolamento, quotas, privacidade, assinaturas, CI estático, 27 ferramentas simples, SQL concorrente, ciclo de vida, Event V2, reconnect storm e modelos de escala (somente checks). Os probes de multidevice DEV `--check` PASS; **não foi feito `--provision` nem `--execute`** porque precisam de plano de limpeza, fixtures dedicados e isolamento contra outros trabalhos.

## 5. Gates que ainda impedem lançamento externo

| Prioridade | Gate | Evidência exigida para PASS |
|---|---|---|
| **P0** | Assinar e distribuir release de cliente que contém os limites de RAM/disco e aprovação segura por padrão | RS256 manifesto/hash, rollback de versão anterior, instalação nova e update por dispositivo comprovados; teste negativo de adulteração |
| **P0** | Segundo cliente/tenant genuinamente independente | OAuth, seleção, pairing, revogação, token cross-tenant e conteúdo privado isolados; conta Founder não basta |
| **P0** | Quota Free real de 10.000/mês | Última unidade aceita, próximo request `QUOTA_EXCEEDED`, replay idempotente, concorrência, retorno de cota em falha, reset mensal |
| **P0** | Stripe | Produto e preço reais, API key/webhook assinados no Worker correto, checkout TEST, falha/recuperação/cancelamento, canário LIVE autorizado e reconciliação de entitlement |
| **P0** | Soak/carga DEV com identidade independente | 24 horas, reconexão/restart/hibernação, prova de isolamento, sem duplicidade de execução ou cobrança, fila recebe `DEVICE_BUSY` sob saturação, memória local dentro do orçamento |
| **P0** | Fronteira de plataformas anunciadas | Linux cliente com distribuição assinada; Windows somente se instala, faz update, respeita aprovação e prova Event V2 com rollback. Se não, lançar beta explicitamente Linux-only |
| **P1** | Telemetria verdadeira | `agent_version`, `last_seen` e `tunnel_mode` não podem divergir da prova por dispositivo sem uma indicação de observação defasada |
| **P1** | Custo real e limite Cloudflare | Worker/DO/D1 requests, duration billed, fatura e SLO por janela, sem inferir redução de R$ a partir de HTTP polling |
| **P1** | Governança CI/Git | Branch canônica readback GitHub, Storage protegido reconciliado por aprovação humana; não fazer force push ou bypass de workflow scope |

### Plano controlado de stress DEV antes do produto comercial

1. Criar fixtures independentes, separar backend DEV e definir rollback/limpeza explícitos. **Não usar a fila CSOTN, GPU, ou máquinas de cliente real como geradores de carga.**
2. Rodar 2, depois 10, 25 e até 100 dispositivos DEV com perfis de carga leves e escalonados; `commander_event_v2_dev_multidevice_lab.py` e `commander_event_v2_dev_multidevice_probe.py` já existem, mas requerem controle de credenciais/teardown e não foram executados de forma live hoje.
3. Rodar bursts **máximo 20 concorrentes por dispositivo** no DEV, com metas iniciais: sucesso **>=99%**, p95 **<=6 s**, p99 **<=12 s**, nenhum token duplicado, vazamento cross-tenant ou mutação sem autorização. São **critérios propostos**, não resultados medidos.
4. Simular desconexões, autenticação expirada, cancelamento de comando, rejeição 429, cold boot/failover e replay ao mesmo tempo; verificar retenção de dados, aprovação e quotas.
5. Medir custos durante 24h, com comparação justa por número de dispositivos ativos e mix de comandos. Somente após todos os gates P0 PASS cogitar abertura pública.

## 6. Execução canônica e política de publicação

```bash
cd /srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current
python3 -B apps/commander/scripts/commander_prelaunch_offline_gate.py --stress 1000 --threads 24
```

Não usar `--execute` em scripts DEV de provisionamento sem ambiente isolado definido. O gate offline é reproduzível, não acessa produção, e devolve falha de saída se qualquer regressão aparecer; **não autoriza deploy automaticamente**.

Todo trabalho deste diagnóstico pertence apenas à branch `local/commander-product-current`; o Storage ref `092f35af...` segue `HOLD` por proteção de governança, não deve ser forçado. O checkpoint GitHub após esta documentação deve ser confirmado por SHA exato.

**Decisão de engenharia:** parar de criar comandos genéricos como primeira resposta. Priorizar release assinada, autorização padrão mínima, teste multi-tenant/Free, limites de recursos, recuperação, preço real e stress DEV. Essas são as mudanças que evitam corrigir o produto às pressas depois de vendê-lo.
