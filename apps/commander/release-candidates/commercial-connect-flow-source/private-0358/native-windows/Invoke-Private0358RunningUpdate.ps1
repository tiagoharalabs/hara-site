# One controlled same-signed-.58 update with an already-running QA Agent.
# interactive, limited Windows PowerShell 5.1 session. No pairing action allowed.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$NativeReceiptPath)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$nuSid='S-1-5-21-1207901905-1500652706-889822281-1005'
$nuDevice='HARA-DEVICE-a544f7b1-3ee1-49f7-aa55-f559376d5d12'
$nuOrigin='https://commander.haralabs.com.br'
$nuRelease='https://192.168.10.23:18445/releases/0.3.58'
$nuController='C:\Users\CommanderQA\Desktop\HARA Commander Conexao QA\Connect-Commander.ps1'
$nuControllerSha='2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da'
$nuOldAgentSha='bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d'
$nuLegacyRollbackSha='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'
$nuTargetAgentSha='bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d'
$nuTargetInstallerSha='27c856bb2b8ce8a100d8b258c8de544d99eb076ae8a0c6494110b17574ccfbc2'
$nuManifestSha='0c48cf879e5a8e564bb6554299c940a6414da64baf3477861450c6ee18be88dd'
$nuResultsRoot='C:\ProgramData\HARA-QA\windows-install-0356-20261028\results'
$nuContext=$null;$nuBefore=$null;$nuPrivate=$null;$nuGuard=$null;$nuOriginalFunctions=@{}
$script:NUUpdateInvocations=0;$script:NUPairingBlocked=0;$script:NUUpdaterStarted=$null
$script:NUSignedReleaseVerified=$false;$script:NUChild=$null;$script:NURecoveryStarted=$null
$nuReport=[ordered]@{
  schema='hara.commander.windows-private-0358-running-update.v1';started_utc=[DateTime]::UtcNow.ToString('o');
  state='HOLD';stage='IDENTITY';device_id=$nuDevice;credential_origin=$nuOrigin;
  artifact_release_base=$nuRelease;artifact_source='EXPLICIT_PRIVATE_SIGNED_RELEASE';
  expected_agent_sha256=$nuTargetAgentSha;expected_installer_sha256=$nuTargetInstallerSha;
  expected_manifest_sha256=$nuManifestSha;public_distribution_changed=$false;
  pairing_permitted=$false;device_token_exposed=$false;optional_rollback_performed=$false;update_path='EXPLICIT_SAME_SIGNED_VERSION_RUNNING_UPDATE';automatic_upgrade_claimed=$false
}
function Need-NU([bool]$Condition,[string]$Code){if(-not $Condition){throw $Code}}
function Code-NU($Failure){
  $message=[string]$Failure.Exception.Message
  if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){return $message}
  return 'NATIVE_PRIVATE_UPGRADE_FAILED'
}
function Policy-NU {
  $value=[ordered]@{}
  foreach($scope in @('MachinePolicy','UserPolicy','Process','CurrentUser','LocalMachine')){$value[$scope]=[string](Get-ExecutionPolicy -Scope $scope)}
  $value.effective=[string](Get-ExecutionPolicy)
  return [pscustomobject]$value
}
function Environment-NU {
  $value=[ordered]@{}
  foreach($scope in @('Process','User','Machine')){
    foreach($name in @('HARA_COMMANDER_URL','HARA_COMMANDER_RELEASE_URL','HARA_COMMANDER_APPROVAL_MODE','HARA_COMMANDER_EVENT_V2_OPT_IN','HARA_COMMANDER_EVENT_V2_DEV_ENABLED')){
      $value[($scope+':'+$name)]=[Environment]::GetEnvironmentVariable($name,$scope)
    }
  }
  return ($value|ConvertTo-Json -Compress)
}
function EventEvidence-NU($Runtime){
  $fields=[ordered]@{}
  foreach($name in @('event_v2','event_v2_enabled','event_v2_state','event_v2_mode','event_v2_opt_in')){
    $property=$Runtime.PSObject.Properties[$name]
    if(-not $property){continue}
    if($property.Value -is [bool]){$fields[$name]=$property.Value}
    elseif($property.Value -is [string] -and $property.Value -cmatch '^(OFF|ON|ENABLED|DISABLED)$'){$fields[$name]=[string]$property.Value}
    elseif($name -eq 'event_v2' -and $property.Value -and $property.Value.PSObject.Properties['enabled'] -and $property.Value.enabled -is [bool]){$fields['event_v2.enabled']=$property.Value.enabled}
  }
  return [pscustomobject]@{state=$(if($fields.Count){'OBSERVED'}else{'NOT_OBSERVED'});fields=[pscustomobject]$fields}
}
function Runtime-NU($Context){
  Assert-CCOwnedFile $Context.RuntimePath $Context.Sid
  Need-NU ((Get-Item -LiteralPath $Context.RuntimePath).Length -le 262144) 'RUNTIME_REPORT_TOO_LARGE'
  $value=Get-Content -LiteralPath $Context.RuntimePath -Raw|ConvertFrom-Json
  return [pscustomobject]@{
    version=[string]$value.agent_version;started_utc=[string]$value.started_at_utc;
    heartbeat_utc=[string]$value.last_successful_heartbeat_at_utc;
    device_id=$(if($value.device_id){[string]$value.device_id}else{$null});
    event_evidence=(EventEvidence-NU $value)
  }
}
function Checkpoint-NU([string]$Stage){
  $nuReport.stage=$Stage;$nuReport.progress_utc=[DateTime]::UtcNow.ToString('o')
  if($nuProgressPath){[IO.File]::WriteAllText($nuProgressPath,($nuReport|ConvertTo-Json -Depth 6 -Compress),[Text.Encoding]::UTF8)}
}
function Fallback-NU {
  # Observation only. No task start/stop, file restoration, credential reset or
  # installer invocation is allowed in this driver fallback.
  $value=[ordered]@{state='UNCONFIRMED';observed_utc=[DateTime]::UtcNow.ToString('o')}
  try{
    $current=Get-CCInstalledState $nuContext
    $value.device_matches=($current.DeviceId -ceq $nuDevice -and $current.Origin -ceq $nuOrigin)
    $value.config_bytes_preserved=([Convert]::ToBase64String([IO.File]::ReadAllBytes($nuContext.ConfigPath)) -ceq [Convert]::ToBase64String($nuConfigBefore))
    $value.approval_mode_preserved=([string]$current.Config.approval_mode -ceq $nuApprovalBefore)
    $value.agent_version=$current.Version;$value.agent_sha256=$current.AgentSha
    $value.task_running=([string](Get-CCTask $nuContext).State -ceq 'Running')
    $taskXml=Export-ScheduledTask -TaskName $nuContext.TaskName -TaskPath '\'
    $value.task_definition_preserved=($taskXml -ceq $nuTaskXmlBefore)
    $value.policy_preserved=((Policy-NU|ConvertTo-Json -Compress) -ceq $nuPolicyBeforeJson)
    $value.commander_environment_preserved=((Environment-NU) -ceq $nuEnvironmentBefore)
    $runtime=Runtime-NU $nuContext
    $value.runtime=$runtime
    $value.authenticated_binding=((Test-CCCredential $current) -ceq 'VALID')
    $heartbeat=[DateTimeOffset]::Parse($runtime.heartbeat_utc)
    $value.runtime_recent=($heartbeat -ge [DateTimeOffset]::UtcNow.AddSeconds(-90) -and $heartbeat -le [DateTimeOffset]::UtcNow.AddSeconds(5) -and $runtime.version -ceq $current.Version)
    if($value.device_matches -and $value.config_bytes_preserved -and $value.approval_mode_preserved -and $value.task_running -and $value.task_definition_preserved -and $value.policy_preserved -and $value.commander_environment_preserved -and $value.authenticated_binding -and $value.runtime_recent){
      if($current.Version -ceq '0.3.58' -and $current.AgentSha -ceq $nuTargetAgentSha){$value.state='TARGET_INSTALLED_AND_CONNECTED'}
    }
  }catch{$value.error_code=Code-NU $_}
  return [pscustomobject]$value
}
# Native checks loaded only from the pinned .58 recovery driver.
function Import-NUAgentFunctions([byte[]]$Bytes,[string[]]$Names){
  $tokens=$null;$errors=$null
  $ast=[Management.Automation.Language.Parser]::ParseInput([Text.Encoding]::UTF8.GetString($Bytes),[ref]$tokens,[ref]$errors)
  Need-NU ($errors.Count -eq 0) 'VERIFIED_0358_AGENT_PARSE_FAILED'
  foreach($name in $Names){
    $nodes=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object {$_.Name -ceq $name})
    Need-NU ($nodes.Count -eq 1) 'AGENT_FUNCTION_EXTRACTION_AMBIGUOUS'
    # Compile only the selected function body; no Agent entry point is run.
    $definition=[regex]::Replace($nodes[0].Extent.Text,('^function\s+'+[regex]::Escape($name)+'(?=[(\s])'),('function script:'+$name))
    . ([scriptblock]::Create($definition))
  }
}
function DirectoryAcl-NU([string]$Path){
  $acl=Get-Acl -LiteralPath $Path
  $raw=New-Object Security.AccessControl.RawSecurityDescriptor($acl.GetSecurityDescriptorBinaryForm(),0)
  $dacl=New-Object byte[] $raw.DiscretionaryAcl.BinaryLength
  $raw.DiscretionaryAcl.GetBinaryForm($dacl,0)
  $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|ForEach-Object {
    @{sid=$_.IdentityReference.Value;rights=[string]$_.FileSystemRights;type=[string]$_.AccessControlType;inherited=$_.IsInherited;inheritance=[string]$_.InheritanceFlags;propagation=[string]$_.PropagationFlags}
  })
  return [pscustomobject]@{owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;group=$acl.GetGroup([Security.Principal.SecurityIdentifier]).Value;protected=$acl.AreAccessRulesProtected;flags=([int]$raw.ControlFlags -band (-bnot 0x400));dacl_base64=[Convert]::ToBase64String($dacl);rules=$rules}
}
function Test-NURepeatedDirectoryAcl([byte[]]$AgentBytes){
  Import-NUAgentFunctions $AgentBytes @('Get-Utf8Sha256','Get-EnrollmentContext','Initialize-EnrollmentState')
  $saved=@{}
  foreach($name in @('Root','ReceiptDir','OperationsDb','ConsoleEvents','PendingApprovalPath','ApprovalResponsePath')){
    $item=Get-Variable -Name $name -Scope Script -ErrorAction SilentlyContinue
    $saved[$name]=@{present=[bool]$item;value=$(if($item){$item.Value}else{$null})}
  }
  try{
    $script:Root=Join-Path $nuPrivate 'acl-regression'
    $cfg=[pscustomobject]@{base_url=$nuOrigin;device_id='QA-ACL-REGRESSION';encrypted_device_token='synthetic-local-only';tenant_id=''}
    $context=Get-EnrollmentContext $cfg
    $folder=Join-Path (Join-Path $Root 'enrollments') $context
    [void][IO.Directory]::CreateDirectory($folder)
    $before=DirectoryAcl-NU $folder
    $first=$null
    for($iteration=0;$iteration -lt 3;$iteration++){
      Need-NU ((Initialize-EnrollmentState $cfg) -ceq $context) 'ACL_REGRESSION_CONTEXT_CHANGED'
      $after=DirectoryAcl-NU $folder
      Need-NU ($after.owner -ceq $before.owner -and $after.group -ceq $before.group -and $after.protected) 'ACL_REGRESSION_OWNER_GROUP_OR_PROTECTION_CHANGED'
      Need-NU ($after.rules.Count -eq 2) 'ACL_REGRESSION_RULE_COUNT'
      foreach($sid in @($nuSid,'S-1-5-18')){
        $rule=@($after.rules|Where-Object {$_.sid -ceq $sid})
        Need-NU ($rule.Count -eq 1 -and $rule[0].rights -ceq 'FullControl' -and $rule[0].type -ceq 'Allow' -and -not $rule[0].inherited -and $rule[0].inheritance -ceq 'ContainerInherit, ObjectInherit' -and $rule[0].propagation -ceq 'None') 'ACL_REGRESSION_PRIVATE_RULES_INVALID'
      }
      if($first){Need-NU ($after.dacl_base64 -ceq $first.dacl_base64 -and $after.flags -eq $first.flags) 'ACL_REGRESSION_REPEAT_NOT_IDEMPOTENT'}else{$first=$after}
    }
    return [pscustomobject]@{state='PASS_ACCESS_ONLY_REPEATED_DIRECTORY';iterations=3;owner_preserved=$true;group_preserved=$true;dacl_protected=$true;qa_and_system_only=$true;exact_repeated_dacl=$true;product_directory_modified=$false}
  }finally{
    foreach($entry in $saved.GetEnumerator()){
      if($entry.Value.present){Set-Variable -Scope Script -Name $entry.Key -Value $entry.Value.value}else{Remove-Variable -Scope Script -Name $entry.Key -ErrorAction SilentlyContinue}
    }
  }
}
function WorkerSnapshot-NU {
  $all=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -OperationTimeoutSec 5)
  $matched=@($all|Where-Object {([string]$_.CommandLine).Contains($nuContext.AgentPath)})
  $main=@($matched|Where-Object {-not ([string]$_.CommandLine).Contains('--relay-worker')})
  Need-NU ($main.Count -eq 1) 'PRODUCT_SUPERVISOR_PROCESS_NOT_UNIQUE'
  $owner=Invoke-CimMethod -InputObject $main[0] -MethodName GetOwnerSid -OperationTimeoutSec 5
  Need-NU ([string]$owner.Sid -ceq $nuSid) 'SUPERVISOR_OWNER_MISMATCH'
  $result=[ordered]@{supervisor_pid=[int]$main[0].ProcessId;supervisor_created_utc=$main[0].CreationDate.ToUniversalTime().ToString('o');workers=@{}}
  foreach($row in $matched){
    if(([string]$row.CommandLine) -cmatch '--relay-worker "(heartbeat|executor|alerts)" "([0-9]+)" "[^"\r\n]+" "[0-9a-f]{64}" "[0-9a-f]{64}"$'){
      $role=$Matches[1];$parent=[int]$Matches[2]
      Need-NU (-not $result.workers.ContainsKey($role) -and $parent -eq $result.supervisor_pid -and [int]$row.ParentProcessId -eq $parent) 'WORKER_PARENT_OR_ROLE_MISMATCH'
      $workerOwner=Invoke-CimMethod -InputObject $row -MethodName GetOwnerSid -OperationTimeoutSec 5
      Need-NU ([string]$workerOwner.Sid -ceq $nuSid) 'WORKER_OWNER_MISMATCH'
      $result.workers[$role]=@{pid=[int]$row.ProcessId;created_utc=$row.CreationDate.ToUniversalTime().ToString('o')}
    }
  }
  Need-NU ($result.workers.Count -eq 3 -and $result.workers.ContainsKey('heartbeat') -and $result.workers.ContainsKey('executor') -and $result.workers.ContainsKey('alerts')) 'THREE_RELAY_WORKERS_REQUIRED'
  return [pscustomobject]$result
}
function RecoveryOutbox-NU([byte[]]$AgentBytes){
  Import-NUAgentFunctions $AgentBytes @('Get-Utf8Sha256','Get-EnrollmentContext','Initialize-WinSqlite')
  Initialize-WinSqlite
  $current=Get-CCInstalledState $nuContext
  $context=Get-EnrollmentContext $current.Config
  $folder=Join-Path (Join-Path $nuContext.Root 'enrollments') $context
  $database=Join-Path $folder 'recovery-events.sqlite3'
  Assert-CCOwnedFile $database $nuSid
  $blocked=@([HaraWinSqlite]::QueryReadOnly($database,"SELECT 1 AS n FROM recovery_meta WHERE key='access_denied'",@()))
  $counts=@([HaraWinSqlite]::QueryReadOnly($database,'SELECT state,count(*) AS n FROM recovery_events GROUP BY state',@()))
  $floor=[long]([DateTimeOffset]$script:NURecoveryStarted).ToUnixTimeMilliseconds()
  $recent=@([HaraWinSqlite]::QueryReadOnly($database,"SELECT worker,health,state,at_utc FROM recovery_events WHERE created_ms>=? ORDER BY ordinal DESC LIMIT 24",@($floor)))
  $bad=@($recent|Where-Object {[string]$_.health -cin @('STALLED','DEGRADED')})
  return [pscustomobject]@{access_blocked=($blocked.Count -gt 0);counts=$counts;new_health_events=$recent;new_stalled_or_degraded=($bad.Count -gt 0);read_only=$true}
}
function Confirm-NUWorkers([byte[]]$AgentBytes){
  $clock=[Diagnostics.Stopwatch]::StartNew();$first=$null
  while($clock.Elapsed.TotalSeconds -lt 20){
    try{$first=WorkerSnapshot-NU;break}catch{Start-Sleep -Milliseconds 500}
  }
  Need-NU ([bool]$first) 'INITIAL_RELAY_WORKERS_NOT_CONFIRMED'
  $stable=[Diagnostics.Stopwatch]::StartNew()
  while($stable.Elapsed.TotalSeconds -lt 40){
    Start-Sleep -Seconds 5
    $next=WorkerSnapshot-NU
    Need-NU ($next.supervisor_pid -eq $first.supervisor_pid -and $next.supervisor_created_utc -ceq $first.supervisor_created_utc) 'RELAY_SUPERVISOR_RESTART_DURING_ACCEPTANCE'
    foreach($role in @('heartbeat','executor','alerts')){Need-NU ($next.workers[$role].pid -eq $first.workers[$role].pid -and $next.workers[$role].created_utc -ceq $first.workers[$role].created_utc) 'RELAY_WORKER_RESTART_DURING_ACCEPTANCE'}
    Need-NU ([string](Get-CCTask $nuContext).State -ceq 'Running') 'PRODUCT_TASK_STOPPED_DURING_ACCEPTANCE'
  }
  $outbox=RecoveryOutbox-NU $AgentBytes
  Need-NU (-not $outbox.access_blocked -and -not $outbox.new_stalled_or_degraded) 'RECOVERY_OUTBOX_HEALTH_HOLD'
  return [pscustomobject]@{state='PASS_THREE_STABLE_WORKERS_AND_OUTBOX';stable_seconds=[int]$stable.Elapsed.TotalSeconds;snapshot=$first;outbox=$outbox;functional_executor_command='PENDING_ROOT_COMMANDER_PROBE';alerts_network_ack=$(if(@($outbox.counts|Where-Object {[string]$_.state -ceq 'PERSISTED' -and [long]$_.n -gt 0}).Count){'PERSISTED_EVENTS_OBSERVED'}else{'NO_PENDING_EVENT_REQUIRED'})}
}

