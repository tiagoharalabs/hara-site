# Windows: falha pública de integridade e correção do caminho de QA

Observação nativa de 28/10/2026, 01:23–01:37 (Brasília).

**Distribuição pública: BLOCKED. QA .56: preflight integral PASS; instalador real aberto como CommanderQA, aguardando entrada legítima. Ainda sem prova de instalação/pareamento concluídos neste recibo.**

## Causa demonstrada

O comando copiado do portal baixou `/install/windows.ps1`. Seu SHA-256 foi
`6ba5c29e6d3a604750331d7699455ad609b4b0a8e191c03ad10503f7a5161c3c`;
a linha 113 corresponde ao `AGENT_SHA256_MISMATCH` mostrado pelo usuário.

| Componente público | Conteúdo observado |
| --- | --- |
| Manifesto com assinatura v1 válida | Versão 0.3.41; espera Agent Windows de 56.752 bytes, SHA `52bb1b3c537c31a357becc38c494ea8494bf310fc3e694d59b1a578509a56d44`. |
| Agent Windows entregue | Versão 0.3.52; 98.717 bytes, SHA `817325667ea552136efa10d807148fa4dc6d035aca24046c884f444a4fb61ebc`. |
| Instalador público | Declara versão 0.3.49 no enrollment e na configuração. |

O mesmo download, tamanho e hash foram reproduzidos em PowerShell 5.1 na VM
`hara-review-win11-restoretest-20261024`, sob o SID real de CommanderQA. Os bytes
coincidem com o download feito em Services; não há evidência de transformação de
encoding na máquina do usuário. Os dois instaladores usam `Invoke-WebRequest
-OutFile`.

O gate público somente de leitura verificou a assinatura contra a chave v1 fixada
no commit histórico `08500d5`. **Os quatro arquivos declarados divergiam**:
Agents Linux e Windows e instaladores Linux e Windows. A assinatura do manifesto
passou; o conjunto distribuído não corresponde ao manifesto.

A seleção de release do checkout permanece `bundle: null`. Não houve assinatura
substituta, alteração de SHA esperado, promoção da candidata .56 nem deployment
de API/UI/arquivos públicos nesta correção. Recompor a distribuição pública
exige um conjunto coerente e admitido, preservando o deployment vigente.

## O que a tentativa do usuário fez

O instalador público pede o token e chama enrollment antes de baixar/verificar o
Agent. A falha de integridade ocorre depois. O `ROLLBACK=PASS` é emitido apenas
quando a resposta de revoke-self confirma a revogação do mesmo dispositivo.

A leitura nativa independente confirmou, após essa tentativa:

- tarefa global do produto ausente;
- diretório do produto, Agent e `device.json` ausentes;
- CurrentUser `RemoteSigned`, preservado nos testes seguintes;
- nenhuma tentativa de enrollment feita pelo diagnóstico.

O código de pareamento da tentativa já foi consumido pelo fluxo de enrollment;
a próxima tentativa requer um código novo da conta Reviewer.

## Correção aplicada à QA .56

Os launchers existentes na Área de Trabalho foram atualizados, com novo pin no
CMD para o wrapper. O instalador assinado original e os artefatos .56 permaneceram
inalterados.

Antes de qualquer prompt de pareamento, o wrapper agora:

1. Executa o preflight oficial com validação real do manifesto e assinatura.
2. Baixa o Agent inteiro pela mesma origem de release configurada, sem redirects.
3. Exige 172.687 bytes, SHA
   `a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620`
   e declaração única da versão 0.3.56.
4. Registra `agent_payload_verified=true` e remove seu cache temporário no
   encerramento normal ou erro tratado.

O instalador oficial ainda realiza sua própria verificação posterior. O servidor
privado carrega somente os oito arquivos fixados por hash em memória, o que
mantém o conteúdo imutável nesta janela. Este backstop da QA **não corrige os
arquivos públicos do portal**.

Às **01:32:13**, o CMD real passou em PowerShell 5.1 como CommanderQA:
`PASS_NATIVE_PREFLIGHT`, exit0, payload integral verificado, cache removido,
política anterior RemoteSigned preservada. O PASS da rodada R4, anterior a esta
mudança, verificava metadados e não deve ser reinterpretado como teste do payload.

## Continuação na VM

Às **01:35:16**, foi aberto o CMD **Instalar HARA Commander** usando tarefa
temporária `Interactive/Limited` para o SID de CommanderQA, sem triggers.
Às **01:36:59**, a tarefa estava Running e o processo do instalador oficial estava
sob esse SID; a tarefa do produto ainda não existia. O código deve ser gerado na
sessão legítima de `openai-reviewer@haralabs.com.br` e digitado no prompt protegido
do instalador. A conexão de Browser desta conversa estava indisponível; não se
forjou uma sessão ou código.

A tarefa interativa foi iniciada efetivamente às 04:35:16Z com limite de 50 minutos:
fim máximo 05:25:16Z, antes do encerramento do servidor privado por volta de
05:29:15Z. O certificado de QA teve remoção agendada para 05:30:15Z/startup.
As regras e a confiança da janela anterior foram verificadas como removidas
antes desta renovação. O novo agendamento não é prova antecipada de limpeza.

Os helpers aqui são registros de uma execução finita, vinculados aos pins,
preimagens e horários acima; não são ferramentas genéricas para reexecutar após
a janela. Se houver timeout, conferir o processo, resultado e resíduos antes de
renovar a preparação.

## Evidências

- [Falha pública e reprodução nativa](public-failure.json).
- [R5 com verificação integral e lançamento](qa-payload-guard.json).
- [Processo interativo observado](interactive-installer.json).
- [Limpeza comprovada da janela anterior](previous-window-cleanup.json).
- [Wrapper atualizado e seus limites](../launcher/README-launcher.md).

Instalação completa, heartbeat, lifecycle/rollback e os demais gates de #240,
#310 e #322 permanecem pendentes conforme seus aceites reais. **Lançamento público:
NO-GO.**
