param([string]$Action = "install")
$ErrorActionPreference = "Stop"
$Action = $Action.TrimStart("-").ToLowerInvariant()

$BaseUrl = if ($env:HARA_COMMANDER_URL) { $env:HARA_COMMANDER_URL.TrimEnd("/") } else { "https://commander.haralabs.com.br" }
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

function Get-AgentReleaseMetadata {
  $manifest = Invoke-RestMethod -Uri "$BaseUrl/release/agent-manifest.json" -Method Get -Headers @{ Accept="application/json" } -TimeoutSec 30 -MaximumRedirection 0
  if (-not $manifest -or [string]$manifest.schema -ne "hara.commander-agent-release.v1") { throw "AGENT_RELEASE_MANIFEST_INVALID" }
  $entry = @($manifest.files | Where-Object { [string]$_.path -eq "agent/windows.ps1" } | Select-Object -First 1)
  if (-not $entry -or -not $entry.sha256 -or -not $manifest.agent_version) { throw "AGENT_RELEASE_MANIFEST_INVALID" }
  return [PSCustomObject]@{ Version=[string]$manifest.agent_version; Sha256=([string]$entry.sha256).ToLowerInvariant() }
}

function Assert-AgentIntegrity {
  param([string]$Path)
  $meta = Get-AgentReleaseMetadata
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
  & $PowerShellExe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Path --self-test | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "AGENT_SELF_TEST_FAILED" }
  Write-Host "HARA_COMMANDER_AGENT_SELF_TEST=PASS"
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
      $payload = @{ device_id=[string]$cfg.device_id; architecture=[string]$cfg.architecture; agent_version="0.3.6" } | ConvertTo-Json -Compress
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
  $manifest = Invoke-RestMethod -Uri "$BaseUrl/release/agent-manifest.json" -Method Get -Headers @{ Accept="application/json" } -TimeoutSec 15 -MaximumRedirection 0
  if (-not $manifest -or [string]$manifest.schema -ne "hara.commander-agent-release.v1" -or -not $manifest.agent_version) { throw "AGENT_RELEASE_MANIFEST_INVALID" }
  $scheduledTaskReady = [bool](Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)
  $powershellReady = [bool](Get-Command powershell.exe -ErrorAction SilentlyContinue)
  $report = [ordered]@{
    schema = "hara.commander-device-preflight.v1"
    platform = "WINDOWS"
    architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    commander_url = $BaseUrl
    commander_health = $true
    release_manifest = $true
    stable_agent_version = [string]$manifest.agent_version
    persistence = "scheduled-task"
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
  Invoke-DeviceAction "heartbeat" | Out-Null
  Write-Host "HARA_COMMANDER_AGENT_DOCTOR=PASS"
  Write-Host "COMMANDER_REMOTE_HEARTBEAT=PASS"
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
  Write-Host ("HARA_COMMANDER_AGENT_VERSION=" + $version)
  if ($cfg -and $cfg.device_id) { Write-Host ("DEVICE_ID=" + [string]$cfg.device_id) }
  Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
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
  $PreviousStarted = Get-RuntimeStartedAt
  $tmp = $Agent + ".update"
  $backup = $Agent + ".rollback"
  Remove-Item -Force $tmp,$backup -ErrorAction SilentlyContinue
  Invoke-WebRequest -Uri "$BaseUrl/agent/windows.ps1" -OutFile $tmp -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
  Assert-AgentIntegrity $tmp
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($tmp,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { Remove-Item -Force $tmp; throw "AGENT_UPDATE_SYNTAX_INVALID" }
  Assert-AgentSelfTest $tmp
  $VersionMatch=Select-String -LiteralPath $tmp -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
  if (-not $VersionMatch -or -not $VersionMatch.Matches.Count) { throw "AGENT_VERSION_NOT_FOUND" }
  $ExpectedVersion=[string]$VersionMatch.Matches[0].Groups[1].Value
  if (Test-Path -LiteralPath $Agent -PathType Leaf) { Copy-Item -Force $Agent $backup }
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Move-Item -Force $tmp $Agent
  Start-ScheduledTask -TaskName $TaskName
  Start-Sleep -Seconds 2
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if (
    -not $task
    -or [string]$task.State -ne "Running"
    -or -not (Wait-AgentStartup $ExpectedVersion $PreviousStarted 10)
  ) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $backup -PathType Leaf) {
      Move-Item -Force $backup $Agent
      Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
      Write-Host "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=PASS"
    }
    throw "AGENT_UPDATE_START_FAILED"
  }
  Remove-Item -Force $backup -ErrorAction SilentlyContinue
  Write-Host "HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS"
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
if ($Action -ne "install") { throw "Usage: windows.ps1 -Action install|preflight|status|doctor|support|update|uninstall" }
if (Test-Path -LiteralPath $Config -PathType Leaf) { throw "DEVICE_ALREADY_ENROLLED: use status, update, or uninstall." }