try{
  Need-NU ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ceq $nuSid -and $env:USERPROFILE -ceq 'C:\Users\CommanderQA') 'EXPECTED_COMMANDERQA_IDENTITY_REQUIRED'
  $NativeReceiptPath=[IO.Path]::GetFullPath($NativeReceiptPath)
  Need-NU ($NativeReceiptPath.StartsWith(($nuResultsRoot+'\'),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetDirectoryName($NativeReceiptPath) -ieq $nuResultsRoot -and [IO.Path]::GetFileName($NativeReceiptPath) -cmatch '^[A-Za-z0-9_.-]+\.json$') 'NATIVE_RECEIPT_PATH_REFUSED'
  Need-NU (-not (Test-Path -LiteralPath $NativeReceiptPath)) 'NATIVE_RECEIPT_ALREADY_EXISTS'
  $nuProgressPath=$NativeReceiptPath+'.progress.json'
  Need-NU (-not (Test-Path -LiteralPath $nuProgressPath)) 'NATIVE_PROGRESS_ALREADY_EXISTS'
  Need-NU ((Get-FileHash -LiteralPath $nuController -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $nuControllerSha) 'FROZEN_CONTROLLER_HASH_MISMATCH'
  . $nuController
  Assert-CCNoReparse $nuResultsRoot
  Need-NU (Test-Path -LiteralPath $nuResultsRoot -PathType Container) 'NATIVE_RECEIPT_DIRECTORY_MISSING'
  $nuContext=New-CCContext $nuOrigin $nuRelease 'ASK_EVERY_ACTION'
  Need-NU ($nuContext.Sid -ceq $nuSid) 'EXPECTED_COMMANDERQA_IDENTITY_REQUIRED'
  $nuGuard=Enter-CCGuard $nuContext
  $nuPrivate=New-CCPrivateStage $nuContext
  $nuReport.private_log_directory=$nuPrivate
  $nuPolicyBefore=Policy-NU;$nuPolicyBeforeJson=$nuPolicyBefore|ConvertTo-Json -Compress
  Need-NU ($nuPolicyBefore.CurrentUser -ceq 'RemoteSigned' -and $nuPolicyBefore.effective -ceq 'RemoteSigned' -and $nuPolicyBefore.Process -ceq 'Undefined') 'EXPECTED_EXECUTION_POLICY_REQUIRED'
  $nuEnvironmentBefore=Environment-NU
  Checkpoint-NU 'PREIMAGE'
  $nuBefore=Get-CCInstalledState $nuContext
  Need-NU ($nuBefore.ConfigPresent -and $nuBefore.DeviceId -ceq $nuDevice -and $nuBefore.Origin -ceq $nuOrigin) 'EXPECTED_EXISTING_DEVICE_REQUIRED'
  Need-NU ($nuBefore.Version -ceq '0.3.58' -and $nuBefore.AgentSha -ceq $nuOldAgentSha) 'EXPECTED_RECOVERED_0358_AGENT_REQUIRED'
  Need-NU ([string](Get-CCTask $nuContext).State -ceq 'Running') 'EXPECTED_RECOVERED_RUNNING_TASK_REQUIRED'
  $nuConfigBefore=[IO.File]::ReadAllBytes($nuContext.ConfigPath)
  $nuApprovalBefore=[string]$nuBefore.Config.approval_mode
  Need-NU ($nuApprovalBefore -ceq 'PERSISTENT_TRUSTED') 'EXPECTED_EXISTING_PERSISTENT_POLICY_REQUIRED'
  $nuTaskXmlBefore=Export-ScheduledTask -TaskName $nuContext.TaskName -TaskPath '\'
  $nuRuntimeBefore=Runtime-NU $nuContext
  Need-NU ($nuRuntimeBefore.version -ceq '0.3.58') 'EXPECTED_RECOVERED_0358_RUNTIME_REQUIRED'
  $nuReport.before=[ordered]@{version=$nuBefore.Version;agent_sha256=$nuBefore.AgentSha;approval_mode=$nuApprovalBefore;runtime=$nuRuntimeBefore;task_state='Running';current_user_policy=$nuPolicyBefore.CurrentUser}
  foreach($name in @('Get-CCPublicBytes','Get-CCRelease','Invoke-CCInstaller','Ensure-CCRuntime')){$nuOriginalFunctions[$name]=(Get-Item ('Function:'+ $name)).ScriptBlock}

  function script:Get-CCPublicBytes([string]$Uri,[int]$Maximum=2097152){
    Need-NU ($Uri -cin @(($nuRelease+'/release/agent-manifest.json'),($nuRelease+'/release/agent-manifest.sig.json'),($nuRelease+'/agent/windows.ps1'),($nuRelease+'/install/windows.ps1'))) 'UNEXPECTED_RELEASE_DOWNLOAD_URI'
    $bytes=& ($nuOriginalFunctions['Get-CCPublicBytes']) $Uri $Maximum
    if($Uri -ceq ($nuRelease+'/release/agent-manifest.json')){Need-NU ((Get-CCSha $bytes) -ceq $nuManifestSha) 'EXPECTED_0358_MANIFEST_HASH_REQUIRED'}
    return ,$bytes
  }
  function script:Get-CCRelease($Context,[string]$Origin){
    Need-NU ($Origin -ceq $nuOrigin -and $Context.QaReleaseBase -ceq $nuRelease) 'CREDENTIAL_AND_RELEASE_SCOPE_MISMATCH'
    $release=& ($nuOriginalFunctions['Get-CCRelease']) $Context $Origin
    Need-NU ($release.Version -ceq '0.3.58' -and $release.BaseUrl -ceq $nuRelease -and $release.AgentSha -ceq $nuTargetAgentSha -and $release.InstallerSha -ceq $nuTargetInstallerSha -and $release.AgentBytes.Length -eq 173192) 'EXPECTED_SIGNED_0358_RELEASE_REQUIRED'
    $script:NUSignedReleaseVerified=$true
    return $release
  }
  function script:Ensure-CCRuntime($Context,$State){
    # The signed update owns its own task restart/rollback. This QA observer
    # deliberately never starts a stopped task, including on failure recovery.
    $floor=if($State.Version -ceq '0.3.58' -and $script:NUUpdaterStarted){[DateTimeOffset]$script:NUUpdaterStarted}else{[DateTimeOffset]::UtcNow.AddSeconds(-90)}
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while($clock.Elapsed.TotalSeconds -lt 90){
      Need-NU ([string](Get-CCTask $Context).State -ceq 'Running') 'READONLY_RUNTIME_TASK_NOT_RUNNING'
      if(Test-Path -LiteralPath $Context.RuntimePath){
        try{
          $runtime=Runtime-NU $Context
          $heartbeat=[DateTimeOffset]::Parse($runtime.heartbeat_utc)
          $deviceOkay=(-not $runtime.device_id -or $runtime.device_id -ceq $nuDevice)
          if($runtime.version -ceq $State.Version -and $deviceOkay -and $heartbeat -ge $floor -and $heartbeat -le [DateTimeOffset]::UtcNow.AddSeconds(5)){return $heartbeat.UtcDateTime.ToString('o')}
        }catch{
          # Startup can precede the first heartbeat; retry partial runtime
          # reports, but preserve every explicit ownership/path/size failure.
          if([string]$_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){throw}
        }
      }
      Start-Sleep -Seconds 1
    }
    throw 'READONLY_FRESH_RUNTIME_NOT_CONFIRMED'
  }
  function script:Invoke-CCInstaller($Context,$State,$Release,[string]$Action){
    if($Action -cne 'update'){$script:NUPairingBlocked++;throw 'PAIRING_ACTION_FORBIDDEN_IN_UPGRADE'}
    Need-NU ($script:NUUpdateInvocations -eq 0 -and $script:NUSignedReleaseVerified) 'UPDATE_DISPATCH_NOT_AUTHORIZED'
    Need-NU ($State.ConfigPresent -and $State.DeviceId -ceq $nuDevice -and $State.Origin -ceq $nuOrigin) 'UPGRADE_EXISTING_BINDING_REQUIRED'
    Need-NU ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Context.ConfigPath)) -ceq [Convert]::ToBase64String($nuConfigBefore)) 'PREUPDATE_CONFIGURATION_CHANGED'
    $dispatchState=Get-CCInstalledState $Context
    Need-NU ($dispatchState.Version -ceq '0.3.58' -and $dispatchState.AgentSha -ceq $nuOldAgentSha -and $dispatchState.TaskState -ceq 'Running') 'PREUPDATE_INSTALLED_STATE_CHANGED'
    Need-NU ($Release.Version -ceq '0.3.58' -and $Release.AgentSha -ceq $nuTargetAgentSha -and $Release.InstallerSha -ceq $nuTargetInstallerSha) 'UPGRADE_TARGET_PIN_MISMATCH'
    Need-NU ((Get-CCFileSha ($Context.AgentPath+'.rollback')) -ceq $nuLegacyRollbackSha -and (Get-CCFileSha $nuLegacyRollbackPrivate) -ceq $nuLegacyRollbackSha) 'LEGACY_ROLLBACK_PREIMAGE_CHANGED'
    $script:NUUpdateInvocations++
    $installerPath=Join-Path $nuPrivate 'verified-update-0358.ps1'
    [IO.File]::WriteAllBytes($installerPath,$Release.InstallerBytes)
    Need-NU ((Get-CCFileSha $installerPath) -ceq $nuTargetInstallerSha) 'STAGED_0358_INSTALLER_MISMATCH'
    $tokens=$null;$errors=$null
    [Management.Automation.Language.Parser]::ParseFile($installerPath,[ref]$tokens,[ref]$errors)|Out-Null
    Need-NU ($errors.Count -eq 0) 'STAGED_0358_INSTALLER_SYNTAX_INVALID'
    $process=New-Object Diagnostics.Process
    $process.StartInfo.FileName=$Context.PowerShellExe
    $process.StartInfo.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+$installerPath+'" -Action update'
    $process.StartInfo.UseShellExecute=$false;$process.StartInfo.CreateNoWindow=$true
    $process.StartInfo.RedirectStandardOutput=$true;$process.StartInfo.RedirectStandardError=$true
    $process.StartInfo.EnvironmentVariables['HARA_COMMANDER_URL']=$nuOrigin
    $process.StartInfo.EnvironmentVariables['HARA_COMMANDER_RELEASE_URL']=$nuRelease
    $process.StartInfo.EnvironmentVariables['HARA_COMMANDER_APPROVAL_MODE']=$nuApprovalBefore
    $stdoutPath=Join-Path $nuPrivate 'installer-update-stdout.private.bin'
    $stderrPath=Join-Path $nuPrivate 'installer-update-stderr.private.bin'
    $stdoutFile=$null;$stderrFile=$null;$stdoutCopy=$null;$stderrCopy=$null
    try{
      $stdoutFile=New-Object IO.FileStream($stdoutPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
      $stderrFile=New-Object IO.FileStream($stderrPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
      $script:NUUpdaterStarted=[DateTime]::UtcNow
      Need-NU ($process.Start()) 'SIGNED_UPDATE_PROCESS_NOT_STARTED'
      $script:NUChild=$process
      $nuReport.child=[ordered]@{pid=$process.Id;started_utc=$script:NUUpdaterStarted.ToString('o');action='update';noninteractive=$true;exit_code=$null}
      $stdoutCopy=$process.StandardOutput.BaseStream.CopyToAsync($stdoutFile)
      $stderrCopy=$process.StandardError.BaseStream.CopyToAsync($stderrFile)
      $clock=[Diagnostics.Stopwatch]::StartNew();$lastCheckpoint=0
      while(-not $process.WaitForExit(1000)){
        if($clock.Elapsed.TotalSeconds-$lastCheckpoint -ge 15){
          $nuReport.child.elapsed_seconds=[int]$clock.Elapsed.TotalSeconds
          $nuReport.child.long_running=($clock.Elapsed.TotalSeconds -ge 240)
          Checkpoint-NU 'SIGNED_UPDATE_RUNNING';$lastCheckpoint=$clock.Elapsed.TotalSeconds
        }
      }
      $nuReport.child.exit_code=$process.ExitCode
      Need-NU ($stdoutCopy.Wait(5000) -and $stderrCopy.Wait(5000)) 'PRIVATE_UPDATE_LOG_CAPTURE_INCOMPLETE'
      $stdoutFile.Flush($true);$stderrFile.Flush($true)
      $nuReport.child.stdout_bytes=$stdoutFile.Length;$nuReport.child.stderr_bytes=$stderrFile.Length
      Need-NU ($process.ExitCode -eq 0) 'SIGNED_UPDATE_PROCESS_FAILED'
    }finally{
      # Do not kill a signed updater halfway through its transaction. The root
      # operator monitors the scheduled task and these bounded progress receipts.
      if($stdoutFile){$stdoutFile.Dispose()};if($stderrFile){$stderrFile.Dispose()}
      $script:NUChild=$null;$process.Dispose()
    }
  }

  Checkpoint-NU 'VERIFY_SIGNED_RUNNING_UPDATE_RELEASE'
  Need-NU ((Test-CCCredential $nuBefore) -ceq 'VALID') 'EXISTING_BINDING_NOT_VALID'
  [void](Ensure-CCRuntime $nuContext $nuBefore)
  $nuReleaseData=Get-CCRelease $nuContext $nuOrigin
  Import-NUAgentFunctions $nuReleaseData.AgentBytes @('Get-Utf8Sha256','Get-EnrollmentContext')
  $nuEnrollmentFolder=Join-Path (Join-Path $nuContext.Root 'enrollments') (Get-EnrollmentContext $nuBefore.Config)
  Assert-CCNoReparse $nuEnrollmentFolder
  $nuEnrollmentAclBefore=DirectoryAcl-NU $nuEnrollmentFolder
  $nuRollbackPath=$nuContext.AgentPath+'.rollback'
  Assert-CCOwnedFile $nuRollbackPath $nuSid
  Need-NU ((Get-CCFileSha $nuRollbackPath) -ceq $nuLegacyRollbackSha -and (Get-Item -LiteralPath $nuRollbackPath).Length -eq 172687) 'EXPECTED_LEGACY_0356_ROLLBACK_REQUIRED'
  $nuLegacyRollbackPrivate=Join-Path $nuPrivate 'original-0356-rollback.private.ps1'
  $nuLegacyBytes=[IO.File]::ReadAllBytes($nuRollbackPath)
  $nuLegacyStream=New-Object IO.FileStream($nuLegacyRollbackPrivate,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  try{$nuLegacyStream.Write($nuLegacyBytes,0,$nuLegacyBytes.Length);$nuLegacyStream.Flush($true)}finally{$nuLegacyStream.Dispose();$nuLegacyBytes=$null}
  Need-NU ((Get-CCFileSha $nuLegacyRollbackPrivate) -ceq $nuLegacyRollbackSha) 'PRIVATE_LEGACY_ROLLBACK_COPY_FAILED'
  $nuReport.legacy_0356_rollback_preserved_private=$true
  $nuReport.legacy_rollback_sha256=$nuLegacyRollbackSha
  Checkpoint-NU 'SIGNED_SAME_VERSION_UPDATE_WHILE_RUNNING'
  Invoke-CCInstaller $nuContext $nuBefore $nuReleaseData 'update'
  $nuUpdated=Get-CCInstalledState $nuContext
  Assert-CCEnrollmentPreserved $nuBefore $nuUpdated
  Need-NU ($nuUpdated.Version -ceq '0.3.58' -and $nuUpdated.AgentSha -ceq $nuTargetAgentSha -and $nuUpdated.TaskState -ceq 'Running') 'EXPECTED_TARGET_RUNNING_UPDATE_REQUIRED'
  Need-NU ((Export-ScheduledTask -TaskName $nuContext.TaskName -TaskPath '\') -ceq $nuTaskXmlBefore -and (Policy-NU|ConvertTo-Json -Compress) -ceq $nuPolicyBeforeJson -and (Environment-NU) -ceq $nuEnvironmentBefore) 'RUNNING_UPDATE_PRESERVATION_FAILED'
  Need-NU ((Get-CCFileSha ($nuContext.AgentPath+'.rollback')) -ceq $nuOldAgentSha -and (Get-CCFileSha $nuLegacyRollbackPrivate) -ceq $nuLegacyRollbackSha) 'RUNNING_UPDATE_ROLLBACK_PREIMAGES_REQUIRED'
  $nuReport.installer_completed_running_task_restart=$true
  $nuReport.explicit_product_task_starts=0
  $script:NURecoveryStarted=$script:NUUpdaterStarted
  $nuReport.recovery_started_utc=$script:NURecoveryStarted.ToString('o')
  [void](Ensure-CCRuntime $nuContext $nuUpdated)
  Need-NU ((Test-CCCredential $nuUpdated) -ceq 'VALID') 'UPDATED_AGENT_AUTH_UNCONFIRMED'
  Checkpoint-NU 'RELAY_WORKER_HEALTH_ACCEPTANCE'
  $nuReport.relay_health=Confirm-NUWorkers $nuReleaseData.AgentBytes
  $nuEnrollmentAclAfter=DirectoryAcl-NU $nuEnrollmentFolder
  $nuReport.actual_enrollment_acl=[ordered]@{owner_preserved=($nuEnrollmentAclAfter.owner -ceq $nuEnrollmentAclBefore.owner);group_preserved=($nuEnrollmentAclAfter.group -ceq $nuEnrollmentAclBefore.group);protected=$nuEnrollmentAclAfter.protected;exact_dacl_preserved=($nuEnrollmentAclAfter.dacl_base64 -ceq $nuEnrollmentAclBefore.dacl_base64 -and $nuEnrollmentAclAfter.flags -eq $nuEnrollmentAclBefore.flags)}
  Need-NU ($nuReport.actual_enrollment_acl.owner_preserved -and $nuReport.actual_enrollment_acl.group_preserved -and $nuReport.actual_enrollment_acl.protected -and $nuReport.actual_enrollment_acl.exact_dacl_preserved) 'ACTUAL_ENROLLMENT_DIRECTORY_PERMISSIONS_CHANGED'
  Checkpoint-NU 'FROZEN_CONNECT_EXISTING_CURRENT_RELEASE'
  $nuCore=Invoke-CCConnect $nuContext
  $nuReport.controller=[ordered]@{}
  foreach($field in @('state','stage','binding','connected','update','error_code','update_error_code','recovery_error_code','installed_version','target_version','enrollment_preserved','last_successful_heartbeat_at_utc')){
    if($nuCore.PSObject.Properties[$field]){$nuReport.controller[$field]=$nuCore.$field}
  }
  Need-NU ($nuCore.state -ceq 'CONNECTED' -and $nuCore.update -ceq 'ALREADY_CURRENT' -and -not $nuCore.paired_this_run) 'EXISTING_CURRENT_CONNECTION_NOT_CONFIRMED'
  Need-NU ($script:NUUpdateInvocations -eq 1 -and $script:NUPairingBlocked -eq 0) 'UNEXPECTED_RECOVERY_ACTION_COUNT'
  Checkpoint-NU 'FINAL_READONLY_ATTESTATION'
  $nuReport.after=Fallback-NU
  Need-NU ($nuReport.after.state -ceq 'TARGET_INSTALLED_AND_CONNECTED') 'TARGET_UPGRADE_ATTESTATION_FAILED'
  $nuHeartbeat=[DateTimeOffset]::Parse($nuReport.after.runtime.heartbeat_utc)
  $nuStarted=[DateTimeOffset]::Parse($nuReport.after.runtime.started_utc)
  $nuRuntimeFloor=[DateTimeOffset]$script:NURecoveryStarted
  Need-NU ($nuHeartbeat -ge $nuRuntimeFloor -and $nuHeartbeat -ge $nuStarted -and $nuStarted -ge $nuRuntimeFloor -and $nuReport.after.runtime.started_utc -cne $nuRuntimeBefore.started_utc) 'NEW_RUNTIME_START_OR_HEARTBEAT_UNCONFIRMED'
  $nuReport.event_v2_runtime=[ordered]@{before=$nuRuntimeBefore.event_evidence;after=$nuReport.after.runtime.event_evidence;comparison=$(if($nuRuntimeBefore.event_evidence.state -ceq 'OBSERVED' -and $nuReport.after.runtime.event_evidence.state -ceq 'OBSERVED'){if(($nuRuntimeBefore.event_evidence.fields|ConvertTo-Json -Compress) -ceq ($nuReport.after.runtime.event_evidence.fields|ConvertTo-Json -Compress)){'UNCHANGED'}else{'CHANGED'}}else{'NOT_OBSERVED'})}
  $nuReport.state='PASS_PRIVATE_SIGNED_0358_RUNNING_UPDATE';$nuReport.stage='COMPLETE'
}catch{
  $nuReport.error_code=Code-NU $_;$nuReport.error_type=$_.Exception.GetType().FullName
  if($nuPrivate){
    $nuPrivateError=$_|Out-String
    try{[IO.File]::WriteAllText((Join-Path $nuPrivate 'driver-error.private.txt'),$nuPrivateError,[Text.Encoding]::UTF8)}catch{$nuReport.private_error_log_written=$false}
    $nuPrivateError=$null
  }
  if($nuContext -and $nuBefore -and $nuConfigBefore){$nuReport.failure_observation=Fallback-NU}
}finally{
  foreach($entry in $nuOriginalFunctions.GetEnumerator()){Set-Item -Path ('Function:script:'+ $entry.Key) -Value $entry.Value}
  if($nuGuard){$nuGuard.ReleaseMutex();$nuGuard.Dispose()}
  $nuReport.update_invocations=$script:NUUpdateInvocations;$nuReport.pairing_actions_blocked=$script:NUPairingBlocked
  $nuReport.signed_private_release_verified=$script:NUSignedReleaseVerified
  $nuReport.finished_utc=[DateTime]::UtcNow.ToString('o')
  $nuConfigBefore=$null;$nuBefore=$null
  $nuJson=$nuReport|ConvertTo-Json -Depth 8 -Compress
  if($nuProgressPath -and -not (Test-Path -LiteralPath $NativeReceiptPath)){
    $bytes=[Text.Encoding]::UTF8.GetBytes($nuJson)
    $file=New-Object IO.FileStream($NativeReceiptPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$file.Write($bytes,0,$bytes.Length);$file.Flush($true)}finally{$file.Dispose()}
  }
}
$nuJson
if($nuReport.state -ceq 'PASS_PRIVATE_SIGNED_0358_RUNNING_UPDATE'){exit 0}
exit 2
