param([string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'))
# #163: extract function definitions from the actual .56 source using the AST.
# No Agent main, installed Agent, enrollment, credential, native wake creation,
# network, scheduled task, VM, installer, signer, or runtime mutation is used.
# The only OS boundary fixture is the named AutoResetEvent's Set/WaitOne API.
$ErrorActionPreference='Stop'
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[object]
$caseCount=0
$baselineSha='ce7ef84bde9158b484d64f43841087f4e6e10d76a9e9e6e01d8c126f77759971'
$origin='https://hara-commander-r163-canary-20261024.tiago-sartori.workers.dev'
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function EventV2-Denied($Cfg,[string]$Name){
 $denied=$false
 try{
  $result=Test-WindowsEventV2Dev $Cfg
  $denied=$result -is [bool] -and -not $result
 }catch{
  # Explicit invalid opt-in may stop config loading instead of silently
  # falling back to V1. Only these admission failures count as denial;
  # unrelated exceptions and non-boolean results remain test failures.
  $denied=$_.Exception.Message -cin @('EVENT_V2_DEV_FLAG_INVALID','EVENT_V2_DEV_SCOPE_INVALID')
 }
 Check $denied $Name
}
function Case([string]$Name,[scriptblock]$Action){
 $script:caseCount++
 try{& $Action | Out-Null;$checks.Add('CASE_'+$Name)}catch{$failures.Add(@{case=$Name;error=$_.Exception.Message;stack=$_.ScriptStackTrace})}
}
function Text-Sha256([string]$Text){
 $hash=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text.Replace("`r`n","`n"))))).Replace('-','').ToLowerInvariant()}
 finally{$hash.Dispose()}
}
$tokens=$null;$errors=$null
$tree=[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $AgentPath),[ref]$tokens,[ref]$errors)
Check ($errors.Count -eq 0) 'EXACT_0356_SOURCE_PARSES'
$source=[IO.File]::ReadAllText((Resolve-Path $AgentPath))
$sourceSha=(Get-FileHash -LiteralPath $AgentPath -Algorithm SHA256).Hash.ToLowerInvariant()
Check ($source -match '\$AgentVersion\s*=\s*"0\.3\.56"') 'ACTUAL_COMMERCIAL_AGENT_VERSION_0356'
$functions=@{}
foreach($node in $tree.EndBlock.Statements){
 if($node -is [Management.Automation.Language.FunctionDefinitionAst]){
  $functions[$node.Name]=$node
  . ([scriptblock]::Create($node.Extent.Text))
 }
}
# These exact function definitions are the p02-e70512a6 source preimage.
# Normalize CRLF only when hashing AST text, so native Windows checkout line
# endings do not change the semantic source guard. No implementation is run.
$unchanged=@{
 'Get-PlainText'='894d56836515bc2841d0817dd0bd6c76abc7b4d9e4fca40c91e9f96b445a651b'
 'Set-LocalStoreAcl'='fed2b86164265e0efdcfcb2985d29f62e31682dd477d7939c482d824103cd887'
 'Get-WindowsRelayFingerprint'='33bfb585d2ca7a32b0ce7dbc5b1269b26fa90b11b1c3095125ade51bc047897e'
 'New-WindowsRelayClaim'='c8e42a1c5ce1dd1c474a5a6cae658549106ec1ddb7461bbafdf95292a792323e'
 'Set-WindowsRelayPhase'='4b5c6154fceb9cd5fad388210a43391b84c0fb113670262427408b21dcf2b2ae'
 'Set-WindowsRelayCompletion'='642a3aa6fb5f4e3a7d3a9e97722c1407cdd194d8e20107fa246d33ec91ef9b95'
 'Invoke-WindowsRelayCall'='8de449cff0cc5688b7ef6b3daf725d7bd018130ba70751350363cbc6430f09f2'
 'Stop-WindowsRelayProcess'='ba68e131a2338f73b83633c78d742d142a2ff0215bc5b355c5de9ed33b8bf6af'
 'Stop-WindowsRelayChild'='d7774bba1c42253b86ccb39691d8b620b1b0bc4d057b2509709692d3acdf1d7b'
 'Restore-WindowsRelayClaims'='d11eb60ad8f935db91f3ce9b9f42c11c60b6b64d4f18fb3fd08d811360aaa6cb'
}
foreach($name in $unchanged.Keys){
 Check ($functions.ContainsKey($name) -and (Text-Sha256 $functions[$name].Extent.Text) -ceq $unchanged[$name]) ('P02_BASELINE_UNCHANGED_'+$name)
}
# Authorized journal orphan delta: the other P02 definitions stay pinned above.
# Executable crash/restart/receipt/quota cases live in the adjacent orphan harness.
Check ((Text-Sha256 $functions['Repair-WindowsRelayJournal'].Extent.Text) -ceq 'c81acc04f79292ec3ac043ecf0b19e18a50109ede9401777bb432cd50e47334b') 'REVIEWED_WINDOWS_JOURNAL_ORPHAN_FIX'
$required=@('Test-WindowsEventV2Dev','New-WindowsEventV2WakeSignal','New-WindowsEventV2DrainGate','Wait-WindowsEventV2Work','Set-WindowsEventV2ClaimResult')
$missing=@($required | Where-Object {-not $functions.ContainsKey($_)})
if($missing.Count){
 @{state='RED_COMMERCIAL_0356_EVENT_V2_API_ABSENT';missing=$missing;checks=$checks.Count;source_sha256=$sourceSha;baseline_p02_sha256=$baselineSha;installed=$false;network_used=$false;native_wake_acl_acceptance=$false;windows_native=([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)} | ConvertTo-Json -Depth 5
 exit 2
}
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
public sealed class HaraCommercialEventV2WakeFixture {
 public bool Pending;
 public int Sets,Resets,Waits;
 public readonly List<int> WaitTimeouts=new List<int>();
 public bool Set(){Sets++;Pending=true;return true;}
 public bool Reset(){Resets++;Pending=false;return true;}
 public bool WaitOne(int milliseconds){
  Waits++;WaitTimeouts.Add(milliseconds);
  if(milliseconds!=500)throw new InvalidOperationException("QA_LOCAL_WAIT_MUST_ALLOW_322_PROGRESS");
  bool ready=Pending;Pending=false;return ready;
 }
}
'@
function New-Config {
 return [pscustomobject]@{event_v2_dev_enabled=$true;environment='DEV';base_url=$origin;device_id='synthetic-device';tenant_id='synthetic-review';approval_mode='PERSISTENT_TRUSTED'}
}
function Reachable-Functions([string[]]$Roots){
 $seen=New-Object 'Collections.Generic.HashSet[string]'
 $todo=New-Object 'Collections.Generic.Queue[string]'
 foreach($rootName in $Roots){$todo.Enqueue($rootName)}
 while($todo.Count -gt 0){
  $name=$todo.Dequeue()
  if(-not $functions.ContainsKey($name) -or -not $seen.Add($name)){continue}
  $commands=@($functions[$name].Body.FindAll({param($n)$n -is [Management.Automation.Language.CommandAst]},$true))
  foreach($command in $commands){$called=$command.GetCommandName();if($called -and $functions.ContainsKey($called)){$todo.Enqueue($called)}}
 }
 return ,$seen
}
Case 'default-off-and-one-explicit-dev-origin' {
 Check (-not (Test-WindowsEventV2Dev $null)) 'NULL_CONFIG_DISABLED'
 Check (-not (Test-WindowsEventV2Dev ([pscustomobject]@{}))) 'EMPTY_CONFIG_DISABLED'
 $cfg=New-Config
 Check (Test-WindowsEventV2Dev $cfg) 'EXPLICIT_BOOL_DEV_AND_EXACT_CANARY_ORIGIN_ENABLED'
 $cfg.PSObject.Properties.Remove('event_v2_dev_enabled')
 Check (-not (Test-WindowsEventV2Dev $cfg)) 'MISSING_OPT_IN_DISABLED'
 $cfg=New-Config;$cfg.event_v2_dev_enabled=$false
 Check (-not (Test-WindowsEventV2Dev $cfg)) 'EXPLICIT_FALSE_DISABLED'
}
Case 'opt-in-type-cannot-coerce-authority' {
 foreach($flag in @('true','TRUE','false',1,0,@($true),([pscustomobject]@{value=$true}))){
  $cfg=New-Config;$cfg.event_v2_dev_enabled=$flag
  EventV2-Denied $cfg 'NON_BOOLEAN_OPT_IN_DENIED'
 }
}
Case 'prod-and-missing-environment-never-enable' {
 foreach($environment in @('PROD','production','DEV ','dev','',1,$null)){
  $cfg=New-Config;$cfg.environment=$environment
  EventV2-Denied $cfg 'ONLY_EXACT_DEV_ENVIRONMENT_ADMITTED'
 }
 $cfg=New-Config;$cfg.PSObject.Properties.Remove('environment')
 EventV2-Denied $cfg 'MISSING_ENVIRONMENT_DISABLED'
}
Case 'origin-alias-path-query-userinfo-fail-closed' {
 $urls=@(
  ($origin+'/'),($origin+'/api/device/channel'),($origin+'?environment=DEV'),($origin+'#DEV'),
  ($origin.Replace('https://','http://')),($origin.Replace('https://','wss://')),
  ($origin.Replace('https://','https://user@')),($origin.Replace('https://','https://user:password@')),
  ($origin.Replace('.workers.dev','.workers.dev.evil.invalid')),($origin+':443'),
  'https://commander.haralabs.com.br',($origin.ToUpperInvariant()),(' '+$origin),($origin+' '),
  '',$null
 )
 foreach($url in $urls){
  $cfg=New-Config;$cfg.base_url=$url
  EventV2-Denied $cfg 'NON_EXACT_ORIGIN_NOT_ADMITTED'
 }
}
Case 'startup-drain-is-bounded-and-yields-before-next-batch' {
 $signal=[HaraCommercialEventV2WakeFixture]::new()
 $gate=New-WindowsEventV2DrainGate $signal
 $watch=[Diagnostics.Stopwatch]::StartNew()
 for($i=1;$i -le 17;$i++){
  Check (Wait-WindowsEventV2Work $gate) 'BACKLOG_CLAIM_HAS_DRAIN_PERMISSION'
  if($i -le 8){Check ($signal.Waits -eq 0) 'FIRST_STARTUP_BATCH_HAS_AT_MOST_EIGHT_DIRECT_CLAIMS'}
  Set-WindowsEventV2ClaimResult $gate $true
 }
 $watch.Stop()
 Check ($signal.Waits -ge 2 -and $signal.Sets -ge 2) 'BACKLOG_REQUEUED_BETWEEN_BOUNDED_BATCHES'
 Check ($watch.Elapsed.TotalMilliseconds -ge 150 -and $watch.Elapsed.TotalSeconds -lt 2) 'BACKLOG_YIELDS_CPU_EVERY_EIGHT_CLAIMS'
 Check (@($signal.WaitTimeouts | Where-Object {$_ -ne 500}).Count -eq 0) 'LOCAL_WAIT_ONLY_FOR_PROGRESS_NOT_HTTP_POLL'
}
Case 'empty-claim-stops-drain-and-idle-does-not-poll' {
 $signal=[HaraCommercialEventV2WakeFixture]::new()
 $gate=New-WindowsEventV2DrainGate $signal
 Check (Wait-WindowsEventV2Work $gate) 'ONE_STARTUP_RECONCILIATION_CLAIM'
 Set-WindowsEventV2ClaimResult $gate $false
 foreach($i in 1..5){Check (-not (Wait-WindowsEventV2Work $gate)) 'IDLE_LOCAL_WAIT_DOES_NOT_AUTHORIZE_HTTP_CLAIM'}
 Check ($signal.Waits -eq 5 -and $signal.Sets -eq 0 -and $signal.Resets -eq 0) 'NO_FIXED_IDLE_HTTP_POLL_OR_SELF_WAKE_AFTER_EMPTY'
}
Case 'concurrent-notification-survives-empty-claim' {
 $signal=[HaraCommercialEventV2WakeFixture]::new()
 $gate=New-WindowsEventV2DrainGate $signal
 Check (Wait-WindowsEventV2Work $gate) 'CONCURRENT_RACE_INITIAL_CLAIM'
 [void]$signal.Set()
 Set-WindowsEventV2ClaimResult $gate $false
 Check ($signal.Pending -and $signal.Resets -eq 0) 'EMPTY_RESULT_CANNOT_RESET_OR_CONSUME_RACING_WAKE'
 Check (Wait-WindowsEventV2Work $gate) 'RACING_NOTIFY_RESUMES_RECONCILIATION'
 Set-WindowsEventV2ClaimResult $gate $false
 Check (-not (Wait-WindowsEventV2Work $gate)) 'EMPTY_AFTER_NOTIFY_RETURNS_TO_LOCAL_WAIT'
}
Case 'notification-storm-coalesces-one-drain' {
 $signal=[HaraCommercialEventV2WakeFixture]::new()
 $gate=New-WindowsEventV2DrainGate $signal
 [void](Wait-WindowsEventV2Work $gate)
 Set-WindowsEventV2ClaimResult $gate $false
 foreach($i in 1..100){[void]$signal.Set()}
 Check (Wait-WindowsEventV2Work $gate) 'COALESCED_NOTIFY_AUTHORIZES_ONE_RECONCILIATION'
 Set-WindowsEventV2ClaimResult $gate $false
 Check (-not (Wait-WindowsEventV2Work $gate)) 'NO_ONE_HTTP_CLAIM_PER_DUPLICATE_WAKE'
 Check ($signal.Sets -eq 100 -and $signal.Resets -eq 0) 'NATIVE_AUTORESET_BOUNDARY_ONLY_COALESCES'
}
Case 'exact-agent-wiring-preserves-journal-and-native-fences' {
 $reachable=Reachable-Functions @('Start-WindowsRelaySupervisor','Start-WindowsRelayWorker')
 foreach($helper in $required){Check ($reachable.Contains($helper)) ('ACTUAL_0356_RUNTIME_REACHES_'+$helper)}
 foreach($helper in @('Invoke-WindowsRelayCall','Test-WindowsRelayWorkerContext','Initialize-EnrollmentState','Get-PlainText')){
  Check ($reachable.Contains($helper)) ('EXISTING_ENROLLMENT_EXECUTION_PATH_RETAINED_'+$helper)
 }
 $runtime=($reachable | ForEach-Object {$functions[$_].Extent.Text}) -join "`n"
 Check (-not $runtime.Contains('Import-StableAgentFunctions') -and -not $runtime.Contains('WINDOWS_EVENT_V2_STABLE_AGENT_MISSING')) 'NO_IMPORT_OF_OTHER_INSTALLED_AGENT'
 $jobs=$functions['Initialize-WindowsRelayProcessType'].Extent.Text
 Check ($jobs.Contains('limits.Basic.Flags=0x2000') -and $jobs.Contains('KILL_ON_JOB_CLOSE')) 'NATIVE_KILL_ON_JOB_CLOSE_PRESERVED'
 Check ($jobs.IndexOf('AssignProcessToJobObject(Job,Child.Handle)') -ge 0 -and $jobs.IndexOf('AssignProcessToJobObject(Job,Child.Handle)') -lt $jobs.IndexOf('Child.StandardInput.WriteLine(handshake)')) 'NATIVE_JOB_ASSIGNMENT_PRECEDES_WORKER_HANDSHAKE'
 Check ($jobs.Contains('Child.HasExited && value.ActiveProcesses==0')) 'NATIVE_QUIESCENCE_FENCE_PRESERVED'
 Check (-not $runtime.Contains('ExecutionPolicy Bypass') -and -not $runtime.Contains('ExecutionPolicy=Bypass')) 'NO_SCRIPT_EXECUTION_POLICY_BYPASS'
 $native=$functions['New-WindowsEventV2WakeSignal'].Extent.Text
 Check ($native.Contains('GetCurrent().User') -and $native.Contains('EventWaitHandleSecurity') -and -not $native.Contains('S-1-1-0')) 'NATIVE_WAKE_OWNER_ACL_SOURCE_GUARD_NOT_ADMISSION'
}
Case 'invalid-opt-in-cannot-silently-fall-back-during-config-load' {
 $priorConfigPath=$script:ConfigPath
 $fixture=[IO.Path]::GetTempFileName()
 try{
  $script:ConfigPath=$fixture
  foreach($code in @('EVENT_V2_DEV_FLAG_INVALID','EVENT_V2_DEV_SCOPE_INVALID')){
   $cfg=New-Config
   $cfg | Add-Member -NotePropertyName architecture -NotePropertyValue 'test'
   $cfg | Add-Member -NotePropertyName encrypted_device_token -NotePropertyValue 'synthetic-protected-not-a-credential'
   if($code -ceq 'EVENT_V2_DEV_FLAG_INVALID'){$cfg.event_v2_dev_enabled='true'}else{$cfg.environment='PROD'}
   [IO.File]::WriteAllText($fixture,($cfg | ConvertTo-Json -Compress),([Text.UTF8Encoding]::new($false)))
   $denied=$false
   try{Read-WindowsRelayConfig | Out-Null}catch{$denied=$_.Exception.Message -ceq $code}
   Check $denied ('CONFIG_LOAD_PROPAGATES_'+$code)
  }
 }finally{
  $script:ConfigPath=$priorConfigPath
  if(Test-Path -LiteralPath $fixture){Remove-Item -LiteralPath $fixture -Force}
 }
}
@{state=$(if($failures.Count){'FAIL_COMMERCIAL_0356_EVENT_V2_SOURCE_QA'}else{'PASS_COMMERCIAL_0356_EVENT_V2_SOURCE_QA'});checks=$checks.Count;cases=$caseCount;failures=$failures.ToArray();source_sha256=$sourceSha;baseline_p02_sha256=$baselineSha;agent_version='0.3.56';exact_agent_function_ast=$true;installed=$false;paired=$false;network_used=$false;native_wake_acl_acceptance=$false;windows_native=([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)} | ConvertTo-Json -Depth 7
if($failures.Count){exit 1}
