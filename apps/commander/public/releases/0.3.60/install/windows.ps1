# HARA Commander 0.3.60 signed release installer.
# HARA_COMMANDER_PAIR_EXISTING=1
# HARA_COMMANDER_REENROLL=1
# HARA_COMMANDER_DEFAULT_CONNECT=1
param([string]$Action = "connect")
$ErrorActionPreference = "Stop"
$Action = $Action.TrimStart("-").ToLowerInvariant()

$BaseUrl = if ($env:HARA_COMMANDER_URL) { $env:HARA_COMMANDER_URL.TrimEnd("/") } else { "https://commander.haralabs.com.br" }
function Assert-CommanderBaseUrl {
  $uri=[Uri]$BaseUrl
  if($uri.Scheme -cne "https" -or -not $uri.Host -or $uri.UserInfo -or $uri.AbsolutePath -ne "/" -or $uri.Query -or $uri.Fragment){throw "COMMANDER_ORIGIN_INVALID"}
}
Assert-CommanderBaseUrl
$ReleaseSigningKid = "commander-release-v2"
$ReleaseSigningN = "p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43"
$ReleaseSigningE = "AQAB"
function Get-ReleaseBaseUrl {
  $value=if($env:HARA_COMMANDER_RELEASE_URL){$env:HARA_COMMANDER_RELEASE_URL.TrimEnd("/")}else{$BaseUrl.TrimEnd("/")+"/releases/0.3.60"}
  $uri=[Uri]$value
  if($uri.Scheme -cne "https" -or $uri.UserInfo -or $uri.Query -or $uri.Fragment){throw "RELEASE_ORIGIN_INVALID"}
  return $value
}
$ApprovalModeRaw = if ($env:HARA_COMMANDER_APPROVAL_MODE) { ([string]$env:HARA_COMMANDER_APPROVAL_MODE).Trim().ToUpperInvariant() } else { "ASK_EVERY_ACTION" }
$ApprovalMode = switch ($ApprovalModeRaw) {
  "ASK" { "ASK_EVERY_ACTION" }
  "ASK_EVERY_ACTION" { "ASK_EVERY_ACTION" }
  "SESSION" { "SESSION_TRUSTED" }
  "SESSION_TRUSTED" { "SESSION_TRUSTED" }
  "AUTO" { "PERSISTENT_TRUSTED" }
  "ALWAYS" { "PERSISTENT_TRUSTED" }
  "PERSISTENT" { "PERSISTENT_TRUSTED" }
  "PERSISTENT_TRUSTED" { "PERSISTENT_TRUSTED" }
  default { throw "DEVICE_APPROVAL_MODE_INVALID" }
}
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$Agent = Join-Path $Root "hara-commander-agent.ps1"
$Config = Join-Path $Root "device.json"
$TaskName = "HARA Commander Agent"
$RuntimeStatus = Join-Path $Root "runtime-status.json"

function Get-InstalledDevice {
  if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { return $null }
  try { return Get-Content -Raw -LiteralPath $Config | ConvertFrom-Json } catch { return $null }
}

function Get-RuntimeStartedAt {
  if (-not (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf)) { return "" }
  try {
    $status=Get-Content -Raw -LiteralPath $RuntimeStatus | ConvertFrom-Json
    return [string]$status.started_at_utc
  } catch {
    return ""
  }
}

function Wait-AgentStartup([string]$ExpectedVersion,[string]$PreviousStarted,[int]$Seconds=10) {
  for ($i=0; $i -lt $Seconds; $i++) {
    if (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf) {
      try {
        $status=Get-Content -Raw -LiteralPath $RuntimeStatus | ConvertFrom-Json
        $started=[string]$status.started_at_utc
        $version=[string]$status.agent_version
        if ($version -eq $ExpectedVersion -and $started -and $started -ne $PreviousStarted) {
          return $true
        }
      } catch {}
    }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Stop-AgentTaskAndWait([int]$Seconds=15) {
  $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
  if([string]$task.State -in @('Ready','Disabled')){return}
  Stop-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt $Seconds){
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
    if([string]$task.State -in @('Ready','Disabled')){return}
    Start-Sleep -Milliseconds 250
  }
  throw 'AGENT_TASK_STOP_UNCONFIRMED'
}

function Wait-AgentTaskStartup([string]$ExpectedVersion,[string]$PreviousStarted,[int]$Seconds=15) {
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt $Seconds){
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
    if([string]$task.State -ceq 'Running' -and (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf)){
      try{
        $status=Get-Content -LiteralPath $RuntimeStatus -Raw|ConvertFrom-Json
        if([string]$status.agent_version -ceq $ExpectedVersion -and $status.started_at_utc -and
           [string]$status.started_at_utc -cne $PreviousStarted){return $true}
      }catch{}
    }
    Start-Sleep -Milliseconds 250
  }
  return $false
}

