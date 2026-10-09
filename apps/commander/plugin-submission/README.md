# H.A.R.A. Commander — pacote candidato para diretório OpenAI

**Status: DRAFT — NÃO SUBMETIDO / NÃO APROVADO.**

Conteúdo:
- `plugin.json`: metadados do plugin H.A.R.A. Commander (capivara dourada) e roteiros de revisão (cinco positivos e três negativos).
- `mcp.json`: **somente** o endpoint comercial `https://commander.haralabs.com.br/api/mcp?profile=simple`, hospedado na Cloudflare, autenticado por HARA Identity OAuth.
- `assets/logo.png` e `assets/icon.png`: cópias convertidas do arquivo de marca existente do Commander (sem gerar outra identidade visual).

Esses roteiros ainda precisam ser **executados ao vivo** num tenant de demonstração autorizado. Não utilizar contas privadas reais ou expor segredos no ZIP.

Pré-requisitos para submissão:
1. Validar URL MCP comercial com uma conexão ChatGPT distinta do conector administrativo Services (login OAuth, leitura, escrita autorizada, negação).
2. Confirmar assinatura válida do Agent distribuído (público atual: 0.3.41). Fonte candidata 0.3.43 **não assinada**.
3. Verificação de organização H.A.R.A. Labs e permissões Apps Management da OpenAI; desafio de domínio apresentado no portal de submissão.
4. Inserir credenciais de uma conta DEMO apenas no formulário privado de revisão da OpenAI.
5. Disponibilizar vídeo real demonstrando os casos de uso e verificar os resultados dos 5 casos positivos e 3 negativos.
6. Submeter e aguardar aprovação; não anunciar como publicado antes disso.

Declaração de transparência: chamadas da modalidade Cloud passam pelo Gateway Cloudflare. Na fila D1, conteúdo pode ficar temporariamente persistido; o TTL nominal é 50 segundos e a redação depende da manutenção agendada. Não afirmar 'zero armazenamento de conteúdo' nem 'sem trânsito por H.A.R.A.'.

Fonte de requisitos: https://developers.openai.com/plugins/deploy/submission
