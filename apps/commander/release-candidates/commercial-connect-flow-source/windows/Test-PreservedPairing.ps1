# Native-ready transaction fixtures. Product paths are isolated temporary files.
# All enrollment, revocation, task operations, task execution and prompts are
# mocked. No real Commander credential or machine enrollment is used.
[CmdletBinding()]
param(
  [string]$Controller='',
  [string]$Helper=''
)
$ErrorActionPreference='Stop'
# Resolve sibling paths after parameter binding. Windows PowerShell 5.1 can
# evaluate parameter defaults before PSScriptRoot is populated by the host.
$fixtureDirectory=$PSScriptRoot
if([string]::IsNullOrWhiteSpace($fixtureDirectory) -and $MyInvocation.MyCommand.Path){
  $fixtureDirectory=Split-Path -Parent $MyInvocation.MyCommand.Path
}
if([string]::IsNullOrWhiteSpace($Controller) -or [string]::IsNullOrWhiteSpace($Helper)){
  if([string]::IsNullOrWhiteSpace($fixtureDirectory)){throw 'FIXTURE_DIRECTORY_UNAVAILABLE'}
  if([string]::IsNullOrWhiteSpace($Controller)){$Controller=Join-Path $fixtureDirectory 'Connect-Commander.ps1'}
  if([string]::IsNullOrWhiteSpace($Helper)){$Helper=Join-Path $fixtureDirectory 'Preserved-Pairing.ps1'}
}
foreach($path in @($Controller,$Helper)){
  $tokens=$null;$errors=$null
  [Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)|Out-Null
  if($errors.Count -ne 0){throw 'TRANSACTION_FIXTURE_PARSE_FAILED'}
}
. $Controller
. $Helper
$ApprovalMode='PERSISTENT_TRUSTED'
$script:PPCases=New-Object Collections.Generic.List[object]
$script:PPFixture=$null
$script:PPOriginal=@{}
foreach($name in @('New-CCContext','Get-CCTask','Test-CCCredential','New-CCPrivateStage','Get-PPVerifiedAgent','Request-PPEnrollment','Revoke-PPNewDevice','Restore-PPFile')){
  $script:PPOriginal[$name]=(Get-Item ('Function:'+ $name)).ScriptBlock
}
function Test-Need([bool]$Condition,[string]$Code){if(-not $Condition){throw $Code}}
function Run-TransactionCase([string]$Name,[scriptblock]$Body){
  try{& $Body;$script:PPCases.Add([pscustomobject]@{name=$Name;state='PASS'})}
  catch{
    $detail=[ordered]@{name=$Name;state='FAIL';code=(Get-CCErrorCode $_)}
    if($script:PPFixture -and $script:PPFixture.RestoreFailure){$detail.restore_failure=$script:PPFixture.RestoreFailure}
    if($script:PPFixture -and $script:PPFixture.Task){$detail.task_state=[string]$script:PPFixture.Task.State}
    $script:PPCases.Add([pscustomobject]$detail)
  }
  finally{
    if($script:PPFixture){
      foreach($stage in $script:PPFixture.Stages){
        if(Test-Path -LiteralPath $stage){
          Test-Need ([IO.Path]::GetFileName($stage) -like 'hara-commander-connect-*') 'FIXTURE_CLEANUP_PATH_REFUSED'
          Remove-Item -LiteralPath $stage -Recurse -Force
        }
      }
      if(Test-Path -LiteralPath $script:PPFixture.Parent){
        Test-Need ([IO.Path]::GetFileName($script:PPFixture.Parent) -like 'hara-preserved-pairing-fixture-*') 'FIXTURE_CLEANUP_PATH_REFUSED'
        Remove-Item -LiteralPath $script:PPFixture.Parent -Recurse -Force
      }
      $script:PPFixture=$null
    }
  }
}
function New-FixtureTask([string]$State){
  $context=$script:PPFixture.Context
  return [pscustomobject]@{
    State=$State;Principal=[pscustomobject]@{UserId=$context.Sid;LogonType='Interactive';RunLevel='Limited'};Triggers=@();
    Actions=@([pscustomobject]@{Execute=$context.PowerShellExe;Arguments=('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$context.AgentPath+'"');WorkingDirectory=''})
  }
}
function New-TransactionFixture([bool]$Enrolled,[bool]$TaskPresent,[bool]$WasRunning){
  $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
  $parent=Join-Path $env:TEMP ('hara-preserved-pairing-fixture-'+[guid]::NewGuid().ToString('N'))
  $root=Join-Path $parent 'Product'
  [void][IO.Directory]::CreateDirectory($root)
  $context=[pscustomobject]@{
    Sid=$identity.User.Value;Root=$root;ConfigPath=(Join-Path $root 'device.json');AgentPath=(Join-Path $root 'hara-commander-agent.ps1');RuntimePath=(Join-Path $root 'runtime-status.json');
    TaskName='HARA-NONEXECUTABLE-FIXTURE';PowerShellExe=(Join-Path $PSHOME 'powershell.exe');RequestedOrigin='https://fixture.invalid';QaReleaseBase='';ApprovalMode='PERSISTENT_TRUSTED'
  }
  [IO.File]::WriteAllText($context.AgentPath,('$AgentVersion = "0.3.55"'+"`n# Inert old fixture; never executed.`n"),[Text.Encoding]::UTF8)
  [IO.File]::WriteAllText($context.RuntimePath,'{"agent_version":"0.3.55","started_at_utc":"2026-01-01T00:00:00Z"}',[Text.Encoding]::UTF8)
  [IO.File]::WriteAllText((Join-Path $root 'keep-unrelated.txt'),'preexisting unrelated file must remain',[Text.Encoding]::UTF8)
  if($Enrolled){
    $oldFixtureSecure=ConvertTo-SecureString 'synthetic-old-fixture-token' -AsPlainText -Force
    try{$oldFixtureCipher=$oldFixtureSecure|ConvertFrom-SecureString}finally{$oldFixtureSecure.Dispose()}
    $oldConfig=@{base_url='https://fixture.invalid';device_id='HARA-DEVICE-OLD-FIXTURE';encrypted_device_token=$oldFixtureCipher;architecture='x64';agent_version='0.3.55';approval_mode='PERSISTENT_TRUSTED'}
    [IO.File]::WriteAllText($context.ConfigPath,($oldConfig|ConvertTo-Json),[Text.Encoding]::UTF8)
  }
  $script:PPFixture=@{
    Parent=$parent;Context=$context;Task=$null;TaskXml='<Task>inert-fixture-v1</Task>';Stages=@();VerifiedPath='';
    PromptCalls=0;RevokeCalls=0;RegisterCalls=0;UnregisterCalls=0;StartCalls=0;StopCalls=0;
    OldCredential='REJECTED';AuthNetworkFailure=$false;RejectNewCredential=$false;PayloadFailure=$false;EmptyCode=$false;TamperCachedAgent=$false;ChangeTaskWhilePrompting=$false;
    FailNewStartup=$false;FailRestore=$false;RevokeSucceeds=$true;RestoreFailure=$null
  }
  if($TaskPresent){$script:PPFixture.Task=New-FixtureTask $(if($WasRunning){'Running'}else{'Ready'})}
  $script:PPFixture.BeforeAgentSha=Get-CCFileSha $context.AgentPath
  $script:PPFixture.BeforeRuntimeSha=Get-CCFileSha $context.RuntimePath
  $script:PPFixture.BeforeConfigSha=if($Enrolled){Get-CCFileSha $context.ConfigPath}else{$null}
  $script:PPFixture.BeforeAcl=@{}
  foreach($path in @($context.AgentPath,$context.RuntimePath,$context.ConfigPath)){
    if(Test-Path -LiteralPath $path){
      $acl=Get-Acl -LiteralPath $path
      $script:PPFixture.BeforeAcl[$path]=@{
        owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;
        group=$acl.GetGroup([Security.Principal.SecurityIdentifier]).Value;
        access=$acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access);
        protected=$acl.AreAccessRulesProtected
      }
    }
  }
  Set-Item Function:script:New-CCContext -Value {param($RequestedOrigin,$QaBase,$RequestedApproval);return $script:PPFixture.Context}
  Set-Item Function:script:Get-CCTask -Value {param($Context);return $script:PPFixture.Task}
  Set-Item Function:script:Test-CCCredential -Value {
    param($State)
    if($State.DeviceId -ceq 'HARA-DEVICE-OLD-FIXTURE'){
      if($script:PPFixture.AuthNetworkFailure){throw 'NETWORK_UNAVAILABLE'}
      return $script:PPFixture.OldCredential
    }
    if($script:PPFixture.RejectNewCredential){throw 'DEVICE_AUTH_CHECK_AMBIGUOUS'}
    return 'VALID'
  }
  Set-Item Function:script:New-CCPrivateStage -Value {
    param($Context)
    $path=& ($script:PPOriginal['New-CCPrivateStage']) $Context
    $script:PPFixture.Stages+=@($path)
    return $path
  }
  Set-Item Function:script:Get-PPVerifiedAgent -Value {
    param($Context,[string]$Stage)
    if($script:PPFixture.PayloadFailure){throw 'PAIRING_AGENT_INTEGRITY_FAILED'}
    $path=Join-Path $Stage 'verified-agent.ps1'
    [IO.File]::WriteAllText($path,('$AgentVersion = "0.3.56"'+"`n# Inert new fixture; never executed.`n"),[Text.Encoding]::UTF8)
    $script:PPFixture.VerifiedPath=$path
    return [pscustomobject]@{Path=$path;Version='0.3.56';Sha=(Get-CCFileSha $path)}
  }
  Set-Item Function:script:Request-PPEnrollment -Value {
    param($Context,$Before,$Verified)
    $script:PPFixture.PromptCalls++
    if($script:PPFixture.EmptyCode){throw 'PAIRING_CODE_EMPTY'}
    if($script:PPFixture.TamperCachedAgent){[IO.File]::AppendAllText($Verified.Path,'tampered')}
    if($script:PPFixture.ChangeTaskWhilePrompting){$script:PPFixture.TaskXml='<Task>inert-external-change</Task>'}
    return [pscustomobject]@{DeviceId='HARA-DEVICE-NEW-FIXTURE';Token='synthetic-nonproduction-fixture-token';Architecture='x64';ApprovalMode='PERSISTENT_TRUSTED'}
  }
  Set-Item Function:script:Revoke-PPNewDevice -Value {
    param($Origin,$DeviceId,$Token)
    Test-Need ($Origin -ceq 'https://fixture.invalid' -and $DeviceId -ceq 'HARA-DEVICE-NEW-FIXTURE') 'FIXTURE_REVOKE_SCOPE_INVALID'
    $script:PPFixture.RevokeCalls++;return $script:PPFixture.RevokeSucceeds
  }
  Set-Item Function:script:Restore-PPFile -Value {
    param($Context,$Preimage)
    if($script:PPFixture.FailRestore -and $Preimage.Path -ceq $Context.AgentPath){throw 'PAIRING_FILE_RESTORE_MISMATCH'}
    try{& ($script:PPOriginal['Restore-PPFile']) $Context $Preimage}
    catch{
      $restoreError=$_
      $kind=if($Preimage.Path -ceq $Context.ConfigPath){'CONFIG'}elseif($Preimage.Path -ceq $Context.AgentPath){'AGENT'}else{'RUNTIME'}
      $inner=$restoreError.Exception.InnerException
      $backupMatches=$null;$targetMatches=$null
      try{$backupMatches=((Get-CCFileSha $Preimage.Backup) -ceq $Preimage.Sha)}catch{}
      try{$targetMatches=((Get-CCFileSha $Preimage.Path) -ceq $Preimage.Sha)}catch{}
      $aclDetail=$null
      try{
        $currentAcl=Get-Acl -LiteralPath $Preimage.Path
        $sidType=[Security.Principal.SecurityIdentifier]
        $accessSection=[Security.AccessControl.AccessControlSections]::Access
        $expectedRaw=New-Object Security.AccessControl.RawSecurityDescriptor($Preimage.Acl.GetSecurityDescriptorBinaryForm(),0)
        $actualRaw=New-Object Security.AccessControl.RawSecurityDescriptor($currentAcl.GetSecurityDescriptorBinaryForm(),0)
        $daclBytesEqual=$null
        if($expectedRaw.DiscretionaryAcl -and $actualRaw.DiscretionaryAcl){
          $expectedBytes=New-Object byte[] $expectedRaw.DiscretionaryAcl.BinaryLength
          $actualBytes=New-Object byte[] $actualRaw.DiscretionaryAcl.BinaryLength
          $expectedRaw.DiscretionaryAcl.GetBinaryForm($expectedBytes,0)
          $actualRaw.DiscretionaryAcl.GetBinaryForm($actualBytes,0)
          $daclBytesEqual=((Get-CCSha $expectedBytes) -ceq (Get-CCSha $actualBytes))
        }
        $aclDetail=[pscustomobject]@{
          owner_matches=($currentAcl.GetOwner($sidType).Value -ceq $Preimage.Acl.GetOwner($sidType).Value);
          group_matches=($currentAcl.GetGroup($sidType).Value -ceq $Preimage.Acl.GetGroup($sidType).Value);
          access_sddl_matches=($currentAcl.GetSecurityDescriptorSddlForm($accessSection) -ceq $Preimage.Acl.GetSecurityDescriptorSddlForm($accessSection));
          protection_matches=($currentAcl.AreAccessRulesProtected -eq $Preimage.Acl.AreAccessRulesProtected);
          dacl_bytes_match=$daclBytesEqual;
          auto_inherited_flag_matches=(([int]$actualRaw.ControlFlags -band 0x0400) -eq ([int]$expectedRaw.ControlFlags -band 0x0400));
          auto_inherit_required_flag_matches=(([int]$actualRaw.ControlFlags -band 0x0100) -eq ([int]$expectedRaw.ControlFlags -band 0x0100))
        }
      }catch{}
      $script:PPFixture.RestoreFailure=[pscustomobject]@{
        file_kind=$kind;code=(Get-CCErrorCode $restoreError);exception_type=$restoreError.Exception.GetType().FullName;hresult=$restoreError.Exception.HResult;
        inner_exception_type=$(if($inner){$inner.GetType().FullName}else{$null});
        inner_hresult=$(if($inner){$inner.HResult}else{$null});
        script_line=$restoreError.InvocationInfo.ScriptLineNumber;
        script_name=[IO.Path]::GetFileName([string]$restoreError.InvocationInfo.ScriptName);
        backup_hash_matches=$backupMatches;target_hash_matches=$targetMatches;acl_comparison=$aclDetail
      }
      throw
    }
  }
}
# Mock the OS/task and remaining installer seams before invoking transactions.
function script:Write-Host {param($Object,$ForegroundColor);}
function script:Invoke-CCRequest {throw 'FIXTURE_NETWORK_ESCAPE_REFUSED'}
function script:Invoke-WebRequest {throw 'FIXTURE_NETWORK_ESCAPE_REFUSED'}
function script:Assert-CommanderBaseUrl {[void](Get-CCOrigin $script:BaseUrl)}
function script:Export-ScheduledTask {param($TaskName,$TaskPath,$ErrorAction);return $script:PPFixture.TaskXml}
function script:Stop-ScheduledTask {param($TaskName,$TaskPath,$ErrorAction);$script:PPFixture.StopCalls++;$script:PPFixture.Task.State='Ready'}
function script:Start-ScheduledTask {param($TaskName,$TaskPath,$ErrorAction);$script:PPFixture.StartCalls++;$script:PPFixture.Task.State='Running'}
function script:New-ScheduledTaskAction {param($Execute,$Argument);return [pscustomobject]@{Execute=$Execute;Arguments=$Argument}}
function script:New-ScheduledTaskPrincipal {param($UserId,$LogonType,$RunLevel);return [pscustomobject]@{UserId=$UserId;LogonType=$LogonType;RunLevel=$RunLevel}}
function script:New-ScheduledTaskSettingsSet {param([switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,[switch]$StartWhenAvailable,$RestartCount,$RestartInterval);return [pscustomobject]@{Inert=$true}}
function script:Register-ScheduledTask {
  param($TaskName,$TaskPath,$Action,$Principal,$Settings,$Description,$ErrorAction,[switch]$Force)
  Test-Need (-not $Force -and -not $script:PPFixture.Task) 'FIXTURE_TASK_OVERWRITE_REFUSED'
  $script:PPFixture.RegisterCalls++;$script:PPFixture.Task=New-FixtureTask 'Ready'
}
function script:Unregister-ScheduledTask {param($TaskName,$TaskPath,[switch]$Confirm,$ErrorAction);$script:PPFixture.UnregisterCalls++;$script:PPFixture.Task=$null}
function script:Get-RuntimeStartedAt {return 'fixture-prior-start'}
function script:Wait-AgentStartup {
  param($ExpectedVersion,$PreviousStarted,$Seconds)
  if($ExpectedVersion -ceq '0.3.56'){
    [IO.File]::WriteAllText($script:PPFixture.Context.RuntimePath,'{"agent_version":"0.3.56","started_at_utc":"fixture-new-start"}',[Text.Encoding]::UTF8)
  }
  if($script:PPFixture.FailNewStartup -and $ExpectedVersion -ceq '0.3.56'){return $false}
  return $true
}
function Assert-FixturePreserved {
  $context=$script:PPFixture.Context
  Test-Need ((Get-CCFileSha $context.AgentPath) -ceq $script:PPFixture.BeforeAgentSha) 'FIXTURE_OLD_AGENT_NOT_RESTORED'
  Test-Need ((Get-CCFileSha $context.RuntimePath) -ceq $script:PPFixture.BeforeRuntimeSha) 'FIXTURE_OLD_RUNTIME_NOT_RESTORED'
  if($script:PPFixture.BeforeConfigSha){
    Test-Need ((Get-CCFileSha $context.ConfigPath) -ceq $script:PPFixture.BeforeConfigSha) 'FIXTURE_OLD_CONFIG_NOT_RESTORED'
    $old=Get-Content -LiteralPath $context.ConfigPath -Raw|ConvertFrom-Json
    Assert-FixtureDpapi ([string]$old.encrypted_device_token) 'synthetic-old-fixture-token'
  }
  else{Test-Need (-not (Test-Path -LiteralPath $context.ConfigPath)) 'FIXTURE_NEW_CONFIG_LEFT_BEHIND'}
  foreach($path in $script:PPFixture.BeforeAcl.Keys){
    $expected=$script:PPFixture.BeforeAcl[$path];$acl=Get-Acl -LiteralPath $path
    Test-Need ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $expected.owner -and $acl.GetGroup([Security.Principal.SecurityIdentifier]).Value -ceq $expected.group) 'FIXTURE_ACL_IDENTITY_NOT_PRESERVED'
    $expectedDescriptor=New-Object Security.AccessControl.RawSecurityDescriptor($expected.access)
    $actualDescriptor=New-Object Security.AccessControl.RawSecurityDescriptor($acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access))
    Test-Need ($null -ne $expectedDescriptor.DiscretionaryAcl -and $null -ne $actualDescriptor.DiscretionaryAcl) 'FIXTURE_DACL_NOT_RESTORED'
    $expectedAclBytes=New-Object byte[] $expectedDescriptor.DiscretionaryAcl.BinaryLength
    $actualAclBytes=New-Object byte[] $actualDescriptor.DiscretionaryAcl.BinaryLength
    $expectedDescriptor.DiscretionaryAcl.GetBinaryForm($expectedAclBytes,0)
    $actualDescriptor.DiscretionaryAcl.GetBinaryForm($actualAclBytes,0)
    $changedFlags=[int]$expectedDescriptor.ControlFlags -bxor [int]$actualDescriptor.ControlFlags
    Test-Need ([Convert]::ToBase64String($expectedAclBytes) -ceq [Convert]::ToBase64String($actualAclBytes) -and ($changedFlags -band (-bnot 0x0400)) -eq 0 -and $acl.AreAccessRulesProtected -eq $expected.protected) 'FIXTURE_DACL_NOT_RESTORED'
  }
  Test-Need ((Get-Content -LiteralPath (Join-Path $context.Root 'keep-unrelated.txt') -Raw) -ceq 'preexisting unrelated file must remain') 'FIXTURE_UNRELATED_FILE_CHANGED'
}
function Assert-FixtureRollbackComplete {
  Assert-FixturePreserved
  Test-Need (-not $script:PPFixture.RestoreFailure) 'FIXTURE_ROLLBACK_RESTORE_FAILED'
  foreach($stage in $script:PPFixture.Stages){Test-Need (-not (Test-Path -LiteralPath $stage)) 'FIXTURE_ROLLBACK_STAGE_RETAINED'}
}
function Assert-FixtureDpapi([string]$Cipher,[string]$Expected){
  $secure=$null;$bstr=[IntPtr]::Zero;$plain=$null
  try{
    $secure=ConvertTo-SecureString $Cipher
    $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    Test-Need ($plain -ceq $Expected) 'FIXTURE_DPAPI_RECOVERY_FAILED'
  }finally{
    $plain=$null
    if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)}
    if($secure){$secure.Dispose()}
  }
}
try{
  Run-TransactionCase 'unpaired_existing_agent_pairs_without_root_deletion' {
    New-TransactionFixture $false $false $false
    Invoke-PreservedPairing 'pair-existing'
    $after=Get-CCInstalledState $script:PPFixture.Context
    Test-Need ($after.DeviceId -ceq 'HARA-DEVICE-NEW-FIXTURE' -and $after.Version -ceq '0.3.56' -and $script:PPFixture.RegisterCalls -eq 1 -and $script:PPFixture.StartCalls -eq 1) 'PAIR_EXISTING_SUCCESS_INVALID'
    Test-Need (Test-Path -LiteralPath (Join-Path $script:PPFixture.Context.Root 'keep-unrelated.txt')) 'PRODUCT_DIRECTORY_WAS_DELETED'
  }
  Run-TransactionCase 'unpaired_startup_failure_restores_agent_and_absent_config_task' {
    New-TransactionFixture $false $false $false;$script:PPFixture.FailNewStartup=$true
    $code='';try{Invoke-PreservedPairing 'pair-existing'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_AGENT_STARTUP_UNCONFIRMED' -and $script:PPFixture.RevokeCalls -eq 1 -and -not $script:PPFixture.Task -and $script:PPFixture.UnregisterCalls -eq 1) 'PAIR_EXISTING_ROLLBACK_INVALID'
    Assert-FixtureRollbackComplete
  }
  Run-TransactionCase 'rejected_old_binding_reenroll_preserves_task_definition' {
    New-TransactionFixture $true $true $true
    Invoke-PreservedPairing 're-enroll'
    $after=Get-CCInstalledState $script:PPFixture.Context
    Test-Need ($after.DeviceId -ceq 'HARA-DEVICE-NEW-FIXTURE' -and $script:PPFixture.RegisterCalls -eq 0 -and $script:PPFixture.TaskXml -ceq '<Task>inert-fixture-v1</Task>' -and $script:PPFixture.Task.State -ceq 'Running') 'REENROLL_TASK_REPLACED'
  }
  Run-TransactionCase 'rejected_binding_startup_failure_restores_exact_old_credential' {
    New-TransactionFixture $true $true $true;$script:PPFixture.FailNewStartup=$true
    $code='';try{Invoke-PreservedPairing 're-enroll'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_AGENT_STARTUP_UNCONFIRMED' -and $script:PPFixture.RevokeCalls -eq 1 -and $script:PPFixture.Task.State -ceq 'Running' -and $script:PPFixture.RegisterCalls -eq 0) 'REENROLL_ROLLBACK_INVALID'
    Assert-FixtureRollbackComplete
  }
  Run-TransactionCase 'reenroll_preserves_manual_stop_until_connect_requests_start' {
    New-TransactionFixture $true $true $false
    Invoke-PreservedPairing 're-enroll'
    Test-Need ($script:PPFixture.Task.State -ceq 'Ready' -and $script:PPFixture.StartCalls -eq 0) 'MANUAL_STOP_NOT_PRESERVED'
  }
  Run-TransactionCase 'valid_old_credential_never_prompts_or_resets' {
    New-TransactionFixture $true $true $true;$script:PPFixture.OldCredential='VALID'
    $code='';try{Invoke-PreservedPairing 're-enroll'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'REENROLL_CURRENT_DEVICE_STILL_VALID' -and $script:PPFixture.PromptCalls -eq 0 -and $script:PPFixture.StopCalls -eq 0) 'ACTIVE_BINDING_RESET'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'network_error_never_becomes_credential_rejection' {
    New-TransactionFixture $true $true $true;$script:PPFixture.AuthNetworkFailure=$true
    $code='';try{Invoke-PreservedPairing 're-enroll'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'NETWORK_UNAVAILABLE' -and $script:PPFixture.PromptCalls -eq 0 -and $script:PPFixture.StopCalls -eq 0) 'NETWORK_ERROR_RESET_BINDING'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'payload_failure_holds_before_code_prompt' {
    New-TransactionFixture $false $false $false;$script:PPFixture.PayloadFailure=$true
    $code='';try{Invoke-PreservedPairing 'pair-existing'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_AGENT_INTEGRITY_FAILED' -and $script:PPFixture.PromptCalls -eq 0) 'PAYLOAD_ERROR_CONSUMED_CODE'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'cancelled_code_preserves_existing_agent' {
    New-TransactionFixture $false $false $false;$script:PPFixture.EmptyCode=$true
    $code='';try{Invoke-PreservedPairing 'pair-existing'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_CODE_EMPTY' -and $script:PPFixture.RegisterCalls -eq 0) 'CANCELLED_PAIR_MUTATED_PRODUCT'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'cached_agent_change_revokes_new_device_without_local_commit' {
    New-TransactionFixture $false $false $false;$script:PPFixture.TamperCachedAgent=$true
    $code='';try{Invoke-PreservedPairing 'pair-existing'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_CACHED_AGENT_CHANGED' -and $script:PPFixture.RevokeCalls -eq 1 -and $script:PPFixture.RegisterCalls -eq 0) 'CACHED_AGENT_CHANGE_COMMITTED'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'new_credential_must_authenticate_before_local_commit' {
    New-TransactionFixture $false $false $false;$script:PPFixture.RejectNewCredential=$true
    $code='';try{Invoke-PreservedPairing 'pair-existing'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'DEVICE_AUTH_CHECK_AMBIGUOUS' -and $script:PPFixture.RevokeCalls -eq 1 -and $script:PPFixture.RegisterCalls -eq 0) 'UNCONFIRMED_NEW_CREDENTIAL_COMMITTED'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'external_task_change_is_preserved_and_pairing_is_held' {
    New-TransactionFixture $true $true $true;$script:PPFixture.ChangeTaskWhilePrompting=$true
    $code='';try{Invoke-PreservedPairing 're-enroll'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_TASK_PREIMAGE_CHANGED' -and $script:PPFixture.StopCalls -eq 0 -and $script:PPFixture.TaskXml -ceq '<Task>inert-external-change</Task>') 'EXTERNAL_TASK_CHANGE_OVERWRITTEN'
    Assert-FixturePreserved
  }
  Run-TransactionCase 'rollback_failure_retains_private_preimages' {
    New-TransactionFixture $false $false $false;$script:PPFixture.FailNewStartup=$true;$script:PPFixture.FailRestore=$true
    $code='';try{Invoke-PreservedPairing 'pair-existing'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_AGENT_STARTUP_UNCONFIRMED') 'ROLLBACK_FAILURE_MASKED_ORIGINAL_ERROR'
    $retained=@($script:PPFixture.Stages|Where-Object {Test-Path -LiteralPath (Join-Path $_ 'agent.preimage')})
    Test-Need ($retained.Count -eq 1 -and (Get-CCFileSha (Join-Path $retained[0] 'agent.preimage')) -ceq $script:PPFixture.BeforeAgentSha) 'ROLLBACK_BACKUP_NOT_RETAINED'
  }
  Run-TransactionCase 'pending_revoke_retains_private_dpapi_new_credential' {
    New-TransactionFixture $true $true $true;$script:PPFixture.FailNewStartup=$true;$script:PPFixture.RevokeSucceeds=$false
    $code='';try{Invoke-PreservedPairing 're-enroll'}catch{$code=Get-CCErrorCode $_}
    Test-Need ($code -ceq 'PAIRING_AGENT_STARTUP_UNCONFIRMED' -and $script:PPFixture.RevokeCalls -eq 1) 'PENDING_REVOKE_FIXTURE_INVALID'
    Assert-FixturePreserved
    $receipts=@($script:PPFixture.Stages|ForEach-Object {Join-Path $_ 'new-enrollment-recovery.private.json'}|Where-Object {Test-Path -LiteralPath $_})
    Test-Need ($receipts.Count -eq 1) 'PENDING_REVOKE_RECOVERY_RECEIPT_MISSING'
    $receipt=Get-Content -LiteralPath $receipts[0] -Raw|ConvertFrom-Json
    Test-Need ($receipt.device_id -ceq 'HARA-DEVICE-NEW-FIXTURE' -and $receipt.origin -ceq 'https://fixture.invalid' -and $receipt.credential_protection -ceq 'DPAPI_CURRENT_USER') 'PENDING_REVOKE_RECOVERY_SCOPE_INVALID'
    Assert-FixtureDpapi ([string]$receipt.encrypted_device_token) 'synthetic-nonproduction-fixture-token'
    $acl=Get-Acl -LiteralPath $receipts[0]
    Test-Need ($acl.AreAccessRulesProtected -and $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $script:PPFixture.Context.Sid) 'PENDING_REVOKE_RECOVERY_ACL_INVALID'
    foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
      Test-Need ($rule.AccessControlType -ne 'Allow' -or $rule.IdentityReference.Value -ceq $script:PPFixture.Context.Sid) 'PENDING_REVOKE_RECOVERY_READERS_INVALID'
    }
  }
}finally{
  foreach($entry in $script:PPOriginal.GetEnumerator()){Set-Item -Path ('Function:script:'+ $entry.Key) -Value $entry.Value}
}
$failed=@($script:PPCases|Where-Object {$_.state -cne 'PASS'})
[pscustomobject]@{schema='hara.commander.preserved-pairing-fixtures.v1';state=$(if($failed.Count -eq 0){'PASS'}else{'FAIL'});case_count=$script:PPCases.Count;failed_count=$failed.Count;real_network_calls=0;real_enrollment_calls=0;real_task_mutations=0;production_paths_touched=$false;cases=$script:PPCases.ToArray()}|ConvertTo-Json -Depth 6
if($failed.Count -gt 0){exit 2}
exit 0
