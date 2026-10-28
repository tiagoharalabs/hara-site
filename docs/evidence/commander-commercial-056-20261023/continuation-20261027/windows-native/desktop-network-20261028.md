# Windows QA — rede, acesso e Desktop

Na VM `hara-review-win11-restoretest-20261024`, a interface de rede estava ausente. Foi adicionada uma **e1000e** à rede existente `hara-review-egress`, no estado ativo e na configuração persistente, sem alterar o guard. O Windows recebeu **192.168.252.113**. As sondas HTTPS retornaram **200** (saúde Commander), **302** (login Commander) e **308** (HARA Identity), todas com exit0. Isso comprova acesso HTTPS; não comprova navegação interativa ou login.

O atalho existente **VM Win11 Sent B**, no Nucleo-A, foi corrigido: o alvo antigo `hara-review-win11` passou para a VM ativa acima. O backup foi preservado e o acesso privado SSH/SPICE foi mantido.

Os cinco arquivos — instalador, Agent .56, instruções, resultado dos testes e orientação de acesso — mais **SHA256SUMS.txt** estão em:

`C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA`

Os hashes foram verificados; o proprietário é **CommanderQA** e a ACL está protegida. Não houve alteração de senha; a senha atual não foi obtida nem publicada.

**Instalado: não. Pareado: não.** Esta entrega não concede aceite de release. O [resumo](desktop-network-20261028.json) contém os nomes/hashes dos arquivos e os hashes dos cinco recibos de origem, sem credenciais, comandos brutos ou endereço de acesso privado.
