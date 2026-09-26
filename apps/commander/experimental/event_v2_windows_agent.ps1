param([switch]$SelfTest)

$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$StableRoot = Join-Path $env:LOCALAPPDATA "HARA Commander"
$StableAgent = Join-Path $StableRoot "hara-commander-agent.ps1"
$TransportPath = Join-Path $Here "event_v2_windows_transport.ps1"

$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$ConfigPath = Join-Path $Root "device.json"
$ReceiptDir = Join-Path $Root "receipts"
$RuntimeStatus = Join-Path $Root "runtime-status.json"
$EventStatus = Join-Path $Root "event-v2-status.json"
$AgentVersion = "0.3.7"
$FunctionId = "device.info"
$OperationalAuthority = "HARA_COMMANDER"
$ExecutionAuthority = "HARA_COMMANDER_AGENT"
$TransportMode = "EVENT_V2"
$MaxDrainCalls = 8
$StableConnectionSeconds = 60
$ReconnectBaseSeconds = 10
$ReconnectMaxSeconds = 15
$DurableLivenessSeconds = 21600

function Import-StableAgentFunctions {
  if (-not (Test-Path -LiteralPath $StableAgent -PathType Leaf)) {
    throw "WINDOWS_EVENT_V2_STABLE_AGENT_MISSING"
  }

  $tokens = $null
  $errors = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $StableAgent,
    [ref]$tokens,
    [ref]$errors
  )
  if ($errors.Count -gt 0) { throw "WINDOWS_EVENT_V2_STABLE_AGENT_PARSE_FAILED" }

  $required = @(
    "Get-PlainText",
    "Get-SafeErrorCode",
    "Set-RuntimeStatus",
    "Try-SetRuntimeStatus",
    "Get-Catalog",
    "Get-Description",
    "Invoke-LocalFunction",
    "Get-Utf8Sha256",
    "Get-Receipt",
    "Send-Json",
    "Complete-Call"
  )

  $functions = @{}
  foreach ($node in $ast.FindAll({
    param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst]
  }, $true)) {
    if ($required -contains $node.Name) {
      $functions[$node.Name] = $node.Extent.Text
    }
  }

  foreach ($name in $required) {
    if (-not $functions.ContainsKey($name)) {
      throw ("WINDOWS_EVENT_V2_BASELINE_FUNCTION_MISSING:" + $name)
    }
    Invoke-Expression $functions[$name]
  }
}

Import-StableAgentFunctions
. $TransportPath -ImportOnly

function Get-EventV2Config {
  if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "DEVICE_CONFIG_INVALID"
  }
  $cfg = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
  if (
    -not $cfg.base_url
    -or -not $cfg.device_id
    -or -not $cfg.encrypted_device_token
    -or -not $cfg.architecture
  ) { throw "DEVICE_CONFIG_INVALID" }
  return $cfg
}

function Get-DeviceToken($Cfg) {
  $secure = ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
  $plain = Get-PlainText $secure
  if ([string]::IsNullOrWhiteSpace($plain)) { throw "DEVICE_CONFIG_INVALID" }
  return $plain
}

function Set-EventV2Status(
  [bool]$Connected,
  [string]$ConnectedAtUtc=$null,
  [string]$DisconnectedAtUtc=$null,
  [string]$ErrorCode=$null
) {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $existing = $null
  if (Test-Path -LiteralPath $EventStatus -PathType Leaf) {
    try { $existing = Get-Content -Raw -LiteralPath $EventStatus | ConvertFrom-Json }
    catch { $existing = $null }
  }
  $payload = [ordered]@{
    schema = "hara.commander-event-v2-runtime-status.v1"
    transport_mode = $TransportMode
    connected = $Connected
    connected_at_utc = if ($ConnectedAtUtc) { $ConnectedAtUtc } elseif ($existing) { [string]$existing.connected_at_utc } else { $null }
    disconnected_at_utc = if ($DisconnectedAtUtc) { $DisconnectedAtUtc } elseif ($existing) { [string]$existing.disconnected_at_utc } else { $null }
    last_error_code = $ErrorCode
    updated_at_utc = [DateTime]::UtcNow.ToString("o")
  }
  $tmp = $EventStatus + ".tmp"
  $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $tmp -Encoding UTF8
  Move-Item -Force -LiteralPath $tmp -Destination $EventStatus
}

function Get-DeviceInfo($Cfg) {
  return @{
    device_id = [string]$Cfg.device_id
    hostname = $env:COMPUTERNAME
    platform = "WINDOWS"
    platform_release = [Environment]::OSVersion.VersionString
    architecture = [string]$Cfg.architecture
    powershell_version = $PSVersionTable.PSVersion.ToString()
    agent_version = $AgentVersion
    tunnel_mode = $TransportMode
  }
}

