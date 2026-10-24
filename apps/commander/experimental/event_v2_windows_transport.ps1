param([switch]$SelfTest,[switch]$ImportOnly)

$ErrorActionPreference = "Stop"
$MaxWakeEventBytes = 4096
$MaxTransientRequestBytes = 163840
$MaxTransientResultBytes = 327680
$MaxEventBytes = $MaxTransientRequestBytes
$KeepAliveSeconds = 60

function ConvertTo-EventV2Uri([string]$BaseUrl) {
  if ([string]::IsNullOrWhiteSpace($BaseUrl)) { throw "WINDOWS_EVENT_V2_ORIGIN_INVALID" }
  $uri = [Uri]$BaseUrl
  if ($uri.Scheme -ne "https") { throw "WINDOWS_EVENT_V2_HTTPS_REQUIRED" }
  if (-not [string]::IsNullOrEmpty($uri.Query) -or -not [string]::IsNullOrEmpty($uri.Fragment)) {
    throw "WINDOWS_EVENT_V2_ORIGIN_INVALID"
  }
  $builder = [UriBuilder]$uri
  $builder.Scheme = "wss"
  $builder.Port = -1
  $builder.Path = "/api/device/channel"
  $builder.Query = ""
  $builder.Fragment = ""
  return $builder.Uri
}

function New-EventV2Client([string]$DeviceToken) {
  if ([string]::IsNullOrWhiteSpace($DeviceToken) -or $DeviceToken.Length -lt 32) {
    throw "WINDOWS_EVENT_V2_DEVICE_TOKEN_INVALID"
  }
  $client = [System.Net.WebSockets.ClientWebSocket]::new()
  $client.Options.SetRequestHeader("Authorization", ("Bearer " + $DeviceToken))
  $client.Options.KeepAliveInterval = [TimeSpan]::FromSeconds($KeepAliveSeconds)
  return $client
}

function Connect-EventV2Client($Client,[Uri]$Uri,[Threading.CancellationToken]$CancellationToken) {
  if ($Uri.Scheme -ne "wss") { throw "WINDOWS_EVENT_V2_WSS_REQUIRED" }
  $Client.ConnectAsync($Uri,$CancellationToken).GetAwaiter().GetResult()
  if ($Client.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
    throw "WINDOWS_EVENT_V2_CONNECT_FAILED"
  }
}

function Start-EventV2Receive($Client,[Threading.CancellationToken]$CancellationToken) {
  $buffer = New-Object byte[] $MaxEventBytes
  $segment = [ArraySegment[byte]]::new($buffer)
  return [pscustomobject]@{
    Buffer = $buffer
    Task = $Client.ReceiveAsync($segment,$CancellationToken)
  }
}

function Complete-EventV2Receive($Receive) {
  $result = $Receive.Task.GetAwaiter().GetResult()
  if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
    throw "WINDOWS_EVENT_V2_SERVER_CLOSED"
  }
  if ($result.MessageType -ne [System.Net.WebSockets.WebSocketMessageType]::Text) {
    throw "WINDOWS_EVENT_V2_MESSAGE_TYPE_DENIED"
  }
  if (-not $result.EndOfMessage) { throw "WINDOWS_EVENT_V2_FRAGMENTATION_DENIED" }
  if ($result.Count -lt 1 -or $result.Count -gt $MaxEventBytes) {
    throw "WINDOWS_EVENT_V2_MESSAGE_SIZE_INVALID"
  }
  return [Text.Encoding]::UTF8.GetString($Receive.Buffer,0,$result.Count)
}

function Receive-EventV2Text($Client,[Threading.CancellationToken]$CancellationToken,$ShutdownTask=$null) {
  $receive = Start-EventV2Receive $Client $CancellationToken
  if ($null -ne $ShutdownTask) {
    $waitTasks = [Threading.Tasks.Task[]]@([Threading.Tasks.Task]$receive.Task,[Threading.Tasks.Task]$ShutdownTask)
    $completed = [Threading.Tasks.Task]::WaitAny($waitTasks)
    if ($completed -eq 1) { throw "WINDOWS_EVENT_V2_LOCAL_SHUTDOWN_REQUESTED" }
  }
  return Complete-EventV2Receive $receive
}

