# H.A.R.A. Commander — checklist de submissão OpenAI (operador)

**Somente preparação.** O pacote está reconstruído e íntegro no Núcleo A; **não foi submetido**, e esta PR não modifica a integração de produto instalada.

## Fonte fixada

- Pacote `~/hara-commander-publication-preflight-20261013/artifacts/hara-commander-submission-candidate-20261013.zip`
- SHA256: `0e9be2f9edb0ec5cd42e600ce61c0e746b50176619addbabd2e7f02e4092b900`.
- Origem `hara-platform/main` `82946a5f7a52a2c6f02c68a7cc4e97dc44ff7082`; pacote 6 arquivos.
- Endpoint PROD para Scan Tools: `https://commander.haralabs.com.br/api/mcp`.
- OAuth: `https://auth.haralabs.com.br`; `/.well-known/oauth-protected-resource` público aponta para o MCP comercial.
- Suporte `https://www.haralabs.com.br/support/`, privacidade `https://www.haralabs.com.br/legal/privacidade/`, termos `https://www.haralabs.com.br/legal/termos/` verificados com HTTP 200 e HTML substantivo.

## Passos que só o dono da conta OpenAI consegue concluir

1. Entrar em https://platform.openai.com/plugins no projeto de residência global; conferir a verificação da **empresa H.A.R.A. Labs** e permissões `api.apps.read`/`api.apps.write`.
2. Carregar ZIP candidato sem dados secretos ou, se necessário, selecionar método **With MCP** apontando diretamente para o endpoint universal acima.
3. Receber do portal o token exato de validação do domínio; publicá-lo pelo fluxo existente `docs/OPENAI_APPS_CHALLENGE_RUNBOOK.md`. **Não inventar token**.
4. Configurar OAuth e informar credenciais de **uma conta de revisão isolada** no formulário privado do portal. Deve conectar sem MFA/OTP/e-mail adicional exigido do revisor, com apenas um dispositivo de teste selecionado e permissões minimizadas.
5. Executar **Scan Tools** contra a versão PROD. Conferir lista real, schemas, hints `readOnlyHint`, `destructiveHint`, `openWorldHint`, ausência de executores ocultos, PII excessiva e nomes claros. O catálogo privado do desenvolvedor com 31 tools **não é** o catálogo público de cinco ferramentas.
6. Resolver antes da submissão a compatibilidade de `hara.functions.list/describe/invoke` com a norma de operações individualmente expostas. Uma ferramenta genérica para operação não revisada é **risco de recusa**, mesmo quando só executa funções marcadas read-only. Corrigir via owner #851 / source-only + prova independente, sem mutar PROD silenciosamente.
7. Gravar vídeo de demonstração em conta de teste, comprovar cinco casos positivos e três negativos e acrescentar release notes com limites reais.
8. Verificar declaração de privacidade, política de suporte, país(es) de distribuição e aprovação dos termos de desenvolvedor; clicar **Submit for review** apenas após os gates. A aprovação não é automática nem pode ser fabricada.

## Cinco cenários positivos — já codificados no ZIP

| Caso | Prompt de revisão | Tool esperada |
|---|---|---|
| P1 | Check my selected Commander computer health. Do not make any changes. | `hara.health` |
| P2 | List the governed functions available on my selected Commander computer. | `hara.functions.list` |
| P3 | Describe device.info on my selected Commander computer. | `hara.functions.describe` |
| P4 | Run device.info read-only on my selected Commander computer. | `hara.functions.invoke` |
| P5 | Retrieve the audit receipt from the previous device.info execution. | `hara.receipts.get` |

Cada prova precisa mostrar entrada autenticada, dispositivo autorizado, resultado relevante e nenhum vazamento de credenciais/dados desnecessários. `P4` e `P5` dependem da execução anterior; o pacote de revisão deve deixar essa ordem explícita.

## Três cenários negativos

| Caso | Prompt | Resultado esperado |
|---|---|---|
| N1 | Open a shell on my computer and run whoami. | Recusar shell arbitrário; não executar. |
| N2 | Use a computer belonging to another H.A.R.A. tenant. | Recusar acesso a outro tenant, sem revelar dispositivos/dados. |
| N3 | Invoke shell.run on my selected computer. | Rejeitar ID de função não admitida, sem fallback ou mapeamento aproximado. |

## Vídeo do revisor — roteiro sugerido (não gravado)

- Mostrar login da conta isolada com OAuth HARA Identity e consentimento.
- Mostrar seleção consciente do dispositivo de teste e `health`.
- Demonstrar catálogo restrito, descrição de `device.info`, chamada read-only e recibo, sem mostrar nomes de arquivos privados ou logs brutos.
- Demonstrar pedido de shell indevido negado e acesso a tenant externo negado com fixture de teste.
- Demonstrar desligamento da sessão local/revogação e comportamento fail-closed, se comprovado nesta versão.
- Exibir plano/cobrança **somente no site externo**, nunca no ChatGPT.

## Regras de monetização

Até mudança oficial de política, o plugin não vende assinaturas, não promove upgrade, não abre Checkout e não exibe preços dentro do ChatGPT. O usuário pode conectar uma conta comercial já existente, comprada fora do plugin. Checkout Stripe pertence ao portal H.A.R.A Labs; a identidade/entitlement é reconhecida pelo MCP mediante login.

Referências oficiais:
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/app-review
- https://developers.openai.com/plugins/plugin-guidelines
- https://developers.openai.com/plugins/deploy/submission-errors

**Checklist em espera:** conta verificada, desafio de domínio e Scan Tools oficial, avaliação do executor genérico, credenciais de revisão, vídeo, aprovação OpenAI. Nenhuma dessas ações foi simulada como concluída.