function New-Receipt($Cfg,$Call,[string]$State,$Result) {
  New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
  $resultBinding = "NONE"
  $resultStdoutSha256 = $null
  if ([string]$Call.tool_id -eq "hara.functions.invoke") {
    $resultBinding = "STDOUT_SHA256_V1"
    $resultStdoutSha256 = Get-Utf8Sha256 ([string]$Result.stdout)
  }

  $receipt = [ordered]@{
    schema = "hara.commander-device-receipt.v1"
    request_id = [string]$Call.request_id
    device_id = [string]$Cfg.device_id
    tool_id = [string]$Call.tool_id
    function_id_if_any = if ($Call.payload) { [string]$Call.payload.function_id } else { $null }
    transport_mode = $TransportMode
    operational_authority = $OperationalAuthority
    execution_authority = $ExecutionAuthority
    mutation_class = "READ_ONLY_OR_NONE_V1"
    state = $State
    payload_values_persisted = $false
    result_binding = $resultBinding
    result_stdout_sha256 = $resultStdoutSha256
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
  }

  $json = $receipt | ConvertTo-Json -Depth 6 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  $sha = [Security.Cryptography.SHA256]::Create()
  try { $hash = ($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
  finally { $sha.Dispose() }
  [IO.File]::WriteAllBytes((Join-Path $ReceiptDir ($hash + ".json")),$bytes)
  return $hash
}

function New-ToolResponse($Result,$Blocker=$null,[string]$ReceiptSha=$null) {
  $response = @{
    state = if ($null -eq $Blocker) { "PASS" } else { "DENIED" }
    operational_authority = $OperationalAuthority
    runtime_authority_from_chatgpt = $false
    mutation_performed = $false
    result = $Result
    blocker = $Blocker
  }
  if ($ReceiptSha) { $response.bridge_receipt_sha256 = $ReceiptSha }
  return $response
}

function Invoke-Tool($Cfg,$Call) {
  $tool = [string]$Call.tool_id
  $payload = $Call.payload

  if ($tool -eq "hara.health") {
    $result = @{
      commander_edge_state = "PASS"
      device_channel_state = "PASS"
      registered_function_count = 1
      executable_function_count = 1
      authority = $OperationalAuthority
      device = Get-DeviceInfo $Cfg
    }
  } elseif ($tool -eq "hara.functions.list") {
    $result = Get-Catalog
  } elseif ($tool -eq "hara.functions.describe") {
    $result = Get-Description ([string]$payload.function_id)
  } elseif ($tool -eq "hara.functions.invoke") {
    $result = Invoke-LocalFunction $Cfg ([string]$payload.function_id) $payload.arguments
  } elseif ($tool -eq "hara.receipts.get") {
    return New-ToolResponse (Get-Receipt ([string]$payload.receipt_id_or_sha256))
  } else {
    throw "TOOL_ID_INVALID"
  }

  $receipt = New-Receipt $Cfg $Call "PASS" $result
  return New-ToolResponse $result $null $receipt
}

function Get-NextDurableCall($Cfg,[string]$Token) {
  try {
    return Send-Json "$($Cfg.base_url)/api/device/calls/next" $Token @{} 25
  } catch {
    try {
      if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 204) {
        return $null
      }
    } catch {}
    throw
  }
}

function Invoke-DurableDrain($Cfg,[string]$Token) {
  $drained = 0
  while ($drained -lt $MaxDrainCalls) {
    $call = Get-NextDurableCall $Cfg $Token
    if ($null -eq $call -or -not $call.call_id) { break }

    try {
      $result = Invoke-Tool $Cfg $call
      Complete-Call $Cfg $Token $call "COMPLETED" $result
    } catch {
      $code = Get-SafeErrorCode $_
      $denied = New-ToolResponse @{} @{code=$code}
      Complete-Call $Cfg $Token $call "FAILED" $denied $code
    }
    $drained += 1
  }
  return $drained
}

function Get-ReconnectDelaySeconds([int]$Attempt) {
  if ($Attempt -lt 0) { throw "WINDOWS_EVENT_V2_RECONNECT_ATTEMPT_INVALID" }
  $cap = [Math]::Min($ReconnectMaxSeconds, $ReconnectBaseSeconds * [Math]::Pow(2,[Math]::Min($Attempt,20)))
  return ([Security.Cryptography.RandomNumberGenerator]::GetInt32(0,1000000) / 1000000.0) * $cap
}

function Invoke-ConnectedSession($Cfg,[string]$Token) {
  $uri = ConvertTo-EventV2Uri ([string]$Cfg.base_url)
  $client = New-EventV2Client $Token
  $cts = [Threading.CancellationTokenSource]::new()
  $connectedAt = [DateTime]::UtcNow
  try {
    Connect-EventV2Client $client $uri $cts.Token
    Set-EventV2Status -Connected $true -ConnectedAtUtc $connectedAt.ToString("o")
    Invoke-DurableDrain $Cfg $Token | Out-Null

    while ($true) {
      $text = Receive-EventV2Text $client $cts.Token
      $wake = Parse-EventV2Wake $text
      if ([string]$wake.type -eq "CALL_AVAILABLE") {
        # The event call_id is never execution authority. It only wakes one
        # bounded reconciliation read from durable D1 call truth.
        Invoke-DurableDrain $Cfg $Token | Out-Null
      }
    }
  } finally {
    Close-EventV2Client $client
    $cts.Dispose()
    Set-EventV2Status -Connected $false -DisconnectedAtUtc ([DateTime]::UtcNow.ToString("o")
    )
  }
}

function Invoke-AgentSelfTest {
  if ($MaxDrainCalls -ne 8) { throw "WINDOWS_EVENT_V2_DRAIN_BOUND_INVALID" }
  if ($ReconnectBaseSeconds -ne 10) { throw "WINDOWS_EVENT_V2_RECONNECT_BASE_INVALID" }
  if ($ReconnectMaxSeconds -ne 15) { throw "WINDOWS_EVENT_V2_RECONNECT_MAX_INVALID" }
  if ($DurableLivenessSeconds -ne 21600) { throw "WINDOWS_EVENT_V2_LIVENESS_INVALID" }

  $cfg = [pscustomobject]@{device_id="windows-event-v2-selftest";architecture="test"}
  $info = Get-DeviceInfo $cfg
  if ([string]$info.tunnel_mode -ne "EVENT_V2") { throw "WINDOWS_EVENT_V2_DEVICE_INFO_FAILED" }

  $health = Invoke-Tool $cfg ([pscustomobject]@{
    call_id="c1";request_id="r1";tool_id="hara.health";payload=[pscustomobject]@{}
  })
  if ([string]$health.operational_authority -ne "HARA_COMMANDER") {
    throw "WINDOWS_EVENT_V2_AUTHORITY_FAILED"
  }

  $blocked = $false
  try {
    Invoke-Tool $cfg ([pscustomobject]@{
      call_id="c2";request_id="r2";tool_id="shell.run";payload=[pscustomobject]@{}
    }) | Out-Null
  } catch {
    if ([string]$_.Exception.Message -eq "TOOL_ID_INVALID") { $blocked = $true }
  }
  if (-not $blocked) { throw "WINDOWS_EVENT_V2_ARBITRARY_TOOL_ALLOWED" }

  Write-Host "COMMANDER_WINDOWS_EVENT_V2_AGENT_ADAPTER=PASS"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_AUTHORITY=HARA_COMMANDER"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_TRANSPORT=EVENT_V2"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_RECONCILIATION_DRAIN=BOUNDED_8"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_IDLE_HTTP_POLLING=ABSENT"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_HTTP_HEARTBEAT=ABSENT"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_SERVICES_PROXY=FALSE"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_PUBLIC_AGENT_MUTATION=FALSE"
}

if ($SelfTest -or ($args -contains "--self-test")) {
  Invoke-AgentSelfTest
  exit 0
}

$attempt = 0
while ($true) {
  $started = [DateTime]::UtcNow
  try {
    $cfg = Get-EventV2Config
    $token = Get-DeviceToken $cfg
    Invoke-ConnectedSession $cfg $token
    $connectedSeconds = ([DateTime]::UtcNow - $started).TotalSeconds
  } catch {
    $connectedSeconds = ([DateTime]::UtcNow - $started).TotalSeconds
    $code = Get-SafeErrorCode $_
    Try-SetRuntimeStatus -ErrorCode $code -ErrorAt ([DateTime]::UtcNow.ToString("o")) | Out-Null
    try { Set-EventV2Status -Connected $false -DisconnectedAtUtc ([DateTime]::UtcNow.ToString("o")) -ErrorCode $code } catch {}
  } finally {
    $token = $null
  }

  if ($connectedSeconds -ge $StableConnectionSeconds) { $attempt = 0 }
  else { $attempt = [Math]::Min($attempt + 1,31) }

  $delay = Get-ReconnectDelaySeconds $attempt
  Start-Sleep -Milliseconds ([int][Math]::Ceiling($delay * 1000))
}
