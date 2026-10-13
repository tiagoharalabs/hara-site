$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
$Name='HARA Commander Clean QA Harness'
$Old=Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if($Old -and [string]$Old.State -eq 'Running'){throw 'QA_HARNESS_RUNNING'}
$Child=Join-Path $Box 'native-normal-start-child.ps1'
$Body=@'
$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Output=Join-Path $Box 'native-normal-start.txt'
[IO.File]::WriteAllText($Output,'QA_USERNAME='+[string]$env:USERNAME+"`n")
$Agent=Join-Path $env:LOCALAPPDATA 'HARA Commander\hara-commander-agent.ps1'
. (Join-Path $Box 'windows_clean_console_api.ps1')
$Exe=(Get-Command powershell.exe).Source
$Child=[CleanConsoleInput]::Launch('"'+$Exe+'" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "'+$Agent+'" start')
try{
 Start-Sleep -Seconds 4
 [IO.File]::AppendAllText($Output,'CLI_PID='+[string]$Child+"`n")
 [IO.File]::AppendAllText($Output,'CLI_EXIT_CODE='+[string][CleanConsoleInput]::ExitCode($Child)+"`n")
 $Session=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander\operator-session.json') -Raw|ConvertFrom-Json
 $Owner=Get-Process -Id ([int]$Session.owner_pid)
 $Match=[int]$Session.owner_pid -eq $Child -and $Owner.StartTime.ToUniversalTime().ToString('o') -ceq [string]$Session.owner_started_at_utc
 [IO.File]::AppendAllText($Output,'ACTUAL_OPERATOR_PID='+[string]$Session.owner_pid+"`nOPERATOR_STARTED_UTC="+[string]$Session.owner_started_at_utc+"`nNORMAL_START_OWNER_MATCH="+[string]$Match+"`n")
 & $Exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Agent status 2>$null|ForEach-Object{if($_ -cmatch '^(HARA_COMMANDER_SESSION|SESSION_STARTED_AT_UTC|SECRET_MATERIAL_EXPOSED)='){[IO.File]::AppendAllText($Output,[string]$_+"`n")}}
}finally{[CleanConsoleInput]::Release($Child)}
'@
[IO.File]::WriteAllText($Child,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Child+'"')
$Qa=Get-LocalUser -Name HARAQA
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 60)
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings $Settings -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{state='NORMAL_SIGNED_AGENT_START_LAUNCHED_IN_QA_CONSOLE';agent_source_modified=$false}|ConvertTo-Json -Compress