function Send-EventV2Liveness($Client,[Threading.CancellationToken]$CancellationToken) {
  if ($Client.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
    throw "WINDOWS_EVENT_V2_LIVENESS_SOCKET_NOT_OPEN"
  }
  $payload = '{"schema":"hara.commander-device-event.v2","type":"LIVENESS"}'
  $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
  if ($bytes.Length -gt $MaxWakeEventBytes) { throw "WINDOWS_EVENT_V2_LIVENESS_SIZE_INVALID" }
  $segment = [ArraySegment[byte]]::new($bytes)
  $Client.SendAsync(
    $segment,
    [System.Net.WebSockets.WebSocketMessageType]::Text,
    $true,
    $CancellationToken
  ).GetAwaiter().GetResult()
}

function Test-EventV2Identifier([string]$Value,[int]$MaxLength,[string]$Code) {
  if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Length -gt $MaxLength -or $Value -notmatch "^[A-Za-z0-9_.:-]+$") {
    throw $Code
  }
  return $Value
}

function Parse-EventV2Wake([string]$Text) {
  $bytes = [Text.Encoding]::UTF8.GetByteCount($Text)
  if ($bytes -gt $MaxTransientRequestBytes) { throw "WINDOWS_EVENT_V2_MESSAGE_SIZE_INVALID" }
  try { $obj = $Text | ConvertFrom-Json } catch { throw "WINDOWS_EVENT_V2_EVENT_INVALID" }
  if ([string]$obj.schema -ne "hara.commander-device-event.v2") { throw "WINDOWS_EVENT_V2_SCHEMA_DENIED" }

  $type = [string]$obj.type
  $names = @($obj.PSObject.Properties.Name | Sort-Object)
  if ($type -eq "CALL_AVAILABLE") {
    if ($bytes -gt $MaxWakeEventBytes) { throw "WINDOWS_EVENT_V2_MESSAGE_SIZE_INVALID" }
    if (($names -join ",") -ne "call_id,schema,type") { throw "WINDOWS_EVENT_V2_EVENT_INVALID" }
    $callId = Test-EventV2Identifier ([string]$obj.call_id) 180 "WINDOWS_EVENT_V2_CALL_ID_INVALID"
    return [pscustomobject]@{ type="CALL_AVAILABLE"; call_id=$callId }
  }

  if ($type -eq "CALL_TRANSIENT") {
    if (($names -join ",") -ne "call_id,execution_mode,payload,request_id,schema,tool_id,type") {
      throw "WINDOWS_EVENT_V2_EVENT_INVALID"
    }
    if ($null -eq $obj.payload -or $obj.payload -is [string] -or $obj.payload -is [array]) {
      throw "WINDOWS_EVENT_V2_TRANSIENT_PAYLOAD_INVALID"
    }
    $callId = Test-EventV2Identifier ([string]$obj.call_id) 180 "WINDOWS_EVENT_V2_CALL_ID_INVALID"
    $requestId = Test-EventV2Identifier ([string]$obj.request_id) 220 "WINDOWS_EVENT_V2_REQUEST_ID_INVALID"
    $toolId = Test-EventV2Identifier ([string]$obj.tool_id) 120 "WINDOWS_EVENT_V2_TOOL_ID_INVALID"
    $executionMode = ([string]$obj.execution_mode).Trim().ToUpperInvariant()
    if ($executionMode -notin @("EXECUTE_OR_REPLAY","REPLAY_ONLY")) {
      throw "WINDOWS_EVENT_V2_TRANSIENT_EXECUTION_MODE_INVALID"
    }
    return [pscustomobject]@{
      schema = "hara.commander-device-event.v2"
      type = "CALL_TRANSIENT"
      call_id = $callId
      request_id = $requestId
      tool_id = $toolId
      execution_mode = $executionMode
      payload = $obj.payload
    }
  }

  throw "WINDOWS_EVENT_V2_EVENT_TYPE_DENIED"
}

