$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$ConfigPath = Join-Path $Root "device.json"
$ReceiptDir = Join-Path $Root "receipts"
$RuntimeStatus = Join-Path $Root "runtime-status.json"
$AgentVersion = "0.3.5"
$FunctionId = "device.info"

function Get-PlainText([Security.SecureString]$SecureValue) {
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-SafeErrorCode($ErrorRecord) {
  try {
    if ($ErrorRecord.Exception.Response -and $ErrorRecord.Exception.Response.StatusCode) {
      return "HTTP_" + [int]$ErrorRecord.Exception.Response.StatusCode
    }
  } catch {}
  $raw=[string]$ErrorRecord.Exception.Message
  if ($raw -match "^[A-Z][A-Z0-9_]{0,79}$") { return $raw }
  $name=[string]$ErrorRecord.Exception.GetType().Name
  $normalized=($name -replace "[^A-Za-z0-9_]", "_").ToUpperInvariant()
  if ($normalized -match "^[A-Z][A-Z0-9_]{0,79}$") { return $normalized }
  return "RUNTIME_ERROR"
}
function Set-RuntimeStatus([string]$HeartbeatAt=$null,[string]$ErrorCode=$null,[string]$ErrorAt=$null,[string]$StartedAt=$null) {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $existing=$null
  if (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf) {
    try { $existing=Get-Content -Raw -LiteralPath $RuntimeStatus | ConvertFrom-Json } catch { $existing=$null }
  }
  $lastHeartbeat=if ($null -ne $HeartbeatAt) {$HeartbeatAt} elseif ($existing) {[string]$existing.last_successful_heartbeat_at_utc} else {$null}
  $startedAt=if ($null -ne $StartedAt) {$StartedAt} elseif ($existing) {[string]$existing.started_at_utc} else {$null}
  $payload=[ordered]@{
    schema="hara.commander-agent-runtime-status.v1"
    agent_version=$AgentVersion
    started_at_utc=$startedAt
    last_successful_heartbeat_at_utc=$lastHeartbeat
    last_runtime_error_code=$ErrorCode
    last_runtime_error_at_utc=$ErrorAt
    updated_at_utc=[DateTime]::UtcNow.ToString("o")
  }
  $tmp=$RuntimeStatus+".tmp"
  $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $tmp -Encoding UTF8
  Move-Item -Force -LiteralPath $tmp -Destination $RuntimeStatus
}

function Try-SetRuntimeStatus([string]$HeartbeatAt=$null,[string]$ErrorCode=$null,[string]$ErrorAt=$null,[string]$StartedAt=$null) {
  try {
    Set-RuntimeStatus -HeartbeatAt $HeartbeatAt -ErrorCode $ErrorCode -ErrorAt $ErrorAt -StartedAt $StartedAt
    return $true
  } catch {
    return $false
  }
}

function Get-DeviceInfo($Cfg) {
  return @{
    device_id=[string]$Cfg.device_id
    hostname=$env:COMPUTERNAME
    platform="WINDOWS"
    platform_release=[Environment]::OSVersion.VersionString
    architecture=[string]$Cfg.architecture
    powershell_version=$PSVersionTable.PSVersion.ToString()
    agent_version=$AgentVersion
    tunnel_mode="OUTBOUND_RELAY"
  }
}
function Get-Catalog {
  return @{
    registered_function_count=1
    executable_function_count=1
    active_function_count=1
    domains=@("DEVICE")
    functions=@(@{function_id=$FunctionId;state="ACTIVE"})
  }
}

function Get-Description([string]$Id) {
  if ($Id -ne $FunctionId) { throw "UNKNOWN_FUNCTION_ID" }
  return @{
    function_id=$FunctionId
    state="ACTIVE"
    IDENTITY=@{domain="DEVICE"}
    PURPOSE=@{description_pt_br="Consulta informações básicas e não sensíveis deste computador."}
    EXECUTION_SEMANTICS=@{risk_class="READ_ONLY";change_intent_required=$false}
    AUTHORITY=@{risk_class="READ_ONLY";change_intent_required=$false;fail_closed=$true}
    FAILURE_ROLLBACK=@{fail_closed=$true}
  }
}

function Invoke-LocalFunction($Cfg,[string]$Id,$Arguments) {
  if ($Id -ne $FunctionId) { throw "UNKNOWN_FUNCTION_ID" }
  if ($null -eq $Arguments -or $null -eq $Arguments.argv -or @($Arguments.argv).Count -ne 0) {
    throw "FUNCTION_ARGUMENTS_DENIED"
  }
  $info = Get-DeviceInfo $Cfg
  return @{
    function_id=$FunctionId
    risk_class="READ_ONLY"
    process_exit_code=0
    stdout=($info | ConvertTo-Json -Depth 5 -Compress)
    domain_success_inferred=$false
  }
}
function New-Receipt($Cfg,$Call,[string]$State) {
  New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
  $receipt = [ordered]@{
    schema="hara.commander-device-receipt.v1"
    request_id=[string]$Call.request_id
    device_id=[string]$Cfg.device_id
    tool_id=[string]$Call.tool_id
    function_id_if_any=if ($Call.payload) {[string]$Call.payload.function_id} else {$null}
    transport_mode="OUTBOUND_RELAY"
    operational_authority="HARA_SERVICES"
    execution_authority="HARA_COMMANDER_AGENT"
    mutation_class="READ_ONLY_OR_NONE_V1"
    state=$State
    payload_values_persisted=$false
    completed_at_utc=[DateTime]::UtcNow.ToString("o")
  }
  $json = $receipt | ConvertTo-Json -Depth 6 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  $sha = [Security.Cryptography.SHA256]::Create()
  try { $hash = ($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
  finally { $sha.Dispose() }
  [IO.File]::WriteAllBytes((Join-Path $ReceiptDir ($hash+".json")),$bytes)
  return $hash
}

function Get-Receipt([string]$Identifier) {
  $value=$Identifier.ToLowerInvariant()
  if ($value -notmatch "^[0-9a-f]{64}$") { throw "RECEIPT_IDENTIFIER_INVALID" }
  $path=Join-Path $ReceiptDir ($value+".json")
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "RECEIPT_NOT_FOUND" }
  return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
}
function Invoke-Tool($Cfg,$Call) {
  $tool=[string]$Call.tool_id
  $payload=$Call.payload
  if ($tool -eq "hara.health") {
    $result=@{
      services_bridge_state="PASS"; hara_services_state="PASS"
      registered_function_count=1; executable_function_count=1
      authority="HARA_SERVICES"; device=(Get-DeviceInfo $Cfg)
    }
  } elseif ($tool -eq "hara.functions.list") {
    $result=Get-Catalog
  } elseif ($tool -eq "hara.functions.describe") {
    $result=Get-Description ([string]$payload.function_id)
  } elseif ($tool -eq "hara.functions.invoke") {
    $result=Invoke-LocalFunction $Cfg ([string]$payload.function_id) $payload.arguments
  } elseif ($tool -eq "hara.receipts.get") {
    $result=Get-Receipt ([string]$payload.receipt_id_or_sha256)
    return @{
      state="PASS";operational_authority="HARA_SERVICES"
      runtime_authority_from_chatgpt=$false;mutation_performed=$false
      result=$result;blocker=$null
    }
  } else { throw "TOOL_ID_INVALID" }

  $receipt=New-Receipt $Cfg $Call "PASS"
  return @{
    state="PASS";operational_authority="HARA_SERVICES"
    runtime_authority_from_chatgpt=$false;mutation_performed=$false
    result=$result;blocker=$null;bridge_receipt_sha256=$receipt
  }
}
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  $headers=@{Accept="application/json";Authorization="Bearer $Token"}
  $json=$Body | ConvertTo-Json -Depth 10 -Compress
  return Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Headers $headers -Body $json -TimeoutSec $Timeout
}

function Complete-Call($Cfg,[string]$Token,$Call,[string]$State,$Result,[string]$ErrorCode="") {
  $body=@{call_id=[string]$Call.call_id;state=$State;result=$Result}
  if ($ErrorCode) { $body.error_code=$ErrorCode }
  Send-Json "$($Cfg.base_url)/api/device/calls/complete" $Token $body 20 | Out-Null
}

function Invoke-AgentSelfTest {
  $previousReceiptDir=$script:ReceiptDir
  $testRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-commander-selftest-"+[guid]::NewGuid().ToString("N"))
  try {
    $script:ReceiptDir=Join-Path $testRoot "receipts"
    New-Item -ItemType Directory -Path $script:ReceiptDir -Force | Out-Null
    $cfg=[pscustomobject]@{device_id="selftest";architecture="test"}
    $base=[ordered]@{call_id="selftest";request_id="selftest-001";tool_id="hara.health";payload=[pscustomobject]@{}}

    $health=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$health.state -ne "PASS") { throw "SELF_TEST_HEALTH_FAILED" }

    $base.request_id="selftest-002"; $base.tool_id="hara.functions.list"; $base.payload=[pscustomobject]@{}
    $listing=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([int]$listing.result.registered_function_count -ne 1) { throw "SELF_TEST_LIST_FAILED" }

    $base.request_id="selftest-003"; $base.tool_id="hara.functions.describe"
    $base.payload=[pscustomobject]@{function_id=$FunctionId}
    $description=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$description.result.function_id -ne $FunctionId) { throw "SELF_TEST_DESCRIBE_FAILED" }

    $base.request_id="selftest-004"; $base.tool_id="hara.functions.invoke"
    $base.payload=[pscustomobject]@{function_id=$FunctionId;arguments=[pscustomobject]@{argv=@()}}
    $invoked=Invoke-Tool $cfg ([pscustomobject]$base)
    $receipt=[string]$invoked.bridge_receipt_sha256
    if ($receipt -notmatch "^[0-9a-f]{64}$") { throw "SELF_TEST_RECEIPT_FAILED" }

    $base.request_id="selftest-005"; $base.tool_id="hara.receipts.get"
    $base.payload=[pscustomobject]@{receipt_id_or_sha256=$receipt}
    $read=Invoke-Tool $cfg ([pscustomobject]$base)
    if ([string]$read.result.tool_id -ne "hara.functions.invoke") { throw "SELF_TEST_RECEIPTS_GET_FAILED" }

    $blocked=$false
    try { Invoke-LocalFunction $cfg "shell.run" ([pscustomobject]@{argv=@()}) | Out-Null }
    catch { if ([string]$_.Exception.Message -eq "UNKNOWN_FUNCTION_ID") { $blocked=$true } }
    if (-not $blocked) { throw "SELF_TEST_ARBITRARY_FUNCTION_ALLOWED" }

    Write-Host "COMMANDER_WINDOWS_FIVE_TOOL_BRIDGE=PASS"
    Write-Host "COMMANDER_WINDOWS_ARBITRARY_FUNCTION=DENIED"
    Write-Host "COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS"
  } finally {
    $script:ReceiptDir=$previousReceiptDir
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if ($args -contains "--self-test") { Invoke-AgentSelfTest; exit 0 }

try {
  $StartupCfg=Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
  if (
    -not $StartupCfg.base_url
    -or -not $StartupCfg.device_id
    -or -not $StartupCfg.encrypted_device_token
    -or -not $StartupCfg.architecture
  ) { throw "DEVICE_CONFIG_INVALID" }
  $StartupSecureToken=ConvertTo-SecureString ([string]$StartupCfg.encrypted_device_token)
  $StartupToken=Get-PlainText $StartupSecureToken
  if ([string]::IsNullOrWhiteSpace($StartupToken)) { throw "DEVICE_CONFIG_INVALID" }
  $StartupToken=$null
  if (-not (Try-SetRuntimeStatus -StartedAt ([DateTime]::UtcNow.ToString("o"))) {
    throw "RUNTIME_STATUS_STARTUP_WRITE_FAILED"
  }
} catch {
  $code=Get-SafeErrorCode $_
  throw $code
}

$LastHeartbeat=[datetime]::MinValue
$LastErrorCode=$null
$LastErrorWrite=[datetime]::MinValue
while ($true) {
  try {
    $Cfg=Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
    $SecureToken=ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
    $DeviceToken=Get-PlainText $SecureToken
    if (((Get-Date)-$LastHeartbeat).TotalSeconds -ge 30) {
      Send-Json "$($Cfg.base_url)/api/device/heartbeat" $DeviceToken @{
        device_id=[string]$Cfg.device_id
        architecture=[string]$Cfg.architecture
        agent_version=$AgentVersion
      } 20 | Out-Null
      $LastHeartbeat=Get-Date
      $LastErrorCode=$null
      Try-SetRuntimeStatus -HeartbeatAt ([DateTime]::UtcNow.ToString("o")) | Out-Null
    }
    try {
      $Call=Send-Json "$($Cfg.base_url)/api/device/calls/next" $DeviceToken @{} 25
    } catch {
      if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 204) { $Call=$null } else { throw }
    }
    if ($null -ne $Call -and $Call.call_id) {
      try {
        $result=Invoke-Tool $Cfg $Call
        Complete-Call $Cfg $DeviceToken $Call "COMPLETED" $result
      } catch {
        $code=Get-SafeErrorCode $_
        $denied=@{
          state="DENIED";operational_authority="HARA_SERVICES"
          runtime_authority_from_chatgpt=$false;mutation_performed=$false
          result=@{};blocker=@{code=$code}
        }
        Complete-Call $Cfg $DeviceToken $Call "FAILED" $denied $code
      }
    }
  } catch {
    $code=Get-SafeErrorCode $_
    $now=Get-Date
    if ($code -ne $LastErrorCode -or ($now-$LastErrorWrite).TotalSeconds -ge 60) {
      Try-SetRuntimeStatus -ErrorCode $code -ErrorAt ([DateTime]::UtcNow.ToString("o")) | Out-Null
      $LastErrorCode=$code
      $LastErrorWrite=$now
    }
  } finally {
    $DeviceToken=$null
  }
  Start-Sleep -Seconds 2
}
