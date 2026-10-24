param([string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'))
# Synthetic state and SQLite only. Portable mode maps the same SQLite ABI in
# this fixture; it does not replace the native Windows DLL or attest Windows QA.
$ErrorActionPreference='Stop'
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-056-windows-recovery-'+[guid]::NewGuid().ToString('N'))
$priorLocal=$env:LOCALAPPDATA
$native=[Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[object]
$caseCount=0
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function Denied([scriptblock]$Action,[string]$Code){
 $seen=$false
 try{& $Action | Out-Null}catch{$seen=$_.Exception.Message.Contains($Code)}
 Check $seen $Code
}
try {
 New-Item -ItemType Directory -Path $qa | Out-Null
 $env:LOCALAPPDATA=$qa
 $tokens=$null;$errors=$null
 $tree=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $AgentPath),[ref]$tokens,[ref]$errors)
 Check ($errors.Count -eq 0) 'AGENT_PARSE'
 $source=[IO.File]::ReadAllText((Resolve-Path $AgentPath))
 $sourceSha=(Get-FileHash -LiteralPath $AgentPath -Algorithm SHA256).Hash.ToLowerInvariant()
 $cut=$source.IndexOf('if ($args -contains "--version")')
 Check ($cut -gt 0) 'NO_DISPATCH_DEFINITIONS_BOUNDARY'
 . ([scriptblock]::Create($source.Substring(0,$cut)))
 Initialize-WinSqlite
 if(-not $native){
  Add-Type -TypeDefinition @'
using System;
using System.Reflection;
using System.Runtime.InteropServices;
public static class HaraRecoveryFixtureSqliteResolver {
 public static void Attach(Assembly assembly) { NativeLibrary.SetDllImportResolver(assembly,Resolve); }
 static IntPtr Resolve(string name,Assembly assembly,DllImportSearchPath? path) {
  return name=="winsqlite3.dll" ? NativeLibrary.Load("libsqlite3.so.0") : IntPtr.Zero;
 }
}
'@
  [HaraRecoveryFixtureSqliteResolver]::Attach([HaraWinSqlite].Assembly)
 }
 $resolverDb=Join-Path $qa 'sqlite-abi-proof.sqlite3'
 [HaraWinSqlite]::Execute($resolverDb,'CREATE TABLE qa (value TEXT)',@())
 [HaraWinSqlite]::Execute($resolverDb,'INSERT INTO qa(value) VALUES(?)',@('synthetic'))
 $rows=@([HaraWinSqlite]::Query($resolverDb,'SELECT value FROM qa',@()))
 Check ($rows.Count -eq 1 -and $rows[0].value -ceq 'synthetic') 'SQLITE_REAL_ABI_ROUNDTRIP'
 $required=@('Initialize-WindowsRelayStore','New-WindowsRelayClaim','Set-WindowsRelayPhase','Set-WindowsRelayCompletion','Send-WindowsRelayCompletion','Repair-WindowsRelayJournal','Invoke-WindowsRelayCall','Get-WindowsRelayFingerprint','Restore-WindowsRelayClaims','Get-WindowsRelayDeliveryError')
 $missing=@($required | Where-Object {-not (Get-Command $_ -CommandType Function -ErrorAction SilentlyContinue)})
 if($missing.Count){
  @{state='RED_WINDOWS_RECOVERY_API_ABSENT';missing=$missing;checks=$checks.Count;source_sha256=$sourceSha;real_sqlite=$true;windows_native=$native;installed=$false;paired=$false;network_used=$false} | ConvertTo-Json -Depth 5
  exit 2
 }
 # Native HTTP cmdlets expose an ErrorRecord with Response.StatusCode and
 # ErrorDetails JSON. Keep that shape in the fixture without network access.
 Add-Type -TypeDefinition @'
using System;
public sealed class HaraRecoveryFixtureHttpResponse {
 public int StatusCode { get { return 409; } }
}
public sealed class HaraRecoveryFixtureHttp409 : Exception {
 public HaraRecoveryFixtureHttp409() : base("synthetic HTTP 409") { }
 public HaraRecoveryFixtureHttpResponse Response { get { return new HaraRecoveryFixtureHttpResponse(); } }
}
'@
 function New-CanonicalHttp409 {
  $record=[Management.Automation.ErrorRecord]::new([HaraRecoveryFixtureHttp409]::new(),'SyntheticHttp409',[Management.Automation.ErrorCategory]::InvalidOperation,$null)
  $record.ErrorDetails=[Management.Automation.ErrorDetails]::new('{"ok":false,"code":"DEVICE_CALL_EXPIRED"}')
  return $record
 }
 # Recovery cases use the production journal with real SQLite. Only the
 # remote API and tool effect are replaced; the effect itself writes a file.
 function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  if(-not $Url.EndsWith('/api/device/calls/complete')){throw 'QA_UNEXPECTED_NETWORK_OPERATION'}
  $script:networkAttempts++
  $script:sentBodies.Add(($Body | ConvertTo-Json -Depth 20 -Compress))
  if($script:networkMode -eq 'offline'){throw 'SYNTHETIC_NETWORK_OFFLINE'}
  if($script:networkMode -eq 'incomplete'){return @{ok=$true}}
  if($script:networkMode -eq 'expired'){throw 'DEVICE_CALL_EXPIRED'}
  if($script:networkMode -eq 'http409'){throw (New-CanonicalHttp409)}
  return @{schema='hara.commander-device-call-result.v1';ok=$true;call_id=[string]$Body.call_id;state=[string]$Body.state}
 }
 function Invoke-Tool($Cfg,$Call) {
  $script:effectCount++
  [IO.File]::AppendAllText($script:effectFile,"effect`n")
  return @{state='PASS';mutation_performed=$true;bridge_receipt_sha256=('a'*64);result=@{stdout='SYNTHETIC_PRIVATE_RESULT';process_exit_code=0}}
 }
 function New-Case([string]$Name) {
  $script:Root=Join-Path $qa $Name
  New-Item -ItemType Directory -Path $script:Root | Out-Null
  $script:OperationsDb=Join-Path $script:Root 'operations.sqlite3'
  $script:ReceiptDir=Join-Path $script:Root 'receipts'
  $script:ConsoleEvents=Join-Path $script:Root 'console-events.jsonl'
  $script:ConfigPath=Join-Path $script:Root 'device.json'
  $script:cfg=[pscustomobject]@{base_url='https://commander.invalid';device_id='synthetic-device';tenant_id='synthetic-review';architecture='test';encrypted_device_token='synthetic-protected-not-a-credential';approval_mode='PERSISTENT_TRUSTED'}
  $script:EnrollmentContext=Get-EnrollmentContext $script:cfg
  $script:cfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $script:ConfigPath -Encoding UTF8
  $script:effectFile=Join-Path $script:Root 'effect.txt'
  $script:effectCount=0;$script:networkAttempts=0;$script:networkMode='ack'
  $script:sentBodies=New-Object Collections.Generic.List[string]
  $script:call=[pscustomobject]@{call_id='synthetic-call';request_id='synthetic-request';tool_id='hara.files.write';payload=[pscustomobject]@{path=$script:effectFile;content='SYNTHETIC_CALL_PAYLOAD_DO_NOT_PERSIST'};expires_at_utc=[DateTime]::UtcNow.AddMinutes(2).ToString('o')}
  Initialize-WindowsRelayStore | Out-Null
 }
 function Journal {
  $rows=@(Invoke-LocalDbQuery 'SELECT * FROM windows_relay_calls WHERE request_id=?' @('synthetic-request'))
  if($rows.Count -ne 1){throw 'QA_JOURNAL_ROW_NOT_UNIQUE'}
  return $rows[0]
 }
 function Case([string]$Name,[scriptblock]$Action) {
  $script:caseCount++
  try {
   New-Case $Name
   & $Action | Out-Null
   $checks.Add('CASE_'+$Name)
  } catch {
   $failures.Add(@{case=$Name;error=$_.Exception.Message})
  }
 }
 Case 'successful-effect-and-correlated-ack' {
  Invoke-WindowsRelayCall $cfg 'synthetic-token' $call
  $row=Journal
  Check ($script:effectCount -eq 1 -and [IO.File]::ReadAllLines($effectFile).Length -eq 1) 'SUCCESS_EFFECT_EXACTLY_ONCE'
  Check ($row.phase -ceq 'EXECUTED') 'SUCCESS_EXECUTED_PROOF_PRESERVED'
  Check ($row.receipt_sha256 -ceq ('a'*64)) 'ACK_PRESERVES_RECEIPT_BINDING'
  Check ($row.delivery_state -ceq 'ACKNOWLEDGED') 'SUCCESS_CORRELATED_ACK'
  Check ([string]::IsNullOrEmpty([string]$row.completion_json)) 'ACK_SCRUBS_PRIVATE_COMPLETION'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
  Check ($script:effectCount -eq 1) 'ACKED_CALL_NEVER_REEXECUTED'
 }
 Case 'claim-replay-and-payload-conflict' {
  New-WindowsRelayClaim $call
  Denied {New-WindowsRelayClaim $call} 'CALL_REPLAY_REFUSED'
  $changed=$call | Select-Object *
  $changed.payload=[pscustomobject]@{path=$effectFile;content='DIFFERENT_INTENT'}
  Denied {New-WindowsRelayClaim $changed} 'CALL_IDEMPOTENCY_CONFLICT'
  $row=Journal
  Check ($row.phase -ceq 'PREPARING') 'CLAIM_CONFLICT_PRESERVES_FIRST_INTENT'
  Check (($row | ConvertTo-Json -Depth 8 -Compress) -notmatch 'SYNTHETIC_CALL_PAYLOAD_DO_NOT_PERSIST') 'CALL_PAYLOAD_NOT_IN_JOURNAL'
 }
 Case 'fingerprint-ignores-json-property-order' {
  $first=$call | Select-Object *;$second=$call | Select-Object *
  $first.payload=[pscustomobject][ordered]@{a=1;b=[pscustomobject][ordered]@{c=2;d=3}}
  $second.payload=[pscustomobject][ordered]@{b=[pscustomobject][ordered]@{d=3;c=2};a=1}
  Check ((Get-WindowsRelayFingerprint $first) -ceq (Get-WindowsRelayFingerprint $second)) 'SEMANTIC_FINGERPRINT_STABLE'
 }
 Case 'delivery-loss-repairs-without-reexecution' {
  $script:networkMode='offline'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'SYNTHETIC_NETWORK_OFFLINE'
  $row=Journal
  Check ($script:effectCount -eq 1 -and $row.phase -ceq 'EXECUTED') 'OFFLINE_EFFECT_REMAINS_EXECUTED'
  Check ($row.delivery_state -ceq 'PENDING' -and ([string]$row.completion_json).Contains('SYNTHETIC_PRIVATE_RESULT')) 'OFFLINE_PRIVATE_OUTBOX_RETAINED'
  $original=[string]$row.completion_json
  $originalBody=$original | ConvertFrom-Json
  $script:networkMode='ack'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  $row=Journal
  Check ($script:effectCount -eq 1) 'REPAIR_DOES_NOT_INVOKE_TOOL'
  Check ($row.delivery_state -ceq 'ACKNOWLEDGED' -and [string]::IsNullOrEmpty([string]$row.completion_json)) 'REPAIR_ACK_SCRUBS_RESULT'
  $replayed=$script:sentBodies[$script:sentBodies.Count-1] | ConvertFrom-Json
  Check ($replayed.call_id -ceq $originalBody.call_id -and $replayed.state -ceq $originalBody.state) 'REPAIR_REUSES_TERMINAL_IDENTITY'
  Check (($replayed.result | ConvertTo-Json -Depth 20 -Compress) -ceq ($originalBody.result | ConvertTo-Json -Depth 20 -Compress)) 'REPAIR_REUSES_EXACT_RESULT'
  $attempts=$script:networkAttempts
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Check ($script:effectCount -eq 1 -and $script:networkAttempts -eq $attempts) 'ACK_IS_NOT_REPLAYED'
 }
 Case 'executing-crash-remains-uncertain' {
  New-WindowsRelayClaim $call
  Set-WindowsRelayPhase $call 'EXECUTING'
  # A real local effect exists, but no EXECUTED checkpoint proves its outcome.
  [IO.File]::WriteAllText($effectFile,'effect-before-crash')
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  $row=Journal
  Check ($row.phase -ceq 'UNCERTAIN') 'CRASH_NOT_RECLASSIFIED_AS_NO_EFFECT'
  Check ([IO.File]::ReadAllText($effectFile) -ceq 'effect-before-crash') 'CRASH_EFFECT_NOT_ROLLED_BACK'
  Check ($script:effectCount -eq 0) 'CRASH_REPAIR_NEVER_EXECUTES_TOOL'
  $terminal=$script:sentBodies[$script:sentBodies.Count-1] | ConvertFrom-Json
  Check ($terminal.state -ceq 'FAILED' -and $terminal.result.state -ceq 'INDETERMINATE') 'UNKNOWN_OUTCOME_NOT_FALSE_PASS'
  Check ($null -eq $terminal.result.mutation_performed) 'UNKNOWN_EFFECT_NOT_FALSE_NO_MUTATION'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
 }
 foreach($phase in @('PREPARING','RESERVED')){
  Case ('crash-before-effect-'+$phase.ToLowerInvariant()) {
   New-WindowsRelayClaim $call
   if($phase -ne 'PREPARING'){Set-WindowsRelayPhase $call $phase}
   Repair-WindowsRelayJournal $cfg 'synthetic-token'
   $row=Journal
   Check ($row.phase -ceq 'FAILED') ('NO_EFFECT_'+$phase+'_TERMINAL_FAILED')
   Check (-not (Test-Path -LiteralPath $effectFile)) ('NO_EFFECT_'+$phase+'_NO_FILE')
   Check ($script:effectCount -eq 0) ('NO_EFFECT_'+$phase+'_NO_EXECUTION')
   $terminal=$script:sentBodies[$script:sentBodies.Count-1] | ConvertFrom-Json
   Check ($terminal.state -ceq 'FAILED' -and $terminal.result.mutation_performed -eq $false) ('NO_EFFECT_'+$phase+'_HONEST_RESULT')
  }
 }
 Case 'incomplete-ack-keeps-result-pending' {
  $script:networkMode='incomplete'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_COMPLETION_NOT_ACKNOWLEDGED'
  $row=Journal
  Check ($row.phase -ceq 'EXECUTED' -and $row.delivery_state -ceq 'PENDING') 'INCOMPLETE_ACK_NOT_ADMITTED'
  Check (-not [string]::IsNullOrEmpty([string]$row.completion_json)) 'INCOMPLETE_ACK_RETAINS_PROOF'
  Check ($script:effectCount -eq 1) 'INCOMPLETE_ACK_ONE_EFFECT'
 }
 Case 'confirmed-expiry-preserves-executed-proof' {
  $script:networkMode='expired'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'DEVICE_CALL_EXPIRED'
  $row=Journal
  Check ($row.phase -ceq 'EXECUTED' -and $row.delivery_state -ceq 'EXPIRED') 'EXPIRY_DOES_NOT_REWRITE_EXECUTION'
  Check ([string]::IsNullOrEmpty([string]$row.completion_json)) 'CONFIRMED_EXPIRY_SCRUBS_RESULT'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
  Check ($script:effectCount -eq 1) 'EXPIRED_RESULT_NEVER_REEXECUTED'
 }
 Case 'local-budget-not-silently-unmetered' {
  $call | Add-Member -NotePropertyName usage -NotePropertyValue ([pscustomobject]@{mode='LOCAL_BUDGET';units=1;budget_id='synthetic';period_key='synthetic'})
  try{Invoke-WindowsRelayCall $cfg 'synthetic-token' $call}catch{
   Check ($_.Exception.Message.Contains('LOCAL_BUDGET')) 'LOCAL_BUDGET_EXPLICIT_DENIAL'
  }
  Check ($script:effectCount -eq 0 -and -not (Test-Path -LiteralPath $effectFile)) 'UNSUPPORTED_BUDGET_NO_EFFECT'
  $row=Journal
  Check ($row.phase -ceq 'FAILED') 'UNSUPPORTED_BUDGET_IS_TERMINAL'
 }
 Case 'completion-byte-limit-preserves-fence' {
  New-WindowsRelayClaim $call
  Set-WindowsRelayPhase $call 'EXECUTING'
  Denied {Set-WindowsRelayCompletion $call 'COMPLETED' @{stdout=('x'*(256*1024+8192))}} 'CALL_COMPLETION_TOO_LARGE'
  $row=Journal
  Check ($row.phase -ceq 'EXECUTING' -and [string]::IsNullOrEmpty([string]$row.completion_json)) 'OVERSIZE_CANNOT_FAKE_CHECKPOINT'
 }
 Case 'restore-authenticated-claim-before-journal-write' {
  $fingerprint=Get-WindowsRelayFingerprint $call
  $seed=[pscustomobject]@{request_id=[string]$call.request_id;call_id=[string]$call.call_id;fingerprint=$fingerprint}
  Restore-WindowsRelayClaims @($seed)
  $row=Journal
  Check ($row.phase -ceq 'PREPARING' -and $row.fingerprint -ceq $fingerprint) 'RESTORED_CLAIM_PRESERVES_AUTHENTICATED_FINGERPRINT'
  Check ($row.call_id -ceq $call.call_id -and $row.request_id -ceq $call.request_id) 'RESTORED_CLAIM_PRESERVES_AUTHENTICATED_IDS'
  Check ($script:effectCount -eq 0 -and -not (Test-Path -LiteralPath $effectFile)) 'RESTORED_CLAIM_DOES_NOT_EXECUTE'
  Restore-WindowsRelayClaims @($seed)
  Check (@(Invoke-LocalDbQuery 'SELECT request_id FROM windows_relay_calls').Count -eq 1) 'RESTORED_SEED_IS_IDEMPOTENT'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  $row=Journal
  Check ($row.phase -ceq 'FAILED' -and $row.delivery_state -ceq 'ACKNOWLEDGED') 'RESTORED_PREPARING_GETS_FAILED_TERMINAL'
  Check ($script:effectCount -eq 0 -and -not (Test-Path -LiteralPath $effectFile)) 'RESTORED_REPAIR_HAS_NO_EFFECT'
  $terminal=$script:sentBodies[$script:sentBodies.Count-1] | ConvertFrom-Json
  Check ($terminal.call_id -ceq $seed.call_id -and $terminal.state -ceq 'FAILED') 'RESTORED_COMPLETION_USES_ORIGINAL_CALL_ID'
  Check ($terminal.result.mutation_performed -eq $false) 'RESTORED_COMPLETION_PROVES_NO_MUTATION'
 }
 Case 'restored-seed-cannot-replace-existing-execution-proof' {
  $script:networkMode='offline'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'SYNTHETIC_NETWORK_OFFLINE'
  $original=Journal
  $before=$original | ConvertTo-Json -Depth 20 -Compress
  Check ($original.phase -ceq 'EXECUTED' -and -not [string]::IsNullOrEmpty([string]$original.completion_json)) 'SEED_CONFLICT_HAS_EXECUTION_PROOF_AND_PENDING_RESULT'
  $changed=$call | Select-Object *
  $changed.payload=[pscustomobject]@{path=$effectFile;content='different-authenticated-intent'}
  $bad=[pscustomobject]@{request_id=[string]$call.request_id;call_id=[string]$call.call_id;fingerprint=(Get-WindowsRelayFingerprint $changed)}
  Denied {Restore-WindowsRelayClaims @($bad)} 'CALL_IDEMPOTENCY_CONFLICT'
  $bad.call_id='different-call';$bad.fingerprint=[string]$original.fingerprint
  Denied {Restore-WindowsRelayClaims @($bad)} 'CALL_IDEMPOTENCY_CONFLICT'
  $after=Journal | ConvertTo-Json -Depth 20 -Compress
  Check ($after -ceq $before) 'SEED_CONFLICT_DOES_NOT_CHANGE_PROOF_OR_RESULT'
  Check ($script:effectCount -eq 1 -and [IO.File]::ReadAllLines($effectFile).Length -eq 1) 'SEED_CONFLICT_DOES_NOT_REPEAT_EFFECT'
  Check ($script:networkAttempts -eq 1) 'SEED_CONFLICT_DOES_NOT_SEND_CONTRADICTORY_RESULT'
  $script:networkMode='ack'
  Repair-WindowsRelayJournal $cfg 'synthetic-token'
  Check ((Journal).delivery_state -ceq 'ACKNOWLEDGED' -and $script:effectCount -eq 1) 'ORIGINAL_RESULT_REMAINS_DELIVERABLE_AFTER_SEED_CONFLICT'
 }
 Case 'canonical-http409-expiry-scrubs-outbox-without-replay' {
  $record=New-CanonicalHttp409
  Check ((Get-SafeErrorCode $record) -ceq 'HTTP_409') 'HTTP_409_RESPONSE_STATUS_RECOGNIZED'
  Check ((Get-WindowsRelayDeliveryError $record) -ceq 'DEVICE_CALL_EXPIRED') 'HTTP_409_CANONICAL_CODE_RECOGNIZED'
  $script:networkMode='http409'
  $seen=$null
  try{Invoke-WindowsRelayCall $cfg 'synthetic-token' $call}catch{$seen=$_}
  Check ($null -ne $seen -and (Get-WindowsRelayDeliveryError $seen) -ceq 'DEVICE_CALL_EXPIRED') 'HTTP_409_PROPAGATES_CANONICAL_EXPIRY'
  $row=Journal
  Check ($row.phase -ceq 'EXECUTED' -and $row.receipt_sha256 -ceq ('a'*64)) 'HTTP_409_PRESERVES_EXECUTION_AND_RECEIPT'
  Check ($row.delivery_state -ceq 'EXPIRED' -and [string]::IsNullOrEmpty([string]$row.completion_json)) 'HTTP_409_CONFIRMED_EXPIRY_SCRUBS_OUTBOX'
  Denied {Invoke-WindowsRelayCall $cfg 'synthetic-token' $call} 'CALL_REPLAY_REFUSED'
  Check ($script:effectCount -eq 1 -and $script:networkAttempts -eq 1) 'HTTP_409_DOES_NOT_REPLAY_EFFECT_OR_DELIVERY'
 }
 Case 'deadline-before-execution-never-has-an-effect' {
  $script:WindowsRelayDeadline=(Get-WindowsRelayNow)-1
  try{Invoke-WindowsRelayCall $cfg 'synthetic-token' $call}finally{$script:WindowsRelayDeadline=$null}
  $row=Journal
  Check ($script:effectCount -eq 0 -and -not (Test-Path -LiteralPath $effectFile)) 'EXPIRED_CALL_NO_EFFECT'
  Check ($row.phase -ceq 'FAILED' -and $row.delivery_state -ceq 'ACKNOWLEDGED') 'EXPIRED_CALL_TERMINAL_CORRELATED'
 }
 Case 'approval-cannot-extend-execution-deadline' {
  function Get-OperatorSession {return [pscustomobject]@{owner_pid=42;owner_started_at_utc='synthetic-marker'}}
  function Invoke-LocalActionApproval { $script:WindowsRelayDeadline=(Get-WindowsRelayNow)-1 }
  function Invoke-WithLocalApprovalLock([scriptblock]$ApprovalCriticalSection){& $ApprovalCriticalSection}
  $ask=$cfg|Select-Object *;$ask.approval_mode='ASK_EVERY_ACTION'
  $script:WindowsRelayDeadline=(Get-WindowsRelayNow)+30
  try{Denied {Assert-StarterMutationAuthorized $ask $call} 'DEVICE_CALL_EXPIRED'}finally{$script:WindowsRelayDeadline=$null}
  Check ($script:effectCount -eq 0) 'APPROVAL_EXPIRY_NO_EFFECT'
 }
 $state=if($failures.Count){'FAIL_WINDOWS_RECOVERY_CONTRACT'}elseif($native){'PASS_NATIVE_WINDOWS_RECOVERY_SQLITE_NO_INSTALL'}else{'PASS_PORTABLE_SQLITE_NOT_WINDOWS_ACCEPTANCE'}
 @{state=$state;checks=$checks.Count;cases=$caseCount;passed=$checks.ToArray();failures=$failures.ToArray();source_sha256=$sourceSha;real_sqlite=$true;windows_native=$native;installed=$false;paired=$false;network_used=$false} | ConvertTo-Json -Depth 8
 if($failures.Count){exit 1}
} finally {
 $env:LOCALAPPDATA=$priorLocal
 if(Test-Path -LiteralPath $qa){Remove-Item -LiteralPath $qa -Recurse -Force}
}
