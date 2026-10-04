$ErrorActionPreference = "Stop"
$Root = Join-Path $env:LOCALAPPDATA "HARA Commander"
$ConfigPath = Join-Path $Root "device.json"
$ReceiptDir = Join-Path $Root "receipts"
$RuntimeStatus = Join-Path $Root "runtime-status.json"
$SessionPath = Join-Path $Root "operator-session.json"
$ConsoleEvents = Join-Path $Root "console-events.jsonl"
$SessionMaxHours = 12
$AgentVersion = "0.3.24"
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

function Get-OperatorProcess([int]$OwnerPid) {
  if ($OwnerPid -le 1) { return $null }
  try { return Get-Process -Id $OwnerPid -ErrorAction Stop }
  catch { return $null }
}

function Get-OperatorSession {
  if (-not (Test-Path -LiteralPath $SessionPath -PathType Leaf)) { return $null }
  try { $session=Get-Content -Raw -LiteralPath $SessionPath | ConvertFrom-Json } catch { return $null }
  if ([string]$session.schema -ne "hara.commander-operator-session.v1") { return $null }
  try { $started=[DateTime]::Parse([string]$session.started_at_utc).ToUniversalTime() } catch { return $null }
  if (([DateTime]::UtcNow-$started).TotalHours -gt $SessionMaxHours) { return $null }
  $proc=Get-OperatorProcess ([int]$session.owner_pid)
  if (-not $proc) { return $null }
  $marker=$proc.StartTime.ToUniversalTime().ToString("o")
  if ($marker -ne [string]$session.owner_started_at_utc) { return $null }
  return $session
}

function Test-OperatorSessionActive {
  return $null -ne (Get-OperatorSession)
}

function Write-ConsoleEvent([string]$Event,$Call=$null,[string]$State="",[string]$ErrorCode="",[string]$ReceiptSha="") {
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $tool=$null; $functionId=$null; $requestId=$null
  if ($null -ne $Call) {
    $tool=[string]$Call.tool_id
    if ($Call.payload) { $functionId=[string]$Call.payload.function_id }
    $requestId=[string]$Call.request_id
  }
  $entry=[ordered]@{
    schema="hara.commander-console-event.v1"
    at_utc=[DateTime]::UtcNow.ToString("o")
    event=$Event
    state=if ($State) {$State} else {$null}
    tool_id=if ($tool) {$tool} else {$null}
    function_id=if ($functionId) {$functionId} else {$null}
    request_id=if ($requestId) {$requestId} else {$null}
    error_code=if ($ErrorCode) {$ErrorCode} else {$null}
    receipt_sha256=if ($ReceiptSha) {$ReceiptSha} else {$null}
    payload_values_exposed=$false
    secret_material_exposed=$false
  }
  Add-Content -LiteralPath $ConsoleEvents -Value ($entry | ConvertTo-Json -Compress) -Encoding UTF8
}

function Format-ConsoleEvent($Entry) {
  $stamp=([DateTime]::Parse([string]$Entry.at_utc)).ToLocalTime().ToString("HH:mm:ss")
  $tool=if ($Entry.tool_id) {[string]$Entry.tool_id} else {"-"}
  $fn=if ($Entry.function_id) {[string]$Entry.function_id} else {"-"}
  $request=if ($Entry.request_id) {[string]$Entry.request_id} else {""}
  $command=if ($fn -ne "-") {$fn} else {$tool}
  $suffix=" cliente=MCP comando=$command tool=$tool"
  if ($request) {$suffix+=" request="+$request.Substring(0,[Math]::Min(12,$request.Length))+$(if ($request.Length -gt 12) {"..."} else {""})}
  if ($Entry.state) {$suffix+=" state="+[string]$Entry.state}
  if ($Entry.error_code) {$suffix+=" error="+[string]$Entry.error_code}
  if ($Entry.receipt_sha256) {$suffix+=" receipt="+([string]$Entry.receipt_sha256).Substring(0,12)+"..."}
  return "[$stamp] $([string]$Entry.event)$suffix"
}