function Convert-Base64UrlBytes([string]$Value) {
  $text = $Value.Replace("-","+").Replace("_","/")
  switch ($text.Length % 4) {
    2 { $text += "==" }
    3 { $text += "=" }
  }
  return [Convert]::FromBase64String($text)
}

function Assert-ReleaseManifestSignature([byte[]]$ManifestBytes,$SignatureObject) {
  if (-not $SignatureObject -or [string]$SignatureObject.schema -ne "hara.commander-release-signature.v1") { throw "AGENT_RELEASE_SIGNATURE_INVALID" }
  if ([string]$SignatureObject.alg -ne "RS256" -or [string]$SignatureObject.kid -ne $ReleaseSigningKid) { throw "AGENT_RELEASE_SIGNATURE_INVALID" }
  $sha=[Security.Cryptography.SHA256]::Create()
  try { $digest=$sha.ComputeHash($ManifestBytes) } finally { $sha.Dispose() }
  $hex=([BitConverter]::ToString($digest)).Replace("-","").ToLowerInvariant()
  if ($hex -ne ([string]$SignatureObject.manifest_sha256).ToLowerInvariant()) { throw "AGENT_RELEASE_SIGNATURE_INVALID" }
  $rsa=[Security.Cryptography.RSA]::Create()
  try {
    $params=New-Object Security.Cryptography.RSAParameters
    $params.Modulus=Convert-Base64UrlBytes $ReleaseSigningN
    $params.Exponent=Convert-Base64UrlBytes $ReleaseSigningE
    $rsa.ImportParameters($params)
    $sig=Convert-Base64UrlBytes ([string]$SignatureObject.signature)
    if (-not $rsa.VerifyData($ManifestBytes,$sig,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)) {
      throw "AGENT_RELEASE_SIGNATURE_INVALID"
    }
  } finally {
    $rsa.Dispose()
  }
}

# Source-only candidate. The signed manifest is still verified by
# Get-AgentReleaseMetadata; this guard only protects installed version state.
function Assert-AgentVersionFloor {
  param([string]$IncomingVersion)
  if (-not $IncomingVersion -or $IncomingVersion -notmatch '^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$') {
    throw "AGENT_RELEASE_INVALID_SEMVER"
  }
  $candidate = [Version]$IncomingVersion
  if ($candidate -lt [Version]"0.3.55") { throw "AGENT_RELEASE_BELOW_WINDOWS_FLOOR" }
  if (Test-Path -LiteralPath $Agent) {
    $item = Get-Item -LiteralPath $Agent -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "AGENT_INSTALLED_PATH_UNTRUSTED" }
    $installed = @(Select-String -LiteralPath $Agent -Pattern '^\$AgentVersion = "([0-9]+\.[0-9]+\.[0-9]+)"$')
    if ($installed.Count -ne 1 -or -not $installed[0].Matches.Count) { throw "AGENT_INSTALLED_VERSION_UNKNOWN" }
    $version = [string]$installed[0].Matches[0].Groups[1].Value
    if ($version -notmatch '^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$') { throw "AGENT_INSTALLED_VERSION_UNKNOWN" }
    $existing = [Version]$version
    if ($candidate -lt $existing) { throw "AGENT_DOWNGRADE_REFUSED" }
  }
}

