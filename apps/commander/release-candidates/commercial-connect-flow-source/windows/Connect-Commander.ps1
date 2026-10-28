# Source candidate: not a replacement for an already signed release.
# Dot-source this file to load functions for the isolated fixture harness.
[CmdletBinding()]
param(
  [string]$CommanderUrl='',
  [string]$QaReleaseBaseUrl='',
  [ValidateSet('ASK_EVERY_ACTION','SESSION_TRUSTED','PERSISTENT_TRUSTED')]
  [string]$ApprovalMode='ASK_EVERY_ACTION'
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$script:CCSigningKid='commander-release-v2'
$script:CCSigningN='p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43'
$script:CCSigningE='AQAB'

function Stop-CC([string]$Code){throw $Code}
function Need-CC([bool]$Condition,[string]$Code){if(-not $Condition){Stop-CC $Code}}
function Get-CCErrorCode($Failure){
  $message=[string]$Failure.Exception.Message
  if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){return $message}
  return 'CONNECT_OPERATION_FAILED'
}
function Get-CCSha([byte[]]$Bytes){
  $algorithm=[Security.Cryptography.SHA256]::Create()
  try{return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
  finally{$algorithm.Dispose()}
}
function Get-CCFileSha([string]$Path){return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Get-CCVersion([string]$Value){
  Need-CC ($Value -cmatch '^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$') 'AGENT_VERSION_INVALID'
  try{return [Version]$Value}catch{Stop-CC 'AGENT_VERSION_INVALID'}
}
function Get-CCOrigin([string]$Value){
  try{$uri=[Uri]$Value}catch{Stop-CC 'COMMANDER_ORIGIN_INVALID'}
  Need-CC ($uri.IsAbsoluteUri -and $uri.Scheme -ceq 'https' -and $uri.Host -and -not $uri.UserInfo -and $uri.AbsolutePath -ceq '/' -and -not $uri.Query -and -not $uri.Fragment) 'COMMANDER_ORIGIN_INVALID'
  return $uri.AbsoluteUri.TrimEnd('/')
}
function Assert-CCNoReparse([string]$Path){
  $cursor=[IO.Path]::GetFullPath($Path);$root=[IO.Path]::GetPathRoot($cursor)
  for($depth=0;$depth -lt 64;$depth++){
    if(Test-Path -LiteralPath $cursor){
      Need-CC (-not ([IO.File]::GetAttributes($cursor) -band [IO.FileAttributes]::ReparsePoint)) 'REPARSE_PATH_REFUSED'
    }
    if($cursor.TrimEnd('\') -ieq $root.TrimEnd('\')){return}
    $cursor=[IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
    Need-CC (-not [string]::IsNullOrWhiteSpace($cursor)) 'PATH_PARENT_INVALID'
  }
  Stop-CC 'PATH_DEPTH_LIMIT_EXCEEDED'
}
function Assert-CCOwnedFile([string]$Path,[string]$Sid){
  Assert-CCNoReparse $Path
  $item=Get-Item -LiteralPath $Path -ErrorAction Stop
  Need-CC (-not $item.PSIsContainer) 'PRODUCT_FILE_REQUIRED'
  $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
  Need-CC ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $Sid) 'PRODUCT_FILE_OWNER_MISMATCH'
}
function New-CCContext([string]$RequestedOrigin,[string]$QaBase,[string]$RequestedApproval){
  $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
  $principal=New-Object Security.Principal.WindowsPrincipal($identity)
  Need-CC (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'CURRENT_USER_LIMITED_CONTEXT_REQUIRED'
  Need-CC ((Get-Process -Id $PID).SessionId -gt 0) 'CURRENT_USER_INTERACTIVE_SESSION_REQUIRED'
  Need-CC ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'POWERSHELL_51_REQUIRED'
  $root=Join-Path $env:LOCALAPPDATA 'HARA Commander'
  return [pscustomobject]@{
    Sid=$identity.User.Value;Root=$root;ConfigPath=(Join-Path $root 'device.json');
    AgentPath=(Join-Path $root 'hara-commander-agent.ps1');RuntimePath=(Join-Path $root 'runtime-status.json');
    TaskName='HARA Commander Agent';PowerShellExe=(Join-Path $PSHOME 'powershell.exe');
    RequestedOrigin=$RequestedOrigin;QaReleaseBase=$QaBase;ApprovalMode=$RequestedApproval
  }
}
function Get-CCTask($Context){
  $readErrors=@()
  $task=Get-ScheduledTask -TaskName $Context.TaskName -TaskPath '\' -ErrorAction SilentlyContinue -ErrorVariable readErrors
  foreach($readError in $readErrors){if($readError.CategoryInfo.Category -ne 'ObjectNotFound'){Stop-CC 'PRODUCT_TASK_READ_FAILED'}}
  if(-not $task){return $null}
  $owner=[string]$task.Principal.UserId
  if($owner -notmatch '^S-1-'){
    try{$owner=(New-Object Security.Principal.NTAccount($owner)).Translate([Security.Principal.SecurityIdentifier]).Value}
    catch{Stop-CC 'PRODUCT_TASK_OWNER_UNKNOWN'}
  }
  Need-CC ($owner -ceq $Context.Sid) 'PRODUCT_TASK_OWNER_MISMATCH'
  Need-CC ([string]$task.Principal.LogonType -ceq 'Interactive' -and [string]$task.Principal.RunLevel -ceq 'Limited') 'PRODUCT_TASK_CONTEXT_INVALID'
  Need-CC (-not $task.Triggers -or @($task.Triggers).Count -eq 0) 'PRODUCT_TASK_AUTOSTART_UNEXPECTED'
  $actions=@($task.Actions)
  $arguments='-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$Context.AgentPath+'"'
  Need-CC ($actions.Count -eq 1 -and [string]$actions[0].Execute -ieq $Context.PowerShellExe -and [string]$actions[0].Arguments -ceq $arguments -and -not $actions[0].WorkingDirectory) 'PRODUCT_TASK_ACTION_INVALID'
  return $task
}
function Get-CCInstalledState($Context){
  Assert-CCNoReparse $Context.Root
  $configPresent=Test-Path -LiteralPath $Context.ConfigPath
  $agentPresent=Test-Path -LiteralPath $Context.AgentPath
  $task=Get-CCTask $Context
  $cfg=$null;$version=$null;$agentSha=$null;$configSha=$null
  if($agentPresent){
    Assert-CCOwnedFile $Context.AgentPath $Context.Sid
    $versions=@(Select-String -LiteralPath $Context.AgentPath -Pattern '^\$AgentVersion = "([^"]+)"$' -CaseSensitive)
    Need-CC ($versions.Count -eq 1) 'INSTALLED_AGENT_VERSION_UNKNOWN'
    $version=[string]$versions[0].Matches[0].Groups[1].Value
    [void](Get-CCVersion $version)
    $agentSha=Get-CCFileSha $Context.AgentPath
  }
  if($configPresent){
    Assert-CCOwnedFile $Context.ConfigPath $Context.Sid
    Need-CC ((Get-Item -LiteralPath $Context.ConfigPath).Length -le 65536) 'DEVICE_CONFIG_INVALID'
    try{$cfg=Get-Content -LiteralPath $Context.ConfigPath -Raw | ConvertFrom-Json}
    catch{Stop-CC 'DEVICE_CONFIG_INVALID'}
    Need-CC ($cfg -and $cfg.device_id -and $cfg.encrypted_device_token -and $cfg.base_url -and $cfg.architecture) 'DEVICE_CONFIG_INVALID'
    $origin=Get-CCOrigin ([string]$cfg.base_url)
    if($Context.RequestedOrigin){Need-CC ($origin -ceq (Get-CCOrigin $Context.RequestedOrigin)) 'EXISTING_DEVICE_ORIGIN_MISMATCH'}
    Need-CC ($agentPresent -and [bool]$task) 'INSTALLED_STATE_INCOMPLETE'
    $configSha=Get-CCFileSha $Context.ConfigPath
  }else{
    $origin=if($Context.RequestedOrigin){Get-CCOrigin $Context.RequestedOrigin}else{'https://commander.haralabs.com.br'}
    Need-CC (-not $task -or $agentPresent) 'UNPAIRED_TASK_WITHOUT_AGENT'
    if($task){Need-CC ([string]$task.State -ne 'Running') 'UNPAIRED_TASK_RUNNING'}
    if(-not $agentPresent -and (Test-Path -LiteralPath $Context.Root)){
      Need-CC (@(Get-ChildItem -LiteralPath $Context.Root -Force).Count -eq 0) 'UNPAIRED_PATH_CONFLICT'
    }
  }
  return [pscustomobject]@{
    ConfigPresent=[bool]$configPresent;AgentPresent=[bool]$agentPresent;TaskPresent=[bool]$task;
    Config=$cfg;ConfigSha=$configSha;Version=$version;AgentSha=$agentSha;Origin=$origin;
    DeviceId=$(if($cfg){[string]$cfg.device_id}else{$null});TaskState=$(if($task){[string]$task.State}else{$null})
  }
}
function Invoke-CCRequest([string]$Uri,[string]$Method='GET',[byte[]]$Body=$null,[string]$Bearer='',[int]$MaximumBytes=2097152){
  $request=[Net.HttpWebRequest]::Create($Uri)
  $request.Method=$Method;$request.AllowAutoRedirect=$false;$request.Timeout=15000;$request.ReadWriteTimeout=15000
  $request.Accept='*/*';$request.UserAgent='HARA-Commander-Connect/1'
  $response=$null;$stream=$null;$memory=$null
  try{
    if($Bearer){$request.Headers['Authorization']='Bearer '+$Bearer}
    if($null -ne $Body){
      $request.ContentType='application/json';$request.ContentLength=$Body.Length
      $requestStream=$request.GetRequestStream()
      try{$requestStream.Write($Body,0,$Body.Length)}finally{$requestStream.Dispose()}
    }
    try{$response=[Net.HttpWebResponse]$request.GetResponse()}
    catch [Net.WebException]{
      if(-not $_.Exception.Response){Stop-CC 'NETWORK_UNAVAILABLE'}
      $response=[Net.HttpWebResponse]$_.Exception.Response
    }
    Need-CC ($response.StatusCode -lt 300 -or $response.StatusCode -ge 400) 'HTTP_REDIRECT_REFUSED'
    Need-CC ($response.ContentLength -le $MaximumBytes) 'HTTP_RESPONSE_TOO_LARGE'
    $stream=$response.GetResponseStream();$memory=New-Object IO.MemoryStream
    $buffer=New-Object byte[] 8192
    while(($read=$stream.Read($buffer,0,$buffer.Length)) -gt 0){
      Need-CC ($memory.Length+$read -le $MaximumBytes) 'HTTP_RESPONSE_TOO_LARGE'
      $memory.Write($buffer,0,$read)
    }
    return [pscustomobject]@{Status=[int]$response.StatusCode;Bytes=$memory.ToArray()}
  }catch [Net.WebException]{Stop-CC 'NETWORK_UNAVAILABLE'}
  finally{
    if($memory){$memory.Dispose()};if($stream){$stream.Dispose()};if($response){$response.Close()}
    $Bearer=$null
  }
}
function Test-CCCredential($State){
  $secure=$null;$bstr=[IntPtr]::Zero;$token=$null
  try{
    try{$secure=ConvertTo-SecureString ([string]$State.Config.encrypted_device_token)}
    catch{Stop-CC 'DEVICE_CREDENTIAL_UNREADABLE'}
    $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $token=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    Need-CC (-not [string]::IsNullOrWhiteSpace($token)) 'DEVICE_CREDENTIAL_UNREADABLE'
    $body=@{device_id=$State.DeviceId;architecture=[string]$State.Config.architecture;agent_version=$State.Version}
    if($State.Config.approval_mode){$body.approval_mode=[string]$State.Config.approval_mode}
    $reply=Invoke-CCRequest ($State.Origin+'/api/device/heartbeat') 'POST' ([Text.Encoding]::UTF8.GetBytes(($body|ConvertTo-Json -Compress))) $token 65536
    try{$value=[Text.Encoding]::UTF8.GetString($reply.Bytes)|ConvertFrom-Json}catch{Stop-CC 'DEVICE_AUTH_CHECK_AMBIGUOUS'}
    if($reply.Status -eq 200 -and $value.ok -eq $true -and [string]$value.device_id -ceq $State.DeviceId){return 'VALID'}
    if($reply.Status -eq 401 -and [string]$value.code -ceq 'DEVICE_AUTH_INVALID'){return 'REJECTED'}
    Stop-CC 'DEVICE_AUTH_CHECK_AMBIGUOUS'
  }finally{
    $token=$null
    if($bstr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)}
    if($secure){$secure.Dispose()}
  }
}
function Convert-CCBase64Url([string]$Text){
  $value=$Text.Replace('-','+').Replace('_','/')
  switch($value.Length%4){2{$value+='=='}3{$value+='='}1{Stop-CC 'RELEASE_SIGNATURE_INVALID'}}
  try{return [Convert]::FromBase64String($value)}catch{Stop-CC 'RELEASE_SIGNATURE_INVALID'}
}
function Assert-CCManifest([byte[]]$ManifestBytes,[byte[]]$SignatureBytes){
  try{$signature=[Text.Encoding]::UTF8.GetString($SignatureBytes)|ConvertFrom-Json}
  catch{Stop-CC 'RELEASE_SIGNATURE_INVALID'}
  Need-CC ([string]$signature.schema -ceq 'hara.commander-release-signature.v1' -and [string]$signature.alg -ceq 'RS256' -and [string]$signature.kid -ceq $script:CCSigningKid) 'RELEASE_SIGNATURE_INVALID'
  Need-CC ([string]$signature.manifest_sha256 -ceq (Get-CCSha $ManifestBytes)) 'RELEASE_SIGNATURE_INVALID'
  $rsa=[Security.Cryptography.RSA]::Create()
  try{
    $parameters=New-Object Security.Cryptography.RSAParameters
    $parameters.Modulus=Convert-CCBase64Url $script:CCSigningN;$parameters.Exponent=Convert-CCBase64Url $script:CCSigningE
    $rsa.ImportParameters($parameters)
    $signatureValue=Convert-CCBase64Url ([string]$signature.signature)
    Need-CC ($rsa.VerifyData($ManifestBytes,$signatureValue,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)) 'RELEASE_SIGNATURE_INVALID'
  }finally{$rsa.Dispose()}
  try{$manifest=[Text.Encoding]::UTF8.GetString($ManifestBytes)|ConvertFrom-Json}catch{Stop-CC 'RELEASE_MANIFEST_INVALID'}
  Need-CC ([string]$manifest.schema -ceq 'hara.commander-agent-release.v1' -and [string]$manifest.product -ceq 'H.A.R.A. Commander' -and [string]$manifest.channel -ceq 'stable') 'RELEASE_MANIFEST_INVALID'
  $target=Get-CCVersion ([string]$manifest.agent_version)
  Need-CC ($target -ge [Version]'0.3.55') 'RELEASE_BELOW_WINDOWS_FLOOR'
  $paths=@('agent/linux.py','agent/windows.ps1','install/linux.sh','install/windows.ps1')
  $rows=@($manifest.files);Need-CC ($rows.Count -eq 4) 'RELEASE_FILESET_INVALID'
  for($index=0;$index -lt 4;$index++){
    $row=$rows[$index]
    Need-CC ([string]$row.path -ceq $paths[$index] -and [string]$row.sha256 -cmatch '^[0-9a-f]{64}$' -and ($row.bytes -is [int] -or $row.bytes -is [long]) -and [long]$row.bytes -gt 0 -and [long]$row.bytes -le 2097152) 'RELEASE_FILESET_INVALID'
  }
  return $manifest
}
function Get-CCPublicBytes([string]$Uri,[int]$Maximum=2097152){
  $reply=Invoke-CCRequest $Uri 'GET' $null '' $Maximum
  Need-CC ($reply.Status -eq 200) 'RELEASE_HTTP_FAILED'
  return ,$reply.Bytes
}
function Assert-CCPayload([byte[]]$Bytes,$Entry){
  Need-CC ($Bytes.Length -eq [long]$Entry.bytes) 'RELEASE_PAYLOAD_SIZE_MISMATCH'
  Need-CC ((Get-CCSha $Bytes) -ceq [string]$Entry.sha256) 'RELEASE_PAYLOAD_HASH_MISMATCH'
}
function Get-CCRelease($Context,[string]$Origin){
  $discoveryBase=$Origin
  if($Context.QaReleaseBase){
    try{$qa=[Uri]$Context.QaReleaseBase}catch{Stop-CC 'QA_RELEASE_URL_INVALID'}
    Need-CC ($qa.IsAbsoluteUri -and $qa.Scheme -ceq 'https' -and -not $qa.UserInfo -and -not $qa.Query -and -not $qa.Fragment) 'QA_RELEASE_URL_INVALID'
    $discoveryBase=$qa.AbsoluteUri.TrimEnd('/')
  }
  $latest=Get-CCPublicBytes ($discoveryBase+'/release/agent-manifest.json') 65536
  $latestSig=Get-CCPublicBytes ($discoveryBase+'/release/agent-manifest.sig.json') 16384
  $manifest=Assert-CCManifest $latest $latestSig
  $version=[string]$manifest.agent_version
  $immutable=$Origin+'/releases/'+$version
  if($Context.QaReleaseBase){
    Need-CC (([Uri]$discoveryBase).AbsolutePath.TrimEnd('/') -ceq ('/releases/'+$version)) 'QA_RELEASE_VERSION_PATH_MISMATCH'
    $immutable=$discoveryBase
  }
  $versioned=Get-CCPublicBytes ($immutable+'/release/agent-manifest.json') 65536
  $versionedSig=Get-CCPublicBytes ($immutable+'/release/agent-manifest.sig.json') 16384
  [void](Assert-CCManifest $versioned $versionedSig)
  Need-CC ([Convert]::ToBase64String($latest) -ceq [Convert]::ToBase64String($versioned)) 'RELEASE_DISCOVERY_IMMUTABLE_MISMATCH'
  $agentBytes=Get-CCPublicBytes ($immutable+'/agent/windows.ps1')
  $installerBytes=Get-CCPublicBytes ($immutable+'/install/windows.ps1')
  Assert-CCPayload $agentBytes $manifest.files[1];Assert-CCPayload $installerBytes $manifest.files[3]
  $agentText=[Text.Encoding]::UTF8.GetString($agentBytes)
  $matches=[regex]::Matches($agentText,'(?m)^\$AgentVersion = "([^"\r\n]+)"\r?$')
  Need-CC ($matches.Count -eq 1 -and $matches[0].Groups[1].Value -ceq $version) 'RELEASE_AGENT_VERSION_MISMATCH'
  $installerText=[Text.Encoding]::UTF8.GetString($installerBytes)
  return [pscustomobject]@{
    Version=$version;BaseUrl=$immutable;AgentSha=[string]$manifest.files[1].sha256;
    AgentBytes=$agentBytes;InstallerBytes=$installerBytes;InstallerSha=[string]$manifest.files[3].sha256;
    PairExisting=($installerText -cmatch '(?m)^# HARA_COMMANDER_PAIR_EXISTING=1\r?$');
    Reenroll=($installerText -cmatch '(?m)^# HARA_COMMANDER_REENROLL=1\r?$')
  }
}
function New-CCPrivateStage($Context){
  $parent=[IO.Path]::GetFullPath($env:TEMP);Assert-CCNoReparse $parent
  $path=Join-Path $parent ('hara-commander-connect-'+[guid]::NewGuid().ToString('N'))
  [void][IO.Directory]::CreateDirectory($path)
  $sid=New-Object Security.Principal.SecurityIdentifier($Context.Sid)
  $acl=New-Object Security.AccessControl.DirectorySecurity
  $acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
  [void]$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
  Set-Acl -LiteralPath $path -AclObject $acl
  return $path
}
function Invoke-CCInstaller($Context,$State,$Release,[string]$Action){
  $stage=New-CCPrivateStage $Context
  $path=Join-Path $stage 'windows.ps1';$errorPath=Join-Path $stage 'child-stderr.private.txt'
  $oldOrigin=$env:HARA_COMMANDER_URL;$oldRelease=$env:HARA_COMMANDER_RELEASE_URL;$oldApproval=$env:HARA_COMMANDER_APPROVAL_MODE
  try{
    [IO.File]::WriteAllBytes($path,$Release.InstallerBytes)
    Need-CC ((Get-CCFileSha $path) -ceq $Release.InstallerSha) 'STAGED_INSTALLER_HASH_MISMATCH'
    $parseTokens=$null;$parseErrors=$null
    [Management.Automation.Language.Parser]::ParseFile($path,[ref]$parseTokens,[ref]$parseErrors)|Out-Null
    Need-CC ($parseErrors.Count -eq 0) 'SIGNED_INSTALLER_SYNTAX_INVALID'
    $env:HARA_COMMANDER_URL=$State.Origin;$env:HARA_COMMANDER_RELEASE_URL=$Release.BaseUrl
    $env:HARA_COMMANDER_APPROVAL_MODE=if($State.ConfigPresent -and $State.Config.approval_mode){[string]$State.Config.approval_mode}else{$Context.ApprovalMode}
    if($Action -eq 'update'){
      & $Context.PowerShellExe -NoLogo -NoProfile -NonInteractive -File $path -Action $Action 2> $errorPath | Out-Host
    }else{
      Write-Host 'Use um codigo de pareamento novo gerado apos entrar no site. Nao digite sua senha neste campo.'
      & $Context.PowerShellExe -NoLogo -NoProfile -File $path -Action $Action 2> $errorPath | Out-Host
    }
    $childExit=$LASTEXITCODE
    Need-CC ($childExit -eq 0) 'VERIFIED_INSTALLER_ACTION_FAILED'
  }finally{
    $env:HARA_COMMANDER_URL=$oldOrigin;$env:HARA_COMMANDER_RELEASE_URL=$oldRelease;$env:HARA_COMMANDER_APPROVAL_MODE=$oldApproval
    foreach($file in @($errorPath,$path)){if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}}
    if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Force}
  }
}
function Ensure-CCRuntime($Context,$State){
  $task=Get-CCTask $Context;Need-CC ([bool]$task) 'PRODUCT_TASK_MISSING'
  $wasRunning=([string]$task.State -eq 'Running')
  # The caller has just completed an authenticated heartbeat for this binding.
  # Existing Agents heartbeat about once a minute; do not reject a valid cycle.
  $floor=if($wasRunning){[DateTimeOffset]::UtcNow.AddSeconds(-90)}else{[DateTimeOffset]::UtcNow.AddSeconds(-5)}
  if(-not $wasRunning){Start-ScheduledTask -TaskName $Context.TaskName -TaskPath '\' -ErrorAction Stop}
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt 45){
    if(Test-Path -LiteralPath $Context.RuntimePath){
      try{
        Assert-CCOwnedFile $Context.RuntimePath $Context.Sid
        $runtime=Get-Content -LiteralPath $Context.RuntimePath -Raw | ConvertFrom-Json
        $time=[DateTimeOffset]::Parse([string]$runtime.last_successful_heartbeat_at_utc)
        $deviceMatches=(-not $runtime.device_id -or [string]$runtime.device_id -ceq $State.DeviceId)
        if([string]$runtime.agent_version -ceq $State.Version -and $deviceMatches -and $time -ge $floor -and $time -le [DateTimeOffset]::UtcNow.AddSeconds(5) -and [string](Get-CCTask $Context).State -ceq 'Running'){
          return $time.UtcDateTime.ToString('o')
        }
      }catch{}
    }
    Start-Sleep -Seconds 1
  }
  Stop-CC 'FRESH_RUNTIME_HEARTBEAT_NOT_CONFIRMED'
}
function Assert-CCEnrollmentPreserved($Before,$After){
  Need-CC ($After.ConfigPresent -and $After.DeviceId -ceq $Before.DeviceId -and $After.Origin -ceq $Before.Origin -and $After.ConfigSha -ceq $Before.ConfigSha) 'EXISTING_ENROLLMENT_CHANGED'
}
function Invoke-CCConnect($Context){
  $report=[ordered]@{schema='hara.commander.connect-result.v1';started_utc=[DateTime]::UtcNow.ToString('o');state='HOLD';stage='READ_LOCAL_STATE';binding='UNKNOWN';connected=$false;update='NOT_CHECKED';paired_this_run=$false;credential_reset=$false;device_token_exposed=$false}
  try{
    $state=Get-CCInstalledState $Context
    $report.commander_url=$state.Origin;$report.installed_version=$state.Version;$report.device_id=$state.DeviceId
    $valid=$false;$rejected=$false
    if($state.ConfigPresent){
      $report.stage='VALIDATE_BINDING';$auth=Test-CCCredential $state
      $valid=($auth -ceq 'VALID');$rejected=($auth -ceq 'REJECTED')
      Need-CC ($valid -or $rejected) 'DEVICE_AUTH_CHECK_AMBIGUOUS'
      $report.binding=if($valid){'VALID'}else{'REJECTED'}
    }else{$report.binding='ABSENT'}
    if($valid){
      $report.stage='CONNECT_EXISTING';$report.last_successful_heartbeat_at_utc=Ensure-CCRuntime $Context $state
      $report.connected=$true
      $updateInvoked=$false
      try{
        $report.stage='VERIFY_LATEST_RELEASE';$release=Get-CCRelease $Context $state.Origin
        $report.target_version=$release.Version
        $comparison=(Get-CCVersion $release.Version).CompareTo((Get-CCVersion $state.Version))
        if($comparison -eq 0){
          Need-CC ($state.AgentSha -ceq $release.AgentSha) 'INSTALLED_AGENT_INTEGRITY_MISMATCH'
          $report.update='ALREADY_CURRENT'
        }elseif($comparison -lt 0){Stop-CC 'RELEASE_CHANNEL_BEHIND_INSTALLED'}
        else{
          $report.stage='UPDATE_SIGNED_AGENT';$updateInvoked=$true;Invoke-CCInstaller $Context $state $release 'update'
          $after=Get-CCInstalledState $Context;Assert-CCEnrollmentPreserved $state $after
          Need-CC ($after.Version -ceq $release.Version -and $after.AgentSha -ceq $release.AgentSha) 'UPDATED_AGENT_ATTESTATION_FAILED'
          Need-CC ((Test-CCCredential $after) -ceq 'VALID') 'UPDATED_DEVICE_AUTH_FAILED'
          $report.last_successful_heartbeat_at_utc=Ensure-CCRuntime $Context $after
          $report.installed_version=$after.Version;$report.update='UPDATED';$report.enrollment_preserved=$true
        }
        $preserved=Get-CCInstalledState $Context;Assert-CCEnrollmentPreserved $state $preserved
        $report.enrollment_preserved=$true
        $report.state='CONNECTED';$report.stage='COMPLETE'
      }catch{
        $report.update='HOLD';$report.update_error_code=Get-CCErrorCode $_
        $report.state='CONNECTED_UPDATE_HOLD'
        if($report.update_error_code -ceq 'INSTALLED_AGENT_INTEGRITY_MISMATCH'){
          $report.connected=$false;$report.state='HOLD';$report.error_code='INSTALLED_AGENT_INTEGRITY_MISMATCH'
        }
        if(-not $updateInvoked){
          try{
            $unchanged=Get-CCInstalledState $Context;Assert-CCEnrollmentPreserved $state $unchanged
            Need-CC ($unchanged.AgentSha -ceq $state.AgentSha) 'EXISTING_AGENT_CHANGED_UNEXPECTEDLY'
            $report.enrollment_preserved=$true
          }catch{
            $report.connected=$false;$report.state='HOLD';$report.preservation_error_code=Get-CCErrorCode $_
          }
        }
        if($updateInvoked){
          try{
            $recovered=Get-CCInstalledState $Context;Assert-CCEnrollmentPreserved $state $recovered
            Need-CC ($recovered.AgentSha -ceq $state.AgentSha -or ($recovered.AgentSha -ceq $release.AgentSha -and $recovered.Version -ceq $release.Version)) 'UPDATE_RECOVERY_INTEGRITY_FAILED'
            Need-CC ((Test-CCCredential $recovered) -ceq 'VALID') 'UPDATE_RECOVERY_AUTH_FAILED'
            $report.last_successful_heartbeat_at_utc=Ensure-CCRuntime $Context $recovered
            $report.installed_version=$recovered.Version;$report.enrollment_preserved=$true
            $report.update_connection_recovery='CONFIRMED'
          }catch{
            $report.connected=$false;$report.state='HOLD';$report.update_connection_recovery='UNCONFIRMED'
            $report.recovery_error_code=Get-CCErrorCode $_
          }
        }
      }
    }else{
      $report.stage='VERIFY_RELEASE_BEFORE_PAIRING';$release=Get-CCRelease $Context $state.Origin
      $report.target_version=$release.Version
      if($state.AgentPresent){Need-CC ((Get-CCVersion $release.Version) -ge (Get-CCVersion $state.Version)) 'RELEASE_WOULD_DOWNGRADE_INSTALLED_AGENT'}
      if($rejected){Need-CC $release.Reenroll 'SIGNED_INSTALLER_REENROLL_UNSUPPORTED';$action='re-enroll'}
      elseif($state.AgentPresent){Need-CC $release.PairExisting 'SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED';$action='pair-existing'}
      else{$action='install'}
      $report.stage='PAIRING_CODE_REQUIRED';$report.pairing_action_invoked=$action
      Invoke-CCInstaller $Context $state $release $action
      $after=Get-CCInstalledState $Context
      Need-CC ($after.ConfigPresent -and $after.Origin -ceq $state.Origin -and $after.Version -ceq $release.Version -and $after.AgentSha -ceq $release.AgentSha) 'PAIRED_INSTALLATION_ATTESTATION_FAILED'
      Need-CC ((Test-CCCredential $after) -ceq 'VALID') 'PAIRED_DEVICE_AUTH_FAILED'
      $report.last_successful_heartbeat_at_utc=Ensure-CCRuntime $Context $after
      $report.connected=$true;$report.binding='VALID';$report.paired_this_run=$true
      $report.device_id=$after.DeviceId;$report.installed_version=$after.Version
      $report.update='LATEST_SIGNED_VERSION_INSTALLED';$report.state='CONNECTED';$report.stage='COMPLETE'
    }
  }catch{$report.error_code=Get-CCErrorCode $_;$report.state='HOLD'}
  $report.finished_utc=[DateTime]::UtcNow.ToString('o')
  return [pscustomobject]$report
}
function Enter-CCGuard($Context){
  $guard=New-Object Threading.Mutex($false,('Local\HARA.Commander.Connect.'+$Context.Sid))
  $owned=$false
  try{
    try{$owned=$guard.WaitOne(0)}catch [Threading.AbandonedMutexException]{$owned=$true}
    Need-CC $owned 'CONNECT_ALREADY_IN_PROGRESS'
    foreach($process in @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction Stop)){
      if([int]$process.ProcessId -eq $PID -or [string]$process.CommandLine -notmatch '(?i)(?<![A-Za-z0-9_.-])(?:Connect-Commander\.ps1|Instalar-ou-verificar-Commander\.ps1|instalar-commander-0\.3\.56\.ps1)(?![A-Za-z0-9_.-])'){continue}
      $owner=Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid -ErrorAction Stop
      Need-CC ([int]$owner.ReturnValue -eq 0) 'CONNECT_PROCESS_OWNER_UNKNOWN'
      Need-CC ([string]$owner.Sid -cne $Context.Sid) 'CONNECT_ALREADY_IN_PROGRESS'
    }
    return $guard
  }catch{if($owned){$guard.ReleaseMutex()};$guard.Dispose();throw}
}
if($MyInvocation.InvocationName -ne '.'){
  $guard=$null
  try{
    $context=New-CCContext $CommanderUrl $QaReleaseBaseUrl $ApprovalMode
    $guard=Enter-CCGuard $context
    $result=Invoke-CCConnect $context
    $result|ConvertTo-Json -Depth 6
    if($result.state -ceq 'CONNECTED'){exit 0}
    if($result.state -ceq 'CONNECTED_UPDATE_HOLD'){exit 3}
    exit 2
  }catch{[pscustomobject]@{state='HOLD';error_code=(Get-CCErrorCode $_);device_token_exposed=$false}|ConvertTo-Json;exit 2}
  finally{if($guard){$guard.ReleaseMutex();$guard.Dispose()}}
}