Write-Host "HARA Commander - Windows device pairing"
$SecurePairing = Read-Host "Pairing token" -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePairing)
try { $PairingToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr) }
if ([string]::IsNullOrWhiteSpace($PairingToken)) { throw "Pairing token cannot be empty." }

$DeviceName = $env:COMPUTERNAME
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
$Payload = @{ pairing_token=$PairingToken; device_name=$DeviceName; platform="WINDOWS"; architecture=$Architecture; agent_version="0.3.6" } | ConvertTo-Json -Compress
$Enroll = Invoke-RestMethod -Uri "$BaseUrl/api/device/enroll" -Method Post -ContentType "application/json" -Headers @{ Accept="application/json" } -Body $Payload -TimeoutSec 30 -MaximumRedirection 0
$PairingToken = $null
$Payload = $null
$SecurePairing.Dispose()
if (-not $Enroll.device_id -or -not $Enroll.device_token) { throw "DEVICE_ENROLLMENT_RESPONSE_INVALID" }

$InstallEnrolled = $true
$DeviceTokenForRollback = [string]$Enroll.device_token
try {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $EncryptedToken = ConvertTo-SecureString $Enroll.device_token -AsPlainText -Force | ConvertFrom-SecureString
  $ConfigObject = @{ base_url=$BaseUrl; device_id=[string]$Enroll.device_id; encrypted_device_token=$EncryptedToken; architecture=$Architecture; agent_version="0.3.6" }
  $ConfigObject | ConvertTo-Json | Set-Content -Path $Config -Encoding UTF8

  $Identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls.exe $Root /inheritance:r /grant:r "$Identity:(OI)(CI)F" | Out-Null
  & icacls.exe $Config /inheritance:r /grant:r "$Identity:F" | Out-Null

  $InstallTmp = $Agent + ".install"
  Remove-Item -Force $InstallTmp -ErrorAction SilentlyContinue
  Invoke-WebRequest -Uri "$BaseUrl/agent/windows.ps1" -OutFile $InstallTmp -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
  Assert-AgentIntegrity $InstallTmp
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($InstallTmp,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { Remove-Item -Force $InstallTmp; throw "AGENT_INSTALL_SYNTAX_INVALID" }
  Assert-AgentSelfTest $InstallTmp
  $VersionMatch=Select-String -LiteralPath $InstallTmp -Pattern '^\$AgentVersion = "([^"]+)"$' | Select-Object -First 1
  if (-not $VersionMatch -or -not $VersionMatch.Matches.Count) { throw "AGENT_VERSION_NOT_FOUND" }
  $ExpectedVersion=[string]$VersionMatch.Matches[0].Groups[1].Value
  Move-Item -Force $InstallTmp $Agent
  & icacls.exe $Agent /inheritance:r /grant:r "$Identity:F" | Out-Null

  $PowerShellExe = (Get-Command powershell.exe).Source
  $Argument = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Agent`""
  $Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $Argument
  $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "HARA Commander outbound device agent" -Force | Out-Null
  Start-ScheduledTask -TaskName $TaskName
  Start-Sleep -Seconds 2
  $Task = Get-ScheduledTask -TaskName $TaskName
  if (
    -not $Task
    -or -not (Wait-AgentStartup $ExpectedVersion "" 10)
  ) { throw "HARA Commander Agent failed startup attestation." }
  Write-Host "HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS"

  $InstallEnrolled = $false
  $DeviceTokenForRollback = $null
  Write-Host "HARA_COMMANDER_DEVICE_ENROLLMENT=PASS"
  Write-Host "HARA_COMMANDER_AGENT_TASK=REGISTERED"
  Write-Host "DEVICE_ID=$($Enroll.device_id)"
  Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
} catch {
  $OriginalError = $_
  if ($InstallEnrolled) {
    $RevokeState = "PENDING"
    try {
      $headers = @{ Accept="application/json"; Authorization=("Bearer " + $DeviceTokenForRollback) }
      $result = Invoke-RestMethod -Uri "$BaseUrl/api/device/revoke-self" -Method Post -ContentType "application/json" -Headers $headers -Body "{}" -TimeoutSec 15 -MaximumRedirection 0
      if ($result.ok -and [string]$result.state -eq "REVOKED" -and [string]$result.device_id -eq [string]$Enroll.device_id) { $RevokeState = "PASS" }
    } catch { $RevokeState = "PENDING" }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ("HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=" + $RevokeState)
    if ($RevokeState -ne "PASS") { Write-Host "SERVER_DEVICE_REVOKE_PENDING=TRUE" }
  }
  $DeviceTokenForRollback = $null
  throw $OriginalError
}
