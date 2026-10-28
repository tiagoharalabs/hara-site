param(
  [ValidateSet('install','preflight')][string]$Action='install',
  [ValidateSet('Undefined','Restricted','RemoteSigned')][string]$PriorExecutionPolicy='RemoteSigned'
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$expectedSid='S-1-5-21-1207901905-1500652706-889822281-1005'
$installerSha='2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401'
$agentSha='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'
$adminRoot='C:\ProgramData\HARA-QA\windows-install-0356-20261028'
$configPath=Join-Path $adminRoot 'config\install-config.json'
$taskName='HARA Commander Agent'
$agentRoot=Join-Path $env:LOCALAPPDATA 'HARA Commander'
$agentPath=Join-Path $agentRoot 'hara-commander-agent.ps1'
$devicePath=Join-Path $agentRoot 'device.json'
$runtimePath=Join-Path $agentRoot 'runtime-status.json'
$installer=Join-Path $PSScriptRoot 'instalar-commander-0.3.56.ps1'
$powerShellExe=Join-Path $PSHOME 'powershell.exe'
$runRoot=$null;$store=$null;$temporaryCertificate=$null;$keepPolicy=$false
$oldUrl=$env:HARA_COMMANDER_URL;$oldRelease=$env:HARA_COMMANDER_RELEASE_URL;$oldApproval=$env:HARA_COMMANDER_APPROVAL_MODE
$r=[ordered]@{schema='hara.commander.qa-windows-launcher.v1';action=$Action;started_utc=[DateTime]::UtcNow.ToString('o');state='PENDING';stage='IDENTITY';installed=$false;paired=$false;prior_current_user_policy=$PriorExecutionPolicy;policy_restored=$false;certificate_preexisting=$false;certificate_added=$false;certificate_removed=$false;plaintext_secret_written=$false}
function Need([bool]$Ok,[string]$Code){if(-not $Ok){throw $Code}}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Progress-Checkpoint([string]$Stage,[bool]$BestEffort=$false){
  $r.stage=$Stage;$r.progress_utc=[DateTime]::UtcNow.ToString('o')
  if(-not $runRoot){return}
  $qaProgressStream=$null
  try{
    $qaProgressBytes=[Text.Encoding]::UTF8.GetBytes(($r|ConvertTo-Json -Depth 6))
    $qaProgressStream=New-Object IO.FileStream((Join-Path $runRoot 'progress.json'),[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $qaProgressStream.Write($qaProgressBytes,0,$qaProgressBytes.Length);$qaProgressStream.Flush($true)
  }catch{
    $r.progress_write_error=@{stage=$Stage;type=$_.Exception.GetType().FullName;code='PROGRESS_CHECKPOINT_WRITE_FAILED'}
    Write-Host ('Checkpoint falhou: '+$Stage+' / '+$r.progress_write_error.type) -ForegroundColor Yellow
    if(-not $BestEffort){throw 'PROGRESS_CHECKPOINT_WRITE_FAILED'}
  }finally{if($qaProgressStream){$qaProgressStream.Dispose()}}
}
function No-Reparse([string]$Path){
  [string]$qaPathCursor=[IO.Path]::GetFullPath($Path)
  [string]$qaPathRoot=[IO.Path]::GetPathRoot($qaPathCursor)
  $qaPathVisited=@{}
  for($qaPathDepth=0;$qaPathDepth -lt 64;$qaPathDepth++){
    Need (-not $qaPathVisited.ContainsKey($qaPathCursor)) 'PATH_PARENT_CYCLE_REFUSED'
    $qaPathVisited[$qaPathCursor]=$true
    $r.path_component=$qaPathCursor;Progress-Checkpoint 'PATH_COMPONENT_BEGIN'
    $qaPathAttributes=[IO.File]::GetAttributes($qaPathCursor)
    Need (-not ($qaPathAttributes -band [IO.FileAttributes]::ReparsePoint)) 'REPARSE_PATH_REFUSED'
    Progress-Checkpoint 'PATH_COMPONENT_VERIFIED'
    if($qaPathCursor.TrimEnd('\') -ieq $qaPathRoot.TrimEnd('\')){return}
    [string]$qaPathParent=[IO.Path]::GetDirectoryName($qaPathCursor.TrimEnd('\'))
    Need (-not [string]::IsNullOrWhiteSpace($qaPathParent)) 'PATH_PARENT_MISSING'
    $qaPathCursor=$qaPathParent
  }
  throw 'PATH_DEPTH_LIMIT_EXCEEDED'
}
function Admin-Controlled([string]$Path){
  $r.config_check_path=$Path;Progress-Checkpoint 'CONFIG_PATH_BEGIN'
  No-Reparse $Path
  Progress-Checkpoint 'CONFIG_ACL_READ_BEGIN'
  $acl=Get-Acl -LiteralPath $Path
  Progress-Checkpoint 'CONFIG_ACL_READ_COMPLETE'
  Need (@('S-1-5-18','S-1-5-32-544') -contains $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value) 'CONFIG_ADMIN_OWNER_REQUIRED'
  Progress-Checkpoint 'CONFIG_ACL_ENUM_BEGIN'
  $qaConfigRules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
  Progress-Checkpoint 'CONFIG_ACL_ENUM_COMPLETE'
  foreach($rule in $qaConfigRules){
    if($rule.AccessControlType -eq 'Allow' -and @('S-1-5-18','S-1-5-32-544') -notcontains $rule.IdentityReference.Value){
      Need (([int64]$rule.FileSystemRights -band 0x500d0156) -eq 0) 'CONFIG_UNTRUSTED_WRITE_REFUSED'
    }
  }
  Progress-Checkpoint 'CONFIG_PATH_COMPLETE'
}
function Task-Read {
  $errors=@();$t=Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue -ErrorVariable errors
  foreach($e in $errors){if($e.CategoryInfo.Category -ne 'ObjectNotFound'){throw 'TASK_READ_FAILED'}}
  if($t){
    $user=[string]$t.Principal.UserId
    if($user -notmatch '^S-1-'){$user=(New-Object Security.Principal.NTAccount($user)).Translate([Security.Principal.SecurityIdentifier]).Value}
    Need ($user -ceq $expectedSid) 'TASK_OWNED_BY_OTHER_USER'
    Need ([string]$t.Principal.LogonType -eq 'Interactive' -and [string]$t.Principal.RunLevel -eq 'Limited') 'TASK_CONTEXT_UNEXPECTED'
    Need (-not $t.Triggers -or @($t.Triggers).Count -eq 0) 'TASK_AUTOSTART_UNEXPECTED'
  }
  return $t
}
function Product-Read {
  No-Reparse $devicePath;No-Reparse $agentPath
  Need ((Sha $agentPath) -ceq $agentSha) 'INSTALLED_AGENT_HASH_MISMATCH'
  $device=Get-Content -Raw -LiteralPath $devicePath | ConvertFrom-Json
  Need ($device.device_id -and $device.encrypted_device_token -and [string]$device.agent_version -ceq '0.3.56') 'INSTALLED_CONFIG_INVALID'
  Need ([string]$device.base_url -ceq 'https://commander.haralabs.com.br' -and [string]$device.approval_mode -ceq 'PERSISTENT_TRUSTED') 'INSTALLED_ORIGIN_OR_APPROVAL_MISMATCH'
  $task=Task-Read;Need ([bool]$task) 'PRODUCT_TASK_MISSING'
  $actions=@($task.Actions)
  Need ($actions.Count -eq 1 -and [string]$actions[0].Execute -ieq $powerShellExe) 'PRODUCT_TASK_EXECUTABLE_MISMATCH'
  $expectedArguments='-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$agentPath+'"'
  Need ([string]$actions[0].Arguments -ceq $expectedArguments -and -not $actions[0].WorkingDirectory) 'PRODUCT_TASK_ARGUMENTS_MISMATCH'
  $r.installed=$true;$r.paired=$true;$r.device_id=[string]$device.device_id
  return $task
}
function Child-Installer([string]$Kind,[bool]$Interactive){
  $errPath=Join-Path $runRoot ($Kind+'-stderr.private.txt')
  Write-Host ('Commander: '+$Kind+'...')
  try{
    if($Interactive){& $powerShellExe -NoLogo -NoProfile -File $installer -Action $Kind 2> $errPath}
    else{& $powerShellExe -NoLogo -NoProfile -NonInteractive -File $installer -Action $Kind 2> $errPath}
    $code=$LASTEXITCODE;$r[($Kind+'_exit_code')]=$code
  }finally{
    # The native child error stream is not copied to a Desktop report or printed.
    if(Test-Path -LiteralPath $errPath){$r[($Kind+'_stderr_bytes')]=(Get-Item -LiteralPath $errPath).Length;Remove-Item -LiteralPath $errPath -Force}
  }
  Need ($code -eq 0) ('INSTALLER_'+$Kind.ToUpperInvariant()+'_FAILED')
}
function Import-QACertificate([string]$Path){
  $qaCertProcess=New-Object Diagnostics.Process
  $qaCertProcess.StartInfo.FileName=Join-Path $env:SystemRoot 'System32\certutil.exe'
  $qaCertProcess.StartInfo.Arguments='-user -f -addstore Root "'+$Path+'"'
  $qaCertProcess.StartInfo.UseShellExecute=$false;$qaCertProcess.StartInfo.CreateNoWindow=$true
  $qaCertProcess.StartInfo.RedirectStandardOutput=$true;$qaCertProcess.StartInfo.RedirectStandardError=$true
  $r.certutil=@{exit_code=$null;timed_out=$false;stdout_utf8_bytes=$null;stderr_utf8_bytes=$null;output_capture_complete=$false}
  $qaCertStarted=$false
  try{
    Need ($qaCertProcess.Start()) 'CERTUTIL_START_FAILED';$qaCertStarted=$true
    $qaCertOut=$qaCertProcess.StandardOutput.ReadToEndAsync();$qaCertErr=$qaCertProcess.StandardError.ReadToEndAsync()
    if(-not $qaCertProcess.WaitForExit(45000)){
      $r.certutil.timed_out=$true
      if(-not $qaCertProcess.HasExited){$qaCertProcess.Kill()}
      Need ($qaCertProcess.WaitForExit(5000)) 'CERTUTIL_TIMEOUT_PROCESS_NOT_EXITED'
      throw 'CERTUTIL_TRUST_IMPORT_TIMEOUT'
    }
    $r.certutil.exit_code=$qaCertProcess.ExitCode
    Need ($qaCertOut.Wait(5000) -and $qaCertErr.Wait(5000)) 'CERTUTIL_OUTPUT_CAPTURE_TIMEOUT'
    $r.certutil.stdout_utf8_bytes=[Text.Encoding]::UTF8.GetByteCount($qaCertOut.Result)
    $r.certutil.stderr_utf8_bytes=[Text.Encoding]::UTF8.GetByteCount($qaCertErr.Result)
    $r.certutil.output_capture_complete=$true
    Need ($qaCertProcess.ExitCode -eq 0) 'CERTUTIL_TRUST_IMPORT_FAILED'
  }finally{
    if($qaCertStarted -and -not $qaCertProcess.HasExited){$qaCertProcess.Kill();[void]$qaCertProcess.WaitForExit(5000)}
    $qaCertProcess.Dispose()
  }
}
try {
  $identity=[Security.Principal.WindowsIdentity]::GetCurrent();$principal=New-Object Security.Principal.WindowsPrincipal($identity)
  Need ($identity.User.Value -ceq $expectedSid -and $env:USERPROFILE -ceq 'C:\Users\CommanderQA') 'COMMANDERQA_PROFILE_REQUIRED'
  Need (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and (Get-Process -Id $PID).SessionId -gt 0) 'COMMANDERQA_LIMITED_INTERACTIVE_REQUIRED'
  Need ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'POWERSHELL_51_REQUIRED'
  Need ([string](Get-ExecutionPolicy) -ceq 'RemoteSigned' -and [string](Get-ExecutionPolicy -Scope Process) -ceq 'Undefined') 'CURRENTUSER_REMOTESIGNED_REQUIRED'
  $r.user_sid=$identity.User.Value
  $logParent=Join-Path $env:LOCALAPPDATA 'HARA Commander QA'
  if(-not (Test-Path -LiteralPath $logParent)){[void][IO.Directory]::CreateDirectory($logParent)}
  No-Reparse $logParent
  $runRoot=Join-Path $logParent ('run-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-'+[guid]::NewGuid().ToString('N'))
  [void][IO.Directory]::CreateDirectory($runRoot)
  $acl=New-Object Security.AccessControl.DirectorySecurity;$acl.SetOwner($identity.User);$acl.SetAccessRuleProtection($true,$false)
  [void]$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity.User,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
  Set-Acl -LiteralPath $runRoot -AclObject $acl
  [IO.File]::WriteAllText((Join-Path $runRoot 'policy-before.json'),(@{current_user=$PriorExecutionPolicy;user_sid=$expectedSid;at_utc=$r.started_utc}|ConvertTo-Json),[Text.Encoding]::UTF8)
  Progress-Checkpoint 'CONFIGURATION'
  foreach($path in @((Split-Path $adminRoot),$adminRoot,(Join-Path $adminRoot 'config'),$configPath)){Admin-Controlled $path}
  Progress-Checkpoint 'CONFIG_SIZE_READ_BEGIN'
  Need ((Get-Item -LiteralPath $configPath).Length -le 16384) 'CONFIG_TOO_LARGE'
  Progress-Checkpoint 'CONFIG_CONTENT_READ_BEGIN'
  $cfg=Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
  Progress-Checkpoint 'CONFIG_CONTENT_READ_COMPLETE'
  Need ([string]$cfg.schema -ceq 'hara.commander.qa-windows-install-config.v1' -and [string]$cfg.target_user_sid -ceq $expectedSid) 'CONFIG_SCOPE_MISMATCH'
  Need ([string]$cfg.base_url -ceq 'https://commander.haralabs.com.br') 'CONFIG_ORIGIN_MISMATCH'
  $release=[Uri]([string]$cfg.release_url)
  Need ($release.IsAbsoluteUri -and $release.Scheme -ceq 'https' -and -not $release.UserInfo -and -not $release.Query -and -not $release.Fragment -and $release.AbsolutePath.TrimEnd('/') -ceq '/releases/0.3.56') 'EXPLICIT_RELEASE_URL_REQUIRED'
  Progress-Checkpoint 'INSTALLER_HASH_BEGIN'
  Need ([string]$cfg.installer_sha256 -ceq $installerSha -and (Sha $installer) -ceq $installerSha) 'INSTALLER_HASH_MISMATCH'
  Progress-Checkpoint 'INSTALLER_HASH_COMPLETE'
  $r.installer_sha256=$installerSha;$r.release_url=$release.AbsoluteUri.TrimEnd('/')
  $env:HARA_COMMANDER_URL=[string]$cfg.base_url;$env:HARA_COMMANDER_RELEASE_URL=$r.release_url;$env:HARA_COMMANDER_APPROVAL_MODE='ALWAYS'
  $existing=$false;$task=$null
  if($Action -eq 'install'){
    $r.stage='TASK_OWNERSHIP';$task=Task-Read
    if(Test-Path -LiteralPath $devicePath){$task=Product-Read;$keepPolicy=$true;$existing=$true;$r.operation='EXISTING_INSTALLATION'}
    else{Need (-not $task -and -not (Test-Path -LiteralPath $agentPath)) 'PARTIAL_INSTALL_REQUIRES_OPERATOR_REPAIR'}
  }
  Progress-Checkpoint 'TEMPORARY_TLS_TRUST'
  if(-not $existing -and $cfg.tls_certificate_file){
    Need ([string]$cfg.tls_certificate_file -cmatch '^[A-Za-z0-9_.-]+\.der$' -and [string]$cfg.tls_certificate_sha256 -cmatch '^[0-9a-f]{64}$') 'TLS_CERTIFICATE_CONFIG_INVALID'
    $certPath=Join-Path (Join-Path $adminRoot 'config') ([string]$cfg.tls_certificate_file)
    Admin-Controlled $certPath;Need ((Sha $certPath) -ceq [string]$cfg.tls_certificate_sha256) 'TLS_CERTIFICATE_HASH_MISMATCH'
    $temporaryCertificate=New-Object Security.Cryptography.X509Certificates.X509Certificate2($certPath)
    Need (-not $temporaryCertificate.HasPrivateKey -and $temporaryCertificate.NotBefore.ToUniversalTime() -le [DateTime]::UtcNow -and $temporaryCertificate.NotAfter.ToUniversalTime() -gt [DateTime]::UtcNow) 'TLS_CERTIFICATE_NOT_CURRENT_PUBLIC_CERT'
    $store=New-Object Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser');$store.Open('ReadWrite')
    $matches=@($store.Certificates.Find('FindByThumbprint',$temporaryCertificate.Thumbprint,$false))
    $r.certificate_thumbprint=$temporaryCertificate.Thumbprint;$r.certificate_preexisting=($matches.Count -gt 0)
    if(-not $r.certificate_preexisting){
      # Persist the native preimage before a trust API that may wait for UI.
      $qaTrustBefore=[Text.Encoding]::UTF8.GetBytes((@{certificate_preexisting=$false;thumbprint=$temporaryCertificate.Thumbprint;der_sha256=[string]$cfg.tls_certificate_sha256;at_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json))
      $qaTrustRecord=New-Object IO.FileStream((Join-Path $runRoot 'trust-before.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
      try{$qaTrustRecord.Write($qaTrustBefore,0,$qaTrustBefore.Length);$qaTrustRecord.Flush($true)}finally{$qaTrustRecord.Dispose()}
      Progress-Checkpoint 'TLS_TRUST_ADD_PENDING'
      $r.certificate_import_attempted=$true
      Import-QACertificate $certPath
      $store.Close();$store.Open('ReadWrite')
      $qaImported=@($store.Certificates.Find('FindByThumbprint',$temporaryCertificate.Thumbprint,$false))
      Need ($qaImported.Count -gt 0) 'TLS_IMPORTED_CERTIFICATE_NOT_FOUND'
      foreach($qaImportedCert in $qaImported){Need ([Convert]::ToBase64String($qaImportedCert.RawData) -ceq [Convert]::ToBase64String($temporaryCertificate.RawData)) 'TLS_IMPORTED_CERTIFICATE_BYTES_MISMATCH'}
      $r.certificate_added=$true
      Progress-Checkpoint 'TLS_TRUST_ADDED'
    }else{Progress-Checkpoint 'TLS_TRUST_ALREADY_PRESENT'}
  }
  if(-not $existing){Progress-Checkpoint 'PREFLIGHT_BEGIN';Child-Installer 'preflight' $false;Progress-Checkpoint 'PREFLIGHT_COMPLETE'}
  if($Action -eq 'preflight'){$r.state='PASS_PREFLIGHT';Write-Host 'Pre-verificacao concluida. Nenhum enrollment ou tarefa foi alterado.'}
  else {
    if($existing){
      Write-Host 'A instalacao .56 desta conta ja existe. Verificando e iniciando quando necessario.'
    } else {
      # A standard user may not see a foreign global task. This recent, admin-owned
      # attestation is mandatory in addition to the user's own task read.
      Need ([string]$cfg.task_slot_clearance -ceq 'EMPTY_FOR_COMMANDERQA') 'ADMIN_TASK_MIGRATION_REQUIRED'
      $clearance=[DateTimeOffset]::Parse([string]$cfg.task_slot_verified_utc)
      Need ($clearance -le [DateTimeOffset]::UtcNow.AddMinutes(2) -and $clearance -ge [DateTimeOffset]::UtcNow.AddHours(-4)) 'ADMIN_TASK_CLEARANCE_EXPIRED'
      $r.stage='INSTALL';$r.operation='NEW_INSTALLATION'
      Write-Host 'Use um pairing token novo da conta openai-reviewer@haralabs.com.br. A senha do Identity nao deve ser digitada neste campo.'
      Child-Installer 'install' $true
      $task=Product-Read;$keepPolicy=$true
    }
    $r.stage='RUNTIME'
    $observedAfter=[DateTime]::UtcNow
    if([string]$task.State -ne 'Running'){Start-ScheduledTask -TaskName $taskName -TaskPath '\';$r.task_started=$true}else{$r.task_started=$false}
    $runtime=$null;$clock=[Diagnostics.Stopwatch]::StartNew()
    $heartbeatFloor=if($existing -and -not $r.task_started){$observedAfter.AddSeconds(-90)}else{$observedAfter.AddSeconds(-5)}
    while($clock.Elapsed.TotalSeconds -lt 45){
      if(Test-Path -LiteralPath $runtimePath){
        try{$candidate=Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json
          if([string]$candidate.agent_version -ceq '0.3.56' -and $candidate.last_successful_heartbeat_at_utc -and [DateTimeOffset]::Parse([string]$candidate.last_successful_heartbeat_at_utc).UtcDateTime -ge $heartbeatFloor){$runtime=$candidate;break}
        }catch{}
      }
      Start-Sleep -Seconds 1
    }
    Need ([bool]$runtime -and [string](Task-Read).State -ceq 'Running') 'FRESH_HEARTBEAT_NOT_CONFIRMED'
    $r.last_successful_heartbeat_at_utc=[string]$runtime.last_successful_heartbeat_at_utc
    $r.approval_mode='PERSISTENT_TRUSTED';$r.state='PASS_INSTALLED_AND_ONLINE'
    Write-Host 'Commander .56 instalado, pareado e com heartbeat recente nesta conta.'
  }
} catch {
  $r.state='HOLD'
  $r.failure_stage=$r.stage
  $message=[string]$_.Exception.Message
  $r.error_code=if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){$message}else{'NATIVE_OPERATION_FAILED'}
  $r.error_type=$_.Exception.GetType().FullName
  Write-Host ('Nao foi concluido. Etapa: '+$r.stage+'. Codigo: '+$r.error_code) -ForegroundColor Yellow
} finally {
  if($store){
    try{
      if(-not $r.certificate_preexisting -and $r.certificate_import_attempted){
        Progress-Checkpoint 'TLS_TRUST_REMOVE_PENDING' $true
        $store.Close();$store.Open('ReadWrite');$qaRemovedCount=0
        foreach($cert in @($store.Certificates.Find('FindByThumbprint',$temporaryCertificate.Thumbprint,$false))){
          Need ([Convert]::ToBase64String($cert.RawData) -ceq [Convert]::ToBase64String($temporaryCertificate.RawData)) 'TLS_CLEANUP_CERTIFICATE_CHANGED'
          $store.Remove($cert);$qaRemovedCount++
        }
        $r.certificate_removed=($qaRemovedCount -gt 0)
        $r.certificate_cleanup_absent=(@($store.Certificates.Find('FindByThumbprint',$temporaryCertificate.Thumbprint,$false)).Count -eq 0)
        Need $r.certificate_cleanup_absent 'TLS_TEMPORARY_TRUST_CLEANUP_FAILED'
        Progress-Checkpoint 'TLS_TRUST_REMOVED' $true
      }
    }catch{$r.state='HOLD_CLEANUP';$r.cleanup_error='TLS_TEMPORARY_TRUST_CLEANUP_FAILED'}finally{$store.Close()}
  }
  if($temporaryCertificate){$temporaryCertificate.Dispose()}
  $env:HARA_COMMANDER_URL=$oldUrl;$env:HARA_COMMANDER_RELEASE_URL=$oldRelease;$env:HARA_COMMANDER_APPROVAL_MODE=$oldApproval
  try{
    if(-not $keepPolicy -or $Action -eq 'preflight'){Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy $PriorExecutionPolicy -Force;$r.policy_restored=([string](Get-ExecutionPolicy -Scope CurrentUser) -ceq $PriorExecutionPolicy)}
    else{$r.policy_retained_for_installed_product='RemoteSigned'}
    $r.final_current_user_policy=[string](Get-ExecutionPolicy -Scope CurrentUser)
  }catch{$r.state='HOLD_CLEANUP';$r.policy_cleanup_error='CURRENTUSER_POLICY_RESTORE_FAILED'}
  $r.finished_utc=[DateTime]::UtcNow.ToString('o')
  if($runRoot){try{[IO.File]::WriteAllText((Join-Path $runRoot 'result.json'),($r|ConvertTo-Json -Depth 6),[Text.Encoding]::UTF8);Write-Host ('Resultado: '+(Join-Path $runRoot 'result.json'))}catch{$r.state='HOLD_RESULT_WRITE';Write-Host 'Nao foi possivel gravar o resultado local.'}}
  $env:HARA_QA_WRAPPER_FINISHED='1'
}
if($r.state -in @('PASS_PREFLIGHT','PASS_INSTALLED_AND_ONLINE')){exit 0}else{exit 2}
