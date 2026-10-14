# H.A.R.A. Commander — roteiro de VÍDEO REAL para revisão OpenAI

**Estado: ROTEIRO PRONTO / VÍDEO NÃO GRAVADO.** Não criar animação ou respostas artificiais para se passar por uma sessão real. O vídeo do revisor deve apresentar o próprio ChatGPT/plug-in ligado ao endpoint comercial, com conta e computador de demonstração **isolados** e os resultados efetivamente obtidos.

Docs: https://developers.openai.com/plugins/deploy/submission ; https://developers.openai.com/plugins/deploy/app-review

A OpenAI exige uma URL de gravação acessível aos revisores. O link pode entrar como `review.demo_recording_url` no ZIP ou no campo aplicável do portal. A gravação é **evidência de uso para avaliação**, não um “vídeo de aprovação” fornecido pela OpenAI.

## Preparação da captura (ANTES de gravar)

- Conta de demonstração separada já criada e testada **fora da rede HARA**, login HARA Identity sem segundo fator, sem OTP ou e-mail pendente.
- Um dispositivo de teste com `device.info` (read-only), online durante a sessão e no período da revisão.
- Conta do revisor com entitlement/quota real para repetir cinco testes positivos, sem acesso ao fundador, Serviços ou dados reais.
- ChatGPT conectado ao **plugin de submissão correto** com o mesmo servidor MCP comercial e a superfície publicada; não usar o plugin privado de desenvolvimento que expõe 31 tools para demonstrar o pacote de cinco.
- Finalizar o gate OpenAI de `functions.list/describe/invoke` e hints antes de chamar o vídeo de definitivo; um vídeo gravado com ferramentas diferentes das submetidas não serve.
- Abrir navegador limpo e fechar abas pessoais. Desativar notificações e ocultar barra de favoritos, histórico, outras conversas, e-mail pessoal, tokens, device IDs sensíveis, contas Stripe/Cloudflare e qualquer conteúdo de gameplay.
- Gravar em qualidade legível (por exemplo, MP4 H.264 1920x1080 30fps e áudio limpo), **opção de produção**, não formato exigido expressamente pela OpenAI.
- Planejar leitura em inglês simples ou legendas claras. Não é necessário mostrar digitação de senha; mostrar origem HARA Identity e sessão já autenticada é suficiente para o fluxo visual.
- **Gravar chamadas reais e observar o status**, inclusive negativas. Se algum teste falhar, parar/registrar o defeito e corrigir antes de gravar a tomada definitiva.

## Storyboard com oito casos obrigatórios

| Cena | Janela sugerida | Tela/ação REAL | Evidência esperada |
|---|---|---|---|
| Abertura | 00:00–00:20 | ChatGPT → plugin **H.A.R.A. Commander**, conta de revisão isolada; versão do pacote | Marca do desenvolvedor, sem dados privados |
| OAuth/dispositivo | 00:20–00:50 | Mostrar login HARA Identity concluído e dispositivo sintético selecionado | Login sem MFA adicional; tenant correto |
| P1 | 00:50–01:20 | Prompt `Check my selected Commander computer health. Do not make any changes.` | `hara.health`, online/saúde real, sem mutação |
| P2 | 01:20–01:50 | Prompt `List the governed functions available on my selected Commander computer.` | `hara.functions.list`; catálogo governado |
| P3 | 01:50–02:20 | Prompt `Describe device.info on my selected Commander computer.` | `hara.functions.describe`, descrição do ID exato |
| P4 | 02:20–03:00 | Prompt `Run device.info read-only on my selected Commander computer.` | `hara.functions.invoke`, resultado real do host sintético |
| P5 | 03:00–03:30 | Prompt `Retrieve the audit receipt from the previous device.info execution.` | `hara.receipts.get`, recibo correlacionado (minimizado) |
| N1 | 03:30–04:00 | Prompt `Open a shell on my computer and run whoami.` | Sem shell arbitrário/execução |
| N2 | 04:00–04:30 | Prompt `Use a computer belonging to another H.A.R.A. tenant.` | Recusa cross-tenant; nenhum dado externo |
| N3 | 04:30–05:00 | Prompt `Invoke shell.run on my selected computer.` | Função desconhecida negada, sem fallback |
| Encerramento | 05:00–05:30 | Repetir URL do produto/versão e ressaltar controle do operador e read-only | Resumo factual sem alegar aprovação da OpenAI |

As janelas são **um roteiro sugerido de edição**, não prazo nem requisito rígido de duração. Se os tempos reais forem maiores, não acelerar a ponto de impedir leitura; prefira cortes apenas entre etapas e mantenha o resultado em tela o bastante para conferência.

## Texto sugerido de narração em inglês

> This is H.A.R.A. Commander, a tool for connecting an authorized computer to ChatGPT through a secured remote MCP endpoint. The account shown belongs to a dedicated review workspace, with a synthetic test device. Authentication is handled by H.A.R.A. Identity.
>
> First, we check the health of the selected device. Next, we list its governed functions and describe the exact read-only `device.info` function. We now invoke `device.info` on the selected device and retrieve the corresponding audit receipt.
>
> Finally, we demonstrate the boundaries. Requests to open an arbitrary shell, access another tenant's computer, or run the unapproved `shell.run` function are not executed. H.A.R.A. Commander uses the user's authenticated device scope, authorization and receipt controls.
>
> All results shown come from this live isolated review environment.

Esta narração só deve afirmar o que foi efetivamente demonstrado. Se a superfície do MCP mudar após a revisão do contrato, atualizar os prompts, o vídeo e os cinco/três casos do pacote conjuntamente.

## Hospedagem e validação do link

1. Exportar vídeo para MP4 legível. Não incluir senha, token ou informações privadas na mídia ou no título.
2. Hospedar em serviço que forneça uma URL durável **acessível ao revisor sem pedir permissão** (por exemplo, vídeo não listado no YouTube, se elegível; ou arquivo Drive com opção de visualização para qualquer pessoa com link). A documentação exige **URL acessível**, não um provedor específico nem upload de MP4 dentro do ZIP.
3. Abrir link em janela anônima, sem conta HARA, Google/YouTube já autenticada, rede local ou VPN; confirmar áudio, vídeo e reprodução.
4. Só após o vídeo final, inserir URL como `review.demo_recording_url` no `plugin.json` do pacote ou campo apropriado do portal e **regerar/validar ZIP**. **Não** usar um placeholder ou link de mídia inacessível.
5. Conferir que os oito testes reais correspondem exatamente ao conjunto declarado pelo pacote e aos tools do Scan Tools. Se a gravação revelar falha, não submeter como PASS.

## Gates antes de declarar VIDEO_READY

```text
REVIEWER_ACCOUNT_EXTERNAL_LOGIN=UNPROVEN
NO_MFA_OR_MAGIC_LINK=UNPROVEN
DEMO_DEVICE_SELECTED_ONLINE=UNPROVEN
OPENAI_TOOL_SCAN_APPROVED=UNPROVEN
VIDEO_REAL_TOOL_CALLS_5_POSITIVE=UNRECORDED
VIDEO_SAFE_NEGATIVES_3=UNRECORDED
VIDEO_NO_SECRETS=UNVERIFIED
VIDEO_ACCESSIBLE_FROM_PRIVATE_WINDOW=UNVERIFIED
REVIEW_DEMO_RECORDING_URL=ABSENT
```

**O vídeo não substitui a conta de revisão, domínio verificado, aprovação dos tool hints ou a decisão oficial da OpenAI.**
