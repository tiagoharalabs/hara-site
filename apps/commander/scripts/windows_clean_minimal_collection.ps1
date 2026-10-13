$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
$Name='HARA Commander Clean QA Harness'
$Old=Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if($Old){if(-not ([string]$Old.Actions[0].Arguments).Contains($Box)){throw 'OWNED_HARNESS_REQUIRED'};Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue}
$Child=Join-Path $Box 'native-minimal-check.ps1'
$Body=@'
$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Output=Join-Path $Box 'native-minimal-installed.txt'
[IO.File]::WriteAllText($Output,"QA_USERNAME="+[string]$env:USERNAME+"`nLOCALAPPDATA="+[string]$env:LOCALAPPDATA+"`n")
function AddLine([string]$Value){[IO.File]::AppendAllText($Output,$Value+"`n")}
try{
 AddLine ('QA_SID='+[string][Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
 $Agent=Join-Path $env:LOCALAPPDATA 'HARA Commander\hara-commander-agent.ps1'
 AddLine ('AGENT_BYTES='+[string](Get-Item -LiteralPath $Agent).Length)
 $hash=(& certutil.exe -hashfile $Agent SHA256 2>$null|Where-Object{$_ -cmatch '^[0-9a-fA-F]{64}$'}|Select-Object -First 1)
 AddLine ('AGENT_SHA256='+[string]$hash)
 $installer=Join-Path $Box 'windows-053-r2.ps1'
 $ihash=(& certutil.exe -hashfile $installer SHA256 2>$null|Where-Object{$_ -cmatch '^[0-9a-fA-F]{64}$'}|Select-Object -First 1)
 AddLine ('INSTALLER_SHA256='+[string]$ihash)
 $cfg=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander\device.json') -Raw|ConvertFrom-Json
 AddLine ('DEV_ORIGIN_CORRECT='+[string]($cfg.base_url -ceq 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'))
 AddLine ('APPROVAL_MODE='+[string]$cfg.approval_mode);$cfg=$null
 $st=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander\runtime-status.json') -Raw|ConvertFrom-Json
 AddLine ('RUNTIME_VERSION='+[string]$st.agent_version)
 Get-Content -LiteralPath (Join-Path $Box 'phase-install.private.log')|Where-Object{$_ -cmatch '^(HARA_COMMANDER_[A-Z_]+|DEVICE_TOKEN_EXPOSED)=[A-Z_0-9]+$'}|ForEach-Object{AddLine ([string]$_)}
 AddLine 'MINIMAL_COLLECTION=PASS'
}catch{AddLine ('COLLECTION_ERROR_ID='+[string]$_.FullyQualifiedErrorId)}
'@
[IO.File]::WriteAllText($Child,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Child+'"')
$Qa=Get-LocalUser -Name HARAQA
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 40)
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings $Settings -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{state='MINIMAL_QA_COLLECTION_STARTED';product_task_modified=$false}|ConvertTo-Json -Compress
