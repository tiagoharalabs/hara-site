$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-18'){throw 'SYSTEM_REQUIRED'}
$sid='S-1-5-21-1207901905-1500652706-889822281-1005'
if((Get-LocalUser CommanderQA).SID.Value -cne $sid -or (Get-CimInstance Win32_ComputerSystem).UserName -ine 'HARA_WIN11\CommanderQA'){throw 'COMMANDERQA_SESSION_REQUIRED'}
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028'
$desktop='C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA'
$pre=Get-Content -Raw (Join-Path $root 'results\preflight-r6-current-result.json')|ConvertFrom-Json
if($pre.state -cne 'PASS_NATIVE_PREFLIGHT' -or -not $pre.wrapper.agent_payload_verified -or [DateTimeOffset]::Parse($pre.finished_utc) -lt [DateTimeOffset]::UtcNow.AddMinutes(-20)){throw 'FRESH_NATIVE_PREFLIGHT_REQUIRED'}
$pins=@{'Instalar-Commander.cmd'='6a4088282c6da3dc0cfd8da2704fbca1e03f52f14ed1baf6ab4e594fe962e6ad';'Instalar-ou-verificar-Commander.ps1'='c0b384d05c7fa45b636bf73a18dd2f4f8e55e001578783162de632c4fab818a1';'instalar-commander-0.3.56.ps1'='2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401'}
foreach($name in $pins.Keys){if((Get-FileHash (Join-Path $desktop $name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pins[$name]){throw 'LAUNCH_SOURCE_PIN_CHANGED'}}
if((Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue) -or (Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json')){throw 'QA_INSTALLATION_ALREADY_EXISTS'}
$active=@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -like '*Instalar-ou-verificar-Commander.ps1*' -or $_.CommandLine -like '*instalar-commander-0.3.56.ps1*'})
if($active.Count){throw 'ANOTHER_INSTALLER_ACTIVE'}
$task='HARA-QA056-Interactive-Install-R6-20261028'
if(Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue){throw 'INTERACTIVE_TASK_ALREADY_EXISTS'}
$cfg=Get-Content -Raw (Join-Path $root 'config\install-config.json')|ConvertFrom-Json
if([DateTimeOffset]::Parse($cfg.qa_administrative_trust_until_utc) -lt [DateTimeOffset]::UtcNow.AddMinutes(10)){throw 'RELEASE_WINDOW_TOO_SHORT'}
$user=@'
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028'
$out=Join-Path $root 'results\interactive-r6-supervisor.json'
$r=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');state='STARTING'};$child=$null
function Stop-InstallerTree([Diagnostics.Process]$Process){
 if($Process.HasExited){$r.parent_exit_verified=$true;return}
 & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F|Out-Null
 $r.kill_exit_code=$LASTEXITCODE
 $r.parent_exit_verified=$Process.WaitForExit(5000)
 $r.descendant_exit_independently_verified=$false
 if(-not $r.parent_exit_verified -or $r.kill_exit_code -ne 0){throw 'INTERACTIVE_TREE_STOP_FAILED'}
}
try{
 if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-21-1207901905-1500652706-889822281-1005' -or (Get-Process -Id $PID).SessionId -le 0){throw 'WRONG_QA_CONTEXT'}
 $cfg=Get-Content -Raw (Join-Path $root 'config\install-config.json')|ConvertFrom-Json
 $deadline=[DateTimeOffset]::Parse($cfg.qa_administrative_trust_until_utc)
 $seconds=[int][Math]::Min(5400,[Math]::Floor(($deadline-[DateTimeOffset]::UtcNow).TotalSeconds)-120)
 if($seconds -lt 60){throw 'RELEASE_WINDOW_TOO_SHORT'}
 $r.window_until_utc=[DateTime]::UtcNow.AddSeconds($seconds).ToString('o')
 $child=Start-Process -FilePath $env:ComSpec -ArgumentList '/d /c call "C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA\Instalar-Commander.cmd"' -WindowStyle Normal -PassThru
 $r.child_pid=$child.Id;$r.state='INSTALLER_RUNNING'
 [IO.File]::WriteAllText($out,($r|ConvertTo-Json),[Text.Encoding]::UTF8)
 if($child.WaitForExit($seconds*1000)){$r.state='INSTALLER_EXITED';$r.child_exit_code=$child.ExitCode}
 else{Stop-InstallerTree $child;$r.state='INTERACTIVE_PARENT_EXIT_VERIFIED';$r.timeout=$true}
}catch{$r.state='HOLD';$r.error_code=if([string]$_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){[string]$_.Exception.Message}else{'INTERACTIVE_LAUNCH_FAILED'}}
finally{
 if($child){try{if(-not $child.HasExited){Stop-InstallerTree $child}}catch{$r.state='HOLD';$r.error_code='INTERACTIVE_TREE_STOP_FAILED'}finally{$child.Dispose()}}
 $r.finished_utc=[DateTime]::UtcNow.ToString('o');[IO.File]::WriteAllText($out,($r|ConvertTo-Json),[Text.Encoding]::UTF8)
}
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($user))
$a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+$encoded)
$p=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 95) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $task -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $task
@{state='SUPERVISED_INSTALLER_STARTED';task=$task;identity='CommanderQA';maximum_window_seconds=5400;release_cleanup_deadline_utc=$cfg.qa_administrative_trust_until_utc}|ConvertTo-Json -Compress
