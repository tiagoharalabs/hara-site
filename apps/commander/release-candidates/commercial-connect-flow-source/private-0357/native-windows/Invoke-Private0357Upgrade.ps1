# Narrow one-device QA upgrade driver. Run only in the existing CommanderQA
# interactive, limited Windows PowerShell 5.1 session. No pairing action allowed.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$NativeReceiptPath)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$nuSid='S-1-5-21-1207901905-1500652706-889822281-1005'
$nuDevice='HARA-DEVICE-a544f7b1-3ee1-49f7-aa55-f559376d5d12'
$nuOrigin='https://commander.haralabs.com.br'
$nuRelease='https://192.168.10.23:18444/releases/0.3.57'
$nuController='C:\Users\CommanderQA\Desktop\HARA Commander Conexao QA\Connect-Commander.ps1'
$nuControllerSha='2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da'
$nuOldAgentSha='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'
$nuTargetAgentSha='3552947e632ba16eb0a1384b8e6b0d3a84d507bbe156ff1bb4db360c212895b7'
$nuTargetInstallerSha='cc6234d0d51e853d9b1a897d496038ceba8b9164d318a70d98f62a7bae3c07ff'
$nuManifestSha='d1a9361f5edec6c926d6febc7990e9b0c00df28f5131c6ffe1146ebe348554d0'
$nuResultsRoot='C:\ProgramData\HARA-QA\windows-install-0356-20261028\results'
$nuContext=$null;$nuBefore=$null;$nuPrivate=$null;$nuGuard=$null;$nuOriginalFunctions=@{}
$script:NUUpdateInvocations=0;$script:NUPairingBlocked=0;$script:NUUpdaterStarted=$null
$script:NUSignedReleaseVerified=$false;$script:NUChild=$null
$nuReport=[ordered]@{
  schema='hara.commander.windows-private-0357-upgrade.v1';started_utc=[DateTime]::UtcNow.ToString('o');
  state='HOLD';stage='IDENTITY';device_id=$nuDevice;credential_origin=$nuOrigin;
  artifact_release_base=$nuRelease;artifact_source='EXPLICIT_PRIVATE_SIGNED_RELEASE';
  expected_agent_sha256=$nuTargetAgentSha;expected_installer_sha256=$nuTargetInstallerSha;
  expected_manifest_sha256=$nuManifestSha;public_distribution_changed=$false;
  pairing_permitted=$false;device_token_exposed=$false;optional_rollback_performed=$false
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
      if($current.Version -ceq '0.3.57' -and $current.AgentSha -ceq $nuTargetAgentSha){$value.state='TARGET_INSTALLED_AND_CONNECTED'}
      elseif($current.Version -ceq '0.3.56' -and $current.AgentSha -ceq $nuOldAgentSha){$value.state='ORIGINAL_INSTALLED_AND_CONNECTED'}
    }
  }catch{$value.error_code=Code-NU $_}
  return [pscustomobject]$value
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
  Need-NU ($nuBefore.Version -ceq '0.3.56' -and $nuBefore.AgentSha -ceq $nuOldAgentSha) 'EXPECTED_0356_AGENT_REQUIRED'
  Need-NU ([string](Get-CCTask $nuContext).State -ceq 'Running') 'EXISTING_AGENT_TASK_MUST_BE_RUNNING'
  $nuConfigBefore=[IO.File]::ReadAllBytes($nuContext.ConfigPath)
  $nuApprovalBefore=[string]$nuBefore.Config.approval_mode
  Need-NU ($nuApprovalBefore -cin @('ASK_EVERY_ACTION','SESSION_TRUSTED','PERSISTENT_TRUSTED')) 'EXISTING_APPROVAL_MODE_INVALID'
  $nuTaskXmlBefore=Export-ScheduledTask -TaskName $nuContext.TaskName -TaskPath '\'
  $nuRuntimeBefore=Runtime-NU $nuContext
  Need-NU ($nuRuntimeBefore.version -ceq '0.3.56') 'EXPECTED_0356_RUNTIME_REQUIRED'
  $nuReport.before=[ordered]@{version=$nuBefore.Version;agent_sha256=$nuBefore.AgentSha;approval_mode=$nuApprovalBefore;runtime=$nuRuntimeBefore;task_state='Running';current_user_policy=$nuPolicyBefore.CurrentUser}
  foreach($name in @('Get-CCPublicBytes','Get-CCRelease','Invoke-CCInstaller','Ensure-CCRuntime')){$nuOriginalFunctions[$name]=(Get-Item ('Function:'+ $name)).ScriptBlock}

  function script:Get-CCPublicBytes([string]$Uri,[int]$Maximum=2097152){
    Need-NU ($Uri -cin @(($nuRelease+'/release/agent-manifest.json'),($nuRelease+'/release/agent-manifest.sig.json'),($nuRelease+'/agent/windows.ps1'),($nuRelease+'/install/windows.ps1'))) 'UNEXPECTED_RELEASE_DOWNLOAD_URI'
    $bytes=& ($nuOriginalFunctions['Get-CCPublicBytes']) $Uri $Maximum
    if($Uri -ceq ($nuRelease+'/release/agent-manifest.json')){Need-NU ((Get-CCSha $bytes) -ceq $nuManifestSha) 'EXPECTED_0357_MANIFEST_HASH_REQUIRED'}
    return ,$bytes
  }
  function script:Get-CCRelease($Context,[string]$Origin){
    Need-NU ($Origin -ceq $nuOrigin -and $Context.QaReleaseBase -ceq $nuRelease) 'CREDENTIAL_AND_RELEASE_SCOPE_MISMATCH'
    $release=& ($nuOriginalFunctions['Get-CCRelease']) $Context $Origin
    Need-NU ($release.Version -ceq '0.3.57' -and $release.BaseUrl -ceq $nuRelease -and $release.AgentSha -ceq $nuTargetAgentSha -and $release.InstallerSha -ceq $nuTargetInstallerSha -and $release.AgentBytes.Length -eq 172687) 'EXPECTED_SIGNED_0357_RELEASE_REQUIRED'
    $script:NUSignedReleaseVerified=$true
    return $release
  }
  function script:Ensure-CCRuntime($Context,$State){
    # The signed update owns its own task restart/rollback. This QA observer
    # deliberately never starts a stopped task, including on failure recovery.
    $floor=if($State.Version -ceq '0.3.57' -and $script:NUUpdaterStarted){[DateTimeOffset]($script:NUUpdaterStarted.AddSeconds(-5))}else{[DateTimeOffset]::UtcNow.AddSeconds(-90)}
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
    Need-NU ($dispatchState.Version -ceq '0.3.56' -and $dispatchState.AgentSha -ceq $nuOldAgentSha -and $dispatchState.TaskState -ceq 'Running') 'PREUPDATE_INSTALLED_STATE_CHANGED'
    Need-NU ($Release.Version -ceq '0.3.57' -and $Release.AgentSha -ceq $nuTargetAgentSha -and $Release.InstallerSha -ceq $nuTargetInstallerSha) 'UPGRADE_TARGET_PIN_MISMATCH'
    $script:NUUpdateInvocations++
    $installerPath=Join-Path $nuPrivate 'verified-update-0357.ps1'
    [IO.File]::WriteAllBytes($installerPath,$Release.InstallerBytes)
    Need-NU ((Get-CCFileSha $installerPath) -ceq $nuTargetInstallerSha) 'STAGED_0357_INSTALLER_MISMATCH'
    $tokens=$null;$errors=$null
    [Management.Automation.Language.Parser]::ParseFile($installerPath,[ref]$tokens,[ref]$errors)|Out-Null
    Need-NU ($errors.Count -eq 0) 'STAGED_0357_INSTALLER_SYNTAX_INVALID'
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

  Checkpoint-NU 'RUN_FROZEN_CONNECT_CORE'
  $nuCore=Invoke-CCConnect $nuContext
  $nuReport.controller=[ordered]@{}
  foreach($field in @('state','stage','binding','connected','update','error_code','update_error_code','recovery_error_code','installed_version','target_version','enrollment_preserved','last_successful_heartbeat_at_utc')){
    if($nuCore.PSObject.Properties[$field]){$nuReport.controller[$field]=$nuCore.$field}
  }
  Need-NU ($nuCore.state -ceq 'CONNECTED' -and $nuCore.update -ceq 'UPDATED' -and -not $nuCore.paired_this_run) 'EXPECTED_CONNECTED_UPGRADE_NOT_COMPLETED'
  Need-NU ($script:NUUpdateInvocations -eq 1 -and $script:NUPairingBlocked -eq 0) 'UNEXPECTED_UPGRADE_ACTION_COUNT'
  Checkpoint-NU 'FINAL_READONLY_ATTESTATION'
  $nuReport.after=Fallback-NU
  Need-NU ($nuReport.after.state -ceq 'TARGET_INSTALLED_AND_CONNECTED') 'TARGET_UPGRADE_ATTESTATION_FAILED'
  $nuHeartbeat=[DateTimeOffset]::Parse($nuReport.after.runtime.heartbeat_utc)
  $nuStarted=[DateTimeOffset]::Parse($nuReport.after.runtime.started_utc)
  $nuRuntimeFloor=[DateTimeOffset]($script:NUUpdaterStarted.AddSeconds(-5))
  Need-NU ($nuHeartbeat -ge $nuRuntimeFloor -and $nuStarted -ge $nuRuntimeFloor -and $nuReport.after.runtime.started_utc -cne $nuRuntimeBefore.started_utc) 'NEW_RUNTIME_START_OR_HEARTBEAT_UNCONFIRMED'
  $nuReport.event_v2_runtime=[ordered]@{before=$nuRuntimeBefore.event_evidence;after=$nuReport.after.runtime.event_evidence;comparison=$(if($nuRuntimeBefore.event_evidence.state -ceq 'OBSERVED' -and $nuReport.after.runtime.event_evidence.state -ceq 'OBSERVED'){if(($nuRuntimeBefore.event_evidence.fields|ConvertTo-Json -Compress) -ceq ($nuReport.after.runtime.event_evidence.fields|ConvertTo-Json -Compress)){'UNCHANGED'}else{'CHANGED'}}else{'NOT_OBSERVED'})}
  $nuReport.state='PASS_PRIVATE_SIGNED_0357_UPGRADE';$nuReport.stage='COMPLETE'
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
if($nuReport.state -ceq 'PASS_PRIVATE_SIGNED_0357_UPGRADE'){exit 0}
exit 2
