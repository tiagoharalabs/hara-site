# Source-only helper embedded by build_windows_candidate.py.
# Requires the installer helpers and the Connect-Commander core.
function Get-PPFilePreimage($Context,[string]$Path,[string]$Stage,[string]$Name){
  $present=Test-Path -LiteralPath $Path
  $entry=[ordered]@{Path=$Path;Present=[bool]$present;Backup=(Join-Path $Stage $Name);Sha=$null;Acl=$null;LastWriteUtc=$null;CreationUtc=$null;Attributes=$null}
  if($present){
    Assert-CCOwnedFile $Path $Context.Sid
    $item=Get-Item -LiteralPath $Path -ErrorAction Stop
    Need-CC ($item.Length -le 2097152) 'PAIRING_PREIMAGE_TOO_LARGE'
    $entry.Acl=Get-Acl -LiteralPath $Path;$entry.LastWriteUtc=$item.LastWriteTimeUtc;$entry.CreationUtc=$item.CreationTimeUtc;$entry.Attributes=$item.Attributes
    $entry.Sha=Get-CCFileSha $Path
    [IO.File]::Copy($Path,$entry.Backup,$false)
    Need-CC ((Get-CCFileSha $entry.Backup) -ceq $entry.Sha) 'PAIRING_PREIMAGE_COPY_MISMATCH'
  }
  return [pscustomobject]$entry
}
function Assert-PPPreimageUnchanged($Context,$Preimage){
  if($Preimage.Present){
    Assert-CCOwnedFile $Preimage.Path $Context.Sid
    Need-CC ((Get-CCFileSha $Preimage.Path) -ceq $Preimage.Sha) 'PAIRING_PREIMAGE_CHANGED'
  }else{Need-CC (-not (Test-Path -LiteralPath $Preimage.Path)) 'PAIRING_PREIMAGE_CHANGED'}
}
function Restore-PPFile($Context,$Preimage){
  Assert-CCNoReparse $Preimage.Path
  if($Preimage.Present){
    Need-CC ((Get-CCFileSha $Preimage.Backup) -ceq $Preimage.Sha) 'PAIRING_BACKUP_CHANGED'
    $ownerType=[Security.Principal.SecurityIdentifier]
    $expectedOwner=$Preimage.Acl.GetOwner($ownerType).Value
    $expectedGroup=$Preimage.Acl.GetGroup($ownerType).Value
    $beforeAcl=Get-Acl -LiteralPath $Preimage.Path
    Need-CC ($expectedOwner -ceq $Context.Sid -and $beforeAcl.GetOwner($ownerType).Value -ceq $expectedOwner) 'PAIRING_ROLLBACK_OWNER_CHANGED'
    Need-CC ($beforeAcl.GetGroup($ownerType).Value -ceq $expectedGroup) 'PAIRING_ROLLBACK_GROUP_CHANGED'
    [IO.File]::Copy($Preimage.Backup,$Preimage.Path,$true)
    # Restore only discretionary access rules. Reapplying a full Get-Acl object
    # through Set-Acl requests owner/group/audit sections and can require a
    # privilege unavailable to the ordinary user. Owner/group must stay intact;
    # the transaction never takes ownership or edits a SACL.
    $access=[Security.AccessControl.AccessControlSections]::Access
    $expectedAccess=$Preimage.Acl.GetSecurityDescriptorSddlForm($access)
    $accessOnly=New-Object Security.AccessControl.FileSecurity
    $accessOnly.SetSecurityDescriptorSddlForm($expectedAccess,$access)
    [IO.File]::SetAccessControl($Preimage.Path,$accessOnly)
    $restoredAcl=Get-Acl -LiteralPath $Preimage.Path
    Need-CC ($restoredAcl.GetOwner($ownerType).Value -ceq $expectedOwner -and $restoredAcl.GetGroup($ownerType).Value -ceq $expectedGroup) 'PAIRING_ROLLBACK_IDENTITY_CHANGED'
    $expectedRaw=New-Object Security.AccessControl.RawSecurityDescriptor($expectedAccess)
    $actualRaw=New-Object Security.AccessControl.RawSecurityDescriptor($restoredAcl.GetSecurityDescriptorSddlForm($access))
    Need-CC ($null -ne $expectedRaw.DiscretionaryAcl -and $null -ne $actualRaw.DiscretionaryAcl) 'PAIRING_DACL_RESTORE_MISMATCH'
    $expectedDacl=New-Object byte[] $expectedRaw.DiscretionaryAcl.BinaryLength
    $actualDacl=New-Object byte[] $actualRaw.DiscretionaryAcl.BinaryLength
    $expectedRaw.DiscretionaryAcl.GetBinaryForm($expectedDacl,0)
    $actualRaw.DiscretionaryAcl.GetBinaryForm($actualDacl,0)
    $flagDifference=[int]$expectedRaw.ControlFlags -bxor [int]$actualRaw.ControlFlags
    # Native Windows normalizes only the descriptor's AUTO_INHERITED (0x400)
    # bookkeeping bit during this DACL-only write. ACE bytes/order/inheritance,
    # protection, and every other descriptor flag must remain exactly equal.
    Need-CC ([Convert]::ToBase64String($expectedDacl) -ceq [Convert]::ToBase64String($actualDacl) -and ($flagDifference -band (-bnot 0x0400)) -eq 0 -and $restoredAcl.AreAccessRulesProtected -eq $Preimage.Acl.AreAccessRulesProtected) 'PAIRING_DACL_RESTORE_MISMATCH'
    [IO.File]::SetCreationTimeUtc($Preimage.Path,$Preimage.CreationUtc)
    [IO.File]::SetLastWriteTimeUtc($Preimage.Path,$Preimage.LastWriteUtc)
    [IO.File]::SetAttributes($Preimage.Path,$Preimage.Attributes)
    Need-CC ((Get-CCFileSha $Preimage.Path) -ceq $Preimage.Sha) 'PAIRING_FILE_RESTORE_MISMATCH'
  }elseif(Test-Path -LiteralPath $Preimage.Path){
    Assert-CCOwnedFile $Preimage.Path $Context.Sid
    Remove-Item -LiteralPath $Preimage.Path -Force -ErrorAction Stop
    Need-CC (-not (Test-Path -LiteralPath $Preimage.Path)) 'PAIRING_NEW_FILE_REMOVE_FAILED'
  }
}
function Set-PPPrivateFileAcl($Context,[string]$Path){
  $sid=New-Object Security.Principal.SecurityIdentifier($Context.Sid)
  $acl=New-Object Security.AccessControl.FileSecurity
  $acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
  [void]$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','Allow')))
  Set-Acl -LiteralPath $Path -AclObject $acl
}
function Assert-PPDpapiReady {
  $secure=$null;$recovered=$null;$bstr=[IntPtr]::Zero
  try{
    $secure=ConvertTo-SecureString 'HARA-Commander-DPAPI-preflight' -AsPlainText -Force
    $cipher=$secure|ConvertFrom-SecureString
    $recovered=ConvertTo-SecureString $cipher
    $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($recovered)
    Need-CC ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) -ceq 'HARA-Commander-DPAPI-preflight') 'PAIRING_DPAPI_NOT_READY'
  }catch{Stop-CC 'PAIRING_DPAPI_NOT_READY'}
  finally{
    if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)}
    if($recovered){$recovered.Dispose()};if($secure){$secure.Dispose()};$cipher=$null
  }
}
function Write-PPRecoveryReceipt($Context,[string]$Stage,[string]$Origin,$NewDevice,[string]$Cipher){
  # The receipt is private and DPAPI-protected. It survives an interrupted
  # transaction or failed revocation; recovery must reconcile local state before
  # deciding whether to revoke the new enrollment. It is never a plaintext token.
  $path=Join-Path $Stage 'new-enrollment-recovery.private.json'
  $receipt=[ordered]@{
    schema='hara.commander.enrollment-recovery.v1';state='NEEDS_RECONCILIATION';
    origin=$Origin;device_id=$NewDevice.DeviceId;encrypted_device_token=$Cipher;
    credential_protection='DPAPI_CURRENT_USER';owner_sid=$Context.Sid;
    created_utc=[DateTime]::UtcNow.ToString('o')
  }
  $bytes=[Text.Encoding]::UTF8.GetBytes(($receipt|ConvertTo-Json))
  $stream=New-Object IO.FileStream($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
  Set-PPPrivateFileAcl $Context $path
  Assert-CCOwnedFile $path $Context.Sid
  $readback=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json
  Need-CC ($readback.device_id -ceq $NewDevice.DeviceId -and $readback.origin -ceq $Origin -and $readback.encrypted_device_token -ceq $Cipher) 'PAIRING_RECOVERY_RECEIPT_INVALID'
  return $path
}
function Get-PPTaskSnapshot($Context){
  $task=Get-CCTask $Context
  if(-not $task){return [pscustomobject]@{Present=$false;WasRunning=$false;State=$null;Xml=$null;Sha=$null}}
  $xml=Export-ScheduledTask -TaskName $Context.TaskName -TaskPath '\' -ErrorAction Stop
  return [pscustomobject]@{Present=$true;WasRunning=([string]$task.State -eq 'Running');State=[string]$task.State;Xml=$xml;Sha=(Get-CCSha ([Text.Encoding]::UTF8.GetBytes($xml)))}
}
function Assert-PPTaskUnchanged($Context,$Snapshot,[bool]$CheckRuntime=$false){
  $current=Get-PPTaskSnapshot $Context
  Need-CC ($current.Present -eq $Snapshot.Present -and $current.Sha -ceq $Snapshot.Sha) 'PAIRING_TASK_PREIMAGE_CHANGED'
  if($CheckRuntime){Need-CC ($current.State -ceq $Snapshot.State) 'PAIRING_TASK_STATE_CHANGED'}
}
function Stop-PPTask($Context){
  $task=Get-CCTask $Context
  if(-not $task -or [string]$task.State -ne 'Running'){return}
  Stop-ScheduledTask -TaskName $Context.TaskName -TaskPath '\' -ErrorAction Stop
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt 15){
    $task=Get-CCTask $Context
    if($task -and [string]$task.State -ne 'Running'){return}
    Start-Sleep -Milliseconds 250
  }
  Stop-CC 'PAIRING_TASK_STOP_UNCONFIRMED'
}
function Get-PPVerifiedAgent($Context,[string]$Stage){
  $metadata=Get-AgentReleaseMetadata
  Assert-AgentVersionFloor -IncomingVersion ([string]$metadata.Version)
  $path=Join-Path $Stage 'verified-agent.ps1'
  Invoke-WebRequest -Uri ((Get-ReleaseBaseUrl)+'/agent/windows.ps1') -OutFile $path -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
  Need-CC ((Get-Item -LiteralPath $path).Length -eq [long]$metadata.Bytes -and (Get-CCFileSha $path) -ceq [string]$metadata.Sha256) 'PAIRING_AGENT_INTEGRITY_FAILED'
  $tokens=$null;$errors=$null
  [Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)|Out-Null
  Need-CC ($errors.Count -eq 0) 'PAIRING_AGENT_SYNTAX_INVALID'
  $versions=@(Select-String -LiteralPath $path -Pattern '^\$AgentVersion = "([^"]+)"$' -CaseSensitive)
  Need-CC ($versions.Count -eq 1 -and $versions[0].Matches[0].Groups[1].Value -ceq [string]$metadata.Version) 'PAIRING_AGENT_VERSION_INVALID'
  Assert-AgentSelfTest $path
  return [pscustomobject]@{Path=$path;Version=[string]$metadata.Version;Sha=[string]$metadata.Sha256}
}
function Request-PPEnrollment($Context,$Before,$Verified){
  $secure=$null;$bstr=[IntPtr]::Zero;$pairing=$null;$payload=$null
  try{
    Write-Host 'Codigo novo do site: entre na sua conta e gere um codigo para esta maquina.'
    $secure=Read-Host 'Codigo de pareamento (nao e a senha da conta)' -AsSecureString
    $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $pairing=([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)).Trim()
    Need-CC (-not [string]::IsNullOrWhiteSpace($pairing)) 'PAIRING_CODE_EMPTY'
    $approval=if($Before.ConfigPresent -and $Before.Config.approval_mode){[string]$Before.Config.approval_mode}else{$Context.ApprovalMode}
    Need-CC ($approval -cin @('ASK_EVERY_ACTION','SESSION_TRUSTED','PERSISTENT_TRUSTED')) 'DEVICE_APPROVAL_MODE_INVALID'
    $architecture=[Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    $payload=@{pairing_token=$pairing;device_name=$env:COMPUTERNAME;platform='WINDOWS';architecture=$architecture;agent_version=$Verified.Version;approval_mode=$approval}|ConvertTo-Json -Compress
    try{$response=Invoke-CCRequest ($Before.Origin+'/api/device/enroll') 'POST' ([Text.Encoding]::UTF8.GetBytes($payload)) '' 65536}
    catch{Stop-CC 'PAIRING_RESULT_UNCERTAIN'}
    Need-CC ($response.Status -in @(200,201)) 'PAIRING_REQUEST_REJECTED'
    try{$value=[Text.Encoding]::UTF8.GetString($response.Bytes)|ConvertFrom-Json}catch{Stop-CC 'PAIRING_RESPONSE_INVALID'}
    Need-CC ($value.device_id -is [string] -and -not [string]::IsNullOrWhiteSpace($value.device_id) -and $value.device_token -is [string] -and -not [string]::IsNullOrWhiteSpace($value.device_token)) 'PAIRING_RESPONSE_INVALID'
    return [pscustomobject]@{DeviceId=[string]$value.device_id;Token=[string]$value.device_token;Architecture=$architecture;ApprovalMode=$approval}
  }finally{
    $pairing=$null;$payload=$null
    if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)}
    if($secure){$secure.Dispose()}
  }
}
function Revoke-PPNewDevice([string]$Origin,[string]$DeviceId,[string]$Token){
  $response=Invoke-CCRequest ($Origin+'/api/device/revoke-self') 'POST' ([Text.Encoding]::UTF8.GetBytes('{}')) $Token 65536
  try{$value=[Text.Encoding]::UTF8.GetString($response.Bytes)|ConvertFrom-Json}catch{return $false}
  return ($response.Status -eq 200 -and $value.ok -eq $true -and [string]$value.state -ceq 'REVOKED' -and [string]$value.device_id -ceq $DeviceId)
}
function Invoke-PreservedPairing([ValidateSet('pair-existing','re-enroll')][string]$Mode){
  $requested=if($env:HARA_COMMANDER_URL){[string]$env:HARA_COMMANDER_URL}else{''}
  $context=New-CCContext $requested '' $ApprovalMode
  $guard=New-Object Threading.Mutex($false,('Local\HARA.Commander.PreservedPairing.'+$context.Sid))
  $guardOwned=$false;$stage=$null;$keepStage=$false;$mutated=$false;$registered=$false;$committed=$false
  $newDevice=$null;$newCipher=$null;$files=@();$taskBefore=$null;$verified=$null;$recoveryReceipt=$null
  try{
    try{$guardOwned=$guard.WaitOne(0)}catch [Threading.AbandonedMutexException]{$guardOwned=$true}
    Need-CC $guardOwned 'PAIRING_ALREADY_IN_PROGRESS'
    $before=Get-CCInstalledState $context
    if($Mode -ceq 'pair-existing'){
      Need-CC (-not $before.ConfigPresent -and $before.AgentPresent) 'PAIR_EXISTING_STATE_INVALID'
    }else{
      Need-CC ($before.ConfigPresent -and $before.AgentPresent -and $before.TaskPresent) 'REENROLL_STATE_INVALID'
      Need-CC ((Test-CCCredential $before) -ceq 'REJECTED') 'REENROLL_CURRENT_DEVICE_STILL_VALID'
    }
    $script:BaseUrl=$before.Origin
    Assert-CommanderBaseUrl
    $stage=New-CCPrivateStage $context
    $taskBefore=Get-PPTaskSnapshot $context
    $files=@(
      (Get-PPFilePreimage $context $context.ConfigPath $stage 'device.preimage'),
      (Get-PPFilePreimage $context $context.AgentPath $stage 'agent.preimage'),
      (Get-PPFilePreimage $context $context.RuntimePath $stage 'runtime.preimage')
    )
    if($taskBefore.Present){[IO.File]::WriteAllText((Join-Path $stage 'task.preimage.xml'),$taskBefore.Xml,[Text.Encoding]::UTF8)}
    $verified=Get-PPVerifiedAgent $context $stage
    Assert-PPDpapiReady
    # No product mutation or token prompt occurs before the cached signed Agent
    # and complete preimages are verified. The installation uses these same bytes.
    $newDevice=Request-PPEnrollment $context $before $verified
    $newSecure=ConvertTo-SecureString $newDevice.Token -AsPlainText -Force
    try{$newCipher=$newSecure|ConvertFrom-SecureString}finally{$newSecure.Dispose()}
    $recoveryReceipt=Write-PPRecoveryReceipt $context $stage $before.Origin $newDevice $newCipher
    $newConfig=[pscustomobject]@{base_url=$before.Origin;device_id=$newDevice.DeviceId;encrypted_device_token=$newCipher;architecture=$newDevice.Architecture;agent_version=$verified.Version;approval_mode=$newDevice.ApprovalMode}
    $newState=[pscustomobject]@{Config=$newConfig;DeviceId=$newDevice.DeviceId;Origin=$before.Origin;Version=$verified.Version}
    Need-CC ((Test-CCCredential $newState) -ceq 'VALID') 'NEW_PAIRING_AUTH_NOT_CONFIRMED'
    foreach($preimage in $files){
      # A running Agent legitimately refreshes runtime-status while the user
      # obtains a code. Only config and executable must stay byte-identical.
      if($preimage.Path -cne $context.RuntimePath){Assert-PPPreimageUnchanged $context $preimage}
    }
    Assert-PPTaskUnchanged $context $taskBefore $true
    Need-CC ((Get-CCFileSha $verified.Path) -ceq $verified.Sha) 'PAIRING_CACHED_AGENT_CHANGED'
    $mutated=$true
    if($taskBefore.Present){Stop-PPTask $context}
    [IO.File]::WriteAllText($context.ConfigPath,($newConfig|ConvertTo-Json),[Text.Encoding]::UTF8)
    Set-PPPrivateFileAcl $context $context.ConfigPath
    [IO.File]::Copy($verified.Path,$context.AgentPath,$true)
    Set-PPPrivateFileAcl $context $context.AgentPath
    if(-not $taskBefore.Present){
      $arguments='-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$context.AgentPath+'"'
      $taskAction=New-ScheduledTaskAction -Execute $context.PowerShellExe -Argument $arguments
      $principal=New-ScheduledTaskPrincipal -UserId $context.Sid -LogonType Interactive -RunLevel Limited
      $settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
      # No -Force: a concurrent or hidden task must never be overwritten.
      Register-ScheduledTask -TaskName $context.TaskName -TaskPath '\' -Action $taskAction -Principal $principal -Settings $settings -Description 'HARA Commander on-demand device agent' -ErrorAction Stop|Out-Null
      $registered=$true
    }
    $after=Get-CCInstalledState $context
    Need-CC ($after.DeviceId -ceq $newDevice.DeviceId -and $after.AgentSha -ceq $verified.Sha -and $after.Version -ceq $verified.Version) 'PAIRING_LOCAL_ATTESTATION_FAILED'
    if($Mode -ceq 'pair-existing' -or $taskBefore.WasRunning){
      $previousStarted=Get-RuntimeStartedAt
      Start-ScheduledTask -TaskName $context.TaskName -TaskPath '\' -ErrorAction Stop
      Need-CC (Wait-AgentStartup $verified.Version $previousStarted 15) 'PAIRING_AGENT_STARTUP_UNCONFIRMED'
    }
    Need-CC ((Test-CCCredential $after) -ceq 'VALID') 'PAIRING_FINAL_AUTH_NOT_CONFIRMED'
    $committed=$true
    Write-Host 'HARA_COMMANDER_PRESERVED_PAIRING=PASS'
    Write-Host ('DEVICE_ID='+$newDevice.DeviceId)
    Write-Host 'DEVICE_TOKEN_EXPOSED=FALSE'
    Write-Host 'PREEXISTING_PRODUCT_DIRECTORIES_REMOVED=FALSE'
    if($Mode -ceq 're-enroll' -and -not $taskBefore.WasRunning){Write-Host 'HARA_COMMANDER_REENROLL_RUNTIME=MANUAL_STOP_PRESERVED'}
  }catch{
    $failure=Get-CCErrorCode $_
    $revoke='NOT_REQUIRED';$rollback='PREIMAGE_PRESERVED'
    if($newDevice -and $newDevice.Token -and -not $committed){
      $revoke='PENDING'
      try{if(Revoke-PPNewDevice $before.Origin $newDevice.DeviceId $newDevice.Token){$revoke='PASS'}}catch{}
    }
    if($mutated){
      $rollback='FAILED_PREIMAGE_RETAINED';$keepStage=$true
      try{
        Stop-PPTask $context
        if($registered){
          [void](Get-CCTask $context)
          Unregister-ScheduledTask -TaskName $context.TaskName -TaskPath '\' -Confirm:$false -ErrorAction Stop
        }
        foreach($preimage in $files){Restore-PPFile $context $preimage}
        Assert-PPTaskUnchanged $context $taskBefore
        if($taskBefore.WasRunning){
          $previousStarted=Get-RuntimeStartedAt
          Start-ScheduledTask -TaskName $context.TaskName -TaskPath '\' -ErrorAction Stop
          Need-CC (Wait-AgentStartup $before.Version $previousStarted 15) 'PAIRING_ROLLBACK_STARTUP_UNCONFIRMED'
        }
        $rollback='PASS';$keepStage=$false
      }catch{}
    }
    if($revoke -ceq 'PENDING'){
      $keepStage=$true
      if($recoveryReceipt -and (Test-Path -LiteralPath $recoveryReceipt)){
        Write-Host 'PENDING_REVOKE_RECOVERY_RECEIPT=DPAPI_PROTECTED'
      }else{Write-Host 'PENDING_REVOKE_RECOVERY_RECEIPT=UNCONFIRMED'}
    }
    Write-Host ('HARA_COMMANDER_PRESERVED_PAIRING_ROLLBACK='+$rollback)
    Write-Host ('SERVER_NEW_DEVICE_REVOKE='+$revoke)
    if($keepStage -and $stage){Write-Host ('PRIVATE_PREIMAGE_DIRECTORY='+$stage)}
    Stop-CC $failure
  }finally{
    if($newDevice){$newDevice.Token=$null};$newCipher=$null
    if($stage -and -not $keepStage){
      foreach($name in @('device.preimage','agent.preimage','runtime.preimage','task.preimage.xml','verified-agent.ps1','new-enrollment-recovery.private.json')){
        $path=Join-Path $stage $name
        if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force -ErrorAction Stop}
      }
      if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Force -ErrorAction Stop}
    }
    if($guardOwned){$guard.ReleaseMutex()};$guard.Dispose()
  }
}
