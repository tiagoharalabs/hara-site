# Native PS5.1: real approval ASTs with a fixture-only clock and keyboard adapter.
# Never dot-sources the Agent, starts a Task, runs an action or touches its profile.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AgentSource,
  [Parameter(Mandatory=$true)][string]$ExpectedSourceSha256
)
$ErrorActionPreference="Stop"
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw "WINDOW49_FIXTURE_REQUIRES_PS51" }
$sourcePath=(Resolve-Path -LiteralPath $AgentSource).Path
$sourceSha=(Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedSourceSha256 -cnotmatch '^[0-9a-f]{64}$' -or $sourceSha -cne $ExpectedSourceSha256) { throw "WINDOW49_FIXTURE_SOURCE_NOT_PINNED" }
$sourceText=[IO.File]::ReadAllText($sourcePath)
if ($sourceText -notmatch '(?m)^\$AgentVersion = "0[.]3[.]49"$') { throw "WINDOW49_FIXTURE_VERSION_NOT_49" }
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($sourcePath,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw "WINDOW49_FIXTURE_SOURCE_PARSE_FAILED" }
$timeoutAssignments=@($ast.EndBlock.Statements|Where-Object {
  $_ -is [Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$ApprovalTimeoutSeconds'
})
if ($timeoutAssignments.Count -ne 1 -or $timeoutAssignments[0].Extent.Text -cnotmatch '^\$ApprovalTimeoutSeconds\s*=\s*900$') { throw "WINDOW49_FIXTURE_TIMEOUT_NOT_900_LITERAL" }
Invoke-Expression $timeoutAssignments[0].Extent.Text
$heartbeatAssignments=@($ast.EndBlock.Statements|Where-Object {
  $_ -is [Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$HeartbeatSeconds'
})
if ($heartbeatAssignments.Count -ne 1 -or $heartbeatAssignments[0].Extent.Text -cnotmatch '^\$HeartbeatSeconds\s*=\s*60$') { throw "WINDOW49_FIXTURE_HEARTBEAT_NOT_60_LITERAL" }
Invoke-Expression $heartbeatAssignments[0].Extent.Text
$AgentVersion=([regex]::Match($sourceText,'(?m)^\$AgentVersion = "(0[.]3[.]49)"$')).Groups[1].Value
$names=@("Get-OperatorProcess","Get-OperatorSession","Test-OperatorSessionActive","Get-Utf8Sha256",
  "Protect-LocalCommandPreview","Get-LocalActionSummary","Get-ApprovalMode","Assert-StarterMutationAuthorized",
  "Invoke-WithLocalApprovalLock","Test-LocalApprovalConsumerAlive","Test-LocalApprovalRequestCurrent",
  "Read-LocalApprovalResponse","Publish-LocalApprovalResponse","Remove-LocalApprovalFiles",
  "Respond-ToLocalApprovalRequest","Send-LocalApprovalConsumerHeartbeat","Invoke-LocalActionApproval")
$nodes=@($ast.FindAll({param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names
},$false))
$script:ClockSeams=[ordered]@{}
foreach($name in $names) {
  $node=@($nodes|Where-Object {$_.Name -ceq $name})
  if ($node.Count -ne 1) { throw ("WINDOW49_FIXTURE_FUNCTION_NOT_UNIQUE:"+$name) }
  $definition=$node[0].Extent.Text
  $script:ClockSeams[$name]=([regex]::Matches($definition,'\[DateTime\]::UtcNow')).Count
  # The sole source transformation is fixture time. Qualifying declaration scope
  # preserves definitions across Invoke-Expression without executing Agent startup.
  $definition=$definition.Replace('[DateTime]::UtcNow','(Get-FixtureUtcNow)')
  $definition=$definition -replace '^function ','function script:'
  Invoke-Expression $definition
}
if ($script:ClockSeams["Invoke-LocalActionApproval"] -lt 1 -or $script:ClockSeams["Read-LocalApprovalResponse"] -lt 1) { throw "WINDOW49_FIXTURE_CLOCK_SEAM_NOT_APPLIED" }
$fixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-window49-fixture-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $fixtureRoot|Out-Null
$Root=$fixtureRoot
$PendingApprovalPath=Join-Path $Root "synthetic-pending.json"
$ApprovalResponsePath=Join-Path $Root "synthetic-response.json"
$SessionPath=Join-Path $Root "synthetic-session.json"
$ConfigPath=Join-Path $Root "synthetic-config.json"
$SessionMaxHours=12
$script:ClockBase=[DateTime]::Parse("2035-01-01T00:00:00.0000000Z").ToUniversalTime()
$script:FixtureNow=$script:ClockBase
$script:Passed=0
$script:Checks=New-Object 'System.Collections.Generic.List[string]'
$script:Messages=New-Object 'System.Collections.Generic.List[string]'
$script:Keys=New-Object 'System.Collections.Generic.Queue[System.ConsoleKeyInfo]'
$script:SleepHook=$null;$script:KeyHook=$null
$script:SleepCount=0;$script:KeyReads=0;$script:ClearCount=0;$script:Phase=0
$script:CapturedPending=$null;$script:ObservedReply=$null
$script:ConsumerAlive=$true
$script:HeartbeatCalls=New-Object 'System.Collections.Generic.List[object]'
$script:RuntimeStatusCalls=New-Object 'System.Collections.Generic.List[object]'
$script:HeartbeatThrows=$false
$script:OriginalConsumerTest=(Get-Command Test-LocalApprovalConsumerAlive).ScriptBlock

function Get-FixtureUtcNow { return $script:FixtureNow }
function Set-FixtureElapsed([double]$Seconds) { $script:FixtureNow=$script:ClockBase.AddSeconds($Seconds) }
function Assert-Fixture([bool]$Condition,[string]$Code) {
  if (-not $Condition) { throw ("WINDOW49_FIXTURE_ASSERT:"+$Code) }
  $script:Passed++;$script:Checks.Add($Code)
}
function Write-FixtureJson([string]$Path,$Value) {
  [IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
  [IO.File]::SetLastWriteTimeUtc($Path,$script:FixtureNow)
}
function Copy-Fixture($Value) { return ($Value|ConvertTo-Json -Depth 8 -Compress|ConvertFrom-Json) }
function Get-FixturePending { return (Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json) }
function Reset-Fixture {
  foreach($file in @(Get-ChildItem -LiteralPath $Root -File)) { Remove-Item -LiteralPath $file.FullName -Force }
  Set-FixtureElapsed 0
  $proc=Microsoft.PowerShell.Management\Get-Process -Id $PID
  Write-FixtureJson $SessionPath ([ordered]@{
    schema="hara.commander-operator-session.v1";owner_pid=$PID
    owner_started_at_utc=$proc.StartTime.ToUniversalTime().ToString("o")
    started_at_utc=$script:FixtureNow.ToString("o")
  })
  Write-FixtureJson $ConfigPath ([ordered]@{approval_mode="ASK_EVERY_ACTION";device_id="SYNTHETIC-49";architecture="x64";base_url="https://synthetic.invalid"})
  $script:Keys.Clear();$script:Messages.Clear()
  $script:SleepHook=$null;$script:KeyHook=$null
  $script:SleepCount=0;$script:KeyReads=0;$script:ClearCount=0;$script:Phase=0
  $script:CapturedPending=$null;$script:ObservedReply=$null;$script:ConsumerAlive=$true
  $script:HeartbeatCalls.Clear();$script:RuntimeStatusCalls.Clear();$script:HeartbeatThrows=$false
  $script:DeviceToken=$null
}
function New-FixturePending {
  $session=Get-OperatorSession
  $nonce=[guid]::NewGuid().ToString("N")
  $pending=[pscustomobject][ordered]@{
    schema="hara.commander-local-action-approval.v1";nonce=$nonce
    challenge=$nonce.Substring(0,8).ToUpperInvariant();request_id="SYNTHETIC-"+[guid]::NewGuid().ToString("N")
    tool_id="hara.files.write";arguments_sha256=("b"*64);owner_pid=$PID
    owner_started_at_utc=[string]$session.owner_started_at_utc
    consumer_pid=$PID;consumer_started_at_utc=(Microsoft.PowerShell.Management\Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
    created_at_utc=$script:ClockBase.ToString("o");expires_at_utc=$script:ClockBase.AddSeconds(900).ToString("o")
    action_summary="SYNTHETIC_ONLY_NEVER_A_CUSTOMER_ACTION"
  }
  Write-FixtureJson $PendingApprovalPath $pending
  return $pending
}
function New-FixtureCall {
  return [pscustomobject]@{request_id="SYNTHETIC-CALL-"+[guid]::NewGuid().ToString("N");tool_id="hara.files.write";payload=@{path="SYNTHETIC_NEVER_WRITTEN.txt";content="SYNTHETIC_NEVER_EXECUTED"}}
}
function Add-FixtureText([string]$Text,[bool]$Enter=$true) {
  foreach($char in $Text.ToCharArray()) {
    $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @($char,[ConsoleKey]::A,$false,$false,$false)))
  }
  if ($Enter) { $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @([char]13,[ConsoleKey]::Enter,$false,$false,$false))) }
}
function Expect-FixtureException([scriptblock]$Action,[string]$Code) {
  $caught=$null
  try { & $Action|Out-Null } catch { $caught=$_.Exception.Message }
  Assert-Fixture ($caught -ceq $Code) ("THROWS_"+$Code)
}
function Assert-FixtureClean([string]$Label) {
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) ($Label+"_NO_OWNED_IPC_REMAINS")
}
# Input, time, host output and a consumer-death result are fixture adapters.
# Valid consumer/session identity, mutex, request/digest binding, publication and
# cleanup use real source functions. The dead-consumer case injects false only.
function Initialize-LocalApprovalConsoleInput { return $true }
function Clear-LocalApprovalConsoleInput { $script:ClearCount++ }
function Read-LocalApprovalConsoleKey {
  $script:KeyReads++
  if ($script:KeyReads -gt 100) { throw "WINDOW49_FIXTURE_KEY_LOOP_UNBOUNDED" }
  if ($script:KeyHook) { & $script:KeyHook|Out-Null }
  if ($script:Keys.Count) { return $script:Keys.Dequeue() }
  return $null
}
function Start-Sleep {
  param([int]$Milliseconds=0,[double]$Seconds=0)
  $script:SleepCount++
  if ($script:SleepCount -gt 24) { throw "WINDOW49_FIXTURE_CLOCK_LOOP_UNBOUNDED" }
  if ($script:SleepHook) { & $script:SleepHook|Out-Null }
  else { $script:FixtureNow=$script:FixtureNow.AddMilliseconds($Milliseconds).AddSeconds($Seconds) }
}
function Write-Host { param([object]$Object,[ConsoleColor]$ForegroundColor,[switch]$NoNewline) $script:Messages.Add([string]$Object) }
function Test-LocalApprovalConsumerAlive($Pending) {
  if (-not $script:ConsumerAlive) { return $false }
  return (& $script:OriginalConsumerTest $Pending)
}
function Get-Date { return $script:FixtureNow }
function Get-LocalActivityHeartbeatSnapshot { return @([pscustomobject]@{schema="SYNTHETIC_ACTIVITY_FIXTURE"}) }
function Get-SafeErrorCode($FixtureError) { return "SYNTHETIC_NETWORK_FAILURE" }
function Try-SetRuntimeStatus {
  param([string]$HeartbeatAt,[string]$ErrorCode,[string]$ErrorAt)
  $script:RuntimeStatusCalls.Add([pscustomobject]@{heartbeat_at=$HeartbeatAt;error_code=$ErrorCode;error_at=$ErrorAt})
}
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  $script:HeartbeatCalls.Add([pscustomobject]@{url=$Url;token=$Token;body=(Copy-Fixture $Body);timeout=$Timeout;at_utc=$script:FixtureNow.ToString("o")})
  if ($script:HeartbeatThrows) { throw "SYNTHETIC_NETWORK_FAILURE" }
  # Hostile-looking heartbeat response must have no consent authority.
  return [pscustomobject]@{approved=$true;state="AUTHORIZED";approval_mode="PERSISTENT_TRUSTED"}
}

