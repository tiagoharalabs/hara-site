$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Uuid=([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant()
if($Uuid -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
if(-not[Security.Principal.WindowsIdentity]::GetCurrent().IsSystem){throw 'CLONE_SYSTEM_REQUIRED'}
$File=Join-Path $Box 'phase-private.json'
$Spec=Get-Content -LiteralPath $File -Raw|ConvertFrom-Json
$Phase=[string]$Spec.phase
if($Phase -notin @('install','inspect','start','stop','update-stopped','update-running','negative-signature','uninstall')){throw 'UNKNOWN_QA_PHASE'}
if([string](Get-CimInstance Win32_ComputerSystem).UserName -notmatch '\\HARAQA$'){throw 'INTERACTIVE_QA_SESSION_REQUIRED'}
$Name='HARA Commander Clean QA Harness'
$Old=Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if($Old -and [string]$Old.State -eq 'Running'){throw 'QA_HARNESS_ALREADY_RUNNING'}
$Result=Join-Path $Box ('phase-'+$Phase+'.json')
Remove-Item -LiteralPath $Result -Force -ErrorAction SilentlyContinue
foreach($Path in @((Join-Path $Box ('harness-error-'+$Phase+'.private.txt')),(Join-Path $Box ('error-'+$Phase+'.private.txt')),(Join-Path $Box ('phase-'+$Phase+'.private.log')))){
 Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
}
$Wrapper=Join-Path $Box 'qa-task-wrapper.ps1'
$Body='$ErrorActionPreference=''Stop'';$global:LASTEXITCODE=0;try{& '''+(Join-Path $Box 'windows_clean_qa_lifecycle.ps1')+''' -Parameters '''+$File+''' *> '''+(Join-Path $Box ('harness-'+$Phase+'.private.log'))+''';if(-not $? -or $LASTEXITCODE -ne 0){exit 1};exit 0}catch{[IO.File]::WriteAllText('''+(Join-Path $Box ('harness-error-'+$Phase+'.private.txt'))+''',([string]$_.Exception.Message));exit 1}'
[IO.File]::WriteAllText($Wrapper,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Wrapper+'"')
$Qa=Get-LocalUser -Name 'HARAQA' -ErrorAction Stop
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings $Settings -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{schema='hara.windows-clean-qa-scheduler.v1';state='QA_PHASE_STARTED';phase=$Phase;task=$Name;qa_name='HARAQA';interactive=$true;clone_uuid=$Uuid;credential_printed=$false}|ConvertTo-Json -Compress
