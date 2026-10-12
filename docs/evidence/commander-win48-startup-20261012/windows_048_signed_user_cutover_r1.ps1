# Signed Windows 0.3.47 -> 0.3.48 installation only; never launches an Agent or task.
[CmdletBinding()]
param([ValidateSet('Inspect','Apply')][string]$Action='Inspect',
 [string]$BundleRoot='C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-048-rc-r1',
 [ValidateRange(2,2147483647)][int]$ExpectedOperatorPid=8768,
 [string]$ExpectedOperatorStart='2026-10-12T16:15:33.0239441Z',
 [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedConfigSha='e8810f67c0ccaa8780a401f767e5ff99660def8d8815b7288c7a9e4d156bc7f8',
 [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedTaskSha='9bcc1704ecbb8afb3ce5edd4cb1f7a21ed4d470fc91870ff354d9da24d5dfa08',
 [switch]$RootSource47NoMutanteOutstandingPlausiblyActive,
 [ValidatePattern('^(|[a-f0-9]{64})$')][string]$RootControlPlaneMetadataSha256='',
 [string]$RootControlPlaneObservedAtUtc='',
 [int]$HistoricalProductSessionsCount=-1,
 [ValidatePattern('^(|[a-f0-9]{64})$')][string]$HistoricalProductSessionsReceiptSha256='',
 [string]$FreshInspectObservedAtUtc='',
 [ValidatePattern('^(|[a-f0-9]{64})$')][string]$FreshInspectSha256='')
$ErrorActionPreference='Stop'
. (Join-Path $BundleRoot 'windows_048_private_rc_validate.ps1') -FunctionsOnly -BundleRoot $BundleRoot
$OldSha='254517c46acf47102ebed5fe31fcb5d880ca0de47b98debeebdcaf4b1b324e36'
$NewSha='f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805'
$ManifestSha='5e65b1862c40bc9164609cdcd1401bb55e02e409b44f1b58bca15151e40de32c'
$Dir=Join-Path $env:LOCALAPPDATA 'HARA Commander';$Root=$Dir
$Target=Join-Path $Dir 'hara-commander-agent.ps1';$Cfg=Join-Path $Dir 'device.json'
$Session=Join-Path $Dir 'operator-session.json';$Pending=Join-Path $Dir 'pending-action-approval.json';$Reply=Join-Path $Dir 'action-approval-response.json'
$script:PendingApprovalPath=$Pending
$ProtectedDir=Join-Path $Dir 'canary-backups\signed-v48-rc-20261012-r1'
$Backup=Join-Path $ProtectedDir 'agent47.preimage.ps1';$CfgBackup=Join-Path $ProtectedDir 'device.preimage.json'
$TaskBackup=Join-Path $ProtectedDir 'task.preimage.xml';$SessionBackup=Join-Path $ProtectedDir 'operator-session.preimage.json'
$Temp=Join-Path $Dir 'hara-commander-agent.ps1.new-v48-20261012-r1.ps1'
$Atomic=Join-Path $ProtectedDir 'agent47.atomic-preimage.ps1'
$RollbackTemp=Join-Path $Dir 'hara-commander-agent.ps1.rollback-v48-20261012-r1.ps1'
$TaskName='HARA Commander Agent';$cfgSha=$ExpectedConfigSha;$taskSha=$ExpectedTaskSha;$sessionSha=''
$script:CutoverApply=($Action -ceq 'Apply');$backupReady=$false;$cutoverStarted=$false;$tempCreated=$false
function Get-CanaryFileSha([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()}
function Need-NoPending {
 if((Test-Path -LiteralPath $Pending) -or (Test-Path -LiteralPath $Reply)){throw 'CANARY_LOCAL_APPROVAL_IN_PROGRESS'}
}
function Get-ExactOperator {
 if(-not(Test-Path -LiteralPath $Session -PathType Leaf)){throw 'CANARY_OPERATOR_SESSION_REQUIRED'}
 if($sessionSha -and (Get-CanaryFileSha $Session) -cne $sessionSha){throw 'CANARY_OPERATOR_MARKER_BYTES_CHANGED'}
 $s=Get-Content -LiteralPath $Session -Raw|ConvertFrom-Json
 if([string]$s.schema -cne 'hara.commander-operator-session.v1' -or [int]$s.owner_pid -le 1){throw 'CANARY_OPERATOR_SESSION_INVALID'}
 $p=Get-Process -Id ([int]$s.owner_pid) -ErrorAction Stop
 if($p.StartTime.ToUniversalTime().ToString('o') -cne [string]$s.owner_started_at_utc){throw 'CANARY_OPERATOR_PID_REUSED'}
 if($p.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId){throw 'CANARY_OPERATOR_NOT_CURRENT_INTERACTIVE_SESSION'}
 $c=Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.Id) -ErrorAction Stop
 if([string]$c.Name -ine 'powershell.exe' -or -not([string]$c.CommandLine -match 'operator-visible-wrapper\.ps1|operator-console-03(?:47|48)\.ps1|hara-commander-agent\.ps1.+\bstart\b')){throw 'CANARY_OPERATOR_COMMAND_UNEXPECTED'}
 $own=Invoke-CimMethod -InputObject $c -MethodName GetOwnerSid -ErrorAction Stop
 if([int]$own.ReturnValue -ne 0 -or [string]$own.Sid -cne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value){throw 'CANARY_OPERATOR_SID_CHANGED'}
 return [pscustomobject]@{pid=$p.Id;started=[string]$s.owner_started_at_utc}
}
function Assert-ExpectedOldOperator {
 $op=Get-ExactOperator
 if($op.pid -ne $ExpectedOperatorPid -or $op.started -cne $ExpectedOperatorStart){throw 'CANARY_EXPECTED_OLD_OPERATOR_CHANGED'}
 return $op
}
function Get-AgentTargetProcesses {
 @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction Stop|Where-Object {
  $_.CommandLine -and (([string]$_.CommandLine).IndexOf($Target,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or [string]$_.CommandLine -match 'operator-visible-wrapper\.ps1|operator-console-03(?:47|48)\.ps1')
 })
}
function Assert-NoAgentConsumersExcept($Expected) {
 $now=Get-ExactOperator
 if($now.pid -ne $Expected.pid -or $now.started -cne $Expected.started){throw 'CANARY_OPERATOR_CHANGED'}
 $other=@(Get-AgentTargetProcesses|Where-Object {[int]$_.ProcessId -ne $Expected.pid})
 if($other.Count -ne 0){throw 'CANARY_AGENT_CONSUMER_PRESENT'}
}
# Metadata is read-only and contains no raw command line, path or SID.
function Assert-ZeroAgentTargetProcesses {
 if(@(Get-AgentTargetProcesses).Count -ne 0){throw 'CANARY_AGENT_TARGET_PROCESS_PRESENT'}
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
 if((Get-Win48TextSha ([string](Export-ScheduledTask -TaskName $TaskName -ErrorAction Stop))) -cne $taskSha){throw 'CANARY_TASK_DEFINITION_CHANGED'}
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
function Need-RootControlEvidence {
 if(-not $RootSource47NoMutanteOutstandingPlausiblyActive -or $RootControlPlaneMetadataSha256 -notmatch '^[a-f0-9]{64}$' -or $RootControlPlaneMetadataSha256 -ceq ('0'*64)){throw 'CANARY_ROOT_MUTANTE_METADATA_REQUIRED'}
 if($HistoricalProductSessionsCount -ne 0 -or $HistoricalProductSessionsReceiptSha256 -notmatch '^[a-f0-9]{64}$' -or $HistoricalProductSessionsReceiptSha256 -ceq ('0'*64)){throw 'CANARY_HISTORICAL_SESSIONS_EVIDENCE_REQUIRED'}
 try{$age=([DateTime]::UtcNow-[DateTime]::Parse($RootControlPlaneObservedAtUtc).ToUniversalTime()).TotalSeconds}catch{throw 'CANARY_ROOT_CONTROL_TIMESTAMP_INVALID'}
 if($age -lt -5 -or $age -gt 120){throw 'CANARY_ROOT_CONTROL_METADATA_NOT_CURRENT'}
}
function InspectionSha([string]$At){
 Get-Win48TextSha ((@($At,$OldSha,$NewSha,$ManifestSha,$cfgSha,$taskSha,$sessionSha,[string]$ExpectedOperatorPid,$ExpectedOperatorStart,$RootControlPlaneMetadataSha256,$RootControlPlaneObservedAtUtc,[string]$HistoricalProductSessionsCount,$HistoricalProductSessionsReceiptSha256,'Ready','NO_IPC','ZERO_CONSUMERS') -join '|'))
}
function Need-FreshInspection {
 try{$age=([DateTime]::UtcNow-[DateTime]::Parse($FreshInspectObservedAtUtc).ToUniversalTime()).TotalSeconds}catch{throw 'CANARY_FRESH_INSPECT_REQUIRED'}
 if($age -lt -5 -or $age -gt 120 -or $FreshInspectSha256 -cne (InspectionSha $FreshInspectObservedAtUtc)){throw 'CANARY_FRESH_INSPECT_MISMATCH_OR_EXPIRED'}
}
function Import-ReviewedMarkerLock {
 $tokens=$null;$errors=$null
 $ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $BundleRoot 'agent\windows.ps1'),[ref]$tokens,[ref]$errors)
 if(@($errors).Count){throw 'CANARY_SOURCE48_PARSE_FAILED'}
 foreach($name in @('Get-Utf8Sha256','Invoke-WithLocalApprovalLock')){
  $defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true))
  if($defs.Count -ne 1){throw 'CANARY_MARKER_LOCK_FUNCTION_MISSING'}
  $definition=$defs[0].Extent.Text
  $prefix=New-Object Text.RegularExpressions.Regex('\Afunction\s+')
  if(-not $prefix.IsMatch($definition)){throw 'CANARY_MARKER_LOCK_DEFINITION_INVALID'}
  Invoke-Expression ($prefix.Replace($definition,'function script:',1))
 }
}
function Close-OnlyExpectedOwner {
 Need-NoPending;Need-RootControlEvidence;Assert-ConfigAndTask 'Ready';$expected=Assert-ExpectedOldOperator
 Assert-NoAgentConsumersExcept $expected
 $p=Get-Process -Id $expected.pid -ErrorAction Stop
 if($p.MainWindowHandle -ne [IntPtr]::Zero){$null=$p.CloseMainWindow();$null=$p.WaitForExit(2500)}
 $alive=Get-Process -Id $expected.pid -ErrorAction SilentlyContinue
 if($alive){
  if($alive.StartTime.ToUniversalTime().ToString('o') -cne $expected.started){throw 'CANARY_OPERATOR_PID_REUSED'}
  Need-NoPending;Need-RootControlEvidence;Assert-ConfigAndTask 'Ready'
  Stop-Process -Id $expected.pid -Force -ErrorAction Stop
  $null=$alive.WaitForExit(3000)
 }
 if(Get-Process -Id $expected.pid -ErrorAction SilentlyContinue){throw 'CANARY_OPERATOR_DID_NOT_CLOSE'}
}
$report=[ordered]@{schema='hara.commander-win48-install-only-canary.v1';state='FAIL';action=$Action;reason='PRECHECK';old_source_sha256=$OldSha;new_source_sha256=$NewSha;manifest_sha256=$ManifestSha;config_sha256=$cfgSha;task_definition_sha256=$taskSha;expected_owner_pid=$ExpectedOperatorPid;expected_owner_started_at_utc=$ExpectedOperatorStart;root_control_plane_metadata_sha256=$RootControlPlaneMetadataSha256;root_control_plane_metadata_provenance='ROOT_NORMALIZED_CONTROL_PLANE_METADATA_NOT_AGENT_RECEIPT';historical_product_sessions_count=$HistoricalProductSessionsCount;historical_product_sessions_receipt_sha256=$HistoricalProductSessionsReceiptSha256;product_sessions_fresh_claimed=$false;agent_top_level_imported=$false;backup_sha_verified=$false;marker_custody_verified=$false;owned_dead_marker_removed=$false;zero_targets_before_replace=$false;config_byte_identical=$false;task_definition_preserved=$false;task_state_after='';rollback_old_agent_verified=$false;human_start_required=$true;agent_or_task_launched=$false;approval_generated=$false;secrets_in_result=$false}
try{
 # Verify signed bundle and parser before touching the live profile.
 $null=Assert-Win48FrozenBundle $BundleRoot
 if((Get-CanaryFileSha (Join-Path $BundleRoot 'agent\windows.ps1')) -cne $NewSha){throw 'CANARY_SOURCE48_PIN_MISMATCH'}
 Import-ReviewedMarkerLock
 $ownerSid=Assert-CanaryTask 'Ready';Assert-ConfigAndTask 'Ready';Need-NoPending;Need-RootControlEvidence
 if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'CANARY_EXPECTED_SOURCE47_NOT_INSTALLED'}
 $oldOperator=Assert-ExpectedOldOperator;$sessionSha=Get-CanaryFileSha $Session
 $null=Assert-ExpectedOldOperator;Assert-NoAgentConsumersExcept $oldOperator
 $taskXml=[string](Export-ScheduledTask -TaskName $TaskName -ErrorAction Stop)
 foreach($path in @($ProtectedDir,$Temp,$RollbackTemp)){if(Test-Path -LiteralPath $path){throw 'CANARY_PRIVATE_PREIMAGE_OR_TEMP_COLLISION'}}
 if(-not $script:CutoverApply){
  $at=[DateTime]::UtcNow.ToString('o');$report.inspect_observed_at_utc=$at;$report.inspection_sha256=InspectionSha $at
  $report.state='PASS';$report.reason='READY_FOR_ROOT_REVIEW';$report.task_state_after='Ready';$report.config_byte_identical=$true;$report.task_definition_preserved=$true
 }else{
  Need-FreshInspection;Need-NoPending;Need-RootControlEvidence;Assert-ConfigAndTask 'Ready';$null=Assert-ExpectedOldOperator;Assert-NoAgentConsumersExcept $oldOperator
  New-Item -ItemType Directory -Path $ProtectedDir -ErrorAction Stop|Out-Null;Set-PrivatePreimageAcl $ProtectedDir $ownerSid $true
  Copy-Item -LiteralPath $Target -Destination $Backup -ErrorAction Stop;Set-PrivatePreimageAcl $Backup $ownerSid $false
  Copy-Item -LiteralPath $Cfg -Destination $CfgBackup -ErrorAction Stop;Set-PrivatePreimageAcl $CfgBackup $ownerSid $false
  [IO.File]::WriteAllText($TaskBackup,$taskXml,(New-Object Text.UTF8Encoding($false)));Set-PrivatePreimageAcl $TaskBackup $ownerSid $false
  Assert-Preimages;$backupReady=$true;$report.backup_sha_verified=$true
  $null=Invoke-WithLocalApprovalLock {
   Need-NoPending;Assert-ConfigAndTask 'Ready';$null=Assert-ExpectedOldOperator
   Copy-Item -LiteralPath $Session -Destination $SessionBackup -ErrorAction Stop;Set-PrivatePreimageAcl $SessionBackup $ownerSid $false
   if((Get-CanaryFileSha $SessionBackup) -cne $sessionSha){throw 'CANARY_MARKER_CUSTODY_HASH_INVALID'}
  }
  $report.marker_custody_verified=$true;$tempCreated=$true
  Copy-Item -LiteralPath (Join-Path $BundleRoot 'agent\windows.ps1') -Destination $Temp -ErrorAction Stop
  if((Get-CanaryFileSha $Temp) -cne $NewSha){throw 'CANARY_TEMP_SOURCE48_HASH_INVALID'}
  Need-FreshInspection;Need-RootControlEvidence;Need-NoPending;Assert-ConfigAndTask 'Ready';Assert-Preimages
  if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'CANARY_SOURCE47_CHANGED_BEFORE_CLOSE'}
  $cutoverStarted=$true;Close-OnlyExpectedOwner
  $null=Invoke-WithLocalApprovalLock {
   Need-NoPending;Assert-ConfigAndTask 'Ready';Assert-ZeroAgentTargetProcesses
   if(Get-Process -Id $ExpectedOperatorPid -ErrorAction SilentlyContinue){throw 'CANARY_OLD_OWNER_PID_STILL_PRESENT'}
   if(Test-Path -LiteralPath $Session){
    if((Get-CanaryFileSha $Session) -cne $sessionSha){throw 'CANARY_OPERATOR_MARKER_REPLACED'}
    $s=Get-Content -LiteralPath $Session -Raw|ConvertFrom-Json
    if([string]$s.schema -cne 'hara.commander-operator-session.v1' -or [int]$s.owner_pid -ne $ExpectedOperatorPid -or [string]$s.owner_started_at_utc -cne $ExpectedOperatorStart){throw 'CANARY_DEAD_MARKER_NOT_OWNED'}
    if((Get-CanaryFileSha $SessionBackup) -cne $sessionSha){throw 'CANARY_MARKER_CUSTODY_CHANGED'}
    Need-NoPending;Remove-Item -LiteralPath $Session -Force -ErrorAction Stop
   }
  }
  $report.owned_dead_marker_removed=$true
  Need-NoPending;Need-RootControlEvidence;Assert-ConfigAndTask 'Ready';Assert-Preimages;Assert-ZeroAgentTargetProcesses
  if(Test-Path -LiteralPath $Session){throw 'CANARY_OPERATOR_MARKER_PRESENT_BEFORE_REPLACE'}
  if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'CANARY_SOURCE47_CHANGED_BEFORE_REPLACE'}
  $report.zero_targets_before_replace=$true
  [IO.File]::Replace($Temp,$Target,$Atomic,$true);Set-PrivatePreimageAcl $Atomic $ownerSid $false
  if((Get-CanaryFileSha $Atomic) -cne $OldSha -or (Get-CanaryFileSha $Target) -cne $NewSha){throw 'CANARY_ATOMIC_SOURCE_HASH_INVALID'}
  Need-NoPending;Assert-ConfigAndTask 'Ready';Assert-ZeroAgentTargetProcesses
  if(Test-Path -LiteralPath $Session){throw 'CANARY_OPERATOR_MARKER_PRESENT_AFTER_REPLACE'}
  $report.config_byte_identical=$true;$report.task_definition_preserved=$true;$report.task_state_after='Ready';$report.state='PASS';$report.reason='INSTALLED_AWAITING_HUMAN_START'
 }
}catch{
 $code=[string]$_.Exception.Message;$report.reason=if($code -match '^[A-Z][A-Z0-9_]{1,100}$'){$code}else{'CANARY_RUNTIME_FAILED'}
 if($backupReady -and $cutoverStarted){
  try{
   Need-NoPending;Assert-ConfigAndTask 'Ready';Assert-Preimages
   $targetSha=Get-CanaryFileSha $Target
   if($targetSha -cne $OldSha -and $targetSha -cne $NewSha){throw 'ROLLBACK_TARGET_DRIFT_HOLD'}
   if($targetSha -ceq $NewSha){
    Assert-ZeroAgentTargetProcesses
    if(Test-Path -LiteralPath $Session){throw 'ROLLBACK_UNEXPECTED_OPERATOR_MARKER_HOLD'}
    Copy-Item -LiteralPath $Backup -Destination $RollbackTemp -ErrorAction Stop
    if((Get-CanaryFileSha $RollbackTemp) -cne $OldSha -or (Get-CanaryFileSha $Target) -cne $NewSha){throw 'ROLLBACK_CAS_SOURCE_HASH_INVALID'}
    Need-NoPending;Assert-ConfigAndTask 'Ready';Assert-ZeroAgentTargetProcesses
    [IO.File]::Replace($RollbackTemp,$Target,$null,$true)
   }
   if((Get-CanaryFileSha $Target) -cne $OldSha){throw 'ROLLBACK_SOURCE47_NOT_RESTORED'}
   Assert-ConfigAndTask 'Ready';$report.rollback_old_agent_verified=$true;$report.task_state_after='Ready';$report.config_byte_identical=$true;$report.task_definition_preserved=$true
  }catch{$report.reason=$report.reason+'_ROLLBACK_HOLD'}
 }
}finally{
 if($tempCreated -and (Test-Path -LiteralPath $Temp)){Remove-Item -LiteralPath $Temp -Force -ErrorAction SilentlyContinue}
 $report|ConvertTo-Json -Depth 5 -Compress
}
