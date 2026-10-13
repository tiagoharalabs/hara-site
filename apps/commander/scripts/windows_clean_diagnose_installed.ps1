$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba' -or $Identity.Name -notmatch '\\HARAQA$'){throw 'REAL_QA_CLONE_REQUIRED'}
$Dev='https://hara-commander-dev-v2.tiago-sartori.workers.dev'
$InstalledRoot=Join-Path $env:LOCALAPPDATA 'HARA Commander'
$Agent=Join-Path $InstalledRoot 'hara-commander-agent.ps1'
$Config=Join-Path $InstalledRoot 'device.json'
function Snapshot {
 $task=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
 $cfg=if(Test-Path -LiteralPath $Config){Get-Content -Raw -LiteralPath $Config|ConvertFrom-Json}else{$null}
 $dpapi=$false
 if($cfg){try{$secure=ConvertTo-SecureString ([string]$cfg.encrypted_device_token);$dpapi=$secure.Length -gt 0;$secure.Dispose()}catch{}}
 $runtime=Join-Path $InstalledRoot 'runtime-status.json'
 $status=if(Test-Path -LiteralPath $runtime){Get-Content -Raw -LiteralPath $runtime|ConvertFrom-Json}else{$null}
 $session=Join-Path $InstalledRoot 'operator-session.json'
 $local=if(Test-Path -LiteralPath $session){Get-Content -Raw -LiteralPath $session|ConvertFrom-Json}else{$null}
 $active=$false
 if($local -and $local.owner_pid){$p=Get-Process -Id ([int]$local.owner_pid) -ErrorAction SilentlyContinue;$active=[bool]($p -and $p.StartTime.ToUniversalTime().ToString('o') -eq [string]$local.owner_started_at_utc)}
 $principal=if($task){[string]$task.Principal.UserId}else{''}
 $principalQa=$principal -ceq $Identity.Name -or $principal -ceq ([string]$Identity.User) -or $principal -ceq 'HARAQA'
 $actionExpected=[bool]($task -and @($task.Actions).Count -eq 1 -and [string]$task.Actions[0].Execute -ceq (Get-Command powershell.exe).Source -and ([string]$task.Actions[0].Arguments).Contains($Agent))
 $taskDigest=$null
 if($task){$sha=[Security.Cryptography.SHA256]::Create();try{$taskDigest=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes((Export-ScheduledTask -TaskName $task.TaskName))))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
 [ordered]@{root_present=(Test-Path -LiteralPath $InstalledRoot);config_present=[bool]$cfg;config_sha256=if($cfg){(Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null};dev_origin_correct=[bool]($cfg -and $cfg.base_url -ceq $Dev);approval_mode=if($cfg){[string]$cfg.approval_mode}else{$null};qa_dpapi_token_readable=$dpapi;agent_present=(Test-Path -LiteralPath $Agent);agent_sha256=if(Test-Path -LiteralPath $Agent){(Get-FileHash -LiteralPath $Agent -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null};task_present=[bool]$task;task_state=if($task){[string]$task.State}else{$null};task_trigger_count=if($task -and $task.Triggers){@($task.Triggers).Count}else{0};task_principal=if($task){[string]$task.Principal.UserId}else{$null};task_principal_is_qa=$principalQa;task_action_matches_installed_qa_agent=$actionExpected;task_xml_sha256=$taskDigest;runtime_version=if($status){[string]$status.agent_version}else{$null};runtime_started_at_utc=if($status){[string]$status.started_at_utc}else{$null};local_operator_session_active=$active;local_operator_owner_pid=if($local){[int]$local.owner_pid}else{$null};local_operator_owner_started_at_utc=if($local){[string]$local.owner_started_at_utc}else{$null}}
}

$Report=[ordered]@{schema='hara.windows-clean-installed-diagnostic.v1';snapshot_state=$null;snapshot_error_id=$null;snapshot_error_type=$null;snapshot=$null;physical_agent_sha256=$null;task_state=$null;task_user=$null;task_actions_count=$null;task_triggers_count=$null;runtime_version=$null;markers=@();qa_identity=$Identity.Name;secrets_printed=$false}
try{$Report.snapshot=Snapshot;$Report.snapshot_state='PASS'}catch{
 $Report.snapshot_state='FAIL';$Report.snapshot_error_id=[string]$_.FullyQualifiedErrorId;$Report.snapshot_error_type=$_.Exception.GetType().FullName
 [IO.File]::WriteAllText((Join-Path $Box 'snapshot-error.private.txt'),([string]$_.Exception.Message+"\n"+[string]$_.ScriptStackTrace),(New-Object Text.UTF8Encoding($false)))
}
try{$Report.physical_agent_sha256=(Get-FileHash -LiteralPath $Agent).Hash.ToLowerInvariant()}catch{}
$t=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
if($t){$Report.task_state=[string]$t.State;$Report.task_user=[string]$t.Principal.UserId;$Report.task_actions_count=@($t.Actions).Count;$Report.task_triggers_count=if($t.Triggers){@($t.Triggers).Count}else{0}}
if(Test-Path (Join-Path $InstalledRoot 'runtime-status.json')){try{$Report.runtime_version=[string](Get-Content -LiteralPath (Join-Path $InstalledRoot 'runtime-status.json') -Raw|ConvertFrom-Json).agent_version}catch{}}
$Log=Join-Path $Box 'phase-install.private.log'
if(Test-Path $Log){$Report.markers=@(Get-Content -LiteralPath $Log|Where-Object{$_ -cmatch '^(HARA_COMMANDER_[A-Z_]+|SERVER_DEVICE_REVOKE|DEVICE_TOKEN_EXPOSED)=[A-Z_0-9]+$'})}
[IO.File]::WriteAllText((Join-Path $Box 'installed-diagnostic.json'),($Report|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
