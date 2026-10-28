# Isolated native-ready fixture harness. No real enrollment, task mutation,
# product file mutation, credential export or network request is permitted.
[CmdletBinding()]
param([string]$Controller=(Join-Path $PSScriptRoot 'Connect-Commander.ps1'))
$ErrorActionPreference='Stop'
$parseTokens=$null;$parseErrors=$null
[Management.Automation.Language.Parser]::ParseFile($Controller,[ref]$parseTokens,[ref]$parseErrors)|Out-Null
if($parseErrors.Count -ne 0){throw 'CONTROLLER_NATIVE_PARSE_FAILED'}
. $Controller
$script:CCCases=New-Object Collections.Generic.List[object]
$script:CCSaved=@{}
foreach($name in @('Get-CCInstalledState','Test-CCCredential','Get-CCRelease','Ensure-CCRuntime','Invoke-CCInstaller','Invoke-CCRequest')){
  $script:CCSaved[$name]=(Get-Item ('Function:'+ $name)).ScriptBlock
}
function Test-Need([bool]$Condition,[string]$Code){if(-not $Condition){throw $Code}}
function Run-Case([string]$Name,[scriptblock]$Body){
  try{& $Body;$script:CCCases.Add([pscustomobject]@{name=$Name;state='PASS'})}
  catch{$script:CCCases.Add([pscustomobject]@{name=$Name;state='FAIL';code=(Get-CCErrorCode $_)})}
}
function Restore-Functions {
  foreach($entry in $script:CCSaved.GetEnumerator()){Set-Item -Path ('Function:script:'+ $entry.Key) -Value $entry.Value}
}
function Reset-Fixture {
  $script:CCFixture=@{
    State=[pscustomobject]@{
      ConfigPresent=$true;AgentPresent=$true;TaskPresent=$true;
      Config=[pscustomobject]@{device_id='HARA-DEVICE-FIXTURE';base_url='https://fixture.invalid';architecture='x64';approval_mode='PERSISTENT_TRUSTED';encrypted_device_token='fixture-only-not-a-credential'};
      ConfigSha='fixture-config-unchanged';Version='0.3.56';AgentSha='fixture-agent-056';
      Origin='https://fixture.invalid';DeviceId='HARA-DEVICE-FIXTURE';TaskState='Running'
    };
    Release=[pscustomobject]@{Version='0.3.56';AgentSha='fixture-agent-056';PairExisting=$true;Reenroll=$true};
    StateError='';AuthError='';ReleaseError='';Actions=@();AuthSequence=@('VALID');AuthCalls=0;RuntimeCalls=0;
    InstallerFailure=$false;RuntimeFailureAfterFirst=$false;ChangeCredential=$false
  }
  Set-Item Function:script:Get-CCInstalledState -Value {
    param($Context)
    if($script:CCFixture.StateError){throw $script:CCFixture.StateError}
    return ($script:CCFixture.State|ConvertTo-Json -Depth 8|ConvertFrom-Json)
  }
  Set-Item Function:script:Test-CCCredential -Value {
    param($State)
    $script:CCFixture.AuthCalls++
    if($script:CCFixture.AuthError){throw $script:CCFixture.AuthError}
    $index=[Math]::Min($script:CCFixture.AuthCalls-1,$script:CCFixture.AuthSequence.Count-1)
    return $script:CCFixture.AuthSequence[$index]
  }
  Set-Item Function:script:Get-CCRelease -Value {
    param($Context,[string]$Origin)
    if($script:CCFixture.ReleaseError){throw $script:CCFixture.ReleaseError}
    return $script:CCFixture.Release
  }
  Set-Item Function:script:Ensure-CCRuntime -Value {
    param($Context,$State)
    $script:CCFixture.RuntimeCalls++
    if($script:CCFixture.RuntimeFailureAfterFirst -and $script:CCFixture.RuntimeCalls -gt 1){throw 'FRESH_RUNTIME_HEARTBEAT_NOT_CONFIRMED'}
    return [DateTime]::UtcNow.ToString('o')
  }
  Set-Item Function:script:Invoke-CCInstaller -Value {
    param($Context,$State,$Release,[string]$Action)
    $script:CCFixture.Actions+=@($Action)
    if($script:CCFixture.InstallerFailure){throw 'VERIFIED_INSTALLER_ACTION_FAILED'}
    $script:CCFixture.State.Version=$Release.Version;$script:CCFixture.State.AgentSha=$Release.AgentSha
    if($Action -ne 'update'){
      $script:CCFixture.State.ConfigPresent=$true;$script:CCFixture.State.AgentPresent=$true;$script:CCFixture.State.TaskPresent=$true
      $script:CCFixture.State.DeviceId='HARA-DEVICE-FIXTURE';$script:CCFixture.State.ConfigSha='fixture-config-unchanged'
    }
    if($script:CCFixture.ChangeCredential){$script:CCFixture.State.ConfigSha='fixture-unexpected-new-credential'}
  }
}
$fixtureContext=[pscustomobject]@{QaReleaseBase='';ApprovalMode='PERSISTENT_TRUSTED'}
try{
  Run-Case 'valid_current_no_prompt_no_update' {
    Reset-Fixture;$result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED' -and $result.update -ceq 'ALREADY_CURRENT' -and $result.enrollment_preserved -eq $true) 'CURRENT_RESULT_INVALID'
    Test-Need ($script:CCFixture.Actions.Count -eq 0 -and $script:CCFixture.AuthCalls -eq 1) 'CURRENT_MUST_NOT_INVOKE_INSTALLER'
  }
  Run-Case 'valid_older_updates_same_binding' {
    Reset-Fixture;$script:CCFixture.State.Version='0.3.55';$script:CCFixture.State.AgentSha='fixture-agent-055'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED' -and $result.update -ceq 'UPDATED' -and $result.installed_version -ceq '0.3.56' -and $result.enrollment_preserved) 'UPDATE_RESULT_INVALID'
    Test-Need ($script:CCFixture.Actions.Count -eq 1 -and $script:CCFixture.Actions[0] -ceq 'update' -and $script:CCFixture.State.ConfigSha -ceq 'fixture-config-unchanged') 'UPDATE_CHANGED_BINDING'
  }
  Run-Case 'older_release_channel_never_downgrades' {
    Reset-Fixture;$script:CCFixture.State.Version='0.3.57';$script:CCFixture.State.AgentSha='fixture-agent-057'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED_UPDATE_HOLD' -and $result.update_error_code -ceq 'RELEASE_CHANNEL_BEHIND_INSTALLED' -and $result.connected -and $script:CCFixture.Actions.Count -eq 0) 'DOWNGRADE_GUARD_FAILED'
  }
  Run-Case 'untrusted_release_preserves_valid_connection' {
    Reset-Fixture;$script:CCFixture.ReleaseError='RELEASE_SIGNATURE_INVALID'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED_UPDATE_HOLD' -and $result.connected -and $result.enrollment_preserved -and $result.binding -ceq 'VALID' -and $script:CCFixture.Actions.Count -eq 0) 'CHANNEL_FAILURE_RESET_BINDING'
  }
  Run-Case 'local_same_version_hash_mismatch_is_hold' {
    Reset-Fixture;$script:CCFixture.State.AgentSha='fixture-tampered-same-version'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and -not $result.connected -and $result.error_code -ceq 'INSTALLED_AGENT_INTEGRITY_MISMATCH' -and $script:CCFixture.Actions.Count -eq 0) 'LOCAL_INTEGRITY_NOT_HELD'
  }
  Run-Case 'partial_installed_state_never_prompts' {
    Reset-Fixture;$script:CCFixture.StateError='INSTALLED_STATE_INCOMPLETE'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and $result.error_code -ceq 'INSTALLED_STATE_INCOMPLETE' -and $script:CCFixture.Actions.Count -eq 0 -and $script:CCFixture.AuthCalls -eq 0) 'PARTIAL_STATE_RESET'
  }
  Run-Case 'network_auth_failure_never_reenrolls' {
    Reset-Fixture;$script:CCFixture.AuthError='NETWORK_UNAVAILABLE'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and $result.error_code -ceq 'NETWORK_UNAVAILABLE' -and $script:CCFixture.Actions.Count -eq 0 -and $script:CCFixture.State.ConfigSha -ceq 'fixture-config-unchanged') 'NETWORK_FAILURE_RESET'
  }
  Run-Case 'clean_unpaired_selects_install_after_release' {
    Reset-Fixture;$script:CCFixture.State.ConfigPresent=$false;$script:CCFixture.State.AgentPresent=$false;$script:CCFixture.State.TaskPresent=$false;$script:CCFixture.State.Version=$null
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED' -and $result.paired_this_run -and $script:CCFixture.Actions.Count -eq 1 -and $script:CCFixture.Actions[0] -ceq 'install') 'CLEAN_PAIR_DISPATCH_INVALID'
  }
  Run-Case 'installed_unpaired_selects_transactional_pair_existing' {
    Reset-Fixture;$script:CCFixture.State.ConfigPresent=$false;$script:CCFixture.State.Version='0.3.55';$script:CCFixture.State.AgentSha='fixture-agent-055'
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED' -and $result.paired_this_run -and $script:CCFixture.Actions[0] -ceq 'pair-existing') 'PAIR_EXISTING_DISPATCH_INVALID'
  }
  Run-Case 'legacy_installer_cannot_delete_unpaired_artifacts' {
    Reset-Fixture;$script:CCFixture.State.ConfigPresent=$false;$script:CCFixture.Release.PairExisting=$false
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and $result.error_code -ceq 'SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED' -and $script:CCFixture.Actions.Count -eq 0) 'UNSUPPORTED_PAIR_WAS_INVOKED'
  }
  Run-Case 'explicit_rejection_requires_signed_reenroll_capability' {
    Reset-Fixture;$script:CCFixture.AuthSequence=@('REJECTED');$script:CCFixture.Release.Reenroll=$false
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and $result.binding -ceq 'REJECTED' -and $result.error_code -ceq 'SIGNED_INSTALLER_REENROLL_UNSUPPORTED' -and $script:CCFixture.Actions.Count -eq 0) 'REJECTED_BINDING_UNSAFE_REPAIR'
  }
  Run-Case 'explicit_rejection_reenrolls_only_after_verified_release' {
    Reset-Fixture;$script:CCFixture.AuthSequence=@('REJECTED','VALID')
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED' -and $result.paired_this_run -and $script:CCFixture.Actions[0] -ceq 're-enroll') 'REENROLL_DISPATCH_INVALID'
  }
  Run-Case 'update_failure_confirms_recovered_connection' {
    Reset-Fixture;$script:CCFixture.State.Version='0.3.55';$script:CCFixture.State.AgentSha='fixture-agent-055';$script:CCFixture.InstallerFailure=$true
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'CONNECTED_UPDATE_HOLD' -and $result.connected -and $result.update_connection_recovery -ceq 'CONFIRMED' -and $result.enrollment_preserved) 'UPDATE_RECOVERY_NOT_CONFIRMED'
  }
  Run-Case 'update_failure_cannot_claim_unconfirmed_connection' {
    Reset-Fixture;$script:CCFixture.State.Version='0.3.55';$script:CCFixture.State.AgentSha='fixture-agent-055';$script:CCFixture.InstallerFailure=$true;$script:CCFixture.RuntimeFailureAfterFirst=$true
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and -not $result.connected -and $result.update_connection_recovery -ceq 'UNCONFIRMED') 'UPDATE_RECOVERY_FALSE_CONNECTED'
  }
  Run-Case 'unexpected_credential_change_is_not_success' {
    Reset-Fixture;$script:CCFixture.State.Version='0.3.55';$script:CCFixture.State.AgentSha='fixture-agent-055';$script:CCFixture.ChangeCredential=$true
    $result=Invoke-CCConnect $fixtureContext
    Test-Need ($result.state -ceq 'HOLD' -and -not $result.connected -and $result.update_error_code -ceq 'EXISTING_ENROLLMENT_CHANGED') 'UNEXPECTED_CREDENTIAL_CHANGE_ACCEPTED'
  }
  Restore-Functions
  $script:CCFixtureHttp=[pscustomobject]@{Status=200;Bytes=[Text.Encoding]::UTF8.GetBytes('{"ok":true,"device_id":"HARA-DEVICE-AUTH-FIXTURE"}')}
  $script:CCCapturedHeartbeat=$null
  Set-Item Function:script:Invoke-CCRequest -Value {
    param([string]$Uri,[string]$Method,[byte[]]$Body,[string]$Bearer,[int]$MaximumBytes)
    if($Uri -notlike 'https://fixture.invalid/*'){throw 'FIXTURE_NETWORK_ESCAPE_REFUSED'}
    $script:CCCapturedHeartbeat=[Text.Encoding]::UTF8.GetString($Body)|ConvertFrom-Json
    return $script:CCFixtureHttp
  }
  $fixtureSecret=ConvertTo-SecureString 'nonproduction-fixture-token' -AsPlainText -Force
  try{$cipher=$fixtureSecret|ConvertFrom-SecureString}finally{$fixtureSecret.Dispose()}
  $authState=[pscustomobject]@{Origin='https://fixture.invalid';DeviceId='HARA-DEVICE-AUTH-FIXTURE';Version='0.3.55';Config=[pscustomobject]@{encrypted_device_token=$cipher;architecture='x64';approval_mode='PERSISTENT_TRUSTED'}}
  Run-Case 'real_heartbeat_uses_actual_installed_version' {
    Test-Need ((Test-CCCredential $authState) -ceq 'VALID') 'AUTH_VALID_FIXTURE_FAILED'
    Test-Need ($script:CCCapturedHeartbeat.agent_version -ceq '0.3.55') 'AUTH_REPORTED_TARGET_INSTEAD_OF_INSTALLED'
  }
  Run-Case 'wrong_device_id_is_ambiguous_not_rejected' {
    $script:CCFixtureHttp.Bytes=[Text.Encoding]::UTF8.GetBytes('{"ok":true,"device_id":"WRONG-DEVICE"}')
    $code='';try{[void](Test-CCCredential $authState)}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'DEVICE_AUTH_CHECK_AMBIGUOUS') 'AUTH_WRONG_DEVICE_ACCEPTED'
  }
  Run-Case 'only_explicit_401_auth_invalid_is_rejected' {
    $script:CCFixtureHttp.Status=401;$script:CCFixtureHttp.Bytes=[Text.Encoding]::UTF8.GetBytes('{"code":"DEVICE_AUTH_INVALID"}')
    Test-Need ((Test-CCCredential $authState) -ceq 'REJECTED') 'AUTH_EXPLICIT_REJECTION_FAILED'
    $script:CCFixtureHttp.Bytes=[Text.Encoding]::UTF8.GetBytes('{"code":"OTHER_FAILURE"}')
    $code='';try{[void](Test-CCCredential $authState)}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'DEVICE_AUTH_CHECK_AMBIGUOUS') 'AUTH_OTHER_401_RESET_BINDING'
  }
  Restore-Functions
  $oldKid=$script:CCSigningKid;$oldN=$script:CCSigningN;$oldE=$script:CCSigningE
  $fixtureRsa=New-Object Security.Cryptography.RSACng(2048)
  Test-Need ($fixtureRsa.KeySize -eq 2048) 'FIXTURE_RSA_KEY_SIZE_INVALID'
  $public=$fixtureRsa.ExportParameters($false)
  $script:CCSigningN=[Convert]::ToBase64String($public.Modulus).TrimEnd('=').Replace('+','-').Replace('/','_')
  $script:CCSigningE=[Convert]::ToBase64String($public.Exponent).TrimEnd('=').Replace('+','-').Replace('/','_')
  function New-FixtureSignature([byte[]]$Bytes){
    $signed=$fixtureRsa.SignData($Bytes,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $document=@{schema='hara.commander-release-signature.v1';alg='RS256';kid=$script:CCSigningKid;manifest_sha256=(Get-CCSha $Bytes);signature=[Convert]::ToBase64String($signed).TrimEnd('=').Replace('+','-').Replace('/','_')}
    return ,[Text.Encoding]::UTF8.GetBytes(($document|ConvertTo-Json -Compress))
  }
  $fixtureAgent=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.56"'+"`n")
  $fixtureInstaller=[Text.Encoding]::UTF8.GetBytes("# HARA_COMMANDER_PAIR_EXISTING=1`n# HARA_COMMANDER_REENROLL=1`n# Inert fixture; never executed.`n")
  $rows=@()
  foreach($name in @('agent/linux.py','agent/windows.ps1','install/linux.sh','install/windows.ps1')){
    $bytes=if($name -eq 'agent/windows.ps1'){$fixtureAgent}elseif($name -eq 'install/windows.ps1'){$fixtureInstaller}else{[Text.Encoding]::UTF8.GetBytes('inert')}
    $rows+=@(@{path=$name;sha256=(Get-CCSha $bytes);bytes=$bytes.Length})
  }
  $manifest=@{schema='hara.commander-agent-release.v1';product='H.A.R.A. Commander';channel='stable';agent_version='0.3.56';files=$rows}
  $manifestBytes=[Text.Encoding]::UTF8.GetBytes(($manifest|ConvertTo-Json -Depth 8 -Compress))
  $signatureBytes=New-FixtureSignature $manifestBytes
  Run-Case 'real_rsa_manifest_signature_passes' {
    $value=Assert-CCManifest $manifestBytes $signatureBytes
    Test-Need ([string]$value.agent_version -ceq '0.3.56') 'SIGNED_FIXTURE_REJECTED'
  }
  Run-Case 'real_rsa_manifest_tampering_fails' {
    $bad=$manifestBytes.Clone();$bad[$bad.Length-1]=32
    $code='';try{[void](Assert-CCManifest $bad $signatureBytes)}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'RELEASE_SIGNATURE_INVALID') 'TAMPERED_MANIFEST_ACCEPTED'
  }
  $script:CCFixtureMap=@{
    'https://fixture.invalid/release/agent-manifest.json'=$manifestBytes;
    'https://fixture.invalid/release/agent-manifest.sig.json'=$signatureBytes;
    'https://fixture.invalid/releases/0.3.56/release/agent-manifest.json'=$manifestBytes;
    'https://fixture.invalid/releases/0.3.56/release/agent-manifest.sig.json'=$signatureBytes;
    'https://fixture.invalid/releases/0.3.56/agent/windows.ps1'=$fixtureAgent;
    'https://fixture.invalid/releases/0.3.56/install/windows.ps1'=$fixtureInstaller
  }
  Set-Item Function:script:Invoke-CCRequest -Value {
    param([string]$Uri,[string]$Method,[byte[]]$Body,[string]$Bearer,[int]$MaximumBytes)
    if($Method -cne 'GET' -or $Bearer -or -not $script:CCFixtureMap.ContainsKey($Uri)){throw 'FIXTURE_NETWORK_ESCAPE_REFUSED'}
    return [pscustomobject]@{Status=200;Bytes=$script:CCFixtureMap[$Uri]}
  }
  Run-Case 'signed_discovery_immutable_and_payload_chain_passes' {
    $release=Get-CCRelease $fixtureContext 'https://fixture.invalid'
    Test-Need ($release.Version -ceq '0.3.56' -and $release.PairExisting -and $release.Reenroll -and $release.AgentSha -ceq (Get-CCSha $fixtureAgent)) 'DISCOVERY_CHAIN_FAILED'
  }
  Run-Case 'different_valid_signed_immutable_manifest_is_held' {
    $other=[Text.Encoding]::UTF8.GetBytes(($manifest|ConvertTo-Json -Depth 8))
    $script:CCFixtureMap['https://fixture.invalid/releases/0.3.56/release/agent-manifest.json']=$other
    $script:CCFixtureMap['https://fixture.invalid/releases/0.3.56/release/agent-manifest.sig.json']=New-FixtureSignature $other
    $code='';try{[void](Get-CCRelease $fixtureContext 'https://fixture.invalid')}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'RELEASE_DISCOVERY_IMMUTABLE_MISMATCH') 'IMMUTABLE_MISMATCH_ACCEPTED'
    $script:CCFixtureMap['https://fixture.invalid/releases/0.3.56/release/agent-manifest.json']=$manifestBytes
    $script:CCFixtureMap['https://fixture.invalid/releases/0.3.56/release/agent-manifest.sig.json']=$signatureBytes
  }
  Run-Case 'signed_manifest_with_wrong_agent_bytes_is_held' {
    $bad=$fixtureAgent.Clone();$bad[0]=35
    $script:CCFixtureMap['https://fixture.invalid/releases/0.3.56/agent/windows.ps1']=$bad
    $code='';try{[void](Get-CCRelease $fixtureContext 'https://fixture.invalid')}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'RELEASE_PAYLOAD_HASH_MISMATCH') 'PAYLOAD_MISMATCH_ACCEPTED'
  }
}finally{
  Restore-Functions
  if($fixtureRsa){$fixtureRsa.Dispose()}
  if($oldN){$script:CCSigningKid=$oldKid;$script:CCSigningN=$oldN;$script:CCSigningE=$oldE}
  $cipher=$null;$authState=$null;$script:CCFixtureHttp=$null;$script:CCCapturedHeartbeat=$null
}
$failed=@($script:CCCases|Where-Object {$_.state -cne 'PASS'})
[pscustomobject]@{schema='hara.commander.connect-fixtures.v1';state=$(if($failed.Count -eq 0){'PASS'}else{'FAIL'});case_count=$script:CCCases.Count;failed_count=$failed.Count;real_enrollment_calls=0;real_task_mutations=0;production_files_modified=$false;cases=$script:CCCases.ToArray()}|ConvertTo-Json -Depth 6
if($failed.Count -gt 0){exit 2}
exit 0
