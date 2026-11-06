# H.A.R.A. Commander — conta de demonstração para a revisão da OpenAI

**Status: PREPARADA COMO PROCEDIMENTO / CONTA NÃO CRIADA.** Owner da conta, do dispositivo e da autorização: equipe H.A.R.A. Labs. A PR não provisiona usuários no HARA Identity, dispositivos, entitlements ou segredos.

## Contratos oficiais da revisão

A OpenAI exige um **login e senha de uma conta de demonstração dedicada com dados de exemplo**, acessível fora da rede da empresa, sem MFA, OTP, magic link nem códigos recebidos por SMS/e-mail para fazer login. Usuário revisor deve conseguir executar os cinco casos positivos e três negativos. As credenciais são inseridas **somente** no formulário seguro do portal (Review details), nunca no ZIP, GitHub, vídeo ou comentários. Manter disponível para eventuais reavaliações.

Docs: https://developers.openai.com/plugins/deploy/submission e https://developers.openai.com/plugins/deploy/app-review

## Especificação recomendada (nomes são modelos, não recursos existentes)

| Objeto | Proposta | Situação |
|---|---|---|
| Conta HARA Identity | Alias de e-mail controlado da H.A.R.A. Labs, **real**, reservado a revisão OpenAI | NÃO CRIADA/VALIDADA AQUI |
| Nome do tenant/workspace | `HARA_OPENAI_REVIEW` ou equivalente autorizado | NÃO CRIADO |
| Papel do revisor | Menor permissão necessária para visualizar e invocar `device.info`; sem ADMIN de toda plataforma | NÃO CONFIGURADO |
| Entitlement | Plano oficial (ex. Trial) ou concessão de revisão governada, com quota suficiente para repetições dos cenários | NÃO ATRIBUÍDO |
| Computador de amostra | VM/host isolado **não produtivo**, sem arquivos reais ou acesso a hosts internos, ligado a esse tenant | NÃO PAREADO |
| Agent | Versão homologada, conectada pelo produto Commander (não pelo MCP Services) | NÃO PROVADO NO TENANT DE REVISÃO |
| Função local permitida | `device.info` somente, `argv=[]`, read-only no alvo sintético | A VALIDAR |
| Login | OAuth HARA Identity, credenciais prontas, sem segunda etapa de verificação para a conta isolada | NÃO PROVADO |
| Estabilidade | Página e dispositivo disponíveis enquanto a análise estiver em curso, sem depender de VPN/NAT privado | NÃO PROVADO |

**Importante:** não usar o próprio tenant Founder/Internal, dispositivos de gameplay ou o computador com arquivos privados como demo pública. O HARA Services interno não é o backend de comandos para clientes; não configurar túnel dele como atalho.

## Procedimento seguro de provisionamento

1. Criar uma **caixa/alias de e-mail existente e controlado** (exemplo descritivo, não provisionado: `<alias-de-review>@haralabs.com.br`). Não assumir que um endereço digitado já recebe mensagens.
2. Abrir https://commander.haralabs.com.br/ em um navegador separado: a UI atual contém **Criar conta** e **Entrar com HARA Identity**. Cadastrar o usuário de demonstração via fluxo normal ou pelo console de administração ZITADEL autorizado. Completar cadastro e eventual verificação inicial de e-mail **antes** de fornecer a conta ao portal.
3. Criar um workspace/tenant isolado, com um único sujeito revisor e nenhuma permissão cruzada; não ligar ao tenant real do fundador.
4. Aplicar entitlement oficial que permita apenas os testes de leitura. Quota não pode ser ampliada silenciosamente nem criada por edição direta do banco.
5. Parear com token de uso único um computador de demo HARA-owned isolado (preferência: VM de teste sem volume de dados real). **Não reutilizar** o Agent do Núcleo A/frota pessoal; ele pertence a outro domínio operacional.
6. Selecionar o dispositivo no portal. Deixar Agent/relay disponível ao revisor durante o período de análise, sem abrir portas inbound.
7. Conferir a política do HARA Identity: se MFA for obrigatório globalmente, criar uma **exceção aprovada estritamente para esta identidade de demonstração**, sem desabilitar MFA dos demais usuários. Revogar exceção após encerramento e quando não houver revisão pendente.
8. Testar em navegador limpo, fora da rede interna, sem cookies e sem sessão prévia, com e-mail/senha. Exigir que **nenhum** segundo código, e-mail, SMS, link mágico, aprovação de operador, VPN ou conexão interna seja necessário.
9. Executar as cinco ações de leitura do pacote (`health`, `list`, `describe(device.info)`, `invoke(device.info)`, `receipts.get`) com quota e recibo corretos.
10. Executar os três testes negativos (`shell`, outro tenant, `shell.run`) e confirmar recusa segura e ausência de execução.
11. Entrar no **OpenAI Plugin Portal → Review information → Review details** e inserir login URL, e-mail, senha e instruções do workspace **exclusivamente no formulário privado**. Não incluir senhas em `plugin.json`, `mcp.json`, vídeos ou issues.
12. Manter conta disponível para revisões posteriores. Se alterar senha/instruções, atualizar o portal e confirmar a nova sessão antes de voltar a submeter.

## Instruções privadas para colar no portal (SEM segredos)

> Login URL: https://commander.haralabs.com.br/
>
> Select **Entrar** / **Entrar com HARA Identity**. Sign in with the dedicated reviewer username and password entered in the separate secure credential fields. The account already belongs to an isolated review workspace and has a synthetic test computer selected. No sign-up or second-factor verification is required. Do not change or revoke the test computer. Start by asking ChatGPT to check the selected computer's health, list available functions, describe `device.info`, invoke it read-only, and retrieve its receipt. Unsupported shell and cross-tenant requests must be denied.

Copiar essa orientação somente **depois** de verificar que corresponde ao login real e às permissões da conta.

## Recibo de aceite da conta (modelo, sem segredo)

```text
REVIEWER_TENANT_ISOLATED=UNVERIFIED
REVIEWER_ACCOUNT_CREATED=NO
REVIEWER_MAILBOX_CONFIRMED=NO
REVIEWER_LOGIN_EXTERNAL_BROWSER=UNVERIFIED
REVIEWER_MFA_OTP_REQUIRED=UNKNOWN
REVIEW_DEVICE_SELECTED=UNVERIFIED
REVIEW_DEVICE_AGENT_ONLINE=UNVERIFIED
REVIEW_FUNCTION_EXACT_DEVICE_INFO=UNVERIFIED
REVIEW_5_POSITIVE_CASES=UNRUN
REVIEW_3_NEGATIVE_CASES=UNRUN
REVIEW_CREDENTIALS_IN_GIT_OR_VIDEO=DENY
OPENAI_REVIEW_DETAILS_SAVED=NO
```

O estado não muda para PASS com base na existência deste documento. Exige teste real de autenticação/Agent sem compartilhar credenciais.
