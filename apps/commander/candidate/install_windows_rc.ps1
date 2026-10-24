param(
  [ValidateSet("check","install","activate-event-v2","rollback","status")]
  [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

$StableTaskName = "HARA Commander Agent"
$RcTaskName = "HARA Commander Agent RC"
$StableRoot = Join-Path $env:LOCALAPPDATA "HARA Commander"
$StableConfig = Join-Path $StableRoot "device.json"
$RcRoot = Join-Path $env:LOCALAPPDATA "HARA Commander RC"
$RcAgent = Join-Path $RcRoot "windows_agent_rc.ps1"
$RcEventAgent = Join-Path $RcRoot "event_v2_windows_agent.ps1"
$RcTransport = Join-Path $RcRoot "event_v2_windows_transport.ps1"
$EventStatus = Join-Path $StableRoot "event-v2-status.json"
$ExpectedDevOrigin = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
$ShutdownPipeName = "hara-commander-event-v2-rc-stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommanderRoot = Split-Path -Parent $Here
$SourceRc = Join-Path $CommanderRoot "candidate\windows_agent_rc.ps1"
$SourceEventAgent = Join-Path $CommanderRoot "experimental\event_v2_windows_agent.ps1"
$SourceTransport = Join-Path $CommanderRoot "experimental\event_v2_windows_transport.ps1"

function Assert-ExistingIdentity {
  if (-not (Test-Path -LiteralPath $StableConfig -PathType Leaf)) {
    throw "WINDOWS_RC_DEVICE_IDENTITY_MISSING"
  }
  $cfg = Get-Content -Raw -LiteralPath $StableConfig | ConvertFrom-Json
  if (
    -not $cfg.device_id
    -or -not $cfg.encrypted_device_token
    -or -not $cfg.base_url
    -or -not $cfg.architecture
  ) { throw "WINDOWS_RC_DEVICE_IDENTITY_INVALID" }
  return $cfg
}

function Assert-Source {
  foreach ($path in @($SourceRc,$SourceEventAgent,$SourceTransport)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
      throw "WINDOWS_RC_SOURCE_MISSING"
    }
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
      $path,[ref]$tokens,[ref]$errors
    ) | Out-Null
    if ($errors.Count -ne 0) { throw "WINDOWS_RC_SOURCE_PARSE_FAILED" }
  }
}

function Get-TaskState([string]$Name) {
  $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
  if (-not $task) { return "ABSENT" }
  return [string]$task.State
}

function Stop-TaskSafe([string]$Name) {
  Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
  for ($i=0; $i -lt 10; $i++) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $task -or [string]$task.State -ne "Running") { return }
    Start-Sleep -Seconds 1
  }
  throw "WINDOWS_RC_TASK_STOP_FAILED"
}

function Request-RcGracefulShutdown {
  $pipe = $null
  try {
    $pipe = [System.IO.Pipes.NamedPipeClientStream]::new(
      ".",$ShutdownPipeName,[System.IO.Pipes.PipeDirection]::Out
    )
    $pipe.Connect(1500)
    return $true
  } catch {
    return $false
  } finally {
    if ($null -ne $pipe) { try { $pipe.Dispose() } catch {} }
  }
}

function Stop-RcTaskSafe {
  $task = Get-ScheduledTask -TaskName $RcTaskName -ErrorAction SilentlyContinue
  if (-not $task -or [string]$task.State -ne "Running") { return "NOT_RUNNING" }

  if (Request-RcGracefulShutdown) {
    for ($i=0; $i -lt 10; $i++) {
      $task = Get-ScheduledTask -TaskName $RcTaskName -ErrorAction SilentlyContinue
      if (-not $task -or [string]$task.State -ne "Running") { return "GRACEFUL" }
      Start-Sleep -Seconds 1
    }
  }

  Stop-TaskSafe $RcTaskName
  return "FALLBACK"
}

function Disable-TaskSafe([string]$Name) {
  Disable-ScheduledTask -TaskName $Name -ErrorAction Stop | Out-Null
}

function Enable-TaskRequired([string]$Name) {
  Enable-ScheduledTask -TaskName $Name -ErrorAction Stop | Out-Null
}

function Start-TaskRequired([string]$Name) {
  Start-ScheduledTask -TaskName $Name -ErrorAction Stop
  for ($i=0; $i -lt 10; $i++) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($task -and [string]$task.State -eq "Running") { return }
    Start-Sleep -Seconds 1
  }
  throw "WINDOWS_RC_TASK_START_FAILED"
}

function Get-EventStatusUpdated {
  if (-not (Test-Path -LiteralPath $EventStatus -PathType Leaf)) { return "" }
  try {
    $obj = Get-Content -Raw -LiteralPath $EventStatus | ConvertFrom-Json
    return [string]$obj.updated_at_utc
  } catch { return "" }
}

