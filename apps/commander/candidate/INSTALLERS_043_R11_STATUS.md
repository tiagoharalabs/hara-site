# R11 — instaladores comerciais 0.3.43 candidatos

`linux_install_043.sh` e `windows_install_043.ps1` partem dos instaladores do
bundle assinado histórico `commercial-0.3.43-v4-autoreconnect`, com o pin
`commander-release-v2`. As fontes modificadas **não possuem assinatura**.
O builder `build_commander_commercial_terminal_drain_candidate.py` as inclui no
pacote local 0.3.43, recalcula os quatro hashes e remove a assinatura antiga.

Na instalação nova, os dois instaladores validam manifesto RS256, `kid`, os
quatro assets, tamanhos, versões dos Agents e o próprio bootstrap salvo antes
de enviar o token ao endpoint de inscrição. O Agent verificado é reutilizado
depois do cadastro, evitando uma segunda consulta suscetível a troca de bytes.
O rollback já existente continua no caminho de falha após o cadastro.

O mock Linux executou o instalador completo: a fonte antiga fez um POST antes
de falhar, enquanto a candidata recusou `kid`, hashes e versão incompatíveis
com **zero POSTs**. A função de verificação Windows foi exercitada na VM
HARA_WIN11 por um probe isolado; parser da fonte completa passou, sem executar
o instalador, fazer inscrição ou trocar o Agent instalado. A fonte Windows
0.3.55 de paridade R10 continua separada do pacote 0.3.43.

**HOLD:** assinatura oficial do pacote completo, readback público pelo gate
`verify_live_release_integrity.py`, instalação limpa em QA Linux/Windows,
canário e rollback, além de aprovação específica. O pacote `/tmp` é transitório
e não é publicação. O rollback v4 é íntegro na assinatura, mas tem regressão
funcional conhecida de drenagem de saída; não é candidato de promoção.