function Send-EventV2TransientResult(
  $Client,
  [Threading.CancellationToken]$CancellationToken,
  $Payload
) {
  if ($Client.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
    throw "WINDOWS_EVENT_V2_TRANSIENT_SOCKET_NOT_OPEN"
  }
  $json = $Payload | ConvertTo-Json -Depth 16 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  if ($bytes.Length -gt $MaxTransientResultBytes) {
    throw "WINDOWS_EVENT_V2_TRANSIENT_RESULT_TOO_LARGE"
  }
  $segment = [ArraySegment[byte]]::new($bytes)
  $Client.SendAsync(
    $segment,
    [System.Net.WebSockets.WebSocketMessageType]::Text,
    $true,
    $CancellationToken
  ).GetAwaiter().GetResult()
}


function Close-EventV2Client($Client) {
  if ($null -eq $Client) { return }
  try {
    if ($Client.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
      $cts = [Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(3))
      try {
        $Client.CloseAsync(
          [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
          "shutdown",
          $cts.Token
        ).GetAwaiter().GetResult()
      } finally {
        $cts.Dispose()
      }
    }
  } catch {
    try { $Client.Abort() } catch {}
  } finally {
    $Client.Dispose()
  }
}

function Invoke-TransportSelfTest {
  $uri = ConvertTo-EventV2Uri "https://commander.example.invalid"
  if ($uri.AbsoluteUri -ne "wss://commander.example.invalid/api/device/channel") {
    throw "WINDOWS_EVENT_V2_URI_SELFTEST_FAILED"
  }

  $denied=$false
  try { ConvertTo-EventV2Uri "http://commander.example.invalid" | Out-Null }
  catch { if ([string]$_.Exception.Message -eq "WINDOWS_EVENT_V2_HTTPS_REQUIRED") { $denied=$true } }
  if (-not $denied) { throw "WINDOWS_EVENT_V2_HTTP_NOT_DENIED" }

  $wake = Parse-EventV2Wake '{"schema":"hara.commander-device-event.v2","type":"CALL_AVAILABLE","call_id":"HARA-CALL-test"}'
  if ($wake.call_id -ne "HARA-CALL-test") { throw "WINDOWS_EVENT_V2_WAKE_SELFTEST_FAILED" }

  $contentDenied=$false
  try {
    Parse-EventV2Wake '{"schema":"hara.commander-device-event.v2","type":"CALL_AVAILABLE","call_id":"HARA-CALL-test","payload":{"command":"deny"}}' | Out-Null
  } catch {
    if ([string]$_.Exception.Message -eq "WINDOWS_EVENT_V2_EVENT_INVALID") { $contentDenied=$true }
  }
  if (-not $contentDenied) { throw "WINDOWS_EVENT_V2_CONTENT_EVENT_NOT_DENIED" }

  $transient = Parse-EventV2Wake '{"schema":"hara.commander-device-event.v2","type":"CALL_TRANSIENT","call_id":"HARA-TRANSIENT-test","request_id":"REQ-test","tool_id":"hara.health","execution_mode":"EXECUTE_OR_REPLAY","payload":{}}'
  if ([string]$transient.type -ne "CALL_TRANSIENT") { throw "WINDOWS_EVENT_V2_TRANSIENT_PARSE_FAILED" }
  if ([string]$transient.request_id -ne "REQ-test") { throw "WINDOWS_EVENT_V2_TRANSIENT_PARSE_FAILED" }
  if ([string]$transient.tool_id -ne "hara.health") { throw "WINDOWS_EVENT_V2_TRANSIENT_PARSE_FAILED" }

  Write-Host "COMMANDER_WINDOWS_EVENT_V2_TRANSPORT_SOURCE=PASS"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_WSS_ONLY=TRUE"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_KEEPALIVE_SECONDS=60"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_MAX_WAKE_BYTES=4096"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_MAX_TRANSIENT_REQUEST_BYTES=163840"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_MAX_TRANSIENT_RESULT_BYTES=327680"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_DURABLE_LIVENESS_FRAME=READY"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_CONTENT_BEARING_WAKE=DENIED"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_TRANSIENT_FRAME=SOURCE_READY"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_TOKEN_OUTPUT=ABSENT"
}

if ($ImportOnly) { return }

if ($SelfTest -or ($args -contains "--self-test")) {
  Invoke-TransportSelfTest
  exit 0
}

throw "SOURCE_ONLY_USE_WINDOWS_EVENT_V2_AGENT"
