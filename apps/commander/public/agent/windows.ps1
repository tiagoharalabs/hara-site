$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$ConfigPath = Join-Path $Root "device.json"
$ReceiptDir = Join-Path $Root "receipts"
$AgentVersion = "0.3.1"
$FunctionId = "device.info"

function Get-PlainText([Security.SecureString]$SecureValue) {
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
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

$LastHeartbeat=[datetime]::MinValue
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
        $code=[string]$_.Exception.Message
        $denied=@{
          state="DENIED";operational_authority="HARA_SERVICES"
          runtime_authority_from_chatgpt=$false;mutation_performed=$false
          result=@{};blocker=@{code=$code}
        }
        Complete-Call $Cfg $DeviceToken $Call "FAILED" $denied $code
      }
    }
    $DeviceToken=$null
  } catch {
  }
  Start-Sleep -Seconds 2
}
