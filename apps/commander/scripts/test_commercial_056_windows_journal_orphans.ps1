param(
 [string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'),
 [switch]$CrashChild,
 [string]$FixtureRoot,
 [string]$OwnerNonce
)
# #240/#322 source QA. Real SQLite and one hard-killed owned subprocess, not
# Agent main, DPAPI, native Jobs, installation, network, quota or VM admission.
# The child persists its phase and exits abruptly; only this parent cleans up.
$ErrorActionPreference='Stop'
$native=[Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$priorLocal=$env:LOCALAPPDATA
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[object]
$caseCount=0
$hardCrashCount=0
$sourceSha=(Get-FileHash -LiteralPath $AgentPath -Algorithm SHA256).Hash.ToLowerInvariant()
$qa=if($CrashChild){$FixtureRoot}else{Join-Path ([IO.Path]::GetTempPath()) ('hara-056-journal-orphans-'+[guid]::NewGuid().ToString('N'))}
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function Denied([scriptblock]$Action,[string]$Code){
 $seen=$false
 try{& $Action | Out-Null}catch{$seen=(Get-WindowsRelayDeliveryError $_) -ceq $Code}
 Check $seen $Code
}
function Protect-FixtureDirectory([string]$Path){
 if($native){
  $acl=Get-Acl -LiteralPath $Path
  $acl.SetAccessRuleProtection($true,$false)
  $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
  $rule=New-Object Security.AccessControl.FileSystemAccessRule -ArgumentList $sid,([Security.AccessControl.FileSystemRights]::FullControl),([Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'),([Security.AccessControl.PropagationFlags]::None),([Security.AccessControl.AccessControlType]::Allow)
  $acl.SetAccessRule($rule);Set-Acl -LiteralPath $Path -AclObject $acl
 }else{
  & chmod 700 -- $Path
  if($LASTEXITCODE -ne 0){throw 'QA_FIXTURE_PRIVACY_REQUIRED'}
 }
}
try{
 if(-not $CrashChild){New-Item -ItemType Directory -Path $qa | Out-Null;Protect-FixtureDirectory $qa}
 if(-not $qa -or -not (Test-Path -LiteralPath $qa -PathType Container)){throw 'QA_FIXTURE_ROOT_REQUIRED'}
 $env:LOCALAPPDATA=$qa
 $tokens=$null;$errors=$null
 $tree=[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $AgentPath),[ref]$tokens,[ref]$errors)
 Check ($errors.Count -eq 0) 'AGENT_PARSE'
 $source=[IO.File]::ReadAllText((Resolve-Path $AgentPath))
 $cut=$source.IndexOf('if ($args -contains "--version")')
 Check ($cut -gt 0) 'DEFINITIONS_ONLY_NO_AGENT_MAIN'
 . ([scriptblock]::Create($source.Substring(0,$cut)))
 Initialize-WinSqlite
 if(-not $native){
  Add-Type -TypeDefinition @'
using System;
using System.Reflection;
using System.Runtime.InteropServices;
public static class HaraOrphanFixtureSqliteResolver {
 public static void Attach(Assembly assembly){NativeLibrary.SetDllImportResolver(assembly,Resolve);}
 static IntPtr Resolve(string name,Assembly assembly,DllImportSearchPath? path){
  return name=="winsqlite3.dll" ? NativeLibrary.Load("libsqlite3.so.0") : IntPtr.Zero;
 }
}
'@
  [HaraOrphanFixtureSqliteResolver]::Attach([HaraWinSqlite].Assembly)
 }
 Add-Type -TypeDefinition @'
using System;
public sealed class HaraOrphanFixtureHttpResponse {
 public int StatusCode {get;private set;}
 public HaraOrphanFixtureHttpResponse(int status){StatusCode=status;}
}
public sealed class HaraOrphanFixtureHttpException : Exception {
 public HaraOrphanFixtureHttpResponse Response {get;private set;}
 public HaraOrphanFixtureHttpException(int status):base("synthetic HTTP delivery failure"){Response=new HaraOrphanFixtureHttpResponse(status);}
}
'@
 function New-HttpFailure([int]$Status){
  $record=[Management.Automation.ErrorRecord]::new([HaraOrphanFixtureHttpException]::new($Status),'SyntheticDeliveryHttp',[Management.Automation.ErrorCategory]::InvalidOperation,$null)
  $record.ErrorDetails=[Management.Automation.ErrorDetails]::new($(if($Status -eq 409){'{"ok":false,"code":"DEVICE_CALL_EXPIRED"}'}else{'{"ok":false,"code":"DEVICE_AUTH_INVALID"}'}))
  return $record
 }
 function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25){
  if($Url -cne 'https://commander.invalid/api/device/calls/complete' -or $Token -cne 'synthetic-token'){throw 'QA_UNEXPECTED_NETWORK_BOUNDARY'}
  $script:attempts++
  $script:sent.Add(($Body | ConvertTo-Json -Depth 20 -Compress))
  if($script:networkMode -ceq 'offline'){throw 'SYNTHETIC_DELIVERY_OFFLINE'}
  if($script:networkMode -ceq 'incomplete'){return @{ok=$true}}
  if($script:networkMode -ceq 'expired'){throw (New-HttpFailure 409)}
  if($script:networkMode -ceq 'revoked401'){throw (New-HttpFailure 401)}
  if($script:networkMode -ceq 'revoked403'){throw (New-HttpFailure 403)}
  return @{schema='hara.commander-device-call-result.v1';ok=$true;call_id=[string]$Body.call_id;state=[string]$Body.state}
 }
 function Invoke-Tool($Cfg,$Call){
  $script:effectCount++
  [IO.File]::AppendAllText($script:effectFile,"UNEXPECTED_EXECUTION`n")
  return @{state='PASS';mutation_performed=$true;result=@{}}
 }
 function Configure-Fixture([string]$Path){
  $script:Root=$Path
  $script:OperationsDb=Join-Path $Path 'operations.sqlite3'
  $script:ReceiptDir=Join-Path $Path 'receipts'
  $script:ConsoleEvents=Join-Path $Path 'console-events.jsonl'
  $script:ConfigPath=Join-Path $Path 'device.json'
  $script:effectFile=Join-Path $Path 'effect.txt'
  $script:effectCount=0;$script:attempts=0;$script:networkMode='ack'
  $script:sent=New-Object Collections.Generic.List[string]
  $script:WindowsRelayWorkerMode=$false
  $script:cfg=[pscustomobject]@{base_url='https://commander.invalid';device_id='synthetic-orphan-device';tenant_id='synthetic-review';architecture='test';encrypted_device_token='synthetic-protected-not-a-credential';approval_mode='PERSISTENT_TRUSTED'}
  $script:EnrollmentContext=Get-EnrollmentContext $cfg
  [IO.File]::WriteAllText($ConfigPath,($cfg | ConvertTo-Json -Compress),([Text.UTF8Encoding]::new($false)))
  $script:call=[pscustomobject]@{call_id='synthetic-orphan-call';request_id='synthetic-orphan-request';tool_id='hara.files.write';payload=[pscustomobject]@{path=$effectFile;content='SYNTHETIC_PRIVATE_PAYLOAD_NOT_JOURNALLED'};expires_at_utc=[DateTime]::UtcNow.AddMinutes(5).ToString('o')}
  Initialize-WindowsRelayStore | Out-Null
 }
 function Journal {
  $rows=@(Invoke-LocalDbQuery 'SELECT * FROM windows_relay_calls WHERE request_id=?' @('synthetic-orphan-request'))
  if($rows.Count -ne 1){throw 'QA_EXPECTED_ONE_JOURNAL_ROW'}
  return $rows[0]
 }
 function Seed-Orphan([string]$Phase,[string]$Receipt=('d'*64)){
  New-WindowsRelayClaim $call
  Set-WindowsRelayPhase $call $Phase $Receipt
  $row=Journal
  Check ($row.phase -ceq $Phase -and $row.delivery_state -ceq 'NONE' -and [string]::IsNullOrEmpty([string]$row.completion_json)) 'REAL_ORPHAN_CHECKPOINT_WITHOUT_COMPLETION'
  return $row
 }
 function Check-Indeterminate($Before){
  $row=Journal
  Check ($row.phase -ceq $Before.phase) 'RECOVERY_PRESERVES_DURABLE_PHASE'
  Check ($row.fingerprint -ceq $Before.fingerprint -and $row.receipt_sha256 -ceq $Before.receipt_sha256) 'RECOVERY_PRESERVES_INTENT_AND_EXECUTION_RECEIPT'
  Check ($row.delivery_state -ceq 'PENDING' -and -not [string]::IsNullOrEmpty([string]$row.completion_json)) 'ORPHAN_GETS_DURABLE_PENDING_COMPLETION'
  $body=$row.completion_json | ConvertFrom-Json
  Check ($body.call_id -ceq $call.call_id -and $body.state -ceq 'FAILED' -and $body.error_code -ceq 'CALL_OUTCOME_UNCERTAIN') 'LOST_RESULT_IS_CORRELATED_FAILED_UNCERTAIN'
  Check ($body.result.state -ceq 'INDETERMINATE' -and $null -eq $body.result.mutation_performed -and $body.result.PSObject.Properties.Name -ccontains 'mutation_performed') 'NO_FALSE_PASS_OR_FALSE_NO_EFFECT'
  if($Before.receipt_sha256){Check ($body.result.bridge_receipt_sha256 -ceq $Before.receipt_sha256) 'KNOWN_RECEIPT_REMAINS_BOUND_TO_TERMINAL_RESULT'}
  else{Check ([string]::IsNullOrEmpty([string]$body.result.bridge_receipt_sha256)) 'MISSING_RECEIPT_IS_NOT_INVENTED'}
  Check ($body.result.runtime_authority_from_chatgpt -eq $false -and $script:effectCount -eq 0) 'RECOVERY_NEVER_EXECUTES_TOOL_OR_CREATES_AUTHORITY'
  return $row
 }
 if($CrashChild){
  $marker=Get-Content -Raw -LiteralPath (Join-Path $FixtureRoot 'owner.json') | ConvertFrom-Json
  if([string]$marker.nonce -cne $OwnerNonce -or [string]$marker.source_sha256 -cne $sourceSha -or [IO.Path]::GetFullPath([string]$marker.root) -cne [IO.Path]::GetFullPath($FixtureRoot)){throw 'QA_CHILD_FIXTURE_OWNER_MISMATCH'}
  Configure-Fixture $FixtureRoot
  New-WindowsRelayClaim $call
  Set-WindowsRelayPhase $call 'EXECUTING'
  [IO.File]::WriteAllText($effectFile,'SYNTHETIC_EFFECT_BEFORE_HARD_CRASH')
  Set-WindowsRelayPhase $call 'UNCERTAIN' ('c'*64)
  $proof=@{pid=$PID;phase=(Journal).phase;fingerprint=(Journal).fingerprint;receipt=(Journal).receipt_sha256;source_sha256=$sourceSha}
  [IO.File]::WriteAllText((Join-Path $FixtureRoot 'crash-checkpoint.json'),($proof | ConvertTo-Json -Compress))
  # Terminate only this owned synthetic child, without managed unwinding.
  [Diagnostics.Process]::GetCurrentProcess().Kill()
  throw 'QA_CHILD_HARD_KILL_DID_NOT_TERMINATE'
 }
 function Case([string]$Name,[scriptblock]$Action){
  $script:caseCount++
  try{
   $path=Join-Path $qa $Name
   New-Item -ItemType Directory -Path $path | Out-Null
   Configure-Fixture $path
   & $Action | Out-Null
   $checks.Add('CASE_'+$Name)
  }catch{$failures.Add(@{case=$Name;error=$_.Exception.Message;stack=$_.ScriptStackTrace})}
 }
 foreach($phase in @('FAILED','UNCERTAIN','EXECUTED')){
  Case ('orphan-'+$phase.ToLowerInvariant()+'-reconstructs-unknown-result') {
   $receipt=if($phase -ceq 'FAILED'){''}elseif($phase -ceq 'EXECUTED'){
    New-Receipt $cfg $call 'PASS' @{stdout='SYNTHETIC_ORIGINAL_RESULT';process_exit_code=0}
   }else{'d'*64}
   if($phase -ceq 'EXECUTED'){$receiptPath=Join-Path $ReceiptDir ($receipt+'.json');$receiptBytes=[Convert]::ToBase64String([IO.File]::ReadAllBytes($receiptPath))}
   $before=Seed-Orphan $phase $receipt
   Repair-WindowsRelayJournal
   Check-Indeterminate $before | Out-Null
   if($phase -ceq 'EXECUTED'){
    $proof=Get-Receipt $receipt $cfg
    Check ($proof.request_id -ceq $call.request_id -and $proof.device_id -ceq $cfg.device_id -and $proof.state -ceq 'PASS') 'ORIGINAL_RECEIPT_REMAINS_CORRELATED_AND_READABLE'
    Check ((Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $receipt) 'ORIGINAL_RECEIPT_REAL_BYTES_MATCH_SHA256'
    Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes($receiptPath)) -ceq $receiptBytes) 'RECONCILIATION_DOES_NOT_REWRITE_ORIGINAL_RECEIPT_BYTES'
   }
   Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
   Check ($effectCount -eq 0 -and $attempts -eq 0) 'ORPHAN_REPAIR_WITHOUT_CFG_HAS_NO_EFFECT_OR_DELIVERY'
  }
 }
 Case 'hard-child-crash-after-uncertain-checkpoint-and-sqlite-restart' {
  $nonce=[guid]::NewGuid().ToString('N')
  [IO.File]::WriteAllText((Join-Path $Root 'owner.json'),(@{nonce=$nonce;source_sha256=$sourceSha;root=$Root} | ConvertTo-Json -Compress))
  $program=if($native){Join-Path $PSHOME 'powershell.exe'}else{Join-Path $PSHOME 'pwsh'}
  $values=@([IO.Path]::GetFullPath($PSCommandPath),([IO.Path]::GetFullPath((Resolve-Path $AgentPath))),$Root,$nonce)
  foreach($value in $values){if($value.IndexOfAny([char[]]@([char]34,[char]13,[char]10,[char]0)) -ge 0){throw 'QA_CHILD_ARGUMENT_INVALID'}}
  $info=New-Object Diagnostics.ProcessStartInfo
  $info.FileName=$program;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
  $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
  $info.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+$values[0]+'" -AgentPath "'+$values[1]+'" -CrashChild -FixtureRoot "'+$values[2]+'" -OwnerNonce "'+$values[3]+'"'
  $process=New-Object Diagnostics.Process
  $process.StartInfo=$info
  try{
   [void]$process.Start()
   if(-not $process.WaitForExit(15000)){$process.Kill();$process.WaitForExit();throw 'QA_OWNED_CHILD_TIMEOUT'}
   $stdout=$process.StandardOutput.ReadToEnd();$stderr=$process.StandardError.ReadToEnd()
   Check ($process.ExitCode -ne 0) 'REAL_CHILD_HARD_EXIT_NONZERO'
   Check (Test-Path -LiteralPath (Join-Path $Root 'crash-checkpoint.json')) 'CHILD_COMMITTED_CHECKPOINT_BEFORE_EXIT'
   $script:hardCrashCount++
  }finally{$process.Dispose()}
  $proof=Get-Content -Raw -LiteralPath (Join-Path $Root 'crash-checkpoint.json') | ConvertFrom-Json
  Check ($proof.phase -ceq 'UNCERTAIN' -and $proof.source_sha256 -ceq $sourceSha) 'CRASH_PROOF_BOUND_TO_TESTED_AGENT_SOURCE'
  Check ([IO.File]::ReadAllText($effectFile) -ceq 'SYNTHETIC_EFFECT_BEFORE_HARD_CRASH') 'CHILD_EFFECT_SURVIVES_PARENT_ONLY_CLEANUP_POLICY'
  Initialize-WindowsRelayStore | Out-Null
  $before=Journal
  Check ($before.phase -ceq 'UNCERTAIN' -and $before.delivery_state -ceq 'NONE' -and [string]::IsNullOrEmpty([string]$before.completion_json)) 'REOPEN_REAL_SQLITE_ORPHAN_AFTER_HARD_CRASH'
  Repair-WindowsRelayJournal
  Check-Indeterminate $before | Out-Null
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Check ((Journal).delivery_state -ceq 'ACKNOWLEDGED' -and $attempts -eq 1) 'CRASH_RECOVERY_HAS_ONE_CORRELATED_TERMINAL_ACK'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
  Check ($attempts -eq 1 -and $effectCount -eq 0 -and [IO.File]::ReadAllText($effectFile) -ceq 'SYNTHETIC_EFFECT_BEFORE_HARD_CRASH') 'RESTART_NEVER_REPEATS_EFFECT_OR_ACKED_DELIVERY'
 }
 Case 'orphan-offline-incomplete-ack-retry-and-single-valid-ack' {
  $before=Seed-Orphan 'EXECUTED'
  Repair-WindowsRelayJournal
  $saved=Check-Indeterminate $before
  $original=[string]$saved.completion_json
  $script:networkMode='offline'
  Denied {Repair-WindowsRelayJournal $cfg 'synthetic-token'} 'SYNTHETIC_DELIVERY_OFFLINE'
  Check ((Journal).completion_json -ceq $original -and (Journal).delivery_state -ceq 'PENDING') 'OFFLINE_RETAINS_EXACT_ORPHAN_COMPLETION'
  Initialize-WindowsRelayStore | Out-Null
  $script:networkMode='incomplete'
  Denied {Repair-WindowsRelayJournal $cfg 'synthetic-token'} 'CALL_COMPLETION_NOT_ACKNOWLEDGED'
  Check ((Journal).completion_json -ceq $original -and (Journal).phase -ceq 'EXECUTED') 'INCOMPLETE_ACK_CANNOT_ERASE_EXECUTION_OR_RESULT'
  $script:networkMode='ack'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Check ((Journal).delivery_state -ceq 'ACKNOWLEDGED' -and [string]::IsNullOrEmpty([string](Journal).completion_json)) 'ONLY_CORRELATED_ACK_SCRUBS_PENDING_COMPLETION'
  Check ($attempts -eq 3 -and $sent[0] -ceq $sent[1] -and $sent[1] -ceq $sent[2]) 'ALL_DELIVERY_RETRIES_REUSE_IDENTICAL_TERMINAL_RESULT'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Check ($attempts -eq 3 -and $effectCount -eq 0 -and (Journal).receipt_sha256 -ceq $before.receipt_sha256) 'ACKED_ORPHAN_NEVER_REDELIVERED_OR_REEXECUTED'
 }
 Case 'orphan-confirmed-http409-expiry-preserves-proof-and-stops-delivery' {
  $before=Seed-Orphan 'UNCERTAIN'
  Repair-WindowsRelayJournal
  Check-Indeterminate $before | Out-Null
  $script:networkMode='expired'
  Denied {Repair-WindowsRelayJournal $cfg 'synthetic-token'} 'DEVICE_CALL_EXPIRED'
  $row=Journal
  Check ($row.delivery_state -ceq 'EXPIRED' -and [string]::IsNullOrEmpty([string]$row.completion_json)) 'CANONICAL_EXPIRY_SCRUBS_ONLY_DELIVERY_BUFFER'
  Check ($row.phase -ceq $before.phase -and $row.receipt_sha256 -ceq $before.receipt_sha256 -and $row.fingerprint -ceq $before.fingerprint) 'EXPIRY_DOES_NOT_REWRITE_EXECUTION_PROOF'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
  Check ($attempts -eq 1 -and $effectCount -eq 0) 'EXPIRED_ORPHAN_NEVER_REQUEUED_OR_REEXECUTED'
 }
 Case 'already-terminal-delivery-is-not-a-new-orphan' {
  $before=Seed-Orphan 'EXECUTED'
  foreach($terminal in @('ACKNOWLEDGED','EXPIRED')){
   Invoke-LocalDbExec 'UPDATE windows_relay_calls SET delivery_state=?,completion_json=NULL WHERE request_id=?' @($terminal,[string]$call.request_id)
   Repair-WindowsRelayJournal $cfg 'synthetic-token'
   $row=Journal
   Check ($row.delivery_state -ceq $terminal -and [string]::IsNullOrEmpty([string]$row.completion_json) -and $row.phase -ceq $before.phase) 'TERMINAL_DELIVERY_WITH_NO_BUFFER_MUST_STAY_TERMINAL'
  }
  Check ($attempts -eq 0 -and $effectCount -eq 0) 'NO_DUPLICATE_TERMINAL_TRANSPORT_OR_TOOL'
 }
 Case 'local-budget-remains-explicitly-unsupported-before-effect' {
  $call | Add-Member -NotePropertyName usage -NotePropertyValue ([pscustomobject]@{mode='LOCAL_BUDGET';units=1;budget_id='synthetic';period_key='synthetic'})
  Invoke-WindowsRelayCall $cfg 'synthetic-token' $call
  Check ($effectCount -eq 0 -and -not (Test-Path -LiteralPath $effectFile)) 'LOCAL_BUDGET_DENIED_BEFORE_ANY_EFFECT'
  Check ($attempts -eq 1 -and (Journal).phase -ceq 'FAILED' -and (Journal).delivery_state -ceq 'ACKNOWLEDGED') 'UNSUPPORTED_QUOTA_HAS_CORRELATED_DENIAL_NOT_FREE_EXECUTION'
  $body=$sent[0] | ConvertFrom-Json
  Check ($body.error_code -ceq 'WINDOWS_LOCAL_BUDGET_UNSUPPORTED' -and $body.result.mutation_performed -eq $false) 'EXISTING_WINDOWS_QUOTA_CAPABILITY_NOT_INVENTED'
 }
 foreach($status in @(401,403)){
  Case ('delivery-http-'+$status+'-keeps-pending-no-effects') {
   $before=Seed-Orphan 'FAILED'
   Repair-WindowsRelayJournal
   $saved=Check-Indeterminate $before
   $original=[string]$saved.completion_json
   $script:networkMode='revoked'+$status
   Denied {Repair-WindowsRelayJournal $cfg 'synthetic-token'} ('HTTP_'+$status)
   $row=Journal
   Check ($row.delivery_state -ceq 'PENDING' -and $row.completion_json -ceq $original) 'AUTH_DENIAL_NEVER_ACKS_OR_DROPS_DURABLE_RESULT'
   Check ($row.phase -ceq $before.phase -and $row.receipt_sha256 -ceq $before.receipt_sha256 -and $row.fingerprint -ceq $before.fingerprint) 'AUTH_DENIAL_PRESERVES_PHASE_RECEIPT_AND_INTENT'
   Check ($attempts -eq 1 -and $effectCount -eq 0) 'REVOKED_DELIVERY_NO_TOOL_EFFECT_OR_FALSE_SUCCESS'
  }
 }
 @{state=$(if($failures.Count){'FAIL_WINDOWS_JOURNAL_ORPHANS'}else{'PASS_WINDOWS_JOURNAL_ORPHANS_SOURCE_QA'});cases=$caseCount;checks=$checks.Count;failures=$failures.ToArray();source_sha256=$sourceSha;real_sqlite=$true;hard_crash_subprocesses=$hardCrashCount;windows_native=$native;native_vm_acceptance=$false;installed=$false;paired=$false;network_used=$false;fixture_cleanup_owner='PARENT_ONLY'} | ConvertTo-Json -Depth 7
 if($failures.Count){exit 1}
}finally{
 $env:LOCALAPPDATA=$priorLocal
 if(-not $CrashChild -and (Test-Path -LiteralPath $qa)){Remove-Item -LiteralPath $qa -Recurse -Force}
}
