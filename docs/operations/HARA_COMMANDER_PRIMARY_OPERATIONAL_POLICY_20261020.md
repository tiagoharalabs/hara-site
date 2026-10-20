# H.A.R.A. — memória operacional: HARA Commander como ferramenta principal

Registro: 2026-10-20. Origem: instrução explícita de Tiago nesta conversa. Estado: DECISÃO DO PROPRIETÁRIO. Não é autorização genérica de produção.

## Decisão persistente

O HARA Commander é, a partir desta decisão, o MCP principal para operar, inspecionar e validar a frota H.A.R.A. Tiago é o primeiro usuário operacional intensivo do produto. Sua experiência diária deve orientar correções e melhorias reutilizáveis também pelos futuros clientes Linux/Windows.

Desktop Commander excedeu o uso da contratação informada pelo proprietário e não deve ser considerado dependência disponível nem fallback automático. Tiago relata que contratou somente um mês, que a franquia era de 10.000 transações e que seu uso chegou a aproximadamente 80.000 antes da interrupção. Esses números são RELATO DO USUÁRIO, não auditoria da conta, benchmark medido nem verificação da política pública do fornecedor. O período exato das 80.000 transações não foi medido nesta frente.

Não propor renovação/recompra nem usar/reconectar Desktop Commander/Remote Desktop Commander por iniciativa própria. Preferir H.A.R.A._Commander para leituras, comandos, edição e evidências. Se uma função do HARA falhar, preservar diagnóstico/recibo, distinguir estado do transporte do exit code do comando, registrar o gap e corrigir pelo fluxo isolado autorizado. Não trocar silenciosamente de conector, não ampliar permissões, não desabilitar segurança para contornar falhas. Outro meio de acesso só por autorização explícita do proprietário.

## Missão para a frente Codex

A prioridade não é só preparar uma demo: entregar uma ferramenta que o proprietário consiga usar diariamente na frota, sem depender do produto concorrente, e converter as correções em uma versão comercial reproduzível.

Continuar na sessão e na branch existentes:
`/home/sartorius/hara-workspaces/commander-prelaunch-fixes-20261020`
`codex/commander-prelaunch-fixes-20261020`

Preservar o trabalho em andamento, os testes e os handoffs R2/R3/R4. Registrar o recebimento desta decisão em PROGRESS.md. Não criar outro executor concorrente nem sobrescrever arquivos da frente.

## Prioridades e critérios de aceite

1. **Confiabilidade de execução e resultado (R4).** Uma operação realizada não pode virar DENIED/nenhuma alteração porque o envio da confirmação falhou. Resultado/recibo persistente, reenvio idempotente, conclusão recuperável, nenhum replay cego de mutações. Incluir falha antes do envio, aceite remoto com resposta perdida, reinício, disco cheio e limites/privacidade da fila local de resultados.
2. **Processos úteis no dia a dia (R3).** Saída contínua sem bloquear filhos, leitura incremental com cursor correto, Unicode íntegro, memória limitada, tempo limite e encerramento de grupos, sessões gerenciadas versus one-shot explícitas. Impedir paginador interativo em execução expressamente não interativa sem proibir sessões legítimas. Corrigir a corrida da fixture /proc já registrada, sem afrouxar gates nem matar sessões reais sem aprovação.
3. **Arquivos e resposta MCP coerentes (R4).** Ler/gravar/editar/copiar/mover/excluir/pesquisar com precondição, preimage quando aplicável, controle de symlinks e isolamento. Orçamento de bytes serializados global e por arquivo, continuação sem perda para read_many, grandes saídas e caracteres escapados. Não cortar JSON nem afirmar ausência de saída quando houve truncamento.
4. **Fila, reconexão e presença (R3).** Manter a correção 72c6820 e testes de 0/1/8/9/12/16. Recuperação após perda de conexão sem polling ocioso permanente; status com versão/build/manifesto e idade de presença, sem confundir ONLINE cadastral com conectividade funcional. Não replicar canário Founder como prova comercial limpa.
5. **Cota, cobrança e proteção ao cliente (R2/R4).** Conclusão e contabilização independentes do chamador; sem dupla contagem, perda de consumo ou reset gratuito. Checkout idempotente, eventos tardios reconciliados, prazo pago e revogação preservados. Testes locais e Stripe mock separados de TEST real e LIVE.
6. **Carga realista sem usar produção como teste de estresse.** Registrar o relato de aproximadamente 80.000 usos como referência do primeiro usuário, não como limite de produto nem throughput medido. Medir chamadas funcionais/overhead, latências, erros, bytes, memória/sessões e custo. Primeiro testes sintéticos locais/reprodutíveis; canário e soak somente em ambiente reservado com escopo, orçamento e aprovação. Não gerar 80.000 operações na frota produtiva para “provar” capacidade.
7. **Entrega operacional segura.** Documentar paridade das ferramentas utilizadas pelo proprietário, gaps Linux/Windows, comando de diagnóstico, instalação/atualização/remoção limpa, versão assinada coerente, canário, rollback e readback. Núcleo/Services em uso não podem perder acesso durante atualização. Preparar promoção pelo próprio HARA; executar mudança produtiva apenas após aprovação específica.

## Modelo comercial preservado

- HARA Commander: R$ 80/mês, assinatura fixa em reais.
- Até cinco computadores ativos por cliente/organização.
- 1.000.000 de chamadas funcionais por mês, compartilhadas, sem cobrança adicional automática por chamada.
- Avaliação: 5.000 chamadas totais, sem renovação mensal.
- Não inventar limite de usuários; Founder/Internal permanece independente e ilimitado.
- Cancelamento para a próxima renovação, com acesso até o fim do período pago e direitos aplicáveis preservados.
- Billing OpenAI continua fora do escopo.
- Âncora da franquia (mês-calendário versus ciclo pago) e migração do consumo Trial histórico ainda exigem decisão/conciliação antes da promoção.

## Evidências e limites

Separar sempre: observado na frota / reproduzido em fixture / corrigido em código / teste local / teste DEV / instalado em canário / publicado PROD. Não prometer produto perfeito ou fechar issue por teste parcial. Preservar recibos e hashes; não colocar conteúdo de clientes, dados pessoais ou segredos nos repositórios.

A autorização de melhorias locais não libera sozinha deploy PROD, migração D1 remota, reinício/upgrade dos Agents usados pelas outras frentes, assinatura com chave privada, cobrança Stripe, cadastro OpenAI ou publicação pública. Registrar os bloqueios exatos e continuar as demais correções permitidas.

Este é um registro persistente no filesystem do projeto e no inbox do Codex; não equivale a uma alteração da memória pessoal automática do ChatGPT.
