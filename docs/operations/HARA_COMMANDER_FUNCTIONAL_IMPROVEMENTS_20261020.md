# HARA Commander — melhorias funcionais orientadas pelo uso diário

Data: 2026-10-20. Complemento explícito do proprietário à decisão de canal primário. Não substitui a fila R2/R3/R4 nem autoriza interromper a correção atual.

## O pedido é melhorar as funções, não apenas produzir auditorias

Tiago reforçou: o Commander passa a ser usado como canal primário e esse uso deve produzir melhorias reais nas ferramentas. A entrega precisa reduzir atrito para ler, pesquisar, editar e operar computadores, com menos chamadas repetidas, retornos claros e recuperação confiável. Relatório sem patch/teste ou sem benefício demonstrado não encerra item funcional.

Já confirmei que a superfície simples contém read_file, read_multiple_files, write_file, edit_block, search, list_directory, get_file_info, start_process, read_process_output, interact_with_process e list_sessions. Melhorar os contratos e implementações existentes antes de criar ferramentas equivalentes com outros nomes. Compatibilidade com clientes atuais deve ser preservada.

Na leitura de 19:44 UTC, o HEAD era 6ea480f (persistência/reenvio de resultados), e o Codex já implementava liquidação de cota. Isso é progresso de código, não afirmação de publicação ou revalidação independente desse novo commit. Não interromper a sequência R4 para redesenho geral.

## Fila funcional com benefício observável

| Grupo existente | Melhoria a entregar | Aceite observável |
| --- | --- | --- |
| read_file / read_multiple_files | Resposta útil dentro do limite agregado serializado; continuação explícita por arquivo; indicar arquivo alterado durante paginação quando houver como verificar versão/hash sem custo desproporcional. | Ler arquivo grande e dez arquivos em páginas, sem linhas perdidas/duplicadas, JSON cortado ou necessidade de adivinhar offset; testar Unicode/escapes e concorrência de alteração. |
| search / list_directory | Busca e listagem previsíveis, filtros e continuação corretos; distinguir ausência de resultado de varredura incompleta, falta de permissão e limite de tempo. Reusar ferramentas atuais. | Encontrar ocorrência conhecida, continuar busca sem repetir/pular resultados em fixture estável e reportar alteração da árvore; cancelamento/limites claros em diretórios grandes. |
| edit_block / write_file / copy / move / delete | Edição precisa com precondição/hash e correspondência inequívoca; falha útil com contexto mínimo, sem vazar conteúdo nem sobrescrever alteração de outra sessão. Manter preimages e symlinks conforme contrato. | Editar trecho, reler e confirmar; arquivo alterado concorrente é recusado sem perda; múltiplas correspondências não viram replace-all implícito; repetir mesma requisição não repete mutação. |
| start_process / read_process_output / interact_with_process | Uso de terminal sem bloqueio por volume de saída; sessões e tarefas curtas distinguíveis; timeout de resposta não confundido com cancelamento; saída incremental com cursor e truncamento explícito. | Processo grande termina sem polling do cliente; leitura posterior preserva cauda/Unicode; tarefa longa dá identificador consultável; eco do terminal é distinguido da saída real; pager desativado somente no modo não interativo. |
| list_sessions / kill_process | Identificar computador, dono lógico, tempo desde atividade e estado; expiração/renovação de sessões gerenciadas sem matar trabalho legítimo; encerramento de grupo/descendentes verificável. | Nenhuma sessão abandonada se torna invisível; revogar/encerrar tarefa QA não afeta sessões alheias; limite retorna explicação e ação possível. Não limpar as 13 sessões reais por iniciativa desta nota. |
| Resultado de todas as ferramentas | Separar sucesso do transporte de sucesso do comando/domínio. Retornar exit_code, execução iniciada/concluída/incerta, conteúdo truncado e como continuar; minimizar envelopes redundantes sem esconder recibo ou evidência. | Comando exit 2/timeout não é interpretado como sucesso só porque o envelope MCP diz PASS. Falha de conexão após mutação preserva resultado verdadeiro e nunca sugere replay cego. |
| Descoberta/saúde da frota | Seleção de computador explícita; capabilities e build/hash reais; presença fresca versus estado cadastral; erros orientados à recuperação. | Nenhuma operação segue para máquina errada por silêncio/default ambíguo. Versão igual com build diferente fica visível. Diagnóstico distingue dispositivo offline, autorização e falha de transporte. |

Os critérios acima são alvos de melhoria/aceite, não declaração de que todas as funções atuais tenham o defeito descrito. Primeiro reproduzir o atrito concreto, depois implementar o menor patch e a regressão. Não criar suporte fictício a recursos do navegador ou Windows que ainda não foi implementado/testado.

## Transformar uso real em melhoria de produto

O uso normal autorizado da frota é a primeira fonte de cenários reais: tarefas variadas, arquivos grandes, várias sessões, desconexões e dias de uso contínuo. Não depende de voltar ao Desktop Commander. Registrar por função apenas metadados necessários (latência, sucesso/erro, bytes, retries, tamanho de fila e sessões), sem prompts, conteúdo de arquivos, tokens ou credenciais.

Usar o ciclo: tarefa real → atrito reproduzível → patch + teste → candidato → canário autorizado → verificar se a tarefa ficou melhor e com menos retrabalho. Não é necessário esperar a publicação comercial para preparar melhorias de uso interno; a instalação do candidato no laboratório precisa preservar o acesso primário e ter rollback, assinatura quando exigida e autorização específica.

Uso intensivo real e teste controlado de sobrecarga são complementares: não chamar um dia de uso de homologação de milhões de chamadas. Carga sintética deve ser em fixture/DEV reservado, com rampa e orçamento próprios; não disparar milhares de operações nas máquinas produtivas. O relato de 80 mil transações do proprietário é referência qualitativa do primeiro usuário, sem período/throughput medido e sem mudar a franquia comercial.

## Forma de entregar na frente atual

1. Concluir os bloqueios de resultado/recibo/cota R4 já em implementação, sem perder a correção de fila e PTY R3.
2. Organizar os próximos commits por função e benefício: reproduzir a dificuldade, implementar, testar negativo/concorrência e mostrar antes/depois. Aproveitar testes já existentes e não reabrir item fechado sem nova evidência.
3. Manter uma tabela curta no handoff: função / gap observado / commit / teste / candidato / canário instalado. Código corrigido não significa que o usuário já recebeu a melhoria no Agent ativo.
4. Não entregar somente esta lista como plano final: usar estas prioridades para patches e demonstrações. Incluir paridade Linux/Windows e cliente comercial independente, preservando Founder separado.

Continuam válidos: HARA Commander primário; não reativar Desktop Commander como fallback automático; modelo R$80/mês, cinco computadores, um milhão de chamadas mensais e cinco mil de avaliação. Não há autorização adicional para deploy PROD, migração D1, cobrança real, uso de chave privada ou parada de Agents. Nenhum limite de usuário ou cobrança por chamada foi adicionado.
