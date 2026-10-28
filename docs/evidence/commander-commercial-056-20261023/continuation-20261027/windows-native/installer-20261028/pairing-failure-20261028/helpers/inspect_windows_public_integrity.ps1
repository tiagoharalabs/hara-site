$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$folder=Join-Path $results 'public-integrity-20261028'
$taskName='HARA-QA056-Public-Integrity-20261028'
if(Test-Path -LiteralPath $folder){throw 'DIAGNOSTIC_ALREADY_EXISTS'}
if(Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue){throw 'DIAGNOSTIC_TASK_EXISTS'}
New-Item -ItemType Directory -Path $folder|Out-Null;Exact-Acl $folder $true 'FullControl'
$global=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
$before=[ordered]@{at_utc=[DateTime]::UtcNow.ToString('o');console_user=$console;product_task_present=[bool]$global;product_task_state=[string]$global.State;product_task_user=[string]$global.Principal.UserId}
[IO.File]::WriteAllText((Join-Path $folder 'system-before.json'),($before|ConvertTo-Json),[Text.Encoding]::UTF8)
$probe=@'
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028\results\public-integrity-20261028'
$r=[ordered]@{at_utc=[DateTime]::UtcNow.ToString('o');state='HOLD';read_only_product=$true;enrollment_attempted=$false}
try{
 $id=[Security.Principal.WindowsIdentity]::GetCurrent();$r.user=$id.Name;$r.sid=$id.User.Value
 if($r.sid -cne 'S-1-5-21-1207901905-1500652706-889822281-1005'){throw 'WRONG_QA_USER'}
 $product=Join-Path $env:LOCALAPPDATA 'HARA Commander'
 $r.product_directory_present=Test-Path -LiteralPath $product -ErrorAction Stop
 $r.product_config_present=Test-Path -LiteralPath (Join-Path $product 'device.json') -ErrorAction Stop
 $r.product_agent_present=Test-Path -LiteralPath (Join-Path $product 'hara-commander-agent.ps1') -ErrorAction Stop
 $r.current_user_policy=[string](Get-ExecutionPolicy -Scope CurrentUser)
 $checks=@()
 foreach($row in @(@('manifest.json','/release/agent-manifest.json'),@('manifest.sig.json','/release/agent-manifest.sig.json'),@('agent.ps1','/agent/windows.ps1'),@('installer.ps1','/install/windows.ps1'))){
  $p=Join-Path $root $row[0];$e=[ordered]@{name=$row[0];path=$row[1]}
  try{
   $resp=Invoke-WebRequest -Uri ('https://commander.haralabs.com.br'+$row[1]) -OutFile $p -PassThru -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0
   $e.status=[int]$resp.StatusCode;$e.bytes=(Get-Item -LiteralPath $p).Length;$e.sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant();$e.etag=[string]$resp.Headers['ETag'];$e.cache=[string]$resp.Headers['CF-Cache-Status']
  }catch{$e.error_type=$_.Exception.GetType().FullName}
  $checks+=,$e
 }
 $r.downloads=$checks
 $manifest=Get-Content -Raw -LiteralPath (Join-Path $root 'manifest.json')|ConvertFrom-Json
 $expected=@($manifest.files|Where-Object path -eq 'agent/windows.ps1')[0]
 $agent=@($checks|Where-Object name -eq 'agent.ps1')[0]
 $ver=Select-String -LiteralPath (Join-Path $root 'agent.ps1') -Pattern '^\$AgentVersion = "([^"]+)"$'|Select-Object -First 1
 $r.manifest_version=[string]$manifest.agent_version;$r.agent_version=[string]$ver.Matches[0].Groups[1].Value;$r.expected_bytes=[long]$expected.bytes;$r.expected_sha256=[string]$expected.sha256
 $r.agent_integrity_matches=($agent.sha256 -ceq [string]$expected.sha256 -and [long]$agent.bytes -eq [long]$expected.bytes)
 $r.state=if($r.agent_integrity_matches){'PUBLIC_PAYLOAD_BYTES_MATCH'}else{'PUBLIC_AGENT_MANIFEST_MISMATCH_CONFIRMED'}
}catch{$r.error_type=$_.Exception.GetType().FullName}
$r.finished_utc=[DateTime]::UtcNow.ToString('o')
[IO.File]::WriteAllText((Join-Path $root 'result.json'),($r|ConvertTo-Json -Depth 7),[Text.Encoding]::UTF8)
if($r.state -eq 'HOLD'){exit 2}else{exit 0}
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($probe))
$a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -EncodedCommand '+$encoded)
$p=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $taskName
[ordered]@{state='PUBLIC_INTEGRITY_PROBE_STARTED';before=$before;task=$taskName;result_file=(Join-Path $folder 'result.json')}|ConvertTo-Json -Depth 5 -Compress
