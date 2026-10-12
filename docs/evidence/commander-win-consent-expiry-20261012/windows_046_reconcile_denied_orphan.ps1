# Exact orphan reconciliation, prepared for root review. Default action is read-only.
# Cloud terminal metadata must be confirmed through the Commander service before Reconcile.
[CmdletBinding()]
param(
 [ValidateSet('Inspect','Reconcile')][string]$Action='Inspect',
 [string]$CloudTerminalState='',
 [string]$CloudErrorCode='',
 [string]$CloudMetadataSha256=''
)
$ErrorActionPreference='Stop'
$expectedRequest='HARA-CUSTOMER-MCP-pNmk7MPzQkccsGKxqqO8Xv4DCHkebOvDfFva3zDGrX8'
$expectedCall='HARA-CALL-4ea93468-2003-4c58-928f-9ce6911c378a'
$expectedPending='c06a2fbac564ca245effee7a92ece813ad1c37efd00c486aedb31112e4e0117c'
$expectedReply='ff9bba228a2dae890879e83620de9ccc13464a34dcef0172b621aa8b17759e0a'
$expectedConfig='e8810f67c0ccaa8780a401f767e5ff99660def8d8815b7288c7a9e4d156bc7f8'
$expectedTask='9bcc1704ecbb8afb3ce5edd4cb1f7a21ed4d470fc91870ff354d9da24d5dfa08'
$expectedAgent='71998b7c5e2dae4f4cbcfe80e5413ab1c6ff8e28ad903734cc1f026dfe8765aa'
$expectedOperatorStart='2026-10-12T03:49:14.2210344Z'
$root=Join-Path $env:LOCALAPPDATA 'HARA Commander'
$pending=Join-Path $root 'pending-action-approval.json'
$reply=Join-Path $root 'action-approval-response.json'
$session=Join-Path $root 'operator-session.json'
$config=Join-Path $root 'device.json'
$agent=Join-Path $root 'hara-commander-agent.ps1'
$taskName='HARA Commander Agent'
$custody=Join-Path $root 'canary-backups\expired-denied-pnmk-20261012'
$pendingMoved=$false;$replyMoved=$false
$script:ReconciliationRequested=($Action -ceq 'Reconcile')
function FileHash([string]$path){return (Get-FileHash -LiteralPath $path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()}
function Assert-Context {
 $wi=[Security.Principal.WindowsIdentity]::GetCurrent()
 if($wi.IsSystem){throw 'ORPHAN_REAL_USER_REQUIRED'}
 if((FileHash $agent) -cne $expectedAgent){throw 'ORPHAN_AGENT_SOURCE_CHANGED'}
 if((FileHash $config) -cne $expectedConfig){throw 'ORPHAN_CONFIG_CHANGED'}
 $cfg=Get-Content -LiteralPath $config -Raw|ConvertFrom-Json
 $mode=if($cfg.approval_mode){[string]$cfg.approval_mode}else{'ASK_EVERY_ACTION'}
 if($mode -cne 'ASK_EVERY_ACTION'){throw 'ORPHAN_POLICY_CHANGED'}
 $t=Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
 if([string]$t.State -cne 'Ready'){throw 'ORPHAN_TASK_STATE_CHANGED'}
 if((Get-Utf8Sha256 ([string](Export-ScheduledTask -TaskName $taskName))) -cne $expectedTask){throw 'ORPHAN_TASK_DEFINITION_CHANGED'}
 $sid=[string]$t.Principal.UserId
 if($sid -notmatch '^S-1-'){$sid=(New-Object Security.Principal.NTAccount($sid)).Translate([Security.Principal.SecurityIdentifier]).Value}
 if($sid -cne $wi.User.Value -or [string]$t.Principal.LogonType -cne 'Interactive' -or [string]$t.Principal.RunLevel -cne 'Limited'){throw 'ORPHAN_TASK_PRINCIPAL_CHANGED'}
 $s=Get-Content -LiteralPath $session -Raw|ConvertFrom-Json
 if([string]$s.schema -cne 'hara.commander-operator-session.v1' -or [int]$s.owner_pid -ne 7572 -or [string]$s.owner_started_at_utc -cne $expectedOperatorStart){throw 'ORPHAN_OPERATOR_SESSION_CHANGED'}
 $owner=Get-Process -Id 7572 -ErrorAction Stop
 if($owner.StartTime.ToUniversalTime().ToString('o') -cne $expectedOperatorStart -or $owner.SessionId -ne [Diagnostics.Process]::GetCurrentProcess().SessionId){throw 'ORPHAN_OPERATOR_PID_REUSED'}
 if(Get-Process -Id 7524 -ErrorAction SilentlyContinue){throw 'ORPHAN_OLD_OWNER_STILL_ALIVE'}
 # The guarded operator also runs this source; only another target process is a consumer.
 $bg=@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {[int]$_.ProcessId -ne 7572 -and $_.CommandLine -and ([string]$_.CommandLine).IndexOf($agent,[StringComparison]::OrdinalIgnoreCase) -ge 0})
 if($bg.Count -ne 0){throw 'ORPHAN_AGENT_CONSUMER_PRESENT'}
 return $wi.User.Value
}
function Assert-ExactFiles {
 if((FileHash $pending) -cne $expectedPending -or (FileHash $reply) -cne $expectedReply){throw 'ORPHAN_IPC_SHA_CHANGED'}
 $p=Get-Content -LiteralPath $pending -Raw|ConvertFrom-Json
 $r=Get-Content -LiteralPath $reply -Raw|ConvertFrom-Json
 if([string]$p.schema -cne 'hara.commander-local-action-approval.v1' -or [string]$r.schema -cne 'hara.commander-local-action-response.v1'){throw 'ORPHAN_IPC_SCHEMA_CHANGED'}
 if([string]$p.request_id -cne $expectedRequest -or [string]$r.request_id -cne $expectedRequest -or [int]$p.owner_pid -ne 7524 -or [int]$r.owner_pid -ne 7524){throw 'ORPHAN_IPC_REQUEST_CHANGED'}
 if($r.approved -isnot [bool] -or $r.approved -ne $false){throw 'ORPHAN_RESPONSE_NOT_DENIED'}
 if(-not [string]$p.nonce -or [string]$p.nonce -cne [string]$r.nonce -or [string]$p.arguments_sha256 -cne [string]$r.arguments_sha256 -or [string]$p.owner_started_at_utc -cne [string]$r.owner_started_at_utc){throw 'ORPHAN_IPC_CORRELATION_FAILED'}
 $expires=[DateTime]::Parse([string]$p.expires_at_utc).ToUniversalTime()
 if($expires -ge [DateTime]::UtcNow){throw 'ORPHAN_REQUEST_NOT_EXPIRED'}
 if((FileHash $pending) -cne $expectedPending -or (FileHash $reply) -cne $expectedReply){throw 'ORPHAN_IPC_CHANGED_DURING_READ'}
}
try{
 # Import only two reviewed function definitions, never execute Agent top level.
 if((FileHash $agent) -cne $expectedAgent){throw 'ORPHAN_AGENT_SOURCE_CHANGED'}
 $tokens=$null;$errors=$null
 $ast=[Management.Automation.Language.Parser]::ParseFile($agent,[ref]$tokens,[ref]$errors)
 if(@($errors).Count -ne 0){throw 'ORPHAN_AGENT_PARSE_FAILED'}
 foreach($name in @('Get-Utf8Sha256','Invoke-WithLocalApprovalLock')){
  $defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true))
  if($defs.Count -ne 1){throw 'ORPHAN_REQUIRED_AST_FUNCTION_MISSING'}
  Invoke-Expression $defs[0].Extent.Text
 }
 $script:PendingApprovalPath=$pending
 $ownerSid=Assert-Context
 if($Action -ceq 'Reconcile'){
  if($CloudTerminalState -cne 'EXPIRED' -or $CloudErrorCode -cne 'DEVICE_CALL_EXPIRED' -or $CloudMetadataSha256 -cne 'aead137447ed5ff3e5a0bb4a2b4933bd03ae5277f40284798c6db2f73ed159c3'){throw 'ORPHAN_CLOUD_TERMINAL_CONFIRMATION_REQUIRED'}
 }
 $report=[ordered]@{schema='hara.commander-win46-denied-orphan-reconciliation.v1';state='READ_ONLY_PREPARED';action=$Action;request_id=$expectedRequest;call_id=$expectedCall;pending_sha256=$expectedPending;response_sha256=$expectedReply;approved_is_bool=$true;approved=$false;old_owner_dead=$true;agent_consumer_absent=$true;current_operator_pid=7572;current_operator_start=$expectedOperatorStart;current_operator_guard_matches=$true;approval_mode='ASK_EVERY_ACTION';task_state_before='Ready';task_restarted=$false;config_preserved=$true;task_definition_preserved=$true;custody_sha_verified=$false;expired_ipc_renamed=$false;cloud_terminal_state=$CloudTerminalState;cloud_error_code=$CloudErrorCode;cloud_metadata_sha256=$CloudMetadataSha256;cloud_bridge_receipt_claimed=$false;agent_top_level_imported=$false;any_approval_generated=$false;nonce_payload_or_credentials_exposed=$false}
 Invoke-WithLocalApprovalLock {
  $null=Assert-Context
  Assert-ExactFiles
  if($script:ReconciliationRequested){
   if(Test-Path -LiteralPath $custody){throw 'ORPHAN_CUSTODY_COLLISION'}
   New-Item -ItemType Directory -Path $custody -ErrorAction Stop|Out-Null
   $acl=New-Object Security.AccessControl.DirectorySecurity
   $acl.SetAccessRuleProtection($true,$false)
   $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier($ownerSid)))
   foreach($sid in @($ownerSid,'S-1-5-18')){
    $id=New-Object Security.Principal.SecurityIdentifier($sid)
    $rule=New-Object Security.AccessControl.FileSystemAccessRule($id,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.AddAccessRule($rule)
   }
   Set-Acl -LiteralPath $custody -AclObject $acl -ErrorAction Stop
   if(-not (Get-Acl -LiteralPath $custody).AreAccessRulesProtected){throw 'ORPHAN_CUSTODY_ACL_UNPROTECTED'}
   $pendingBackup=Join-Path $custody 'pending.preimage.json'
   $replyBackup=Join-Path $custody 'response.preimage.json'
   $pendingArchive=Join-Path $custody 'pending.original-renamed.json'
   $replyArchive=Join-Path $custody 'response.original-renamed.json'
   Copy-Item -LiteralPath $pending -Destination $pendingBackup -ErrorAction Stop
   Copy-Item -LiteralPath $reply -Destination $replyBackup -ErrorAction Stop
   if((FileHash $pendingBackup) -cne $expectedPending -or (FileHash $replyBackup) -cne $expectedReply){throw 'ORPHAN_CUSTODY_SHA_MISMATCH'}
   $null=Assert-Context
   Assert-ExactFiles
   [IO.File]::Move($pending,$pendingArchive);$script:pendingMoved=$true
   try{[IO.File]::Move($reply,$replyArchive);$script:replyMoved=$true}catch{
    if(-not(Test-Path -LiteralPath $pending) -and (FileHash $pendingArchive) -ceq $expectedPending){[IO.File]::Move($pendingArchive,$pending);$script:pendingMoved=$false}
    throw 'ORPHAN_SECOND_RENAME_FAILED'
   }
   if((FileHash $pendingArchive) -cne $expectedPending -or (FileHash $replyArchive) -cne $expectedReply){throw 'ORPHAN_ARCHIVE_SHA_MISMATCH'}
   $null=Assert-Context
   if((Test-Path -LiteralPath $pending) -or (Test-Path -LiteralPath $reply)){throw 'ORPHAN_NEW_IPC_PRESENT_AFTER_RENAME'}
   $report.state='PASS';$report.custody_sha_verified=$true;$report.expired_ipc_renamed=$true
  }
 }
 $report|ConvertTo-Json -Depth 3 -Compress
}catch{
 $code=[string]$_.Exception.Message
 if($code -notmatch '^[A-Z][A-Z0-9_]{1,100}$'){$code='ORPHAN_RECONCILIATION_RUNTIME_FAILED'}
 [pscustomobject]@{schema='hara.commander-win46-denied-orphan-reconciliation.v1';state='HOLD';action=$Action;reason=$code;pending_renamed=[bool]$pendingMoved;response_renamed=[bool]$replyMoved;task_restarted=$false;any_approval_generated=$false;nonce_payload_or_credentials_exposed=$false}|ConvertTo-Json -Compress
}