function Start-OperatorConsole {
  $cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
  $existing=Get-OperatorSession
  if ($existing -and [int]$existing.owner_pid -ne $PID) { throw "OPERATOR_SESSION_ALREADY_ACTIVE" }
  New-Item -ItemType Directory -Path $Root -Force | Out-Null
  $session=[ordered]@{
    schema="hara.commander-operator-session.v1"
    owner_pid=$PID
    owner_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
    started_at_utc=[DateTime]::UtcNow.ToString("o")
    device_id=[string]$cfg.device_id
    authorization="LOCAL_OPERATOR_TERMINAL"
  }
  $session | ConvertTo-Json -Compress | Set-Content -LiteralPath $SessionPath -Encoding UTF8
  Write-ConsoleEvent "SESSION_OPEN" $null "AUTHORIZED"
  Write-Host ""
  Write-Host "H.A.R.A. Labs - Commander"
  Write-Host ("="*58)
  Write-Host "Sessao local autorizada para clientes de IA"
  Write-Host ("Computador: "+$env:COMPUTERNAME)
  Write-Host ("Device ID : "+[string]$cfg.device_id)
  Write-Host ("Agent     : "+$AgentVersion)
  Write-Host ""
  Write-Host "Comandos permitidos nesta sessao:"
  Write-Host "  hara.health"
  Write-Host "  hara.functions.list"
  Write-Host "  hara.functions.describe"
  Write-Host "  hara.functions.invoke (somente funcoes governadas)"
  Write-Host "  hara.receipts.get"
  Write-Host ""
  Write-Host "Origem     : OpenAI / cliente MCP autorizado"
  Write-Host "Acesso     : ativo somente enquanto este terminal permanecer aberto"
  Write-Host "Argumentos sensiveis, tokens e segredos nunca sao exibidos."
  Write-Host "Cada acao sera mostrada abaixo com tool, funcao, estado e receipt."
  Write-Host "Pressione Ctrl+C para revogar o acesso imediatamente."
  Write-Host ("-"*58)
  try {
    $seen=0
    while ($true) {
      $current=Get-OperatorSession
      if (-not $current -or [int]$current.owner_pid -ne $PID) { break }
      if (Test-Path -LiteralPath $ConsoleEvents -PathType Leaf) {
        $rows=@(Get-Content -LiteralPath $ConsoleEvents)
        while ($seen -lt $rows.Count) {
          try { $entry=$rows[$seen] | ConvertFrom-Json; Write-Host (Format-ConsoleEvent $entry) } catch {}
          $seen++
        }
      }
      Start-Sleep -Milliseconds 250
    }
  } finally {
    try {
      $current=Get-OperatorSession
      if (-not $current -or [int]$current.owner_pid -eq $PID) { Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue }
    } catch {
      Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue
    }
    Set-DeviceOffline $cfg | Out-Null
    Write-ConsoleEvent "SESSION_CLOSE" $null "REVOKED"
    Write-Host "HARA_COMMANDER_SESSION=INACTIVE"
  }
}

function Stop-OperatorSession {
  $was=Test-Path -LiteralPath $SessionPath -PathType Leaf
  Remove-Item -Force -LiteralPath $SessionPath -ErrorAction SilentlyContinue
  Set-DeviceOffline | Out-Null
  Write-ConsoleEvent "SESSION_CLOSE" $null "REVOKED"
  Write-Host "HARA_COMMANDER_SESSION=INACTIVE"
  Write-Host ("SESSION_WAS_ACTIVE="+($(if ($was) {"TRUE"} else {"FALSE"})))
  Write-Host "SECRET_MATERIAL_EXPOSED=FALSE"
}

function Show-OperatorSession {
  $session=Get-OperatorSession
  Write-Host ("HARA_COMMANDER_SESSION="+($(if ($session) {"ACTIVE"} else {"INACTIVE"})))
  if ($session) { Write-Host ("SESSION_STARTED_AT_UTC="+[string]$session.started_at_utc) }
  Write-Host "SECRET_MATERIAL_EXPOSED=FALSE"
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
function Get-Utf8Sha256([string]$Text) {
  $bytes=[Text.Encoding]::UTF8.GetBytes([string]$Text)
  $sha=[Security.Cryptography.SHA256]::Create()
  try { return ($sha.ComputeHash($bytes) | ForEach-Object {$_.ToString("x2")}) -join "" }
  finally { $sha.Dispose() }
}
function New-Receipt($Cfg,$Call,[string]$State,$Result) {
  New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
  $resultBinding="NONE"
  $resultStdoutSha256=$null
  if ([string]$Call.tool_id -eq "hara.functions.invoke") {
    $resultBinding="STDOUT_SHA256_V1"
    $resultStdoutSha256=Get-Utf8Sha256 ([string]$Result.stdout)
  }
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
    result_binding=$resultBinding
    result_stdout_sha256=$resultStdoutSha256
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

  $receipt=New-Receipt $Cfg $Call "PASS" $result
  return @{
    state="PASS";operational_authority="HARA_SERVICES"
    runtime_authority_from_chatgpt=$false;mutation_performed=$false
    result=$result;blocker=$null;bridge_receipt_sha256=$receipt
  }
}
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  $headers=@{Accept="application/json";Authorization="Bearer $Token"}
  $json=$Body | ConvertTo-Json -Depth 10 -Compress
  return Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Headers $headers -Body $json -TimeoutSec $Timeout -MaximumRedirection 0
}

