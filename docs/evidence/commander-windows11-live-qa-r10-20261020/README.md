# R10 Windows QA — provas reais e limitações

As observações registram invocações diretas do HARA Commander contra a VM HARA_WIN11 logada em 20/10/2026. O arquivo QA C:\Users\Public\Documents\HARA_COMMANDER_QA_20261020_WIN11\probe.txt é sintético e foi preservado para a frente Codex. Testes de pasta/arquivo/processo usam a conta Founder no Agent Windows 0.3.53. Nenhum Agent foi reinstalado.

O comando real QEMU informou 8,sockets=8,cores=1,threads=1; o Windows 11 Pro detectou dois lógicos. Não alteramos VM/topologia nem reiniciamos a máquina. Os microbursts não medem capacidade máxima ou performance de Windows 0.3.43 candidato, apenas a versão 0.3.53 em OUTBOUND_RELAY. Timestamps/recibos da interface suportam o relato, mas os IDs de solicitações brutas não foram persistidos.

Exemplos para refazer com autorização e somente na pasta QA:
- HARA Commander get_config/ping(computer=HARA_WIN11)
- list_directory(C:\,limit=4,offset=0/4/100)
- read_file do probe.txt offset 0/3
- process.run PowerShell Write-Output, exit 7 e oito linhas max_lines 3
- read_multiple_files/search/edit_block exclusivamente na pasta QA
- processo interativo: não usar Read-Host para ações produtivas antes de corrigir contrato

A evidência não autoriza instalar release não assinado, mudar política de aprovação, reiniciar VM ou promover Cloudflare. Relatório: docs/operations/HARA_COMMANDER_WINDOWS11_LIVE_QA_R10_20261020.md.