try {
  Reset-Fixture
  Assert-Fixture ($ApprovalTimeoutSeconds -eq 900) "SOURCE_TIMEOUT_LITERAL_900_SECONDS"
  $pending=New-FixturePending
  Set-FixtureElapsed 899.999
  Assert-Fixture (Test-LocalApprovalRequestCurrent $pending) "CURRENT_AT_899_999_SECONDS"
  Assert-Fixture (Publish-LocalApprovalResponse $pending $true) "REAL_PUBLICATION_AT_899_999_SECONDS"
  $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  Assert-Fixture ($reply.approved -ceq $true -and $reply.responded_at_utc -ceq $script:FixtureNow.ToString("o")) "PUBLICATION_TIMESTAMP_BEFORE_DEADLINE"

  foreach($seconds in @(900,900.001,1200)) {
    Reset-Fixture;$pending=New-FixturePending;Set-FixtureElapsed $seconds
    Assert-Fixture (-not (Test-LocalApprovalRequestCurrent $pending)) ("REQUEST_NOT_CURRENT_AT_"+$seconds)
    Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) ("NO_POSITIVE_PUBLICATION_AT_"+$seconds)
    Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) ("NO_REPLY_AT_"+$seconds)
  }

  Reset-Fixture;$pending=New-FixturePending
  $script:SleepHook={
    $script:Phase++
    if ($script:Phase -eq 1) { Set-FixtureElapsed 899.999 }
    else { Set-FixtureElapsed 900 }
  }
  $timer=[Diagnostics.Stopwatch]::StartNew()
  $response=Read-LocalApprovalResponse $pending
  $timer.Stop()
  Assert-Fixture ($response.state -ceq "EXPIRED" -and $null -eq $response.text) "SILENCE_EXPIRES_AT_900_SECONDS"
  Assert-Fixture ($script:SleepCount -eq 2 -and $timer.Elapsed.TotalSeconds -lt 5) "FIFTEEN_MINUTES_SIMULATED_WITHOUT_WALL_CLOCK_WAIT"
  Assert-Fixture ($script:ClearCount -eq 2 -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) "SILENCE_REQUESTS_INPUT_CLEAR_WITHOUT_REPLY"

  Reset-Fixture;$pending=New-FixturePending
  Add-FixtureText "APROVAR " $false
  $script:SleepHook={
    $script:Phase++
    if ($script:Phase -eq 1) {
      Set-FixtureElapsed 899
      Add-FixtureText ($pending.challenge.Substring(0,4)) $false
    } else {
      Set-FixtureElapsed 899.999
      Add-FixtureText ($pending.challenge.Substring(4))
    }
  }
  $response=Read-LocalApprovalResponse $pending
  Assert-Fixture ($response.state -ceq "SUBMITTED" -and $response.text -ceq ("APROVAR "+$pending.challenge)) "FULL_PHRASE_ACCEPTED_IN_DELAYED_CHUNKS_BEFORE_900"
  Assert-Fixture ($script:SleepCount -eq 2) "CHUNKS_AT_899_AND_899_999_SECONDS"

  Reset-Fixture;$pending=New-FixturePending;Set-FixtureElapsed 899.999
  Add-FixtureText ("APROVAR "+$pending.challenge)
  $script:KeyHook={if ($script:Keys.Count -eq 1) { Set-FixtureElapsed 900 }}
  $response=Read-LocalApprovalResponse $pending
  Assert-Fixture ($response.state -ceq "EXPIRED" -and $null -eq $response.text) "ENTER_AT_EXACT_900_DISCARDS_FULL_PHRASE"
  Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "ENTER_AT_DEADLINE_CANNOT_PUBLISH"

  foreach($inputText in @("APROVAR","","APROVAR WRONGCODE")) {
    Reset-Fixture;$pending=New-FixturePending;Set-FixtureElapsed 899.999
    Add-FixtureText $inputText
    Respond-ToLocalApprovalRequest
    $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
    Assert-Fixture ($reply.approved -is [bool] -and $reply.approved -ceq $false) ("INCOMPLETE_OR_WRONG_INPUT_DENIED_"+$inputText)
    Assert-Fixture ($reply.nonce -ceq $pending.nonce -and $reply.arguments_sha256 -ceq $pending.arguments_sha256) "DENIAL_BOUND_TO_EXACT_PENDING"
  }
  Reset-Fixture;$pending=New-FixturePending;Set-FixtureElapsed 899.999
  Add-FixtureText ("APROVAR "+$pending.challenge)
  Respond-ToLocalApprovalRequest
  $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  Assert-Fixture ($reply.approved -ceq $true) "RESPONDER_REQUIRES_FULL_PHRASE_AND_CODE"
  Assert-Fixture (($script:Messages -join " ") -match '15\s+minutos') "PROMPT_SHOWS_FIFTEEN_MINUTE_WINDOW"

  Reset-Fixture;$call=New-FixtureCall
  $script:SleepHook={
    $script:CapturedPending=Get-FixturePending
    Assert-Fixture (([DateTime]::Parse($script:CapturedPending.expires_at_utc)-[DateTime]::Parse($script:CapturedPending.created_at_utc)).TotalSeconds -eq 900) "REAL_INVOKE_CREATES_900_SECOND_DEADLINE"
    $expectedDigest=Get-Utf8Sha256 ([string]$call.tool_id+"|"+[string]$call.request_id+"|"+($call.payload|ConvertTo-Json -Depth 10 -Compress))
    Assert-Fixture ($script:CapturedPending.arguments_sha256 -ceq $expectedDigest) "REAL_INVOKE_BINDS_TOOL_REQUEST_AND_PAYLOAD_SHA256"
    Set-FixtureElapsed 899.999
    Add-FixtureText ("APROVAR "+$script:CapturedPending.challenge)
    Respond-ToLocalApprovalRequest
    $script:ObservedReply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  }
  Assert-Fixture ((Invoke-LocalActionApproval $call) -eq $true) "REAL_INVOKE_CONSUMES_HUMAN_INPUT_FIXTURE_AT_899_999"
  Assert-Fixture ($script:ObservedReply.owner_pid -eq $PID -and $script:ObservedReply.consumer_pid -eq $PID -and $script:ObservedReply.nonce -ceq $script:CapturedPending.nonce) "ACCEPTED_REPLY_BOUND_TO_OWNER_CONSUMER_AND_NONCE"
  Assert-FixtureClean "BEFORE_DEADLINE_ACCEPTANCE"

  foreach($seconds in @(900,900.001)) {
    Reset-Fixture;$call=New-FixtureCall
    $script:BoundaryCaseSeconds=[double]$seconds
    $script:SleepHook={
      $script:CapturedPending=Get-FixturePending
      Set-FixtureElapsed $script:BoundaryCaseSeconds
      Assert-Fixture (-not (Publish-LocalApprovalResponse $script:CapturedPending $true)) "DEADLINE_REPLY_REJECTED_BY_REAL_PUBLISHER"
    }
    Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_ACTION_APPROVAL_EXPIRED"
    Assert-FixtureClean ("CONSUMER_AT_"+$seconds)
  }

  Reset-Fixture;$call=New-FixtureCall
  $script:SleepHook={
    $pendingReply=Get-FixturePending
    Set-FixtureElapsed 899.999
    Assert-Fixture (Publish-LocalApprovalResponse $pendingReply $true) "VALID_REPLY_PUBLISHED_BEFORE_CONSUMER_DEADLINE"
    Set-FixtureElapsed 900
  }
  Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_ACTION_APPROVAL_EXPIRED"
  Assert-FixtureClean "VALID_REPLY_CONSUMED_TOO_LATE"

  foreach($field in @("nonce","request_id","arguments_sha256","owner_pid","owner_started_at_utc","consumer_pid","consumer_started_at_utc","responded_at_utc","approved")) {
    Reset-Fixture;$call=New-FixtureCall
    $script:SleepHook={
      $pendingReply=Get-FixturePending
      Set-FixtureElapsed 899.999
      Assert-Fixture (Publish-LocalApprovalResponse $pendingReply $true) ("ORIGINAL_REPLY_PUBLISHED_BEFORE_TAMPER_"+$field)
      $answer=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
      if ($field -in @("owner_pid","consumer_pid")) { $answer.$field=$PID+1000000 }
      elseif ($field -eq "approved") { $answer.$field="true" }
      elseif ($field -eq "responded_at_utc") { $answer.$field=$script:ClockBase.AddSeconds(900).ToString("o") }
      else { $answer.$field=[string]$answer.$field+"-TAMPERED" }
      Write-FixtureJson $ApprovalResponsePath $answer
      $script:TamperedReplySha=(Get-FileHash -LiteralPath $ApprovalResponsePath -Algorithm SHA256).Hash
    }
    Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_ACTION_APPROVAL_RESPONSE_INVALID"
    if ($field -ceq "nonce") {
      Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath)) "TAMPERED_FOREIGN_NONCE_REMOVES_ONLY_OWNED_PENDING"
      Assert-Fixture ((Get-FileHash -LiteralPath $ApprovalResponsePath -Algorithm SHA256).Hash -ceq $script:TamperedReplySha) "TAMPERED_FOREIGN_NONCE_REPLY_BYTES_PRESERVED"
    } else { Assert-FixtureClean ("TAMPERED_REPLY_"+$field) }
  }

  Reset-Fixture;$call=New-FixtureCall
  $script:SleepHook={Set-FixtureElapsed 600;$script:ConsumerAlive=$false}
  Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_ACTION_APPROVAL_REQUEST_CHANGED"
  Assert-FixtureClean "DEAD_CONSUMER"

  Reset-Fixture;$pending=New-FixturePending
  $pendingSha=(Get-FileHash -LiteralPath $PendingApprovalPath -Algorithm SHA256).Hash
  Set-FixtureElapsed 600
  $call=New-FixtureCall
  Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_APPROVAL_REQUEST_BUSY"
  Assert-Fixture ((Get-FileHash -LiteralPath $PendingApprovalPath -Algorithm SHA256).Hash -ceq $pendingSha) "CONCURRENT_REQUEST_AFTER_TWO_MINUTES_PRESERVES_LIVE_PENDING"
  Assert-Fixture (Test-LocalApprovalRequestCurrent $pending) "ORIGINAL_REQUEST_STILL_APPROVABLE_AT_TEN_MINUTES"
  Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "CONCURRENT_BUSY_DID_NOT_CREATE_REPLY"

  Reset-Fixture;$expiredPending=New-FixturePending
  Set-FixtureElapsed 899.999
  Assert-Fixture (Publish-LocalApprovalResponse $expiredPending $false) "EXPIRED_PAIR_CONTROL_ORIGINAL_DENIAL"
  Set-FixtureElapsed 900.001;$call=New-FixtureCall
  $script:SleepHook={
    $newPending=Get-FixturePending
    Assert-Fixture ($newPending.nonce -cne $expiredPending.nonce -and $newPending.request_id -ceq $call.request_id) "EXPIRED_PAIR_REPLACED_WITH_NEW_NONCE_AND_REQUEST"
    Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "OLD_DENIAL_DID_NOT_AUTHORIZE_NEW_REQUEST"
    Add-FixtureText ("APROVAR "+$newPending.challenge)
    Respond-ToLocalApprovalRequest
  }
  Assert-Fixture ((Invoke-LocalActionApproval $call) -eq $true) "EXPIRED_EXACT_PAIR_CLEANUP_REQUIRES_FRESH_APPROVAL"
  Assert-FixtureClean "EXPIRED_PAIR_RECOVERY"

  Reset-Fixture;$expiredPending=New-FixturePending
  Assert-Fixture (Publish-LocalApprovalResponse $expiredPending $false) "MISMATCHED_PAIR_CONTROL_ORIGINAL_DENIAL"
  $foreignReply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  $foreignReply.nonce=[guid]::NewGuid().ToString("N")
  Write-FixtureJson $ApprovalResponsePath $foreignReply
  $replySha=(Get-FileHash -LiteralPath $ApprovalResponsePath -Algorithm SHA256).Hash
  Set-FixtureElapsed 900.001;$call=New-FixtureCall
  Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_APPROVAL_REQUEST_BUSY"
  Assert-Fixture ((Get-FileHash -LiteralPath $ApprovalResponsePath -Algorithm SHA256).Hash -ceq $replySha) "EXPIRED_PENDING_WITH_FOREIGN_REPLY_PRESERVES_FOREIGN_REPLY_BYTES"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath)) "MISMATCHED_PAIR_NEVER_CREATES_NEW_PENDING"

  Reset-Fixture;$orphanPending=New-FixturePending
  Assert-Fixture (Publish-LocalApprovalResponse $orphanPending $false) "ORPHAN_REPLY_CONTROL_ORIGINAL_DENIAL"
  Remove-Item -LiteralPath $PendingApprovalPath -Force
  $replySha=(Get-FileHash -LiteralPath $ApprovalResponsePath -Algorithm SHA256).Hash
  Set-FixtureElapsed 600;$call=New-FixtureCall
  Expect-FixtureException {Invoke-LocalActionApproval $call} "LOCAL_APPROVAL_REQUEST_BUSY"
  Assert-Fixture ((Get-FileHash -LiteralPath $ApprovalResponsePath -Algorithm SHA256).Hash -ceq $replySha) "ORPHAN_REPLY_YOUNGER_THAN_900_SECONDS_PRESERVED"
  Set-FixtureElapsed 900;$call=New-FixtureCall
  $script:SleepHook={
    $newPending=Get-FixturePending
    Assert-Fixture ($newPending.nonce -cne $orphanPending.nonce -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) "OLD_ORPHAN_REPLY_REMOVED_WITHOUT_GRANTING_APPROVAL"
    Add-FixtureText ("APROVAR "+$newPending.challenge)
    Respond-ToLocalApprovalRequest
  }
  Assert-Fixture ((Invoke-LocalActionApproval $call) -eq $true) "ORPHAN_REPLY_AT_900_SECONDS_REQUIRES_NEW_FULL_PHRASE"
  Assert-FixtureClean "ORPHAN_REPLY_RECOVERY"

  foreach($transportFails in @($false,$true)) {
    Reset-Fixture;$call=New-FixtureCall
    $cfg=Get-Content -Raw -LiteralPath $ConfigPath|ConvertFrom-Json
    $cfgSha=(Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
    $script:HeartbeatThrows=$transportFails
    $script:DeviceToken="SYNTHETIC_TOKEN_NEVER_SENT_TO_A_NETWORK"
    $heartbeatBefore=$script:ClockBase.AddMinutes(-1)
    $script:LastHeartbeat=$heartbeatBefore
    $script:SleepHook={
      $pendingPulse=Get-FixturePending
      Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "HEARTBEAT_RESPONSE_NEVER_CREATES_CONSENT_REPLY"
      $script:FixtureNow=$script:FixtureNow.AddSeconds(60)
    }
    # Enter through real ASK_EVERY_ACTION wiring, not just the heartbeat helper.
    Expect-FixtureException {Assert-StarterMutationAuthorized $cfg $call} "LOCAL_ACTION_APPROVAL_EXPIRED"
    Assert-Fixture ($script:HeartbeatCalls.Count -eq 14) "APPROVAL_WAIT_SENDS_FOURTEEN_HEARTBEATS_OVER_FAKE_900_SECONDS"
    $previous=$script:ClockBase
    foreach($pulse in $script:HeartbeatCalls) {
      $at=[DateTime]::Parse($pulse.at_utc).ToUniversalTime()
      Assert-Fixture (($at-$previous).TotalSeconds -eq 60) "HEARTBEATS_USE_SIXTY_SECOND_CADENCE"
      Assert-Fixture ($pulse.url -ceq "https://synthetic.invalid/api/device/heartbeat" -and $pulse.timeout -eq 5) "HEARTBEAT_TRANSPORT_IS_BOUNDED_AND_DOES_NOT_POLL_NEXT_CALL"
      Assert-Fixture ($pulse.token -ceq $script:DeviceToken -and $pulse.body.device_id -ceq $cfg.device_id -and $pulse.body.agent_version -ceq "0.3.49" -and $pulse.body.architecture -ceq "x64" -and $pulse.body.approval_mode -ceq "ASK_EVERY_ACTION") "HEARTBEAT_PRESERVES_DEVICE_TOKEN_VERSION_AND_APPROVAL_POLICY"
      $previous=$at
    }
    Assert-Fixture (($script:FixtureNow-$previous).TotalSeconds -eq 60 -and $script:FixtureNow -eq $script:ClockBase.AddSeconds(900)) "HEARTBEATS_STOP_AT_APPROVAL_DEADLINE"
    if ($transportFails) {
      Assert-Fixture ($script:RuntimeStatusCalls.Count -eq 14 -and @($script:RuntimeStatusCalls|Where-Object {$_.error_code -cne "SYNTHETIC_NETWORK_FAILURE"}).Count -eq 0) "FAILED_HEARTBEATS_RECORDED_WITHOUT_AUTHORIZING_ACTION"
      Assert-Fixture ($script:LastHeartbeat -eq $heartbeatBefore) "FAILED_HEARTBEAT_DOES_NOT_ADVANCE_SHARED_LAST_HEARTBEAT"
    } else {
      Assert-Fixture ($script:RuntimeStatusCalls.Count -eq 14 -and @($script:RuntimeStatusCalls|Where-Object {$_.heartbeat_at -eq ""}).Count -eq 0) "SUCCESSFUL_HEARTBEATS_RECORDED_WITHOUT_AUTHORIZING_ACTION"
      Assert-Fixture ($script:LastHeartbeat -eq $script:ClockBase.AddSeconds(840)) "SUCCESSFUL_HEARTBEAT_ADVANCES_SHARED_LAST_HEARTBEAT"
    }
    Assert-Fixture ((Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash -ceq $cfgSha) "HEARTBEAT_NEVER_PROMOTES_ASK_EVERY_ACTION"
    Assert-FixtureClean "HEARTBEAT_WAIT_EXPIRY"
  }

  Reset-Fixture;$call=New-FixtureCall
  $cfg=Get-Content -Raw -LiteralPath $ConfigPath|ConvertFrom-Json
  $script:DeviceToken="SYNTHETIC_TOKEN_NEVER_SENT_TO_A_NETWORK"
  $script:SleepHook={
    $pendingReady=Get-FixturePending
    Set-FixtureElapsed 895
    Add-FixtureText ("APROVAR "+$pendingReady.challenge)
    Respond-ToLocalApprovalRequest
  }
  Assert-Fixture ((Invoke-LocalActionApproval $call $cfg $script:DeviceToken) -eq $true) "VALID_REPLY_AT_895_ACCEPTED_BEFORE_DUE_HEARTBEAT"
  Assert-Fixture ($script:HeartbeatCalls.Count -eq 0) "READY_REPLY_ACCEPTANCE_NEVER_BLOCKED_BY_NETWORK_HEARTBEAT"
  Assert-FixtureClean "REPLY_BEFORE_DUE_HEARTBEAT"

  Reset-Fixture;$cfg=Get-Content -Raw -LiteralPath $ConfigPath|ConvertFrom-Json
  $cfgSha=(Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
  Assert-Fixture ((Get-ApprovalMode $cfg) -ceq "ASK_EVERY_ACTION") "POLICY_REMAINS_ASK_EVERY_ACTION"
  $call=New-FixtureCall
  $script:SleepHook={
    $pendingReply=Get-FixturePending
    Set-FixtureElapsed 899.999
    Add-FixtureText "APROVAR"
    Respond-ToLocalApprovalRequest
  }
  Expect-FixtureException {Assert-StarterMutationAuthorized $cfg $call} "HUMAN_ACTION_APPROVAL_DENIED"
  Assert-Fixture ((Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash -ceq $cfgSha) "DENIAL_NEVER_PROMOTES_DEVICE_OR_SESSION_POLICY"
  Assert-FixtureClean "ASK_EVERY_ACTION_DENIAL"
  Assert-Fixture ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $sourceSha) "SOURCE_IMMUTABLE_AFTER_AST_CLOCK_FIXTURE"
  [ordered]@{
    schema="hara.commander-windows-approval-window49-fixture.v1";state="PASS"
    checks=$script:Passed;passed_checks=$script:Checks.ToArray()
    source_sha256=$sourceSha;powershell_version=$PSVersionTable.PSVersion.ToString()
    approval_timeout_seconds=$ApprovalTimeoutSeconds;clock_seam_replacements=$script:ClockSeams
    source_function_ast_real=$true;clock_and_keyboard_fixture_only=$true;consumer_liveness_fixture_adapter=$true;heartbeat_transport_and_telemetry_mocked=$true;source_main_loop_executed=$false
    real_task_touched=$false;live_profile_touched=$false;production_action_executed=$false
    real_human_approval_proven=$false;fifteen_minute_wall_clock_wait_performed=$false
  }|ConvertTo-Json -Depth 8 -Compress|Write-Output
} finally { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue }
