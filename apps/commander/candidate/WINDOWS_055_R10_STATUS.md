# Windows 0.3.55 R10 — fonte candidata sem assinatura

`windows_agent_055.ps1` deriva do Agent Windows do bundle histórico
`commercial-0.3.54-v14-rc-r2` em `0e0c2ac`; o verificador local confirma a
assinatura RS256 desse **bundle de origem** e seu SHA-256
`fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62`.
Isso não autentica criptograficamente a fonte 0.3.55 modificada. Ela não possui
manifesto nem assinatura, e não foi selecionada pelo instalador comercial.

O patch acrescenta paginação Windows de diretórios, leitura múltipla, busca,
edição com precondição e mutex entre processos, saída one-shot consultável e
continuação limitada de claims após conclusão no relay. A entrada da sessão
gerenciada continua sendo **linhas de comando PowerShell**, sem `Read-Host` nem
STDIN interativo. A listagem informa `stable_across_calls=false`: offset entre
chamadas é melhor esforço se a árvore mudar, mesmo quando a varredura de cada
chamada está completa.

O probe gerado por `build_windows_r10_runtime_probe.py` extrai as funções da
fonte exata e executa apenas em pasta sintética de QA no HARA_WIN11. Passaram no
Windows 11 real: páginas distintas, resumo `PARTIAL`, busca Unicode, CAS
sequencial e entre dois processos, oito linhas em três páginas sem repetir o
comando, Unicode/exit 7 e política de burst. O SHA da fonte candidata foi lido
de volta na VM; parser PowerShell e `--self-test` passaram. O Agent instalado
continuou 0.3.53, pingou e terminou com zero sessões gerenciadas.

**HOLD de promoção:** assinatura oficial, pacote Linux/Windows coerente,
staging, teste de instalação limpa e rollback, canário Windows instalado,
medição real 1/4/8 chamadas com `queue_ms`/`execution_ms`, teste DEV comercial e
aprovação específica. O helper de burst passou isoladamente, mas não mede a
cauda do relay em uso. Nenhum item acima autoriza PROD.