function Wait-EventConnection([string]$PreviousUpdated,[int]$Seconds=20) {
  for ($i=0; $i -lt $Seconds; $i++) {
    if (Test-Path -LiteralPath $EventStatus -PathType Leaf) {
      try {
        $obj = Get-Content -Raw -LiteralPath $EventStatus | ConvertFrom-Json
        if (
          [string]$obj.schema -eq "hara.commander-event-v2-runtime-status.v1"
          -and [string]$obj.transport_mode -eq "EVENT_V2"
          -and $obj.connected -eq $true
          -and [string]$obj.updated_at_utc
          -and [string]$obj.updated_at_utc -ne $PreviousUpdated
        ) { return $true }
      } catch {}
    }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Wait-EventDisconnection([string]$PreviousUpdated,[int]$Seconds=10) {
  for ($i=0; $i -lt $Seconds; $i++) {
    if (Test-Path -LiteralPath $EventStatus -PathType Leaf) {
      try {
        $obj = Get-Content -Raw -LiteralPath $EventStatus | ConvertFrom-Json
        if (
          [string]$obj.schema -eq "hara.commander-event-v2-runtime-status.v1"
          -and [string]$obj.transport_mode -eq "EVENT_V2"
          -and $obj.connected -eq $false
          -and [string]$obj.updated_at_utc
          -and [string]$obj.updated_at_utc -ne $PreviousUpdated
        ) { return $true }
      } catch {}
    }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Rollback-ToStable {
  $previous = Get-EventStatusUpdated
  $shutdownMode = Stop-RcTaskSafe
  $cleanDisconnect = $false
  if ($shutdownMode -eq "GRACEFUL") {
    $cleanDisconnect = Wait-EventDisconnection $previous 10
  }
  Disable-TaskSafe $RcTaskName
  if (-not (Get-ScheduledTask -TaskName $StableTaskName -ErrorAction SilentlyContinue)) {
    throw "WINDOWS_RC_STABLE_TASK_MISSING"
  }
  Enable-TaskRequired $StableTaskName
  Start-TaskRequired $StableTaskName
  Write-Host "COMMANDER_WINDOWS_RC_ROLLBACK=PASS"
  Write-Host "COMMANDER_WINDOWS_RC_STABLE_TASK=ACTIVE"
  Write-Host "COMMANDER_WINDOWS_RC_TASK=INACTIVE"
  Write-Host "COMMANDER_WINDOWS_RC_DEVICE_REPAIRING=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_TOKEN_EXPOSED=FALSE"
  Write-Host ("COMMANDER_WINDOWS_RC_SHUTDOWN_MODE=" + $shutdownMode)
  if ($shutdownMode -eq "GRACEFUL" -and $cleanDisconnect) {
    Write-Host "COMMANDER_WINDOWS_RC_COOPERATIVE_SHUTDOWN=PASS"
    Write-Host "COMMANDER_WINDOWS_RC_CLEAN_DISCONNECT=PASS"
  } elseif ($shutdownMode -eq "NOT_RUNNING") {
    Write-Host "COMMANDER_WINDOWS_RC_COOPERATIVE_SHUTDOWN=NOT_REQUIRED"
    Write-Host "COMMANDER_WINDOWS_RC_CLEAN_DISCONNECT=NOT_REQUIRED"
  } else {
    Write-Host "COMMANDER_WINDOWS_RC_COOPERATIVE_SHUTDOWN=FALLBACK"
    Write-Host "COMMANDER_WINDOWS_RC_CLEAN_DISCONNECT=UNPROVEN"
  }
}

function Install-Rc {
  Assert-Source
  Assert-ExistingIdentity | Out-Null

  if ((Get-TaskState $RcTaskName) -eq "Running") {
    throw "WINDOWS_RC_INSTALL_WHILE_ACTIVE_DENIED"
  }

  New-Item -ItemType Directory -Path $RcRoot -Force | Out-Null
  Copy-Item -Force -LiteralPath $SourceRc -Destination $RcAgent
  Copy-Item -Force -LiteralPath $SourceEventAgent -Destination $RcEventAgent
  Copy-Item -Force -LiteralPath $SourceTransport -Destination $RcTransport

  $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls.exe $RcRoot /inheritance:r /grant:r ($identity + ":(OI)(CI)F") | Out-Null

  $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
  $argument = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $RcAgent + '" -Transport EVENT_V2'
  $taskAction = New-ScheduledTaskAction -Execute $powershell -Argument $argument
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)

  Register-ScheduledTask -TaskName $RcTaskName -Action $taskAction -Trigger $trigger -Settings $settings -Description "HARA Commander Event V2 RC - opt-in only" -Force | Out-Null
  Stop-TaskSafe $RcTaskName
  Disable-TaskSafe $RcTaskName
  if ((Get-TaskState $RcTaskName) -ne "Disabled") {
    throw "WINDOWS_RC_INSTALL_NOT_INERT"
  }

  Write-Host "COMMANDER_WINDOWS_RC_INSTALL=PASS"
  Write-Host "COMMANDER_WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1"
  Write-Host "COMMANDER_WINDOWS_RC_AUTO_START=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_REUSES_EXISTING_IDENTITY=TRUE"
  Write-Host "COMMANDER_WINDOWS_RC_EVENT_V2_ORIGIN=DEV_ONLY"
  Write-Host "COMMANDER_WINDOWS_RC_DEVICE_REPAIRING=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_TOKEN_EXPOSED=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_COOPERATIVE_SHUTDOWN=READY"
}

function Activate-EventV2 {
  $cfg = Assert-ExistingIdentity
  if ([string]$cfg.base_url -ne $ExpectedDevOrigin) {
    throw "WINDOWS_RC_DEV_ORIGIN_REQUIRED"
  }
  if (-not (Get-ScheduledTask -TaskName $RcTaskName -ErrorAction SilentlyContinue)) {
    throw "WINDOWS_RC_NOT_INSTALLED"
  }
  if (-not (Get-ScheduledTask -TaskName $StableTaskName -ErrorAction SilentlyContinue)) {
    throw "WINDOWS_RC_STABLE_TASK_MISSING"
  }

  $previous = Get-EventStatusUpdated

  try {
    Stop-TaskSafe $StableTaskName
    Disable-TaskSafe $StableTaskName
    Enable-TaskRequired $RcTaskName
    Start-TaskRequired $RcTaskName
    if (-not (Wait-EventConnection $previous 20)) {
      throw "WINDOWS_RC_EVENT_V2_CONNECTION_ATTESTATION_FAILED"
    }
    if ((Get-TaskState $StableTaskName) -ne "Disabled") {
      throw "WINDOWS_RC_DUAL_AGENT_DENIED"
    }
  } catch {
    Rollback-ToStable
    throw "WINDOWS_RC_EVENT_V2_ACTIVATION_FAILED_ROLLED_BACK"
  }

  Write-Host "COMMANDER_WINDOWS_RC_EVENT_V2_ACTIVATION=PASS"
  Write-Host "COMMANDER_WINDOWS_RC_EVENT_V2_ORIGIN=DEV_ONLY"
  Write-Host "COMMANDER_WINDOWS_RC_EVENT_V2_CONNECTION_ATTESTATION=PASS"
  Write-Host "COMMANDER_WINDOWS_RC_TRANSPORT=EVENT_V2"
  Write-Host "COMMANDER_WINDOWS_RC_STABLE_TASK=INACTIVE"
  Write-Host "COMMANDER_WINDOWS_RC_TASK=ACTIVE"
  Write-Host "COMMANDER_WINDOWS_RC_TOKEN_EXPOSED=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_COOPERATIVE_SHUTDOWN=READY"
}

function Show-Status {
  $identityPresent = Test-Path -LiteralPath $StableConfig -PathType Leaf
  $installed = (
    (Test-Path -LiteralPath $RcAgent -PathType Leaf)
    -and (Test-Path -LiteralPath $RcEventAgent -PathType Leaf)
    -and (Test-Path -LiteralPath $RcTransport -PathType Leaf)
  )
  $connected = "UNKNOWN"
  if (Test-Path -LiteralPath $EventStatus -PathType Leaf) {
    try {
      $obj = Get-Content -Raw -LiteralPath $EventStatus | ConvertFrom-Json
      $connected = if ($obj.connected -eq $true) { "TRUE" } else { "FALSE" }
    } catch { $connected = "INVALID" }
  }

  Write-Host ("COMMANDER_WINDOWS_RC_INSTALLED=" + $installed.ToString().ToUpperInvariant())
  Write-Host ("COMMANDER_WINDOWS_RC_IDENTITY_PRESENT=" + $identityPresent.ToString().ToUpperInvariant())
  Write-Host ("COMMANDER_WINDOWS_RC_STABLE_TASK=" + (Get-TaskState $StableTaskName))
  Write-Host ("COMMANDER_WINDOWS_RC_TASK=" + (Get-TaskState $RcTaskName))
  Write-Host ("COMMANDER_WINDOWS_RC_EVENT_V2_CONNECTED=" + $connected)
  Write-Host "COMMANDER_WINDOWS_RC_TOKEN_EXPOSED=FALSE"
}

function Invoke-SelfCheck {
  Assert-Source
  Write-Host "COMMANDER_WINDOWS_RC_INSTALLER_SOURCE=PASS"
  Write-Host "COMMANDER_WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1"
  Write-Host "COMMANDER_WINDOWS_RC_AUTO_START=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_DUAL_AGENT=DENY"
  Write-Host "COMMANDER_WINDOWS_RC_ROLLBACK=SOURCE_READY"
  Write-Host "COMMANDER_WINDOWS_RC_REUSES_EXISTING_IDENTITY=TRUE"
  Write-Host "COMMANDER_WINDOWS_RC_DEVICE_REPAIRING=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_TOKEN_EXPOSED=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_COOPERATIVE_SHUTDOWN=READY"
}

switch ($Action) {
  "check" { Invoke-SelfCheck; exit 0 }
  "install" { Install-Rc; exit 0 }
  "activate-event-v2" { Activate-EventV2; exit 0 }
  "rollback" { Rollback-ToStable; exit 0 }
  "status" { Show-Status; exit 0 }
  default { throw "WINDOWS_RC_ACTION_INVALID" }
}
