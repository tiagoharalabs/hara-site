$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028';$desktop='C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA'
$sid='S-1-5-21-1207901905-1500652706-889822281-1005'
if((Get-CimInstance Win32_ComputerSystem).UserName -ine 'HARA_WIN11\CommanderQA'){throw 'COMMANDERQA_CONSOLE_REQUIRED'}
$r=Get-Content -Raw -LiteralPath (Join-Path $root 'results\preflight-r5-result.json')|ConvertFrom-Json
if($r.state -cne 'PASS_NATIVE_PREFLIGHT' -or -not $r.wrapper.agent_payload_verified){throw 'FULL_PAYLOAD_PREFLIGHT_REQUIRED'}
if(Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue){throw 'PRODUCT_TASK_NOT_EMPTY'}
$old=@{'LEIA-ME.txt'='3b72e553d79f8a8986f1302d226b56b9c6db65cf27540c060a62d28ba2fab495';'RESULTADO-DOS-TESTES.txt'='f8f95525a9ac5b38e592553de2b3462978ec81d0463fd416af8360ab9b5bd42c'}
foreach($n in $old.Keys){$p=Join-Path $desktop $n;if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $old[$n]){throw 'DESKTOP_DOCUMENT_CHANGED'};Copy-Item -LiteralPath $p -Destination (Join-Path $root ('backup\'+$n+'.before-payload-guard'))}
$readme=@'
HARA Commander 0.3.56 — Windows QA
VM Win11 Sent B / hara-review-win11-restoretest-20261024 / Sentinela B.
Usuario Windows: CommanderQA. Conta Identity: openai-reviewer@haralabs.com.br.

Use o atalho Instalar HARA Commander da Area de Trabalho.
A verificacao agora baixa e confere o Agent inteiro ANTES de pedir o codigo.
O teste nativo passou em 28/10/2026 01:32, horario de Brasilia.
Assinatura, versao .56, tamanho 172687 bytes e SHA-256 do Agent foram conferidos.

No portal Commander, gere um NOVO codigo de pareamento. Cole somente esse codigo
no campo Pairing token do instalador aberto pelo atalho de QA.
O codigo usado na tentativa que falhou foi consumido; nao o reutilize.
A senha do HARA Identity e diferente do codigo de pareamento.

O comando de instalacao atualmente exibido pelo portal usa uma distribuicao publica
inconsistente. Para esta campanha, a entrada correta e o atalho de QA acima.
A janela privada atual encerra em 28/10/2026 aproximadamente 02:29, Brasilia.
Depois disso, a Valky precisa renovar a preparacao antes da instalacao.

A instalacao so estara concluida quando o resultado indicar instalado, pareado
e heartbeat recente. O produto continua sem liberacao para lancamento publico.
'@
$result=@'
28/10/2026 01:23, Brasilia: falha publica reproduzida como CommanderQA.
Manifesto assinado .41, Agent Windows entregue .52 e instalador declarando .49.
A tarefa do produto, Agent e device.json estavam ausentes apos a tentativa.
A conta manteve sua politica CurrentUser RemoteSigned.

28/10/2026 01:32, Brasilia: PASS_NATIVE_PREFLIGHT com verificacao integral do Agent .56.
Saude, manifesto, assinatura, download real de 172687 bytes, hash e versao: PASS.
agent_payload_verified=true; cache temporario removido; politica preservada.
Este PASS ainda nao representa instalacao ou pareamento.
'@
[IO.File]::WriteAllText((Join-Path $desktop 'LEIA-ME.txt'),$readme,[Text.Encoding]::UTF8)
[IO.File]::WriteAllText((Join-Path $desktop 'RESULTADO-DOS-TESTES.txt'),$result,[Text.Encoding]::UTF8)
$files=@(Get-ChildItem -LiteralPath $desktop -File|Where-Object Name -ne 'SHA256SUMS.txt'|Sort-Object Name|ForEach-Object{(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+$_.Name})
[IO.File]::WriteAllLines((Join-Path $desktop 'SHA256SUMS.txt'),[string[]]$files,[Text.Encoding]::ASCII)
$name='HARA-QA056-Interactive-Install-R5-20261028'
if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'INTERACTIVE_TASK_EXISTS'}
$a=New-ScheduledTaskAction -Execute $env:ComSpec -Argument ('/d /c call "'+(Join-Path $desktop 'Instalar-Commander.cmd')+'"') -WorkingDirectory $desktop
$p=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 50) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $name
[ordered]@{state='QA_INSTALLER_INTERACTIVE_STARTED';at_utc=[DateTime]::UtcNow.ToString('o');task=$name;user='CommanderQA';logon='Interactive';runlevel='Limited';full_payload_preflight='PASS';awaits='FRESH_REVIEWER_PAIRING_INPUT';public_distribution='BLOCKED_MIXED_VERSIONS'}|ConvertTo-Json -Depth 5 -Compress
