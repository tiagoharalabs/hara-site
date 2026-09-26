param(
  [ValidateSet("POLL_V1","EVENT_V2")]
  [string]$Transport = $env:HARA_DEVICE_TRANSPORT_MODE
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Transport)) { $Transport = "POLL_V1" }
$Transport = $Transport.ToUpperInvariant()

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommanderRoot = Split-Path -Parent $Here
$StableAgent = Join-Path $CommanderRoot "public\agent\windows.ps1"
$EventV2Agent = Join-Path $CommanderRoot "experimental\event_v2_windows_agent.ps1"

function Invoke-SelfTest {
  if (-not (Test-Path -LiteralPath $StableAgent -PathType Leaf)) { throw "COMMANDER_WINDOWS_RC_STABLE_AGENT_MISSING" }
  if ($Transport -notin @("POLL_V1","EVENT_V2")) { throw "COMMANDER_WINDOWS_RC_TRANSPORT_INVALID" }

  Write-Host "COMMANDER_WINDOWS_RC_SOURCE=PASS"
  Write-Host "COMMANDER_WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1"
  Write-Host "COMMANDER_WINDOWS_RC_EVENT_V2=FAIL_CLOSED_UNTIL_IMPLEMENTED"
  Write-Host "COMMANDER_WINDOWS_RC_PUBLIC_RELEASE_MUTATION=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_REPAIRING=FALSE"
  Write-Host "COMMANDER_WINDOWS_RC_SERVICES_PROXY=FALSE"
}

if ($args -contains "--self-test") { Invoke-SelfTest; exit 0 }

if ($Transport -eq "POLL_V1") {
  & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $StableAgent
  exit $LASTEXITCODE
}

if ($Transport -eq "EVENT_V2") {
  if (-not (Test-Path -LiteralPath $EventV2Agent -PathType Leaf)) {
    throw "COMMANDER_WINDOWS_EVENT_V2_TRANSPORT_NOT_READY"
  }
  & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $EventV2Agent
  exit $LASTEXITCODE
}

throw "COMMANDER_WINDOWS_RC_TRANSPORT_INVALID"
