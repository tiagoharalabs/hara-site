param([string]$Action = "install")
$ErrorActionPreference = "Stop"
$Action = $Action.TrimStart("-").ToLowerInvariant()

$BaseUrl = if ($env:HARA_COMMANDER_URL) { $env:HARA_COMMANDER_URL.TrimEnd("/") } else { "https://commander.haralabs.com.br" }
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$Agent = Join-Path $Root "hara-commander-agent.ps1"
$Config = Join-Path $Root "device.json"
$TaskName = "HARA Commander Agent"

function Get-InstalledDevice {
  if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { return $null }
  try { return Get-Content -Raw -LiteralPath $Config | ConvertFrom-Json } catch { return $null }
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

if ($Action -eq "status") { Show-Status; exit 0 }
if ($Action -eq "update") {
  if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw "DEVICE_NOT_ENROLLED" }
  if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) { throw "AGENT_TASK_NOT_INSTALLED" }
  $cfg = Get-InstalledDevice
  if ($cfg -and $cfg.base_url) { $BaseUrl = ([string]$cfg.base_url).TrimEnd("/") }
  $tmp = $Agent + ".update"
  Invoke-WebRequest -Uri "$BaseUrl/agent/windows.ps1" -OutFile $tmp -UseBasicParsing -TimeoutSec 30
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($tmp,[ref]$tokens,[ref]$errors) | Out-Null
  if ($errors.Count -ne 0) { Remove-Item -Force $tmp; throw "AGENT_UPDATE_SYNTAX_INVALID" }
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Move-Item -Force $tmp $Agent
  Start-ScheduledTask -TaskName $TaskName
  Write-Host "HARA_COMMANDER_AGENT_UPDATE=PASS"
  Show-Status
  exit 0
}
if ($Action -eq "uninstall") {
  $cfg = Get-InstalledDevice
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host "HARA_COMMANDER_AGENT_UNINSTALL=PASS"
  if ($cfg -and $cfg.device_id) { Write-Host ("DEVICE_ID=" + [string]$cfg.device_id) }
  Write-Host "SERVER_DEVICE_REVOKE_REQUIRED=TRUE"
  Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
  exit 0
}
if ($Action -ne "install") { throw "Usage: windows.ps1 -Action install|status|update|uninstall" }
if (Test-Path -LiteralPath $Config -PathType Leaf) { throw "DEVICE_ALREADY_ENROLLED: use status, update, or uninstall." }

Write-Host "HARA Commander - Windows device pairing"
$SecurePairing = Read-Host "Pairing token" -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePairing)
try { $PairingToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr) }
if ([string]::IsNullOrWhiteSpace($PairingToken)) { throw "Pairing token cannot be empty." }

$DeviceName = $env:COMPUTERNAME
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
$Payload = @{ pairing_token=$PairingToken; device_name=$DeviceName; platform="WINDOWS"; architecture=$Architecture; agent_version="0.3.1" } | ConvertTo-Json -Compress
$Enroll = Invoke-RestMethod -Uri "$BaseUrl/api/device/enroll" -Method Post -ContentType "application/json" -Headers @{ Accept="application/json" } -Body $Payload -TimeoutSec 30
$PairingToken = $null
$SecurePairing.Dispose()
if (-not $Enroll.device_id -or -not $Enroll.device_token) { throw "DEVICE_ENROLLMENT_RESPONSE_INVALID" }

New-Item -ItemType Directory -Path $Root -Force | Out-Null
$EncryptedToken = ConvertTo-SecureString $Enroll.device_token -AsPlainText -Force | ConvertFrom-SecureString
$ConfigObject = @{ base_url=$BaseUrl; device_id=[string]$Enroll.device_id; encrypted_device_token=$EncryptedToken; architecture=$Architecture; agent_version="0.3.1" }
$ConfigObject | ConvertTo-Json | Set-Content -Path $Config -Encoding UTF8

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $Root /inheritance:r /grant:r "$Identity:(OI)(CI)F" | Out-Null
& icacls.exe $Config /inheritance:r /grant:r "$Identity:F" | Out-Null

Invoke-WebRequest -Uri "$BaseUrl/agent/windows.ps1" -OutFile $Agent -UseBasicParsing -TimeoutSec 30
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
if (-not $Task) { throw "HARA Commander Agent scheduled task was not created." }

Write-Host "HARA_COMMANDER_DEVICE_ENROLLMENT=PASS"
Write-Host "HARA_COMMANDER_AGENT_TASK=REGISTERED"
Write-Host "DEVICE_ID=$($Enroll.device_id)"
Write-Host "DEVICE_TOKEN_EXPOSED=FALSE"
