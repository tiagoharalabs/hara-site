# Resume only the existing signed48 Task behind an exact existing operator.
[CmdletBinding()]
param([ValidateSet('Inspect','Resume')][string]$Action='Inspect')
$ErrorActionPreference='Stop'
$d=Join-Path $env:LOCALAPPDATA 'HARA Commander';$a=Join-Path $d 'hara-commander-agent.ps1';$c=Join-Path $d 'device.json';$m=Join-Path $d 'operator-session.json'
$taskName='HARA Commander Agent';$ownerPid=8184;$ownerStart='2026-10-12T17:23:02.2031480Z';$markerSha=''
function Get-ResumeFileSha([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Get-ResumeTextSha([string]$s){$h=[Security.Cryptography.SHA256]::Create();try{([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($s)))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function Guard-Resume([string]$State,[bool]$NoIpc){
 $wi=[Security.Principal.WindowsIdentity]::GetCurrent();if($wi.IsSystem){throw 'RESUME_INTERACTIVE_USER_REQUIRED'}
 if((Get-ResumeFileSha $a) -cne  'f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805' -or (Get-ResumeFileSha $c) -cne  'e8810f67c0ccaa8780a401f767e5ff99660def8d8815b7288c7a9e4d156bc7f8'){throw 'RESUME_SOURCE_OR_CONFIG_CHANGED'}
 $t=Get-ScheduledTask -TaskName $taskName
 if([string]$t.State -cne  $State -or (Get-ResumeTextSha ([string](Export-ScheduledTask -TaskName $taskName))) -cne  '9bcc1704ecbb8afb3ce5edd4cb1f7a21ed4d470fc91870ff354d9da24d5dfa08'){throw 'RESUME_TASK_CHANGED'}
 $sid=[string]$t.Principal.UserId;if($sid -notmatch  '^S-1-'){$sid=(New-Object Security.Principal.NTAccount($sid)).Translate([Security.Principal.SecurityIdentifier]).Value}
 if($sid -cne  $wi.User.Value -or [string]$t.Principal.LogonType -cne  'Interactive' -or [string]$t.Principal.RunLevel -cne  'Limited'){throw 'RESUME_PRINCIPAL_CHANGED'}
 $cfg=Get-Content -LiteralPath $c -Raw|ConvertFrom-Json;$mode=if($cfg.approval_mode){[string]$cfg.approval_mode}else{'ASK_EVERY_ACTION'};if($mode -cne  'ASK_EVERY_ACTION'){throw 'RESUME_POLICY_CHANGED'}
 $s=Get-Content -LiteralPath $m -Raw|ConvertFrom-Json;$p=Get-Process -Id $ownerPid
 if([int]$s.owner_pid -ne  $ownerPid -or [string]$s.owner_started_at_utc -cne  $ownerStart -or $p.StartTime -isnot [DateTime] -or $p.StartTime.ToUniversalTime().ToString('o') -cne  $ownerStart -or $p.SessionId -ne  [Diagnostics.Process]::GetCurrentProcess().SessionId){throw 'RESUME_OWNER_CHANGED'}
 $ci=Get-CimInstance Win32_Process -Filter ('ProcessId='+$ownerPid);$ow=Invoke-CimMethod -InputObject $ci -MethodName GetOwnerSid
 if($ow.ReturnValue -ne  0 -or [string]$ow.Sid -cne  $wi.User.Value -or [string]$ci.Name -ine 'powershell.exe' -or ([string]$ci.CommandLine).IndexOf($a,[StringComparison]::OrdinalIgnoreCase) -lt  0){throw 'RESUME_OWNER_IDENTITY_CHANGED'}
 if($markerSha -and (Get-ResumeFileSha $m) -cne  $markerSha){throw 'RESUME_MARKER_BYTES_CHANGED'}
 if($NoIpc -and ((Test-Path -LiteralPath (Join-Path $d 'pending-action-approval.json')) -or (Test-Path -LiteralPath (Join-Path $d 'action-approval-response.json')))){throw 'RESUME_LOCAL_IPC_PRESENT'}
}
function Get-ResumeConsumers {
 @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'"|Where-Object {[int]$_.ProcessId -ne  $ownerPid -and $_.CommandLine -and ([string]$_.CommandLine).IndexOf($a,[StringComparison]::OrdinalIgnoreCase) -ge  0})
}
$r=[ordered]@{schema='hara.commander-win48-existing-task-resume.v1';state='HOLD';action=$Action;agent_task_started=$false;operator_preserved=$false;config_xml_policy_preserved=$false;new_mcp_call_generated=$false;approval_generated=$false;pending_call_replayed_by_helper=$false;consumer_pid=0;consumer_started_at_utc='';historical_sessions_zero_only=$true;historical_sessions_receipt='84c0feeaffdfa757fc26e64f9548a851233a005fc9d9f5ea51157f8d01a0364b'}
try{
 Guard-Resume 'Ready' $true;$markerSha=Get-ResumeFileSha $m
 if(@(Get-ResumeConsumers).Count -ne  0){throw 'RESUME_UNEXPECTED_CONSUMER_PRESENT'}
 foreach($line in @(Get-Content -LiteralPath (Join-Path $d 'console-events.jsonl') -Tail 100)){
  try{$e=$line|ConvertFrom-Json;$at=[DateTime]::Parse([string]$e.at_utc).ToUniversalTime()}catch{throw 'RESUME_EVENT_LOG_MALFORMED'}
  if([string]$e.schema -cne 'hara.commander-console-event.v1' -or -not $e.event){throw 'RESUME_EVENT_LOG_MALFORMED'}
  if($at -ge [DateTime]::Parse('2026-10-12T17:24:00Z').ToUniversalTime() -and [string]$e.event -ceq 'RECEIVED' -and [string]$e.tool_id -notin @('hara.device.info','hara.process.sessions','hara.ping','hara.health')){throw 'RESUME_UNEXPECTED_MUTANTE_RECEIVED'}
 }
 Guard-Resume 'Ready' $true
 if($Action -ceq  'Resume'){
  Start-ScheduledTask -TaskName $taskName;$r.agent_task_started=$true
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.ElapsedMilliseconds -lt  8000){if([string](Get-ScheduledTask -TaskName $taskName).State -ceq  'Running' -and @(Get-ResumeConsumers).Count -eq  1){break};Start-Sleep -Milliseconds 100}
  Guard-Resume 'Running' $false;$rows=@(Get-ResumeConsumers);if($rows.Count -ne  1){throw 'RESUME_CONSUMER_COUNT_NOT_ONE'}
  $row=$rows[0];$p=Get-Process -Id $row.ProcessId;$ow=Invoke-CimMethod -InputObject $row -MethodName GetOwnerSid
  if($p.StartTime -isnot [DateTime] -or $ow.ReturnValue -ne  0 -or [string]$ow.Sid -cne  [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -or $p.SessionId -ne  [Diagnostics.Process]::GetCurrentProcess().SessionId){throw 'RESUME_CONSUMER_IDENTITY_CHANGED'}
  $r.consumer_pid=$p.Id;$r.consumer_started_at_utc=$p.StartTime.ToUniversalTime().ToString('o')
 }
 $r.operator_preserved=$true;$r.config_xml_policy_preserved=$true;$r.state='PASS'
}catch{$code=[string]$_.Exception.Message;$r.reason=if($code -match  '^RESUME_[A-Z_]+$'){$code}else{'RESUME_RUNTIME_ERROR'}}
$r|ConvertTo-Json -Compress

