# Guarded private Windows 0.3.46 -> frozen signed 0.3.47 canary.
# Inspect is default. Apply is reserved for the authorized laboratory cutover.
[CmdletBinding()]
param([ValidateSet('Inspect','Apply')][string]$Action='Inspect',
      [string]$BundleRoot='C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-047-rc-r2',
      [ValidateRange(2,2147483647)][int]$ExpectedOperatorPid=3332,
      [string]$ExpectedOperatorStart='2026-10-12T04:50:29.9435744Z',
      [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedConfigSha='e8810f67c0ccaa8780a401f767e5ff99660def8d8815b7288c7a9e4d156bc7f8',
      [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedTaskSha='9bcc1704ecbb8afb3ce5edd4cb1f7a21ed4d470fc91870ff354d9da24d5dfa08')
$ErrorActionPreference='Stop'
. (Join-Path $BundleRoot 'windows_047_private_rc_validate.ps1') -FunctionsOnly -BundleRoot $BundleRoot
$OldSha='71998b7c5e2dae4f4cbcfe80e5413ab1c6ff8e28ad903734cc1f026dfe8765aa'
$NewSha='254517c46acf47102ebed5fe31fcb5d880ca0de47b98debeebdcaf4b1b324e36'
$Dir=Join-Path $env:LOCALAPPDATA 'HARA Commander'
$Target=Join-Path $Dir 'hara-commander-agent.ps1'
$Cfg=Join-Path $Dir 'device.json'
$Session=Join-Path $Dir 'operator-session.json'
$Pending=Join-Path $Dir 'pending-action-approval.json'
$Reply=Join-Path $Dir 'action-approval-response.json'
$ProtectedDir=Join-Path $Dir 'canary-backups\signed-v47-rc-20261012-r2'
$Backup=Join-Path $ProtectedDir 'hara-commander-agent.ps1.pre-v47-rc-20261012.ps1'
$CfgBackup=Join-Path $ProtectedDir 'device.pre-v47-rc-20261012.json'
$TaskBackup=Join-Path $ProtectedDir 'task.pre-v47-rc-20261012.xml'
$Temp=Join-Path $Dir 'hara-commander-agent.ps1.new-v47-rc-20261012-r2.ps1'
$Atomic=Join-Path $ProtectedDir 'hara-commander-agent.ps1.atomic-pre-v47-rc-20261012.ps1'
$RollbackTemp=Join-Path $Dir 'hara-commander-agent.ps1.rollback-v47-20261012-r2.ps1'
$Wrapper47=Join-Path $BundleRoot 'operator-console-0347.ps1'
$TaskName='HARA Commander Agent'
function Get-CanaryFileSha([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()}
function Need-NoPending {
 if((Test-Path -LiteralPath $Pending) -or (Test-Path -LiteralPath $Reply)){throw 'CANARY_LOCAL_APPROVAL_IN_PROGRESS'}
}
function Get-ExactOperator {
 if(-not(Test-Path -LiteralPath $Session -PathType Leaf)){throw 'CANARY_OPERATOR_SESSION_REQUIRED'}
 $s=Get-Content -LiteralPath $Session -Raw|ConvertFrom-Json
 if([string]$s.schema -cne 'hara.commander-operator-session.v1' -or [int]$s.owner_pid -le 1){throw 'CANARY_OPERATOR_SESSION_INVALID'}
 $p=Get-Process -Id ([int]$s.owner_pid) -ErrorAction Stop
 if($p.StartTime.ToUniversalTime().ToString('o') -cne [string]$s.owner_started_at_utc){throw 'CANARY_OPERATOR_PID_REUSED'}
 if($p.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId){throw 'CANARY_OPERATOR_NOT_CURRENT_INTERACTIVE_SESSION'}
 $c=Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.Id) -ErrorAction Stop
 if([string]$c.Name -ine 'powershell.exe' -or -not([string]$c.CommandLine -match 'operator-visible-wrapper\.ps1|operator-console-03(?:46|47)\.ps1|hara-commander-agent\.ps1.+\bstart\b')){throw 'CANARY_OPERATOR_COMMAND_UNEXPECTED'}
 return [pscustomobject]@{pid=$p.Id;started=[string]$s.owner_started_at_utc}
}
function Assert-ExpectedOldOperator {
 $op=Get-ExactOperator
 if($op.pid -ne $ExpectedOperatorPid -or $op.started -cne $ExpectedOperatorStart){throw 'CANARY_EXPECTED_OLD_OPERATOR_CHANGED'}
 return $op
}
function Get-AgentTargetProcesses {
 @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction Stop|Where-Object {
  $_.CommandLine -and (([string]$_.CommandLine).IndexOf($Target,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or [string]$_.CommandLine -match 'operator-visible-wrapper\.ps1|operator-console-03(?:46|47)\.ps1')
 })
}
function Assert-NoAgentConsumersExcept($Expected) {
 $now=Get-ExactOperator
 if($now.pid -ne $Expected.pid -or $now.started -cne $Expected.started){throw 'CANARY_OPERATOR_CHANGED'}
 $other=@(Get-AgentTargetProcesses|Where-Object {[int]$_.ProcessId -ne $Expected.pid})
 if($other.Count -ne 0){throw 'CANARY_AGENT_CONSUMER_PRESENT'}
}
# Metadata is read-only and contains no raw command line, path or SID.
function Get-SanitizedProcessMetadata($Processes){
 $currentSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
 foreach($row in @($Processes)){
  $command=[string]$row.CommandLine
  $meta=[ordered]@{
   pid=[int]$row.ProcessId;started_at_utc='';session_id=[int]$row.SessionId
   user_sid_matches_current=$false;user_sid_check_complete=$false
   commandline_sha256=(Get-Win47TextSha $command);metadata_complete=$false;read_only_error_code=''
   guarded_old_owner=$false
   installed_agent_path_referenced=($command.IndexOf($Target,[StringComparison]::OrdinalIgnoreCase) -ge 0)
   visible_wrapper_referenced=($command -match 'operator-visible-wrapper\.ps1')
   wrapper_0346_referenced=($command -match 'operator-console-0346\.ps1')
   wrapper_0347_referenced=($command -match 'operator-console-0347\.ps1')
   agent_start_referenced=($command -match 'hara-commander-agent\.ps1.+\bstart\b')
   encoded_command_present=($command -match '(?i)(?:^|\s)-(?:EncodedCommand|enc)(?:\s|$)')
  }
  try{
   # Recheck the same CIM creation time before associating a live PID with its metadata.
   $fresh=Get-CimInstance Win32_Process -Filter ('ProcessId='+[int]$row.ProcessId) -ErrorAction Stop
   if(-not $fresh -or $fresh.CreationDate -ne $row.CreationDate){throw 'CANARY_METADATA_PROCESS_CHANGED'}
   $process=Get-Process -Id ([int]$row.ProcessId) -ErrorAction Stop
   $meta.started_at_utc=$process.StartTime.ToUniversalTime().ToString('o')
   $meta.session_id=$process.SessionId
   $meta.guarded_old_owner=([int]$row.ProcessId -eq $ExpectedOperatorPid -and $meta.started_at_utc -ceq $ExpectedOperatorStart)
   $owner=Invoke-CimMethod -InputObject $fresh -MethodName GetOwnerSid -ErrorAction Stop
   if([int]$owner.ReturnValue -ne 0){throw 'CANARY_METADATA_OWNER_UNAVAILABLE'}
   $meta.user_sid_matches_current=([string]$owner.Sid -ceq $currentSid)
   $meta.user_sid_check_complete=$true
   $again=Get-CimInstance Win32_Process -Filter ('ProcessId='+[int]$row.ProcessId) -ErrorAction Stop
   if(-not $again -or $again.CreationDate -ne $row.CreationDate){throw 'CANARY_METADATA_PROCESS_CHANGED'}
   $meta.metadata_complete=$true
  }catch{
   $code=[string]$_.Exception.Message
   $meta.read_only_error_code=if($code -match '^CANARY_METADATA_[A-Z_]+$'){$code}else{'CANARY_METADATA_READ_FAILED'}
   if(-not $meta.started_at_utc -and $row.CreationDate){
    try{$meta.started_at_utc=([DateTime]$row.CreationDate).ToUniversalTime().ToString('o')}catch{}
   }
  }
  [pscustomobject]$meta
 }
}
function Get-SanitizedAgentProcessSnapshot {
 try{
  $rows=@(Get-AgentTargetProcesses)
  @(Get-SanitizedProcessMetadata $rows)
 }catch{throw 'CANARY_PROCESS_SNAPSHOT_READ_FAILED'}
}
function Wait-NoAgentConsumersExcept($Expected){
 # No extra process is stopped or ignored. The only exemption is the exact old owner.
 $clock=[Diagnostics.Stopwatch]::StartNew()
 try{
  while($true){
   if($clock.ElapsedMilliseconds -ge 5000){$report.consumer_wait_expired=$true;throw 'CANARY_AGENT_CONSUMER_PRESENT'}
   Need-NoPending
   Assert-ConfigAndTask 'Ready'
   $now=Assert-ExpectedOldOperator
   if($now.pid -ne $Expected.pid -or $now.started -cne $Expected.started){throw 'CANARY_OPERATOR_CHANGED'}
   $rows=@(Get-AgentTargetProcesses)
   $report.after_stop_processes=@(Get-SanitizedProcessMetadata $rows)
   $report.consumer_wait_observations++
   $other=@($rows|Where-Object {[int]$_.ProcessId -ne $Expected.pid})
   if($clock.ElapsedMilliseconds -ge 5000){$report.consumer_wait_expired=$true;throw 'CANARY_AGENT_CONSUMER_PRESENT'}
   if($other.Count -eq 0){$report.consumer_wait_zero_verified=$true;return}
   $remaining=5000-$clock.ElapsedMilliseconds
   if($remaining -le 0){$report.consumer_wait_expired=$true;throw 'CANARY_AGENT_CONSUMER_PRESENT'}
   Start-Sleep -Milliseconds ([int][Math]::Min(100,$remaining))
  }
 }finally{$clock.Stop();$report.consumer_wait_elapsed_ms=$clock.ElapsedMilliseconds}
}
function Assert-ZeroAgentTargetProcesses {
 if(@(Get-AgentTargetProcesses).Count -ne 0){throw 'CANARY_AGENT_TARGET_PROCESS_PRESENT'}
}
function Close-ExactOperator($Expected) {
 Need-NoPending
 $now=Get-ExactOperator
 if($now.pid -ne $Expected.pid -or $now.started -cne $Expected.started){throw 'CANARY_OPERATOR_CHANGED'}
 $p=Get-Process -Id $Expected.pid -ErrorAction Stop
 if($p.MainWindowHandle -ne [IntPtr]::Zero){$null=$p.CloseMainWindow();$null=$p.WaitForExit(2500)}
 $alive=Get-Process -Id $Expected.pid -ErrorAction SilentlyContinue
 if($alive){
  if($alive.StartTime.ToUniversalTime().ToString('o') -cne $Expected.started){throw 'CANARY_OPERATOR_PID_REUSED'}
  Need-NoPending
  Stop-Process -Id $Expected.pid -Force -ErrorAction Stop
 }
 for($i=0;$i -lt 30;$i++){if(-not(Get-Process -Id $Expected.pid -ErrorAction SilentlyContinue)){break};Start-Sleep -Milliseconds 100}
 if(Get-Process -Id $Expected.pid -ErrorAction SilentlyContinue){throw 'CANARY_OPERATOR_DID_NOT_CLOSE'}
 if(Test-Path -LiteralPath $Session){
  $current=Get-Content -LiteralPath $Session -Raw|ConvertFrom-Json
  if([int]$current.owner_pid -ne $Expected.pid -or [string]$current.owner_started_at_utc -cne $Expected.started){throw 'CANARY_SESSION_REPLACED_AFTER_CLOSE'}
  Need-NoPending
  Remove-Item -LiteralPath $Session -Force -ErrorAction Stop
 }
}
function Wait-TaskState([string]$Wanted){
 for($i=0;$i -lt 50;$i++){
  if([string](Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop).State -ceq $Wanted){return}
  Start-Sleep -Milliseconds 200
 }
 throw 'CANARY_TASK_STATE_TIMEOUT'
}
function Assert-CanaryTask([string]$Wanted){
 $wi=[Security.Principal.WindowsIdentity]::GetCurrent()
 if($wi.IsSystem){throw 'CANARY_INTERACTIVE_USER_REQUIRED'}
 $task=Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
 if([string]$task.State -cne $Wanted){throw 'CANARY_TASK_STATE_CHANGED'}
 $taskSid=[string]$task.Principal.UserId
 if($taskSid -notmatch '^S-1-'){try{$taskSid=(New-Object Security.Principal.NTAccount($taskSid)).Translate([Security.Principal.SecurityIdentifier]).Value}catch{throw 'CANARY_TASK_OWNER_UNRESOLVED'}}
 if($wi.User.Value -cne $taskSid -or [string]$task.Principal.LogonType -cne 'Interactive' -or [string]$task.Principal.RunLevel -cne 'Limited'){throw 'CANARY_TASK_PRINCIPAL_CHANGED'}
 return $wi.User.Value
}
function Assert-ConfigAndTask([string]$Wanted){
 $null=Assert-CanaryTask $Wanted
 if((Get-CanaryFileSha $Cfg) -cne $cfgSha){throw 'CANARY_CONFIG_CHANGED'}
 $cfgValue=Get-Content -LiteralPath $Cfg -Raw|ConvertFrom-Json
 $mode=if($cfgValue.approval_mode){[string]$cfgValue.approval_mode}else{'ASK_EVERY_ACTION'}
 if($mode -cne 'ASK_EVERY_ACTION'){throw 'CANARY_APPROVAL_MODE_NOT_ASK'}
 if((Get-Win47TextSha ([string](Export-ScheduledTask -TaskName $TaskName -ErrorAction Stop))) -cne $taskSha){throw 'CANARY_TASK_DEFINITION_CHANGED'}
}
function Assert-PrivatePreimageAcl([string]$Path,[string]$OwnerSid){
 $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
 if(-not $acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $OwnerSid -or @($acl.Access).Count -ne 2){throw 'CANARY_PREIMAGE_ACL_INVALID'}
 $seen=@()
 foreach($rule in $acl.Access){
  $sid=$rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
  if($sid -cne $OwnerSid -and $sid -cne 'S-1-5-18'){throw 'CANARY_PREIMAGE_ACL_INVALID'}
  if($rule.IsInherited -or $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl){throw 'CANARY_PREIMAGE_ACL_INVALID'}
  $seen+=$sid
 }
 if(@($seen|Select-Object -Unique).Count -ne 2){throw 'CANARY_PREIMAGE_ACL_INVALID'}
}
function Set-PrivatePreimageAcl([string]$Path,[string]$OwnerSid,[bool]$IsDirectory){
 $acl=if($IsDirectory){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
 $acl.SetAccessRuleProtection($true,$false)
 $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier($OwnerSid)))
 foreach($sid in @($OwnerSid,'S-1-5-18')){
  $id=New-Object Security.Principal.SecurityIdentifier($sid)
  $rule=if($IsDirectory){New-Object Security.AccessControl.FileSystemAccessRule($id,'FullControl','ContainerInherit,ObjectInherit','None','Allow')}else{New-Object Security.AccessControl.FileSystemAccessRule($id,'FullControl','Allow')}
  $acl.AddAccessRule($rule)
 }
 Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
 Assert-PrivatePreimageAcl $Path $OwnerSid
}
function Assert-Preimages {
 foreach($path in @($ProtectedDir,$Backup,$CfgBackup,$TaskBackup)){Assert-PrivatePreimageAcl $path $ownerSid}
 if((Get-CanaryFileSha $Backup) -cne $OldSha){throw 'CANARY_BACKUP_HASH_INVALID'}
 if((Get-CanaryFileSha $CfgBackup) -cne $cfgSha -or (Get-CanaryFileSha $TaskBackup) -cne $taskSha){throw 'CANARY_PRIVATE_PREIMAGE_HASH_INVALID'}
}
function New-OperatorWrapper([string]$Version,[string]$Hash){
 $path=Join-Path $BundleRoot ('operator-console-'+$Version.Replace('.','')+'.ps1')
 if(Test-Path -LiteralPath $path){throw 'CANARY_WRAPPER_COLLISION'}
 $body=@'
$ErrorActionPreference='Stop'
$agent=Join-Path $env:LOCALAPPDATA 'HARA Commander\hara-commander-agent.ps1'
if((Get-FileHash -LiteralPath $agent -Algorithm SHA256).Hash.ToLowerInvariant() -cne '@HASH@'){throw 'CANARY_WRAPPER_AGENT_HASH_INVALID'}
$Host.UI.RawUI.WindowTitle='H.A.R.A. Commander @VERSION@ - APROVACAO LOCAL'
& $agent start
'@
 $body=$body.Replace('@HASH@',$Hash).Replace('@VERSION@',$Version)
 [IO.File]::WriteAllText($path,$body,(New-Object Text.UTF8Encoding($false)))
 return $path
}
function Open-VerifiedOperator([string]$Wrapper,$Previous){
 Need-NoPending
 if(Test-Path -LiteralPath $Session){throw 'CANARY_NEW_OPERATOR_COLLISION'}
 $proc=Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoLogo -NoProfile -NoExit -ExecutionPolicy Bypass -File "'+$Wrapper+'"') -WindowStyle Normal -WorkingDirectory $env:USERPROFILE -PassThru -ErrorAction Stop
 $script:LaunchedOperator=[pscustomobject]@{pid=$proc.Id;started=$proc.StartTime.ToUniversalTime().ToString('o')}
 if($proc.Id -eq $Previous.pid -or $script:LaunchedOperator.started -ceq $Previous.started){throw 'CANARY_NEW_OPERATOR_NOT_FRESH'}
 for($i=0;$i -lt 60;$i++){
  Start-Sleep -Milliseconds 150
  if($proc.HasExited){throw 'CANARY_NEW_OPERATOR_EXITED'}
  if(Test-Path -LiteralPath $Session){
   $s=Get-Content -LiteralPath $Session -Raw|ConvertFrom-Json
   if([int]$s.owner_pid -eq $proc.Id -and [string]$s.owner_started_at_utc -ceq $script:LaunchedOperator.started){
    $exact=Get-ExactOperator
    $cmd=Get-CimInstance Win32_Process -Filter ('ProcessId='+$proc.Id) -ErrorAction Stop
    if($exact.pid -ne $proc.Id -or $exact.started -cne $script:LaunchedOperator.started -or ([string]$cmd.CommandLine).IndexOf($Wrapper,[StringComparison]::OrdinalIgnoreCase) -lt 0){throw 'CANARY_NEW_OPERATOR_WRAPPER_CHANGED'}
    return $exact
   }
  }
 }
 throw 'CANARY_NEW_OPERATOR_SESSION_TIMEOUT'
}
$changed=$false;$backupReady=$false;$newOperator=$null;$taskStopped=$false;$tempCreated=$false;$script:LaunchedOperator=$null
$report=[ordered]@{schema='hara.commander-win47-signed-user-canary.v1';state='FAIL';action=$Action;reason='PRECHECK';old_version='0.3.46';new_version='0.3.47';old_source_sha256=$OldSha;new_source_sha256=$NewSha;backup_sha_verified=$false;private_preimages_verified=$false;config_byte_identical=$false;task_definition_preserved=$false;task_principal_preserved=$false;task_state_restored=$false;old_operator_guard_matches=$false;old_operator_pid=$ExpectedOperatorPid;old_operator_started_at_utc=$ExpectedOperatorStart;zero_target_processes_before_replace=$false;operator_console_replaced=$false;new_operator_pid=0;new_operator_started_at_utc='';rollback_old_agent_verified=$false;approval_mode_unchanged=$true;real_human_positive_approval_proven=$false;any_action_autoapproved=$false;new_enrollment=$false;secrets_in_result=$false;before_stop_processes=@();after_stop_processes=@();hold_processes=@();hold_snapshot_read_ok=$false;hold_snapshot_read_error='';consumer_wait_budget_ms=5000;consumer_wait_elapsed_ms=0;consumer_wait_observations=0;consumer_wait_expired=$false;consumer_wait_zero_verified=$false}
try{
 $ownerSid=Assert-CanaryTask 'Running'
 $null=Assert-Win47FrozenBundle $BundleRoot
 if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'CANARY_EXPECTED_SIGNED_WIN46_NOT_INSTALLED'}
 if(-not(Test-Path -LiteralPath $Cfg -PathType Leaf)){throw 'CANARY_DEVICE_IDENTITY_MISSING'}
 if((Get-CanaryFileSha $Cfg) -cne $ExpectedConfigSha){throw 'CANARY_EXPECTED_CONFIG_CHANGED'}
 $cfgSha=$ExpectedConfigSha
 $taskXml=[string](Export-ScheduledTask -TaskName $TaskName -ErrorAction Stop)
 if((Get-Win47TextSha $taskXml) -cne $ExpectedTaskSha){throw 'CANARY_EXPECTED_TASK_CHANGED'}
 $taskSha=$ExpectedTaskSha
 Assert-ConfigAndTask 'Running'
 Need-NoPending
 $oldOperator=Assert-ExpectedOldOperator
 $report.old_operator_guard_matches=$true;$report.task_principal_preserved=$true
 $report.config_sha256=$cfgSha;$report.task_definition_sha256=$taskSha
 foreach($p in @($ProtectedDir,$Temp,$Atomic,$RollbackTemp,$Wrapper47)){if(Test-Path -LiteralPath $p){throw 'CANARY_BACKUP_OR_TEMP_COLLISION'}}
 if($Action -ceq 'Inspect'){
  $report.state='PASS';$report.reason='READY_TO_APPLY';$report.config_byte_identical=$true;$report.task_definition_preserved=$true;$report.task_state_restored=$true
 }else{
  # Full gate and root review must have completed before this explicit action.
  New-Item -ItemType Directory -Path $ProtectedDir -ErrorAction Stop|Out-Null
  Set-PrivatePreimageAcl $ProtectedDir $ownerSid $true
  Copy-Item -LiteralPath $Target -Destination $Backup -ErrorAction Stop
  Set-PrivatePreimageAcl $Backup $ownerSid $false
  Copy-Item -LiteralPath $Cfg -Destination $CfgBackup -ErrorAction Stop
  Set-PrivatePreimageAcl $CfgBackup $ownerSid $false
  [IO.File]::WriteAllText($TaskBackup,$taskXml,(New-Object Text.UTF8Encoding($false)))
  Set-PrivatePreimageAcl $TaskBackup $ownerSid $false
  Assert-Preimages
  $backupReady=$true;$report.backup_sha_verified=$true;$report.private_preimages_verified=$true
  $tempCreated=$true
  Copy-Item -LiteralPath (Join-Path $BundleRoot 'agent\windows.ps1') -Destination $Temp -ErrorAction Stop
  if((Get-CanaryFileSha $Temp) -cne $NewSha){throw 'CANARY_TEMP_AGENT_HASH_INVALID'}
  Need-NoPending
  Assert-ConfigAndTask 'Running'
  if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'CANARY_OLD_SOURCE_CHANGED_BEFORE_STOP'}
  $currentOld=Assert-ExpectedOldOperator
  if($currentOld.pid -ne $oldOperator.pid -or $currentOld.started -cne $oldOperator.started){throw 'CANARY_OPERATOR_CHANGED'}
  $report.before_stop_processes=@(Get-SanitizedAgentProcessSnapshot)
  $taskStopped=$true
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  Wait-TaskState 'Ready'
  Need-NoPending
  Assert-ConfigAndTask 'Ready'
  $null=Assert-ExpectedOldOperator
  Wait-NoAgentConsumersExcept $oldOperator
  Assert-NoAgentConsumersExcept $oldOperator
  Close-ExactOperator $oldOperator
  Need-NoPending
  Assert-ConfigAndTask 'Ready'
  Assert-Preimages
  if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'CANARY_OLD_SOURCE_CHANGED_BEFORE_REPLACE'}
  Assert-ZeroAgentTargetProcesses
  $report.zero_target_processes_before_replace=$true
  [IO.File]::Replace($Temp,$Target,$Atomic,$true)
  $changed=$true
  Set-PrivatePreimageAcl $Atomic $ownerSid $false
  if((Get-CanaryFileSha $Atomic) -cne $OldSha){throw 'CANARY_ATOMIC_PREIMAGE_HASH_INVALID'}
  if((Get-CanaryFileSha $Target) -cne $NewSha){throw 'CANARY_POSTINSTALL_HASH_INVALID'}
  Assert-ConfigAndTask 'Ready'
  $wrapper=New-OperatorWrapper '0.3.47' $NewSha
  Need-NoPending
  Assert-ZeroAgentTargetProcesses
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  Wait-TaskState 'Running';$taskStopped=$false
  $newOperator=Open-VerifiedOperator $wrapper $oldOperator
  Need-NoPending
  Assert-ConfigAndTask 'Running'
  if((Get-CanaryFileSha $Target) -cne $NewSha){throw 'CANARY_POSTINSTALL_HASH_INVALID'}
  $report.config_byte_identical=$true;$report.task_definition_preserved=$true;$report.task_state_restored=$true
  $report.operator_console_replaced=$true;$report.new_operator_pid=$newOperator.pid;$report.new_operator_started_at_utc=$newOperator.started
  $report.state='PASS';$report.reason='NONE'
 }
}catch{
 $code=[string]$_.Exception.Message
 $report.reason=if($code -match '^[A-Z][A-Z0-9_]{1,100}$'){$code}else{'CANARY_RUNTIME_FAILED'}
 # Capture diagnostic metadata on HOLD without allowing a read error to replace the guarded result.
 try{$report.hold_processes=@(Get-SanitizedAgentProcessSnapshot);$report.hold_snapshot_read_ok=$true}
 catch{$report.hold_snapshot_read_error='CANARY_HOLD_SNAPSHOT_READ_FAILED'}
 if($backupReady -and ($changed -or $taskStopped)){
  try{
   Need-NoPending
   if($newOperator){Close-ExactOperator $newOperator}
   elseif($script:LaunchedOperator){
    $tracked=$script:LaunchedOperator
    $child=Get-Process -Id $tracked.pid -ErrorAction SilentlyContinue
    if($child){
     if($child.StartTime.ToUniversalTime().ToString('o') -cne $tracked.started -or $child.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId){throw 'ROLLBACK_LAUNCHED_PID_REUSED'}
     Need-NoPending
     Stop-Process -Id $tracked.pid -Force -ErrorAction Stop
     $null=$child.WaitForExit(3000)
     if(Get-Process -Id $tracked.pid -ErrorAction SilentlyContinue){throw 'ROLLBACK_LAUNCHED_OPERATOR_DID_NOT_CLOSE'}
    }
    if(Test-Path -LiteralPath $Session){
     $marker=Get-Content -LiteralPath $Session -Raw|ConvertFrom-Json
     if([int]$marker.owner_pid -ne $tracked.pid -or [string]$marker.owner_started_at_utc -cne $tracked.started){throw 'ROLLBACK_OPERATOR_SESSION_REPLACED'}
     Need-NoPending;Remove-Item -LiteralPath $Session -Force -ErrorAction Stop
    }
   }
   if([string](Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop).State -ceq 'Running'){Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop}
   Wait-TaskState 'Ready'
   Need-NoPending
   Assert-ConfigAndTask 'Ready'
   Assert-Preimages
   $remainingOperator=$null
   if(Test-Path -LiteralPath $Session){$remainingOperator=Assert-ExpectedOldOperator}
   $rollbackTargetSha=Get-CanaryFileSha $Target
   if($rollbackTargetSha -cne $OldSha -and $rollbackTargetSha -cne $NewSha){throw 'ROLLBACK_TARGET_DRIFT_HOLD'}
   if($rollbackTargetSha -ceq $NewSha){
    if($remainingOperator){Close-ExactOperator $remainingOperator;$remainingOperator=$null}
    Assert-ZeroAgentTargetProcesses
    if(Test-Path -LiteralPath $RollbackTemp){throw 'ROLLBACK_TEMP_COLLISION'}
    Copy-Item -LiteralPath $Backup -Destination $RollbackTemp -ErrorAction Stop
    if((Get-CanaryFileSha $RollbackTemp) -cne $OldSha){throw 'ROLLBACK_TEMP_HASH_INVALID'}
    Need-NoPending
    Assert-ConfigAndTask 'Ready'
    Assert-ZeroAgentTargetProcesses
    if((Get-CanaryFileSha $Target) -cne $NewSha){throw 'ROLLBACK_TARGET_DRIFT_BEFORE_REPLACE'}
    [IO.File]::Replace($RollbackTemp,$Target,$null,$true)
   }elseif($remainingOperator){Assert-NoAgentConsumersExcept $remainingOperator}
   else{Assert-ZeroAgentTargetProcesses}
   $report.rollback_old_agent_verified=((Get-CanaryFileSha $Target) -ceq $OldSha)
   if(-not $report.rollback_old_agent_verified){throw 'ROLLBACK_RESTORED_SOURCE_HASH_INVALID'}
   Need-NoPending
   Assert-ConfigAndTask 'Ready'
   Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop;Wait-TaskState 'Running'
   Assert-ConfigAndTask 'Running'
   $report.task_state_restored=$true;$report.config_byte_identical=$true;$report.task_definition_preserved=$true;$report.task_principal_preserved=$true
   # A failed cutover with no surviving old console leaves restored Agent inert until manual opening.
  }catch{$report.reason=$report.reason+'_ROLLBACK_INCOMPLETE'}
 }
}finally{
 # Private preimages are retained. No approval or operator marker is removed here.
 if($tempCreated -and (Test-Path -LiteralPath $Temp)){Remove-Item -LiteralPath $Temp -Force -ErrorAction SilentlyContinue}
 $report|ConvertTo-Json -Depth 5 -Compress
}
