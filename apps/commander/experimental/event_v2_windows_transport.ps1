param([switch]$SelfTest,[switch]$ImportOnly)

$ErrorActionPreference = "Stop"
$MaxEventBytes = 4096
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

function Receive-EventV2Text($Client,[Threading.CancellationToken]$CancellationToken) {
  $buffer = New-Object byte[] $MaxEventBytes
  $segment = [ArraySegment[byte]]::new($buffer)
  $result = $Client.ReceiveAsync($segment,$CancellationToken).GetAwaiter().GetResult()
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
  return [Text.Encoding]::UTF8.GetString($buffer,0,$result.Count)
}

function Parse-EventV2Wake([string]$Text) {
  try { $obj = $Text | ConvertFrom-Json } catch { throw "WINDOWS_EVENT_V2_EVENT_INVALID" }
  $names = @($obj.PSObject.Properties.Name | Sort-Object)
  if (($names -join ",") -ne "call_id,schema,type") { throw "WINDOWS_EVENT_V2_EVENT_INVALID" }
  if ([string]$obj.schema -ne "hara.commander-device-event.v2") { throw "WINDOWS_EVENT_V2_SCHEMA_DENIED" }
  if ([string]$obj.type -ne "CALL_AVAILABLE") { throw "WINDOWS_EVENT_V2_EVENT_TYPE_DENIED" }
  $callId = [string]$obj.call_id
  if ([string]::IsNullOrWhiteSpace($callId) -or $callId.Length -gt 180 -or $callId -notmatch "^[A-Za-z0-9_.:-]+$") {
    throw "WINDOWS_EVENT_V2_CALL_ID_INVALID"
  }
  return [pscustomobject]@{ type="CALL_AVAILABLE"; call_id=$callId }
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

  Write-Host "COMMANDER_WINDOWS_EVENT_V2_TRANSPORT_SOURCE=PASS"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_WSS_ONLY=TRUE"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_KEEPALIVE_SECONDS=60"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_MAX_EVENT_BYTES=4096"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_CONTENT_BEARING_WAKE=DENIED"
  Write-Host "COMMANDER_WINDOWS_EVENT_V2_TOKEN_OUTPUT=ABSENT"
}

if ($ImportOnly) { return }

if ($SelfTest -or ($args -contains "--self-test")) {
  Invoke-TransportSelfTest
  exit 0
}

throw "SOURCE_ONLY_USE_WINDOWS_EVENT_V2_AGENT"
