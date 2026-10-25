# DEV source review only. Called by the .56 guardian's native Job Object child.
# The adjacent wire module has no Agent, journal, tool or credential loader.
function Get-CommercialEventV2Entropy {
  $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
  try {$bytes=New-Object byte[] 4;$rng.GetBytes($bytes);return [BitConverter]::ToUInt32($bytes,0)/4294967296.0}
  finally {$rng.Dispose()}
}
function Wait-CommercialEventV2Retry([double]$Seconds) {
  $until=(Get-WindowsRelayNow)+$Seconds
  while((Get-WindowsRelayNow) -lt $until){
    $delay=[Math]::Min(15.0,$until-(Get-WindowsRelayNow))
    Write-WindowsRelayProgress 'HEARTBEAT_RETRY' @{delay=$delay;code='EVENT_V2_RECONNECT_WAIT'}
    Start-Sleep -Milliseconds ([int][Math]::Ceiling($delay*1000))
  }
}
function Get-CommercialEventV2ErrorCode($Failure) {
  $errorObject=$Failure.Exception
  for($depth=0;$null -ne $errorObject -and $depth -lt 8;$depth++){
    # PS 5.1 wraps asynchronous .NET failures. Inspect typed status only;
    # exception text may contain private origin/credential details.
    if($errorObject.Response -and $null -ne $errorObject.Response.StatusCode){
      $status=[int]$errorObject.Response.StatusCode
      if($status -ge 400 -and $status -le 599){return 'HTTP_'+$status}
    }
    $errorObject=$errorObject.InnerException
  }
  return Get-SafeErrorCode $Failure
}
function Invoke-CommercialEventV2Heartbeat($Cfg,[string]$Token,$Signal) {
  if(-not (Test-WindowsEventV2Dev $Cfg)){throw 'EVENT_V2_DEV_REQUIRED'}
  . (Join-Path $PSScriptRoot 'event_v2_wire.ps1') -ImportOnly
  $attempt=0;$lastLiveness=Get-WindowsRelayNow
  Wait-CommercialEventV2Retry (120.0*(Get-CommercialEventV2Entropy))
  while($true){
    $client=$null;$cts=New-Object Threading.CancellationTokenSource
    $started=Get-WindowsRelayNow
    try {
      Write-WindowsRelayProgress 'HEARTBEAT_ATTEMPT'
      $client=New-EventV2Client $Token
      Connect-EventV2Client $client (ConvertTo-EventV2Uri ([string]$Cfg.base_url)) $cts.Token
      $watchdog=New-EventV2Watchdog ((Get-WindowsRelayNow)-60.0)
      $receive=Start-EventV2Receive $client $cts.Token
      $confirmed=$false
      while($true){
        $now=Get-WindowsRelayNow
        [void](Step-EventV2Watchdog $watchdog $client $cts.Token $now)
        Write-WindowsRelayProgress 'HEARTBEAT_ATTEMPT'
        if($now-$lastLiveness -ge 21600){
          Wait-EventV2ProbeSend $watchdog $client $cts.Token
          Send-EventV2Liveness $client $cts.Token;$lastLiveness=Get-WindowsRelayNow
        }
        if(-not $receive.Task.Wait(500)){continue}
        $received=$receive.Task.GetAwaiter().GetResult()
        if($received.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close -and [int]$received.CloseStatus -eq 4003){
          Write-WindowsRelayProgress 'REVOKED' @{code='EVENT_V2_AUTHORIZATION_ENDED'};return
        }
        $text=Complete-EventV2Receive $receive
        if($text -ceq 'HARA_EVENT_V2_PROBE_ACK_V1'){
          Wait-EventV2ProbeSend $watchdog $client $cts.Token (Get-WindowsRelayNow)
          if(-not (Confirm-EventV2Watchdog $watchdog $text (Get-WindowsRelayNow))){throw 'EVENT_V2_UNSOLICITED_PROBE_ACK'}
          Write-WindowsRelayProgress 'HEARTBEAT_CONFIRMED'
          Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString('o')) -ErrorCode '' -ErrorAt '' | Out-Null
          if(-not $confirmed){[void]$Signal.Set();$confirmed=$true}
        } else {
          $wake=Parse-EventV2Wake $text
          if([string]$wake.type -cne 'CALL_AVAILABLE'){throw 'EVENT_V2_TRANSIENT_NOT_ADMITTED'}
          [void]$Signal.Set()
        }
        $receive=Start-EventV2Receive $client $cts.Token
      }
    } catch {
      $code=Get-CommercialEventV2ErrorCode $_
      # HTTP failures remain typed; a rejection is never permission to fall
      # back to V1 or treat an Upgrade/PID as confirmed health.
      if($code -cin @('HTTP_401','HTTP_403')){Write-WindowsRelayProgress 'REVOKED' @{code=$code};return}
      if((Get-WindowsRelayNow)-$started -ge 60){$attempt=0}
      $cap=[Math]::Min(120.0,60.0*[Math]::Pow(2.0,[Math]::Min(31,$attempt)))
      $delay=1.0+(Get-CommercialEventV2Entropy)*($cap-1.0);$attempt=[Math]::Min(31,$attempt+1)
      Write-WindowsRelayProgress 'HEARTBEAT_RETRY' @{delay=[Math]::Min(15.0,$delay);code=$code}
    } finally {
      $cts.Cancel();if($client){$client.Abort();$client.Dispose()};$cts.Dispose()
    }
    Wait-CommercialEventV2Retry $delay
  }
}