function Set-DeviceOffline($Cfg=$null) {
  try {
    if (-not $Cfg) { $Cfg=Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json }
    $SecureToken=ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
    $Token=Get-PlainText $SecureToken
    $result=Send-Json "$($Cfg.base_url)/api/device/offline" $Token @{device_id=[string]$Cfg.device_id;agent_version=$AgentVersion;architecture=[string]$Cfg.architecture} 5
    $ok=$result -and $result.ok -eq $true -and [string]$result.state -eq "OFFLINE"
    Write-ConsoleEvent "AGENT_OFFLINE" $null $(if ($ok) {"OFFLINE"} else {"FAILED"})
    return $ok
  } catch {
    Write-ConsoleEvent "OFFLINE_SYNC_ERROR" $null "FAILED" (Get-SafeErrorCode $_)
    return $false
  } finally {
    $Token=$null
  }
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
    $expectedStdoutSha=Get-Utf8Sha256 ([string]$invoked.result.stdout)
    if ([string]$read.result.result_binding -ne "STDOUT_SHA256_V1") { throw "SELF_TEST_RECEIPT_RESULT_BINDING_FAILED" }
    if ([string]$read.result.result_stdout_sha256 -ne $expectedStdoutSha) { throw "SELF_TEST_RECEIPT_RESULT_SHA_FAILED" }

    $blocked=$false
    try { Invoke-LocalFunction $cfg "shell.run" ([pscustomobject]@{argv=@()}) | Out-Null }
    catch { if ([string]$_.Exception.Message -eq "UNKNOWN_FUNCTION_ID") { $blocked=$true } }
    if (-not $blocked) { throw "SELF_TEST_ARBITRARY_FUNCTION_ALLOWED" }

    $previousSessionPath=$script:SessionPath
    $previousConsoleEvents=$script:ConsoleEvents
    try {
      $script:SessionPath=Join-Path $testRoot "operator-session.json"
      $script:ConsoleEvents=Join-Path $testRoot "console-events.jsonl"
      if (Test-OperatorSessionActive) { throw "SELF_TEST_SESSION_SHOULD_START_INACTIVE" }
      [ordered]@{
        schema="hara.commander-operator-session.v1"
        owner_pid=$PID
        owner_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
        started_at_utc=[DateTime]::UtcNow.ToString("o")
      } | ConvertTo-Json -Compress | Set-Content -LiteralPath $script:SessionPath -Encoding UTF8
      if (-not (Test-OperatorSessionActive)) { throw "SELF_TEST_SESSION_GATE_FAILED" }
      Write-ConsoleEvent "SELFTEST" ([pscustomobject]@{request_id="r";tool_id="hara.health";payload=[pscustomobject]@{secret="never"}})
      $entry=(Get-Content -LiteralPath $script:ConsoleEvents | Select-Object -Last 1) | ConvertFrom-Json
      if ($entry.payload_values_exposed -ne $false -or $entry.secret_material_exposed -ne $false) { throw "SELF_TEST_CONSOLE_SANITIZATION_FAILED" }
      if (($entry | ConvertTo-Json -Compress) -match "never") { throw "SELF_TEST_CONSOLE_PAYLOAD_LEAK" }
    } finally {
      $script:SessionPath=$previousSessionPath
      $script:ConsoleEvents=$previousConsoleEvents
    }

    Write-Host "COMMANDER_WINDOWS_OPERATOR_SESSION_GATE=PASS"
    Write-Host "COMMANDER_WINDOWS_CONSOLE_SANITIZATION=PASS"
    Write-Host "COMMANDER_WINDOWS_FIVE_TOOL_BRIDGE=PASS"
    Write-Host "COMMANDER_WINDOWS_ARBITRARY_FUNCTION=DENIED"
    Write-Host "COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS"
  } finally {
    $script:ReceiptDir=$previousReceiptDir
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if ($args -contains "--self-test") { Invoke-AgentSelfTest; exit 0 }
if ($args -contains "--session-start" -or ($args.Count -gt 0 -and [string]$args[0] -eq "start")) { Start-OperatorConsole; exit 0 }
if ($args -contains "--session-status" -or ($args.Count -gt 0 -and [string]$args[0] -eq "status")) { Show-OperatorSession; exit 0 }
if ($args -contains "--session-stop" -or ($args.Count -gt 0 -and [string]$args[0] -eq "stop")) { Stop-OperatorSession; exit 0 }
if ($args.Count -gt 0 -and @("help","--help","-h") -contains [string]$args[0]) {
  Write-Host "Usage: hara-commander [start|status|stop|help]"
  exit 0
}
if ($args.Count -gt 0) {
  Write-Host ("HARA_COMMANDER_UNKNOWN_COMMAND="+[string]$args[0])
  Write-Host "Usage: hara-commander [start|status|stop|help]"
  exit 64
}

try {
  $StartupCfg=Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
  if (-not $StartupCfg.base_url -or -not $StartupCfg.device_id -or -not $StartupCfg.encrypted_device_token -or -not $StartupCfg.architecture) { throw "DEVICE_CONFIG_INVALID" }
  $StartupSecureToken=ConvertTo-SecureString ([string]$StartupCfg.encrypted_device_token)
  $StartupToken=Get-PlainText $StartupSecureToken
  if ([string]::IsNullOrWhiteSpace($StartupToken)) { throw "DEVICE_CONFIG_INVALID" }
  $StartupToken=$null
  if (-not (Try-SetRuntimeStatus -StartedAt ([DateTime]::UtcNow.ToString("o")))) {
    throw "RUNTIME_STATUS_STARTUP_WRITE_FAILED"
  }
} catch {
  $code=Get-SafeErrorCode $_
  throw $code
}

$LastHeartbeat=[datetime]::MinValue
$LastErrorCode=$null
$LastErrorWrite=[datetime]::MinValue
$WasAuthorized=$false
if (-not (Test-OperatorSessionActive)) {
  Set-DeviceOffline $StartupCfg | Out-Null
  Write-ConsoleEvent "AGENT_INERT" $null "LOCAL_SESSION_REQUIRED"
}
while ($true) {
  if (-not (Test-OperatorSessionActive)) {
    $WasAuthorized=$false
    Start-Sleep -Seconds 1
    continue
  }
  if (-not $WasAuthorized) {
    $LastHeartbeat=[datetime]::MinValue
    Write-ConsoleEvent "AGENT_ONLINE" $null "AUTHORIZED"
    $WasAuthorized=$true
  }
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
      if (-not (Test-OperatorSessionActive)) {
        $code="LOCAL_OPERATOR_SESSION_REQUIRED"
        Write-ConsoleEvent "DENIED" $Call "DENIED" $code
        $denied=@{
          state="DENIED";operational_authority="LOCAL_OPERATOR_SESSION"
          runtime_authority_from_chatgpt=$false;mutation_performed=$false
          result=@{};blocker=@{code=$code}
        }
        Complete-Call $Cfg $DeviceToken $Call "FAILED" $denied $code
      } else {
        Write-ConsoleEvent "RECEIVED" $Call "PENDING"
        try {
          Write-ConsoleEvent "EXECUTING" $Call "EXECUTING"
          $result=Invoke-Tool $Cfg $Call
          Complete-Call $Cfg $DeviceToken $Call "COMPLETED" $result
          $receipt=if ($result.bridge_receipt_sha256) {[string]$result.bridge_receipt_sha256} else {""}
          Write-ConsoleEvent "PASS" $Call "COMPLETED" "" $receipt
        } catch {
          $code=Get-SafeErrorCode $_
          Write-ConsoleEvent "DENIED" $Call "FAILED" $code
          $denied=@{
            state="DENIED";operational_authority="LOCAL_OPERATOR_SESSION"
            runtime_authority_from_chatgpt=$false;mutation_performed=$false
            result=@{};blocker=@{code=$code}
          }
          Complete-Call $Cfg $DeviceToken $Call "FAILED" $denied $code
        }
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