function Get-AgentReleaseMetadata {
  $manifestPath=Join-Path $env:TEMP ("hara-commander-manifest-"+[guid]::NewGuid().ToString("N")+".json")
  $signaturePath=Join-Path $env:TEMP ("hara-commander-manifest-"+[guid]::NewGuid().ToString("N")+".sig.json")
  try {
    Invoke-WebRequest -Uri "$(Get-ReleaseBaseUrl)/release/agent-manifest.json" -OutFile $manifestPath -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
    Invoke-WebRequest -Uri "$(Get-ReleaseBaseUrl)/release/agent-manifest.sig.json" -OutFile $signaturePath -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
    $manifestBytes=[IO.File]::ReadAllBytes($manifestPath)
    $signature=Get-Content -Raw -LiteralPath $signaturePath | ConvertFrom-Json
    Assert-ReleaseManifestSignature $manifestBytes $signature
    $manifest=[Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
    if (-not $manifest -or [string]$manifest.schema -ne "hara.commander-agent-release.v1" -or [string]$manifest.product -ne "H.A.R.A. Commander" -or [string]$manifest.channel -ne "stable") { throw "AGENT_RELEASE_MANIFEST_INVALID" }
    $paths = @("agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1")
    if (@($manifest.files).Count -ne 4) { throw "AGENT_RELEASE_FILESET_INVALID" }
    for ($i=0; $i -lt 4; $i++) {
      $row=$manifest.files[$i]
      if ([string]$row.path -cne $paths[$i] -or [string]$row.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
          $null -eq $row.bytes -or $row.bytes -is [bool] -or ($row.bytes -isnot [int] -and $row.bytes -isnot [long]) -or
          [long]$row.bytes -le 0 -or [long]$row.bytes -gt 2097152) { throw "AGENT_RELEASE_MANIFEST_INVALID" }
    }
    if ([string]$manifest.agent_version -cne "0.3.60") { throw "INSTALLER_AGENT_VERSION_MISMATCH" }
    $entry=$manifest.files[1]
    return [PSCustomObject]@{ Version=[string]$manifest.agent_version; Sha256=[string]$entry.sha256; Bytes=[long]$entry.bytes; InstallerSha256=[string]$manifest.files[3].sha256; InstallerBytes=[long]$manifest.files[3].bytes }

  } finally {
    Remove-Item -Force -LiteralPath $manifestPath,$signaturePath -ErrorAction SilentlyContinue
  }
}

function Install-PairCommand {
  # Retain only the installer authenticated by the release signature. The
  # command never needs a temporary QA server or another full installation.
  $meta=Get-AgentReleaseMetadata
  if (-not $PSCommandPath -or -not (Test-Path -LiteralPath $PSCommandPath -PathType Leaf)) { throw 'PAIR_INSTALLER_FILE_REQUIRED' }
  if ((Get-Item -LiteralPath $PSCommandPath).Length -ne $meta.InstallerBytes -or
      (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $meta.InstallerSha256) { throw 'PAIR_INSTALLER_INTEGRITY_FAILED' }
  $saved=Join-Path $Root 'hara-commander-install.ps1'
  foreach($path in @($Root,$saved,(Join-Path $Root 'hara.cmd'),(Join-Path $Root 'hara-commander.cmd'))){
    if((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'PAIR_COMMAND_PATH_UNTRUSTED'}
  }
  if([IO.Path]::GetFullPath($PSCommandPath) -ine [IO.Path]::GetFullPath($saved)){
    [IO.File]::Copy($PSCommandPath,$saved,$true)
  }
  $wrapper='@echo off'+"`r`n"+'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0hara-commander-agent.ps1" '
  [IO.File]::WriteAllText((Join-Path $Root 'hara.cmd'),($wrapper+'--hara-cli %*'+"`r`n"+'exit /b %errorlevel%'+"`r`n"),[Text.Encoding]::ASCII)
  [IO.File]::WriteAllText((Join-Path $Root 'hara-commander.cmd'),($wrapper+'%*'+"`r`n"+'exit /b %errorlevel%'+"`r`n"),[Text.Encoding]::ASCII)
  $userPath=[string][Environment]::GetEnvironmentVariable('Path','User')
  if(@($userPath -split ';'|Where-Object {$_.TrimEnd('\') -ieq $Root.TrimEnd('\')}).Count -eq 0){
    [Environment]::SetEnvironmentVariable('Path',(($userPath.TrimEnd(';')+';'+$Root).TrimStart(';')),'User')
  }
  if(@($env:Path -split ';'|Where-Object {$_.TrimEnd('\') -ieq $Root.TrimEnd('\')}).Count -eq 0){$env:Path+=';'+$Root}
  Write-Host 'HARA_COMMANDER_PAIR_COMMAND=INSTALLED'
  Write-Host 'Novo pareamento: hara commander pair (abra um novo terminal).'
}

function Assert-AgentIntegrity {
  param([string]$Path)
  $meta = Get-AgentReleaseMetadata
  Assert-AgentVersionFloor -IncomingVersion ([string]$meta.Version)
  if ((Get-Item -LiteralPath $Path).Length -ne $meta.Bytes) { throw "AGENT_SIZE_MISMATCH" }
  $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $meta.Sha256) { throw "AGENT_SHA256_MISMATCH" }
  $match = Select-String -LiteralPath $Path -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
  if (-not $match -or -not $match.Matches.Count) { throw "AGENT_VERSION_NOT_FOUND" }
  $version = $match.Matches[0].Groups[1].Value
  if ([string]$version -ne [string]$meta.Version) { throw "AGENT_VERSION_MANIFEST_MISMATCH" }
  Write-Host "HARA_COMMANDER_AGENT_INTEGRITY=PASS"
}

function Assert-AgentSelfTest {
  param([string]$Path)
  $PowerShellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
  & $PowerShellExe -NoLogo -NoProfile -NonInteractive -File $Path --self-test | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "AGENT_SELF_TEST_FAILED" }
  Write-Host "HARA_COMMANDER_AGENT_SELF_TEST=PASS"
}

function Assert-InstallPayloadPreflight {
  # Verify actual signed Agent bytes before asking for or consuming a pairing
  # token. Installation still performs its independent post-enrollment check.
  $path=Join-Path $env:TEMP ("hara-commander-install-preflight-"+[guid]::NewGuid().ToString("N")+".ps1")
  $owned=$false
  try {
    $reservation=New-Object IO.FileStream($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $owned=$true
    $reservation.Dispose()
    Invoke-WebRequest -Uri "$(Get-ReleaseBaseUrl)/agent/windows.ps1" -OutFile $path -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
    Assert-AgentIntegrity $path
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors) | Out-Null
    if ($errors.Count -ne 0) { throw "AGENT_INSTALL_SYNTAX_INVALID" }
    Assert-AgentSelfTest $path
  } finally {
    if ($owned -and (Test-Path -LiteralPath $path)) {
      Remove-Item -LiteralPath $path -Force -ErrorAction Stop
      if (Test-Path -LiteralPath $path) { throw "AGENT_PREFLIGHT_CLEANUP_FAILED" }
    }
  }
  Write-Host "HARA_COMMANDER_INSTALL_PAYLOAD_PREFLIGHT=PASS"
}

function Get-DeviceToken {
  param($Cfg)
  if (-not $Cfg -or -not $Cfg.encrypted_device_token) { throw "DEVICE_TOKEN_UNAVAILABLE" }
  $Secure = ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
  $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr) }
}

function Invoke-DeviceAction {
  param([string]$Kind)
  $cfg = Get-InstalledDevice
  if (-not $cfg -or -not $cfg.device_id) { throw "DEVICE_NOT_ENROLLED" }
  $base = if ($cfg.base_url) { ([string]$cfg.base_url).TrimEnd("/") } else { $BaseUrl }
  $token = Get-DeviceToken $cfg
  try {
    $headers = @{ Accept="application/json"; Authorization=("Bearer " + $token) }
    if ($Kind -eq "heartbeat") {
      $payload = @{ device_id=[string]$cfg.device_id; architecture=[string]$cfg.architecture; agent_version="0.3.60"; approval_mode=$(if ($cfg.approval_mode) {[string]$cfg.approval_mode} else {"ASK_EVERY_ACTION"}) } | ConvertTo-Json -Compress
      $result = Invoke-RestMethod -Uri "$base/api/device/heartbeat" -Method Post -ContentType "application/json" -Headers $headers -Body $payload -TimeoutSec 15 -MaximumRedirection 0
      if (-not $result.ok -or [string]$result.device_id -ne [string]$cfg.device_id) { throw "REMOTE_HEARTBEAT_INVALID" }
      return $result
    }
    if ($Kind -eq "revoke") {
      $result = Invoke-RestMethod -Uri "$base/api/device/revoke-self" -Method Post -ContentType "application/json" -Headers $headers -Body "{}" -TimeoutSec 15 -MaximumRedirection 0
      if (-not $result.ok -or [string]$result.state -ne "REVOKED" -or [string]$result.device_id -ne [string]$cfg.device_id) { throw "REMOTE_REVOKE_INVALID" }
      return $result
    }
    throw "DEVICE_ACTION_INVALID"
  } finally {
    $token = $null
  }
}

function Invoke-Preflight {
  $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -Headers @{ Accept="application/json" } -TimeoutSec 15 -MaximumRedirection 0
  if (-not $health.ok -or [string]$health.service -ne "hara-commander") { throw "COMMANDER_HEALTH_INVALID" }
  $release = Get-AgentReleaseMetadata
  Assert-InstallPayloadPreflight
  $scheduledTaskReady = [bool](Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)
  $powershellReady = [bool](Get-Command powershell.exe -ErrorAction SilentlyContinue)
  $report = [ordered]@{
    schema = "hara.commander-device-preflight.v1"
    platform = "WINDOWS"
    architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    commander_url = $BaseUrl
    commander_health = $true
    release_manifest = $true
    release_signature = $true
    agent_payload = $true
    agent_payload_syntax = $true
    agent_payload_self_test = $true
    stable_agent_version = [string]$release.Version
    persistence = "on-demand-scheduled-task"
    persistence_ready = ($scheduledTaskReady -and $powershellReady)
    mutation_performed = $false
  }
  $report | ConvertTo-Json -Compress
  if (-not $report.persistence_ready) { throw "WINDOWS_PERSISTENCE_PREREQUISITE_MISSING" }
}

function Show-SupportReport {
  $cfg = Get-InstalledDevice
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  $version = "unknown"
  $sha256 = $null
  if (Test-Path -LiteralPath $Agent -PathType Leaf) {
    $match = Select-String -LiteralPath $Agent -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
    if ($match -and $match.Matches.Count) { $version = $match.Matches[0].Groups[1].Value }
    try { $sha256 = (Get-FileHash -LiteralPath $Agent -Algorithm SHA256).Hash.ToLowerInvariant() } catch { $sha256 = $null }
  }
  $tokenPresent = $false
  if ($cfg -and $cfg.encrypted_device_token) { $tokenPresent = $true }
  $runtime = $null
  if (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf) {
    try { $runtime = Get-Content -Raw -LiteralPath $RuntimeStatus | ConvertFrom-Json } catch { $runtime = $null }
  }
  $report = [ordered]@{
    schema = "hara.commander-support-report.v1"
    platform = "WINDOWS"
    device_id = $(if ($cfg -and $cfg.device_id) { [string]$cfg.device_id } else { $null })
    architecture = $(if ($cfg -and $cfg.architecture) { [string]$cfg.architecture } else { [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant() })
    commander_url = $(if ($cfg -and $cfg.base_url) { [string]$cfg.base_url } else { $null })
    agent_version = $version
    agent_sha256 = $sha256
    config_present = (Test-Path -LiteralPath $Config -PathType Leaf)
    task_present = [bool]$task
    task_state = $(if ($task) { [string]$task.State } else { $null })
    device_token_present = $tokenPresent
    device_token_exposed = $false
    last_successful_heartbeat_at_utc = $(if ($runtime) { [string]$runtime.last_successful_heartbeat_at_utc } else { $null })
    last_runtime_error_code = $(if ($runtime) { [string]$runtime.last_runtime_error_code } else { $null })
    last_runtime_error_at_utc = $(if ($runtime) { [string]$runtime.last_runtime_error_at_utc } else { $null })
  }
  $report | ConvertTo-Json -Compress
}

function Invoke-Doctor {
  $cfg = Get-InstalledDevice
  if (-not $cfg) { throw "DEVICE_NOT_ENROLLED" }
  if (-not (Test-Path -LiteralPath $Agent -PathType Leaf)) { throw "AGENT_BINARY_MISSING" }
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if (-not $task) { throw "AGENT_TASK_NOT_INSTALLED" }
  if ([string]$task.State -ne "Running") { throw "AGENT_TASK_NOT_RUNNING" }
  $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -Headers @{ Accept="application/json" } -TimeoutSec 15 -MaximumRedirection 0
  if (-not $health.ok -or [string]$health.service -ne "hara-commander") { throw "COMMANDER_HEALTH_INVALID" }
  Write-Host "HARA_COMMANDER_AGENT_DOCTOR=PASS"
  Write-Host "COMMANDER_REMOTE_HEALTH=PASS"
  Write-Host "COMMANDER_REMOTE_HEARTBEAT=SKIPPED_LOCAL_SESSION_REQUIRED"
  Show-Status
}

function Show-Status {
  $cfg = Get-InstalledDevice
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  $version = "unknown"
  if (Test-Path -LiteralPath $Agent -PathType Leaf) {
    $match = Select-String -LiteralPath $Agent -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
    if ($match -and $match.Matches.Count) { $version = $match.Matches[0].Groups[1].Value }
  }
  Write-Host ("HARA_COMMANDER_DEVICE_ENROLLED=" + $(if ($cfg) {"TRUE"} else {"FALSE"}))
  Write-Host ("HARA_COMMANDER_AGENT_REGISTERED=" + $(if ($task) {"TRUE"} else {"FALSE"}))
  Write-Host ("HARA_COMMANDER_AGENT_ACTIVE=" + $(if ($task -and [string]$task.State -eq "Running") {"TRUE"} else {"FALSE"}))
  Write-Host ("HARA_COMMANDER_AGENT_AUTOSTART=" + $(if ($task -and $task.Triggers) {"ON"} else {"OFF"}))
  Write-Host ("HARA_COMMANDER_AGENT_VERSION=" + $version)
  if ($cfg -and $cfg.device_id) { Write-Host ("DEVICE_ID=" + [string]$cfg.device_id) }
  if ($cfg -and $cfg.approval_mode) { Write-Host ("HARA_COMMANDER_APPROVAL_MODE=" + [string]$cfg.approval_mode) }
  if (Test-Path -LiteralPath $Agent -PathType Leaf) {
    $PowerShellExe = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Source
    if ($PowerShellExe) { & $PowerShellExe -NoLogo -NoProfile -File $Agent --session-status }
  }
  Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
}


# Embedded controller source SHA256: 2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da
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
    Install-PairCommand
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


if ($Action -in @('connect','conectar')) {
  $connectGuard=$null;$connectExit=2
  try {
    $connectOrigin=if($env:HARA_COMMANDER_URL){[string]$env:HARA_COMMANDER_URL}else{''}
    $connectRelease=if($env:HARA_COMMANDER_RELEASE_URL){[string]$env:HARA_COMMANDER_RELEASE_URL}else{''}
    $connectContext=New-CCContext $connectOrigin $connectRelease $ApprovalMode
    $connectGuard=Enter-CCGuard $connectContext
    $connectResult=Invoke-CCConnect $connectContext
    if($connectResult.state -ceq 'CONNECTED'){
      Write-Host 'Commander conectado. O pareamento e a versao foram verificados.'
      $connectExit=0
    }elseif($connectResult.state -ceq 'CONNECTED_UPDATE_HOLD'){
      Write-Host 'Commander conectado. A atualizacao nao foi concluida; o pareamento foi preservado.' -ForegroundColor Yellow
      $connectExit=3
    }else{
      Write-Host 'Nao foi possivel concluir a conexao. Consulte o codigo de diagnostico abaixo.' -ForegroundColor Yellow
    }
    $connectResult|ConvertTo-Json -Depth 6
  }catch{
    [pscustomobject]@{state='HOLD';error_code=(Get-CCErrorCode $_);device_token_exposed=$false}|ConvertTo-Json
  }finally{if($connectGuard){$connectGuard.ReleaseMutex();$connectGuard.Dispose()}}
  exit $connectExit
}
if ($Action -in @('pair','parear','re-pair')) {
  if(Test-Path -LiteralPath $Config -PathType Leaf){
    $pairContext=New-CCContext '' '' $ApprovalMode
    $pairState=Get-CCInstalledState $pairContext
    $pairCredential=Test-CCCredential $pairState
    if($pairCredential -ceq 'VALID'){
      Write-Host 'Esta maquina ja esta pareada. Para trocar o vinculo, revogue o acesso no site e execute hara commander pair com um codigo novo.'
      Write-Host 'HARA_COMMANDER_PAIRING=ALREADY_VALID'
      exit 0
    }
    Need-CC ($pairCredential -ceq 'REJECTED') 'PAIRING_CURRENT_STATE_UNCONFIRMED'
    $Action='re-enroll'
  }else{$Action='pair-existing'}
}
if ($Action -in @('pair-existing','re-enroll')) {
  Invoke-PreservedPairing $Action
  exit 0
}
if ($Action -eq 'install' -and -not (Test-Path -LiteralPath $Config)) {
  if (Test-Path -LiteralPath $Agent) {
    Invoke-PreservedPairing 'pair-existing'
    exit 0
  }
  if ((Test-Path -LiteralPath $Root) -and @(Get-ChildItem -LiteralPath $Root -Force).Count -gt 0) {
    throw 'UNPAIRED_PATH_CONFLICT'
  }
}

if ($Action -eq "preflight") { Invoke-Preflight; exit 0 }
if ($Action -eq "status") { Show-Status; exit 0 }
if ($Action -eq "doctor") { Invoke-Doctor; exit 0 }
if ($Action -eq "support") { Show-SupportReport; exit 0 }
if ($Action -eq "update") {
  if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw "DEVICE_NOT_ENROLLED" }
  if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) { throw "AGENT_TASK_NOT_INSTALLED" }
  $cfg = Get-InstalledDevice
  if ($cfg -and $cfg.base_url) { $BaseUrl = ([string]$cfg.base_url).TrimEnd("/") }
  Assert-CommanderBaseUrl
  $taskBefore = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  $UpdateTaskWasRunning = [string]$taskBefore.State -eq "Running"
  $PreviousStarted = Get-RuntimeStartedAt
  # PowerShell -File requires an executable .ps1 suffix. The previous
  # '.ps1.update' name failed before self-test, even for a signed valid Agent.
  $tmp = $Agent + ".update.ps1"
  $backup = $Agent + ".rollback"
  Remove-Item -Force $tmp,$backup -ErrorAction SilentlyContinue
  Invoke-WebRequest -Uri "$(Get-ReleaseBaseUrl)/agent/windows.ps1" -OutFile $tmp -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
  Assert-AgentIntegrity $tmp
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($tmp,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { Remove-Item -Force $tmp; throw "AGENT_UPDATE_SYNTAX_INVALID" }
  Assert-AgentSelfTest $tmp
  $VersionMatch=Select-String -LiteralPath $tmp -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
  if (-not $VersionMatch -or -not $VersionMatch.Matches.Count) { throw "AGENT_VERSION_NOT_FOUND" }
  $ExpectedVersion=[string]$VersionMatch.Matches[0].Groups[1].Value
  if (-not (Test-Path -LiteralPath $Agent -PathType Leaf)) { throw "AGENT_UPDATE_PREIMAGE_REQUIRED" }
  Copy-Item -Force $Agent $backup -ErrorAction Stop
  $PreviousVersionMatches=@(Select-String -LiteralPath $backup -Pattern '^\$AgentVersion = "([^"]+)"$' -CaseSensitive)
  if ($PreviousVersionMatches.Count -ne 1) { throw "AGENT_INSTALLED_VERSION_UNKNOWN" }
  $PreviousVersion=[string]$PreviousVersionMatches[0].Matches[0].Groups[1].Value
  $PreviousSha=(Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash
  try {
    if ($UpdateTaskWasRunning) { Stop-AgentTaskAndWait }
    Move-Item -Force $tmp $Agent -ErrorAction Stop
    Install-PairCommand
    if ($UpdateTaskWasRunning) {
      Start-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
      if (-not (Wait-AgentTaskStartup $ExpectedVersion $PreviousStarted 15)) {
        throw "AGENT_UPDATE_START_FAILED"
      }
      Write-Host "HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS"
    } else {
      # Updating a manually stopped agent must never initiate a connection.
      Write-Host "HARA_COMMANDER_AGENT_UPDATE_RUNTIME_ATTESTATION=SKIPPED_MANUAL_STOP"
    }
  } catch {
    $UpdateFailure=$_
    $RollbackState="AGENT_RESTORE_FAILED"
    try {
      if ($UpdateTaskWasRunning) { Stop-AgentTaskAndWait }
      # Keep the exact preimage available even if runtime recovery fails.
      Copy-Item -Force $backup $Agent -ErrorAction Stop
      if ((Get-FileHash -LiteralPath $Agent -Algorithm SHA256).Hash -cne $PreviousSha) { throw "AGENT_ROLLBACK_INTEGRITY_FAILED" }
      if ($UpdateTaskWasRunning) {
        $RollbackPreviousStarted=Get-RuntimeStartedAt
        $RollbackState="SERVICE_RESTART_FAILED"
        Start-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
        $RollbackState="STARTUP_ATTESTATION_FAILED"
        if (Wait-AgentTaskStartup $PreviousVersion $RollbackPreviousStarted 15) { $RollbackState="PASS" }
      } else { $RollbackState="AGENT_RESTORED_MANUAL_STOP" }
    } catch {
      # The state names the failed recovery step; never turn it into PASS.
    }
    Write-Host ("HARA_COMMANDER_AGENT_UPDATE_ROLLBACK="+$RollbackState)
    throw $UpdateFailure
  }
  # Retain the exact preimage advertised by ROLLBACK_READY, also on success.
  Write-Host ("HARA_COMMANDER_AGENT_UPDATE_TASK_WAS_RUNNING=" + $(if ($UpdateTaskWasRunning) {"TRUE"} else {"FALSE"}))
  Write-Host "HARA_COMMANDER_AGENT_UPDATE=PASS"
  Write-Host "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE"
  Show-Status
  exit 0
}
if ($Action -eq "uninstall") {
  $cfg = Get-InstalledDevice
  $revokeState = "PENDING"
  if ($cfg) {
    try { Invoke-DeviceAction "revoke" | Out-Null; $revokeState = "PASS" } catch { $revokeState = "PENDING" }
  }
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host "HARA_COMMANDER_AGENT_UNINSTALL=PASS"
  if ($cfg -and $cfg.device_id) { Write-Host ("DEVICE_ID=" + [string]$cfg.device_id) }
  Write-Host ("SERVER_DEVICE_REVOKE=" + $revokeState)
  if ($revokeState -ne "PASS") { Write-Host "SERVER_DEVICE_REVOKE_PENDING=TRUE" }
  Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
  exit 0
}
if ($Action -ne "install") { throw "Usage: windows.ps1 -Action connect|install|pair|pair-existing|re-enroll|preflight|status|doctor|support|update|uninstall" }
if (Test-Path -LiteralPath $Config -PathType Leaf) { throw "DEVICE_ALREADY_ENROLLED: use status, update, or uninstall." }
# Hold an obsolete public manifest before asking for a pairing token.
Assert-AgentVersionFloor -IncomingVersion ([string](Get-AgentReleaseMetadata).Version)
Assert-InstallPayloadPreflight

Write-Host "HARA Commander - Windows device pairing"
$SecurePairing = Read-Host "Pairing token" -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePairing)
try { $PairingToken = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr) }
if ([string]::IsNullOrWhiteSpace($PairingToken)) { throw "Pairing token cannot be empty." }

$DeviceName = $env:COMPUTERNAME
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
$Payload = @{ pairing_token=$PairingToken; device_name=$DeviceName; platform="WINDOWS"; architecture=$Architecture; agent_version="0.3.60"; approval_mode=$ApprovalMode } | ConvertTo-Json -Compress
$Enroll = Invoke-RestMethod -Uri "$BaseUrl/api/device/enroll" -Method Post -ContentType "application/json" -Headers @{ Accept="application/json" } -Body $Payload -TimeoutSec 30 -MaximumRedirection 0
$PairingToken = $null
$Payload = $null
$SecurePairing.Dispose()
if (-not $Enroll.device_id -or -not $Enroll.device_token) { throw "DEVICE_ENROLLMENT_RESPONSE_INVALID" }

$InstallEnrolled = $true
$EnrollDeviceId = [string]$Enroll.device_id
$DeviceTokenForRollback = [string]$Enroll.device_token
$Enroll.device_token = $null
$Enroll = $null
try {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $EncryptedToken = ConvertTo-SecureString $DeviceTokenForRollback -AsPlainText -Force | ConvertFrom-SecureString
  $ConfigObject = @{ base_url=$BaseUrl; device_id=$EnrollDeviceId; encrypted_device_token=$EncryptedToken; architecture=$Architecture; agent_version="0.3.60"; approval_mode=$ApprovalMode }
  $ConfigObject | ConvertTo-Json | Set-Content -Path $Config -Encoding UTF8

  $Identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls.exe $Root /inheritance:r /grant:r "${Identity}:(OI)(CI)F" | Out-Null
  & icacls.exe $Config /inheritance:r /grant:r "${Identity}:F" | Out-Null

  $InstallTmp = $Agent + ".install.ps1"
  Remove-Item -Force $InstallTmp -ErrorAction SilentlyContinue
  Invoke-WebRequest -Uri "$(Get-ReleaseBaseUrl)/agent/windows.ps1" -OutFile $InstallTmp -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
  Assert-AgentIntegrity $InstallTmp
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($InstallTmp,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { Remove-Item -Force $InstallTmp; throw "AGENT_INSTALL_SYNTAX_INVALID" }
  Assert-AgentSelfTest $InstallTmp
  $VersionMatch=Select-String -LiteralPath $InstallTmp -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
  if (-not $VersionMatch -or -not $VersionMatch.Matches.Count) { throw "AGENT_VERSION_NOT_FOUND" }
  $ExpectedVersion=[string]$VersionMatch.Matches[0].Groups[1].Value
  Move-Item -Force $InstallTmp $Agent
  & icacls.exe $Agent /inheritance:r /grant:r "${Identity}:F" | Out-Null

  $PowerShellExe = (Get-Command powershell.exe).Source
  $Argument = "-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File `"$Agent`""
  $TaskAction = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $Argument
  # Register an ON-DEMAND task with NO AtLogOn / AtStartup trigger.
  # Installation starts it once; reboot/login never starts it automatically.
  $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Settings $Settings -Description "HARA Commander on-demand device agent" -Force | Out-Null
  $Registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  if ($Registered.Triggers -and @($Registered.Triggers).Count -gt 0) { throw "AGENT_MANUAL_START_POLICY_VIOLATED" }
  Start-ScheduledTask -TaskName $TaskName
  Start-Sleep -Seconds 2
  $Task = Get-ScheduledTask -TaskName $TaskName
  if (-not $Task -or -not (Wait-AgentStartup $ExpectedVersion "" 10)) { throw "HARA Commander Agent failed startup attestation." }
  Write-Host "HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS"

  Install-PairCommand
  $InstallEnrolled = $false
  $DeviceTokenForRollback = $null
  Write-Host "HARA_COMMANDER_DEVICE_ENROLLMENT=PASS"
  Write-Host "HARA_COMMANDER_AGENT_TASK=REGISTERED_INERT_UNTIL_LOCAL_SESSION"
  Write-Host "HARA_COMMANDER_AGENT_AUTOSTART=OFF"
  Write-Host "HARA_COMMANDER_AGENT_START_MODE=MANUAL_AFTER_INSTALL"
  Write-Host "DEVICE_ID=$EnrollDeviceId"
  Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
  Write-Host ("NEXT_COMMAND=powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"" + $Agent + "`" start")
  Write-Host "SESSION_AUTHORITY=LOCAL_OPERATOR_TERMINAL"
} catch {
  $OriginalError = $_
  if ($InstallEnrolled) {
    $RevokeState = "PENDING"
    try {
      $headers = @{ Accept="application/json"; Authorization=("Bearer " + $DeviceTokenForRollback) }
      $result = Invoke-RestMethod -Uri "$BaseUrl/api/device/revoke-self" -Method Post -ContentType "application/json" -Headers $headers -Body "{}" -TimeoutSec 15 -MaximumRedirection 0
      if ($result.ok -and [string]$result.state -eq "REVOKED" -and [string]$result.device_id -eq $EnrollDeviceId) { $RevokeState = "PASS" }
    } catch { $RevokeState = "PENDING" }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ("HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=" + $RevokeState)
    if ($RevokeState -ne "PASS") { Write-Host "SERVER_DEVICE_REVOKE_PENDING=TRUE" }
  }
  $DeviceTokenForRollback = $null
  throw $OriginalError
}
