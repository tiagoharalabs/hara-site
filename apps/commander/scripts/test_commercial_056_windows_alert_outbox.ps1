param([string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'))
# #163 source QA: real private SQLite and production outbox functions. Only the
# authenticated remote boundary and clock are fixtures. This is not Windows VM
# acceptance, delivery to a customer, Agent installation, or release admission.
$ErrorActionPreference='Stop'
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-056-windows-alerts-'+[guid]::NewGuid().ToString('N'))
$priorLocal=$env:LOCALAPPDATA
$native=[Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[object]
$caseCount=0
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
try {
 New-Item -ItemType Directory -Path $qa | Out-Null
 $env:LOCALAPPDATA=$qa
 $tokens=$null;$errors=$null
 $tree=[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $AgentPath),[ref]$tokens,[ref]$errors)
 Check ($errors.Count -eq 0) 'AGENT_PARSE'
 $source=[IO.File]::ReadAllText((Resolve-Path $AgentPath))
 $sourceSha=(Get-FileHash -LiteralPath $AgentPath -Algorithm SHA256).Hash.ToLowerInvariant()
 $cut=$source.IndexOf('if ($args -contains "--version")')
 Check ($cut -gt 0) 'DEFINITIONS_ONLY_NO_AGENT_DISPATCH'
 . ([scriptblock]::Create($source.Substring(0,$cut)))
 Initialize-WinSqlite
 if(-not $native){
  Add-Type -TypeDefinition @'
using System;
using System.Reflection;
using System.Runtime.InteropServices;
public static class HaraAlertFixtureSqliteResolver {
 public static void Attach(Assembly assembly) { NativeLibrary.SetDllImportResolver(assembly,Resolve); }
 static IntPtr Resolve(string name,Assembly assembly,DllImportSearchPath? path) {
  return name=="winsqlite3.dll" ? NativeLibrary.Load("libsqlite3.so.0") : IntPtr.Zero;
 }
}
'@
  [HaraAlertFixtureSqliteResolver]::Attach([HaraWinSqlite].Assembly)
 }
 $proof=Join-Path $qa 'sqlite-abi-proof.sqlite3'
 [HaraWinSqlite]::Execute($proof,'CREATE TABLE proof(value TEXT)',@())
 [HaraWinSqlite]::Execute($proof,'INSERT INTO proof VALUES(?)',@('synthetic'))
 Check (@([HaraWinSqlite]::Query($proof,'SELECT value FROM proof',@()))[0].value -ceq 'synthetic') 'SQLITE_REAL_ABI'
 $required=@('Initialize-WindowsRecoveryOutbox','Add-WindowsRecoveryEvent','Send-WindowsRecoveryEvents','Get-WindowsRecoveryNow','Get-WindowsRecoveryProgressKind')
 $missing=@($required | Where-Object {-not (Get-Command $_ -CommandType Function -ErrorAction SilentlyContinue)})
 if($missing.Count){
  @{state='RED_WINDOWS_ALERT_OUTBOX_API_ABSENT';missing=$missing;checks=$checks.Count;source_sha256=$sourceSha;real_sqlite=$true;windows_native=$native;installed=$false;network_used=$false} | ConvertTo-Json -Depth 5
  exit 2
 }
 function Get-WindowsRecoveryNow {return [long]$script:clockMs}
 function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25){
  if($Url -cne 'https://commander.invalid/api/device/recovery-events'){throw 'QA_UNEXPECTED_ENDPOINT'}
  if($Token -cne 'synthetic-device-token-not-a-real-credential'){throw 'QA_WRONG_AUTHENTICATED_DEVICE_TOKEN'}
  Check ($Timeout -gt 0 -and $Timeout -le 25) 'NETWORK_TIMEOUT_BOUNDED'
  $script:attempts++
  $copy=$Body | ConvertTo-Json -Depth 12 -Compress | ConvertFrom-Json
  $script:sent.Add($copy)
  if($script:networkMode -eq 'offline'){throw 'SYNTHETIC_NETWORK_OFFLINE'}
  if($script:networkMode -eq 'revoked'){throw 'HTTP_403'}
  if($script:networkMode -eq 'unauthorized'){throw 'HTTP_401'}
  if($script:networkMode -eq 'incomplete'){return @{ok=$true}}
  if($script:networkMode -eq 'human'){return @{schema='hara.commander.recovery-portal-ack.v1';ack='PORTAL_ACKNOWLEDGED';event_id=('HARA-REC-'+('a'*48));client_event_id=$Body.event_id;external_delivery_confirmed=$false}}
  return @{schema='hara.commander.recovery-ingest.v1';ack='PERSISTED';event_id=$(if($script:networkMode -eq 'bad-server-id'){'fake-receipt'}else{'HARA-REC-'+('a'*48)});client_event_id=$(if($script:networkMode -eq 'wrong-client'){'f'*32}else{$Body.event_id});duplicate=$false;external_delivery_confirmed=$false}
 }
 function New-Case([string]$Name){
  $script:Root=Join-Path $qa $Name
  New-Item -ItemType Directory -Path $script:Root | Out-Null
  $script:OperationsDb=Join-Path $script:Root 'operations.sqlite3'
  $script:ConfigPath=Join-Path $script:Root 'device.json'
  $script:cfg=[pscustomobject]@{base_url='https://commander.invalid';device_id='synthetic-device';tenant_id='synthetic-review';architecture='test';encrypted_device_token='synthetic-protected-not-a-real-credential';approval_mode='PERSISTENT_TRUSTED'}
  $script:EnrollmentContext=Get-EnrollmentContext $script:cfg
  $script:cfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $script:ConfigPath -Encoding UTF8
  $script:clockMs=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $script:attempts=0;$script:networkMode='ack'
  $script:sent=New-Object Collections.Generic.List[object]
  $script:outboxPath=[string](Initialize-WindowsRecoveryOutbox $script:cfg)
 }
 function Add([string]$Worker,[string]$State){
  $event=Add-WindowsRecoveryEvent $script:cfg $Worker $State
  if($null -ne $event){return $event | ConvertTo-Json -Depth 10 -Compress | ConvertFrom-Json}
 }
 function Send([bool]$Authorized=$true){Send-WindowsRecoveryEvents $script:cfg 'synthetic-device-token-not-a-real-credential' $Authorized | Out-Null}
 function Advance { $script:clockMs+=360000 }
 function Case([string]$Name,[scriptblock]$Action){
  $script:caseCount++
  try{New-Case $Name;& $Action | Out-Null;$checks.Add('CASE_'+$Name)}catch{$failures.Add(@{case=$Name;error=$_.Exception.Message;stack=$_.ScriptStackTrace})}
 }
 Case 'real-independent-private-sqlite' {
  Check ([IO.Path]::GetFullPath($outboxPath) -cne [IO.Path]::GetFullPath($OperationsDb)) 'ALERT_DATABASE_SEPARATE_FROM_TOOL_JOURNAL'
  Check ((Split-Path $outboxPath) -ceq (Split-Path $OperationsDb)) 'ALERT_DATABASE_ENROLLMENT_DIRECTORY'
  $event=Add 'executor' 'STALLED'
  Check (Test-Path -LiteralPath $outboxPath -PathType Leaf) 'ALERT_SQLITE_PERSISTED_FILE'
  $bytes=[IO.File]::ReadAllBytes($outboxPath)
  Check ([Text.Encoding]::ASCII.GetString($bytes,0,15) -ceq 'SQLite format 3') 'ALERT_SQLITE_REAL_HEADER'
  # sqlite3_open16 can initialize UTF-16LE storage. Inspect each supported
  # SQLite text encoding so the privacy check cannot miss NUL-separated text.
  foreach($encoding in @([Text.Encoding]::UTF8,[Text.Encoding]::Unicode,[Text.Encoding]::BigEndianUnicode)){
   $raw=$encoding.GetString($bytes)
   Check (-not $raw.Contains('synthetic-device-token-not-a-real-credential') -and -not $raw.Contains('synthetic-protected-not-a-real-credential')) ('NO_DEVICE_CREDENTIAL_BYTES_IN_ALERT_DB_'+$encoding.WebName)
  }
  $wanted=@('schema','event_id','client_incident_key','transition_seq','worker','state','observed_at_utc','detector') | Sort-Object
  Check (($event.PSObject.Properties.Name | Sort-Object) -join ',' -ceq ($wanted -join ',')) 'METADATA_ONLY_ENVELOPE_ALLOWLIST'
  Check ($event.schema -ceq 'hara.commander.recovery-alert.proposal.v1' -and $event.detector -ceq 'WINDOWS_JOB_GUARDIAN') 'EXACT_ADMITTED_COMPATIBLE_ENVELOPE'
  Check ($event.event_id -cmatch '^[0-9a-f]{32}$' -and $event.client_incident_key -cmatch '^[0-9a-f]{32}$') 'STABLE_VALID_EVENT_AND_INCIDENT_IDENTITIES'
 }
 Case 'sequences-restart-dedup-and-new-incident' {
  $first=Add 'executor' 'STALLED'
  Add 'executor' 'STALLED' | Out-Null
  $sameIncident=Add 'executor' 'RECOVERING'
  Initialize-WindowsRecoveryOutbox $cfg | Out-Null
  $recovered=Add 'executor' 'RECOVERED'
  $second=Add 'executor' 'STALLED'
  $heartbeat=Add 'heartbeat' 'STALLED'
  Check ($first.transition_seq -eq 1 -and $sameIncident.transition_seq -eq 2 -and $recovered.transition_seq -eq 3) 'CONTIGUOUS_SEQUENCE_SURVIVES_REINITIALIZATION'
  Check ($first.client_incident_key -ceq $sameIncident.client_incident_key -and $first.client_incident_key -ceq $recovered.client_incident_key) 'ONE_INCIDENT_THROUGH_RECOVERY'
  Check ($second.client_incident_key -cne $first.client_incident_key -and $second.transition_seq -eq 1) 'LATER_FAILURE_NEW_INCIDENT'
  Check ($heartbeat.client_incident_key -cne $second.client_incident_key -and $heartbeat.transition_seq -eq 1) 'WORKER_INCIDENTS_INDEPENDENT'
  foreach($n in 1..8){Send;Advance}
  Check ($attempts -eq 5) 'DUPLICATE_LOCAL_TRANSITION_NOT_ENQUEUED'
  Check (@($sent | Select-Object -ExpandProperty event_id -Unique).Count -eq 5) 'UNIQUE_EVENT_PER_TRANSITION'
 }
 Case 'persisted-ack-stops-ingest-retries-without-delivery-claim' {
  $event=Add 'heartbeat' 'STALLED'
  Send
  Initialize-WindowsRecoveryOutbox $cfg | Out-Null
  foreach($n in 1..5){Advance;Send}
  Check ($attempts -eq 1) 'PERSISTED_REMAINS_TERMINAL_AFTER_RESTART'
  Check ($sent[0].event_id -ceq $event.event_id) 'PERSISTED_ACK_CORRELATED_WITH_ORIGINAL_EVENT'
  $rows=@([HaraWinSqlite]::Query($outboxPath,'SELECT state,server_event_id FROM recovery_events WHERE event_id=?',@([string]$event.event_id)))
  Check ($rows.Count -eq 1 -and $rows[0].state -ceq 'PERSISTED' -and $rows[0].server_event_id -ceq ('HARA-REC-'+('a'*48))) 'PERSISTED_NOT_RECIPIENT_OR_HUMAN_ACK'
 }
 Case 'offline-restart-retry-same-event-before-next-sequence' {
  $event=Add 'executor' 'STALLED'
  Add 'executor' 'RECOVERING' | Out-Null
  $script:networkMode='offline'
  Send
  Check ($attempts -eq 1) 'OFFLINE_ONE_BOUNDED_ATTEMPT'
  Send
  Check ($attempts -eq 1) 'RETRY_BACKOFF_PREVENTS_HOT_LOOP'
  Initialize-WindowsRecoveryOutbox $cfg | Out-Null
  $script:networkMode='ack'
  Advance;Send
  Advance;Send
  Check ($attempts -eq 3) 'OUTAGE_RETRY_THEN_NEXT_TRANSITION'
  Check ($sent[0].event_id -ceq $sent[1].event_id -and $sent[0].client_incident_key -ceq $sent[1].client_incident_key) 'OUTAGE_REUSES_DURABLE_IDEMPOTENCY_KEY'
  Check ($sent[0].transition_seq -eq 1 -and $sent[1].transition_seq -eq 1 -and $sent[2].transition_seq -eq 2) 'NEXT_SEQUENCE_WAITED_FOR_PERSISTED_RECEIPT'
  Check (($sent[0] | ConvertTo-Json -Depth 10 -Compress) -ceq ($sent[1] | ConvertTo-Json -Depth 10 -Compress)) 'RETRY_REUSES_EXACT_ENVELOPE'
 }
 foreach($badAck in @('incomplete','wrong-client','bad-server-id','human')){
  Case ('reject-'+$badAck+'-ack') {
   $event=Add 'executor' 'STALLED'
   $script:networkMode=$badAck
   Send
   Check ($attempts -eq 1) ('ONE_ATTEMPT_'+$badAck)
   $script:networkMode='ack'
   Advance;Send
   Check ($attempts -eq 2 -and $sent[0].event_id -ceq $sent[1].event_id) ('UNPROVEN_ACK_RETRIED_SAME_ID_'+$badAck)
   Advance;Send
   Check ($attempts -eq 2) ('VALID_PERSISTED_ACK_TERMINATES_'+$badAck)
  }
 }
 Case 'stop-pauses-network-with-durable-pending-event' {
  Add 'executor' 'STALLED' | Out-Null
  Send $false
  Advance;Send $false
  Check ($attempts -eq 0) 'NO_TRANSPORT_WITHOUT_LOCAL_AUTHORIZATION'
  Send $true
  Check ($attempts -eq 1) 'PENDING_RESUMES_ONLY_WITH_AUTHORIZATION'
 }
 foreach($denial in @('revoked','unauthorized')){
  Case ('latch-'+$denial+'-until-new-enrollment') {
   Add 'heartbeat' 'STALLED' | Out-Null
   $script:networkMode=$denial
   Send
   Initialize-WindowsRecoveryOutbox $cfg | Out-Null
   $script:networkMode='ack'
   foreach($n in 1..3){Advance;Send}
   Check ($attempts -eq 1) ('AUTH_DENIAL_PERSISTENT_LATCH_'+$denial)
  }
 }
 Case 'finite-retry-budget-survives-restart' {
  Add 'executor' 'DEGRADED' | Out-Null
  $script:networkMode='offline'
  foreach($n in 1..40){Advance;Initialize-WindowsRecoveryOutbox $cfg | Out-Null;Send}
  $capped=$attempts
  Check ($capped -gt 1 -and $capped -le 32) 'FINITE_DURABLE_RETRY_BUDGET'
  foreach($n in 1..5){Advance;Send}
  Check ($attempts -eq $capped) 'EXHAUSTED_EVENT_NEVER_HOT_REPLAYS'
 }
 Case 'changed-enrollment-cannot-reuse-outbox' {
  Add 'executor' 'STALLED' | Out-Null
  $cfg.device_id='different-synthetic-device'
  $cfg.encrypted_device_token='different-protected-fixture'
  try{Send}catch{}
  Check ($attempts -eq 0) 'OLD_ENROLLMENT_ALERTS_NOT_SENT_AS_NEW_DEVICE'
 }
 Case 'invalid-metadata-never-reaches-network' {
  foreach($pair in @(@('untrusted-worker','STALLED'),@('executor','DELIVERED'),@('executor','payload=private'))){
   $denied=$false
   try{Add ([string]$pair[0]) ([string]$pair[1]) | Out-Null}catch{$denied=$true}
   Check $denied 'INVALID_GUARDIAN_EVENT_DENIED'
  }
  Send
  Check ($attempts -eq 0) 'INVALID_METADATA_NOT_PERSISTED_OR_TRANSMITTED'
 }
 Case 'route-auth-is-not-enrollment-revocation' {
  Add 'executor' 'STALLED' | Out-Null
  $script:networkMode='revoked'
  $result=Send-WindowsRecoveryEvents $cfg 'synthetic-device-token-not-a-real-credential' $true
  Check ($result.state -ceq 'BLOCKED_AUTH') 'AUTHORITY_DENIAL_SCOPED_TO_ALERT_TRANSPORT'
  Check ((Get-WindowsRecoveryProgressKind $result.state) -ceq 'ALERTS_BLOCKED') 'ALERT_DENIAL_CANNOT_REVOKE_BASE_AGENT'
  Check ((Get-WindowsRecoveryProgressKind 'PERSISTED') -ceq 'ALERTS_PERSISTED') 'ONLY_CORRELATED_PERSISTENCE_PROVES_ALERT_RECOVERY'
 }
 Case 'exhausted-alert-is-visible-after-restart' {
  Add 'executor' 'STALLED' | Out-Null
  $script:networkMode='offline'
  foreach($n in 1..33){Advance;Send}
  Initialize-WindowsRecoveryOutbox $cfg | Out-Null
  $result=Send-WindowsRecoveryEvents $cfg 'synthetic-device-token-not-a-real-credential' $true
  Check ($result.state -ceq 'EXHAUSTED') 'EXHAUSTED_ALERT_NOT_SILENT_EMPTY_QUEUE'
  Check ((Get-WindowsRecoveryProgressKind $result.state) -ceq 'ALERTS_BLOCKED') 'EXHAUSTION_VISIBLE_TO_GUARDIAN'
 }
 $result=@{state=$(if($failures.Count){'FAIL_WINDOWS_ALERT_OUTBOX'}else{'PASS_WINDOWS_ALERT_OUTBOX_SOURCE_QA'});checks=$checks.Count;cases=$caseCount;failures=$failures.ToArray();source_sha256=$sourceSha;real_sqlite=$true;windows_native=$native;native_vm_acceptance=$false;installed=$false;paired=$false;network_used=$false}
 $result | ConvertTo-Json -Depth 7
 if($failures.Count){exit 1}
} finally {
 $env:LOCALAPPDATA=$priorLocal
 if(Test-Path -LiteralPath $qa){Remove-Item -LiteralPath $qa -Recurse -Force}
}
