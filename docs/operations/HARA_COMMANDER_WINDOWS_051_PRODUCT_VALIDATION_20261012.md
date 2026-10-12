# H.A.R.A. Commander — validação real Windows 0.3.51 (12/10/2026)

O núcleo funcional Windows foi validado pelo plugin **H.A.R.A. Commander** no MCP real. A VM respondeu com Agent **0.3.51**; sua fonte instalada é byte-idêntica à RC privada assinada, SHA-256 `4c563987986249d78c76258d062a4d360ffb88199539429ea97c2f346644656a`. O gate da versão passou **115/115**, e a assinatura RS256/RSA3072 foi verificada independentemente com a autoridade v2 existente.

Aprovação individual de 15 minutos teve aceite humano positivo na versão49, recibo `4963b1d2f09e21f27f3507d38c3c62cdddb810462fd08adec30319ac2ddf8dd1`. O usuário confirmou a frase completa na janela; o resultado retornou HARA_WIN11 após aproximadamente126 segundos. Não se afirma espera real de900 segundos. O modo atual observado é **SESSION_TRUSTED**, configuração SHA `ecf734ae64557ba51767268efa94beab1b924ff5b8145afdd80d17c50078e5b6`; os testes51 usaram esse modo existente, sem alterar a configuração nem gerar aprovação humana artificial.

| Teste real | Resultado |
| --- | --- |
| Identificação da VM | PASS, Windows51/PowerShell5.1 |
| Escrita com acentos, travessão e emoji | PASS,40 bytes exatos |
| Atualização com SHA-256 correto | PASS |
| SHA-256 antigo | DENIED/FILE_PRECONDITION_FAILED; arquivo inalterado |
| Terminal: início e envio de comandos | PASS |
| Unicode na entrada e na saída | PASS |
| Variável preservada entre comandos Unicode | PASS |
| Saída após encerramento | PASS, exit7 e texto íntegro |
| Paginação de saída | PASS |
| Encerramento normal solicitado | PASS, EXITED/exit0 |
| Encerramento forçado | PASS, KILLED/exit-1 |
| Recuperação de recibo anterior após reconexão | PASS, mesmo recibo; leitura redigida sem nova execução |

Arquivo próprio de teste: `HARA_Commander49_CAS_20261012_6843883f.txt`,40 bytes, SHA `891fb469306d0f68212e044dec89e4a1c770bee194d4171c5de341b4976e1808`. A confirmação usa os bytes e o hash calculados no Windows, além da leitura pelo MCP. A evidência anterior36→43 bytes e a perda de travessão/emoji no terminal50 permanecem preservadas como controles negativos.

As correções incluem JSON HTTP em UTF-8 explícito nos dois sentidos, substituição do parâmetro automático PowerShell `$Input` por `$InputText`, codificação de stdout/stderr e transporte de comandos Unicode por um envelope ASCII antes do leitor OEM do ConsoleHost. A versão51 preserva as variáveis da sessão ao executar esses comandos.

Fonte/assinatura50 e51 vieram da frente paralela já preparada e foram verificadas por hash e criptografia. A instalação não é atribuída aos drafts de cutover Root50 nem aos helpers abortados. As provas funcionais acima são chamadas próprias Root pelo Commander direto. Baseline não foi chamado.

## Distribuição pública e backend

Uma publicação paralela colocou manifesto público41 com fontes incompatíveis, substituindo os oito assets assinados43. O Root restaurou **commercial-0.3.43-v3**, preservando os módulos do Worker UTF-8 e seus bindings, a UI e as imagens. Fonte Worker `9bfd38d5adb3e0b2d990f586683cbec1c211d0d06c5429d1309780395d0da7d6`; deployment `a9680c55-bf22-4499-92cb-7ff2e2769cec`, versão `f5f667e4-1e65-4a84-a850-8fef6877598d` em100%. Compilado dry-run e produção idênticos. **15/15 URLs normais públicas** e os oito arquivos assinados foram confirmados depois do primeiro readback transitório. Nenhuma migração nova, alteração Stripe, reboot ou atualização dos Agents Linux foi feita nessa restauração.

## Evidências e limites

Evidências próprias: `docs/evidence/commander-win51-product-validation-20261012-root/`. Código51: `4da72a6973981f462f5bf6595d36ba72898728ab`. A versão51 permanece canário privado; o download público continua43.

Há dois defeitos de metadados registrados: o envelope Windows retorna `mutation_performed=false` mesmo quando a ação executou, e o replay redigido pode perder `risk_class=PROCESS_EXECUTION`. Os gates de autorização continuam anteriores aos efeitos; estes campos ainda exigem correção. As sessões Windows validadas são comandos PowerShell por pipes; ConPTY e stdin de aplicações arbitrárias não foram certificados. Cobrança, Stripe, soak e mil clientes reais continuam fora desta aceitação. O resultado é **PASS do núcleo funcional Windows**, sem certificação de disponibilidade geral.
