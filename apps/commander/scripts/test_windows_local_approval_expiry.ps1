# Synthetic isolated tests: never dot-source or start a live Commander Agent.
# Runs on Windows PowerShell 5.1; extracts only approval-related function ASTs.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$AgentSource)
$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
  throw "FIXTURE_REQUIRES_WINDOWS_POWERSHELL_51"
}
$sourcePath = (Resolve-Path -LiteralPath $AgentSource).Path
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($sourcePath,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw "FIXTURE_CANDIDATE_PARSE_FAILED" }
$nodes=@($ast.FindAll({
  param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
  ($node.Name -match 'LocalApproval|LocalActionApproval|Respond-ToLocalApprovalRequest' -or
   $node.Name -in @("Get-OperatorProcess","Get-OperatorSession","Test-OperatorSessionActive",
                   "Get-Utf8Sha256","Get-LocalActionSummary","Protect-LocalCommandPreview",
                   "Get-ApprovalMode","Assert-StarterMutationAuthorized"))
},$false))
foreach($node in $nodes) { Invoke-Expression $node.Extent.Text }
$required=@("Invoke-WithLocalApprovalLock","Test-LocalApprovalRequestCurrent",
            "Initialize-LocalApprovalConsoleInput","Clear-LocalApprovalConsoleInput",
            "Read-LocalApprovalConsoleKey","Read-LocalApprovalResponse",
            "Publish-LocalApprovalResponse","Remove-LocalApprovalFiles",
            "Respond-ToLocalApprovalRequest","Invoke-LocalActionApproval",
            "Assert-StarterMutationAuthorized")
foreach($name in $required) {
  if (-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)) {
    throw ("FIXTURE_CANDIDATE_FUNCTION_MISSING:"+$name)
  }
}
$fixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-synthetic-approval-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
$Root=$fixtureRoot
$PendingApprovalPath=Join-Path $Root "pending-action-approval.json"
$ApprovalResponsePath=Join-Path $Root "action-approval-response.json"
$SessionPath=Join-Path $Root "operator-session.json"
$SessionMaxHours=12
$ApprovalTimeoutSeconds=0.5
$script:Passed=0
$script:Checks=New-Object 'System.Collections.Generic.List[string]'
$script:KeyHook=$null
$script:SleepHook=$null
$script:CleanupRaceHook=$null
$script:ReplacementProcess=$null
$script:Keys=New-Object 'System.Collections.Generic.Queue[System.ConsoleKeyInfo]'
$script:BufferedKeys=New-Object 'System.Collections.Generic.Queue[System.ConsoleKeyInfo]'
$script:ClearCount=0
$script:OriginalRead=(Get-Command Read-LocalApprovalResponse).ScriptBlock
$script:OriginalCleanup=(Get-Command Remove-LocalApprovalFiles).ScriptBlock

function Assert-Fixture([bool]$Condition,[string]$Code) {
  if (-not $Condition) { throw ("FIXTURE_ASSERT:"+$Code) }
  $script:Passed++
  $script:Checks.Add($Code)
}
function Write-FixtureJson([string]$Path,$Value) {
  [IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
}
function Copy-Fixture($Value) { return ($Value|ConvertTo-Json -Depth 8 -Compress|ConvertFrom-Json) }
function Reset-Fixture {
  foreach($file in @(Get-ChildItem -LiteralPath $Root -File)) { Remove-Item -LiteralPath $file.FullName -Force }
  $proc=Get-Process -Id $PID
  Write-FixtureJson $SessionPath ([ordered]@{
    schema="hara.commander-operator-session.v1";owner_pid=$PID
    owner_started_at_utc=$proc.StartTime.ToUniversalTime().ToString("o")
    started_at_utc=[DateTime]::UtcNow.ToString("o")
  })
  $script:KeyHook=$null; $script:SleepHook=$null; $script:CleanupRaceHook=$null
  $script:Keys.Clear(); $script:BufferedKeys.Clear(); $script:ClearCount=0
  Set-Item -Path Function:script:Read-LocalApprovalResponse -Value $script:OriginalRead
}
function New-FixturePending([double]$Seconds=5) {
  $session=Get-OperatorSession
  $nonce=[guid]::NewGuid().ToString("N")
  $pending=[pscustomobject][ordered]@{
    schema="hara.commander-local-action-approval.v1";nonce=$nonce
    challenge=$nonce.Substring(0,8).ToUpperInvariant()
    request_id="SYNTHETIC-"+[guid]::NewGuid().ToString("N");tool_id="hara.files.write"
    arguments_sha256=("b"*64);owner_pid=$PID
    owner_started_at_utc=[string]$session.owner_started_at_utc
    consumer_pid=$PID
    consumer_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString("o")
    created_at_utc=[DateTime]::UtcNow.ToString("o")
    expires_at_utc=[DateTime]::UtcNow.AddSeconds($Seconds).ToString("o")
    action_summary="SYNTHETIC_FIXTURE_ONLY_NO_CUSTOMER_ACTION"
  }
  Write-FixtureJson $PendingApprovalPath $pending
  return $pending
}
function Add-FixtureText([string]$Text,[bool]$Enter=$true) {
  foreach($c in $Text.ToCharArray()) {
    $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @($c,[ConsoleKey]::A,$false,$false,$false)))
  }
  if ($Enter) {
    $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @([char]13,[ConsoleKey]::Enter,$false,$false,$false)))
  }
}
function Expect-FixtureException([scriptblock]$Action,[string]$Code) {
  $caught=$null
  try { & $Action | Out-Null } catch { $caught=$_.Exception.Message }
  Assert-Fixture ($caught -eq $Code) ("THROWS_"+$Code)
}
# Test adapters exist only in this isolated harness. The Agent has no test switch.
function Initialize-LocalApprovalConsoleInput { return $true }
function Clear-LocalApprovalConsoleInput {
  $script:ClearCount++
  $script:BufferedKeys.Clear()
}
function Read-LocalApprovalConsoleKey {
  if ($script:KeyHook) { & $script:KeyHook | Out-Null }
  if ($script:Keys.Count) { return $script:Keys.Dequeue() }
  return $null
}
function Start-Sleep {
  param([int]$Milliseconds=0,[double]$Seconds=0)
  if ($script:SleepHook) {
    $hook=$script:SleepHook; $script:SleepHook=$null
    & $hook | Out-Null
  }
  if ($Milliseconds -gt 0) { Microsoft.PowerShell.Utility\Start-Sleep -Milliseconds $Milliseconds }
  elseif ($Seconds -gt 0) { Microsoft.PowerShell.Utility\Start-Sleep -Seconds $Seconds }
}
function Remove-LocalApprovalFiles([string]$Nonce) {
  & $script:OriginalCleanup $Nonce | Out-Null
  # Inject a synthetic race after actual cleanup releases the mutex.
  if ($script:CleanupRaceHook) {
    $hook=$script:CleanupRaceHook; $script:CleanupRaceHook=$null
    & $hook | Out-Null
  }
}

try {
  Reset-Fixture
  $pending=New-FixturePending
  Assert-Fixture (Test-LocalApprovalRequestCurrent $pending) "CURRENT_VALID_REQUEST"
  Assert-Fixture (Publish-LocalApprovalResponse $pending $true) "POSITIVE_FIXTURE_PUBLISHED"
  $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  Assert-Fixture ($reply.approved -ceq $true -and $reply.nonce -ceq $pending.nonce -and
    $reply.request_id -ceq $pending.request_id -and $reply.arguments_sha256 -ceq $pending.arguments_sha256) "POSITIVE_REPLY_BOUND"
  Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "REPLY_NEVER_OVERWRITTEN"

  Reset-Fixture
  $pending=New-FixturePending -1
  Assert-Fixture (-not (Test-LocalApprovalRequestCurrent $pending)) "EXPIRED_CURRENT_FALSE"
  Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "LATE_REPLY_NOT_PUBLISHED"
  Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "LATE_REPLY_FILE_ABSENT"

  foreach($field in @("schema","nonce","request_id","tool_id","arguments_sha256","owner_pid",
                     "owner_started_at_utc","consumer_pid","consumer_started_at_utc",
                     "created_at_utc","expires_at_utc","challenge","action_summary")) {
    Reset-Fixture
    $pending=New-FixturePending
    $replacement=Copy-Fixture $pending
    if ($field -in @("owner_pid","consumer_pid")) { $replacement.$field=$PID+1000000 }
    elseif ($field -eq "expires_at_utc") { $replacement.$field=[DateTime]::UtcNow.AddMinutes(1).ToString("o") }
    else { $replacement.$field=([string]$replacement.$field+"-REPLACED") }
    Write-FixtureJson $PendingApprovalPath $replacement
    Assert-Fixture (-not (Test-LocalApprovalRequestCurrent $pending)) ("REPLACEMENT_"+$field+"_REJECTED")
    Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) ("REPLACEMENT_"+$field+"_NO_REPLY")
  }

  foreach($field in @("owner_pid","owner_started_at_utc")) {
    Reset-Fixture
    $pending=New-FixturePending
    $session=Get-Content -Raw -LiteralPath $SessionPath|ConvertFrom-Json
    if ($field -eq "owner_pid") { $session.$field=$PID+1000000 }
    else { $session.$field=[DateTime]::UtcNow.AddMinutes(-1).ToString("o") }
    Write-FixtureJson $SessionPath $session
    Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) ("SESSION_"+$field+"_REVOKED")
  }

  Reset-Fixture
  $pending=New-FixturePending
  $script:SleepHook={
    $replacement=Copy-Fixture $pending
    $replacement.nonce="FOREIGN_SYNTHETIC_NONCE"
    Write-FixtureJson $PendingApprovalPath $replacement
  }
  # Publication checks under the same mutex; cleanup only removes owned nonce.
  $other=Copy-Fixture $pending; $other.nonce="FOREIGN_SYNTHETIC_NONCE"
  Write-FixtureJson $PendingApprovalPath $other
  Write-FixtureJson $ApprovalResponsePath @{nonce="FOREIGN_SYNTHETIC_NONCE";approved=$false}
  Remove-LocalApprovalFiles ([string]$pending.nonce)
  Assert-Fixture ((Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json).nonce -ceq "FOREIGN_SYNTHETIC_NONCE") "CLEANUP_PRESERVES_NEXT_PENDING"
  Assert-Fixture ((Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json).nonce -ceq "FOREIGN_SYNTHETIC_NONCE") "CLEANUP_PRESERVES_NEXT_REPLY"
  $script:SleepHook=$null

  Reset-Fixture
  $pending=New-FixturePending
  $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @([char]13,[ConsoleKey]::Enter,$false,$false,$false)))
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "SUBMITTED" -and [string]$answer.text -ceq "") "ENTER_SUBMITS_DENIAL"

  Reset-Fixture
  $pending=New-FixturePending
  Add-FixtureText ("APROVAR "+$pending.challenge)
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "SUBMITTED" -and $answer.text -ceq ("APROVAR "+$pending.challenge)) "EXACT_MANUAL_FIXTURE_INPUT"

  Reset-Fixture
  $pending=New-FixturePending
  Add-FixtureText ("APROVAR "+$pending.challenge+"X") $false
  $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @([char]8,[ConsoleKey]::Backspace,$false,$false,$false)))
  $script:Keys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @([char]13,[ConsoleKey]::Enter,$false,$false,$false)))
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "SUBMITTED" -and $answer.text -ceq ("APROVAR "+$pending.challenge)) "BACKSPACE_INPUT_EDIT"

  Reset-Fixture
  $pending=New-FixturePending 0.5
  $clock=[Diagnostics.Stopwatch]::StartNew()
  $answer=Read-LocalApprovalResponse $pending
  $clock.Stop()
  Assert-Fixture ($answer.state -ceq "EXPIRED" -and $null -eq $answer.text) "SILENCE_EXPIRES_WITHOUT_INPUT"
  Assert-Fixture ($clock.Elapsed.TotalSeconds -lt 3) "SILENCE_DEADLINE_BOUNDED"
  Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "SILENCE_NO_REPLY"

  Reset-Fixture
  $pending=New-FixturePending 0.5
  Add-FixtureText "APROVAR " $false
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "EXPIRED" -and $null -eq $answer.text) "PARTIAL_INPUT_DISCARDED_AT_DEADLINE"
  Assert-Fixture ($script:ClearCount -ge 2) "PARTIAL_INPUT_FINAL_DRAIN"

  Reset-Fixture
  $pending=New-FixturePending 0.5
  Add-FixtureText ("APROVAR "+$pending.challenge)
  $script:KeyHook={
    if ($script:Keys.Count -eq 1) {
      Microsoft.PowerShell.Utility\Start-Sleep -Milliseconds 600
      $script:KeyHook=$null
    }
  }
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "EXPIRED" -and $null -eq $answer.text) "ENTER_AFTER_DEADLINE_DISCARDED"
  Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "LATE_ENTER_NEVER_PUBLISHED"

  Reset-Fixture
  $pending=New-FixturePending
  $script:KeyHook={
    Remove-Item -LiteralPath $SessionPath -Force
    $script:KeyHook=$null
  }
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "EXPIRED") "SESSION_REVOKED_DURING_PROMPT"

  Reset-Fixture
  $pending=New-FixturePending
  $script:KeyHook={
    $replacement=Copy-Fixture $pending; $replacement.nonce="NEXT-SYNTHETIC"
    Write-FixtureJson $PendingApprovalPath $replacement
    $script:KeyHook=$null
  }
  Add-FixtureText ("APROVAR "+$pending.challenge)
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($answer.state -ceq "EXPIRED") "NONCE_SWAP_DURING_INPUT"
  Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "NONCE_SWAP_NEVER_APPROVES_NEXT"

  Reset-Fixture
  $pending=New-FixturePending
  function Read-LocalApprovalResponse($Pending) {
    $replacement=Copy-Fixture $Pending; $replacement.nonce="PUBLISH-RACE-SYNTHETIC"
    Write-FixtureJson $PendingApprovalPath $replacement
    return @{state="SUBMITTED";text=("APROVAR "+$Pending.challenge)}
  }
  $hostOutput=(& { Respond-ToLocalApprovalRequest } 6>&1|Out-String)
  Assert-Fixture ($hostOutput -notmatch "APROVACAO_INDIVIDUAL=(CONCEDIDA|ENVIADA)") "PUBLISH_RACE_NEVER_REPORTS_SENT"
  Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "PUBLISH_RACE_NO_REPLY"

  Reset-Fixture
  $pending=New-FixturePending
  Add-FixtureText ("APROVAR "+$pending.challenge)
  $hostOutput=(& { Respond-ToLocalApprovalRequest } 6>&1|Out-String)
  Assert-Fixture ($hostOutput -match "APROVACAO_INDIVIDUAL=ENVIADA" -and $hostOutput -notmatch "APROVACAO_INDIVIDUAL=CONCEDIDA") "SENT_ONLY_AFTER_PUBLISH"
  Assert-Fixture (Test-Path -LiteralPath $ApprovalResponsePath) "SENT_HAS_PUBLISHED_REPLY"

  Reset-Fixture
  $pending=New-FixturePending
  Add-FixtureText ("aprovar "+$pending.challenge)
  $hostOutput=(& { Respond-ToLocalApprovalRequest } 6>&1|Out-String)
  $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  Assert-Fixture ($reply.approved -ceq $false) "CHALLENGE_CASE_MISMATCH_DENIED"
  Assert-Fixture ($hostOutput -notmatch "APROVACAO_INDIVIDUAL=(CONCEDIDA|ENVIADA)") "CASE_MISMATCH_NEVER_REPORTS_SENT"

  Reset-Fixture
  $pending=New-FixturePending
  Add-FixtureText "APROVAR"
  $hostOutput=(& { Respond-ToLocalApprovalRequest } 6>&1|Out-String)
  $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
  Assert-Fixture ($reply.approved -ceq $false) "APROVAR_WITHOUT_CHALLENGE_DENIED"
  Assert-Fixture ($hostOutput -notmatch "APROVACAO_INDIVIDUAL=(CONCEDIDA|ENVIADA)") "APROVAR_ALONE_NEVER_REPORTS_SENT"

  Reset-Fixture
  $pending=New-FixturePending
  $script:BufferedKeys.Enqueue((New-Object ConsoleKeyInfo -ArgumentList @([char]13,[ConsoleKey]::Enter,$false,$false,$false)))
  Add-FixtureText ("APROVAR "+$pending.challenge)
  $answer=Read-LocalApprovalResponse $pending
  Assert-Fixture ($script:BufferedKeys.Count -eq 0 -and $script:ClearCount -ge 1) "NEXT_REQUEST_DRAINS_STALE_CONSOLE_KEYS"
  Assert-Fixture ($answer.text -ceq ("APROVAR "+$pending.challenge)) "NEXT_REQUEST_USES_NEW_CHALLENGE"

  $syntheticCall=[pscustomobject]@{
    request_id="SYNTHETIC-WORKER";tool_id="hara.files.create_directory"
    payload=@{path=(Join-Path $Root "NEVER_EXECUTED")}
  }
  Reset-Fixture
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    Publish-LocalApprovalResponse $p $true|Out-Null
  }
  Assert-Fixture (Invoke-LocalActionApproval $syntheticCall) "WORKER_ACCEPTS_BOUND_FIXTURE_RESPONSE"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "WORKER_SUCCESS_CLEANUP"

  $syntheticCall.request_id="SYNTHETIC-WORKER-NEXT"
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    Publish-LocalApprovalResponse $p $true|Out-Null
  }
  Assert-Fixture (Invoke-LocalActionApproval $syntheticCall) "WORKER_NEXT_REQUEST_AFTER_CLEANUP"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "WORKER_NEXT_REQUEST_CLEANUP"

  Reset-Fixture
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    Publish-LocalApprovalResponse $p $false|Out-Null
  }
  Expect-FixtureException {Invoke-LocalActionApproval $syntheticCall} "HUMAN_ACTION_APPROVAL_DENIED"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "WORKER_DENIAL_CLEANUP"

  Reset-Fixture
  Expect-FixtureException {Invoke-LocalActionApproval $syntheticCall} "LOCAL_ACTION_APPROVAL_EXPIRED"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "WORKER_EXPIRY_CLEANUP"

  Reset-Fixture
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    Publish-LocalApprovalResponse $p $true|Out-Null
    Remove-Item -LiteralPath $SessionPath -Force
  }
  Expect-FixtureException {Invoke-LocalActionApproval $syntheticCall} "LOCAL_OPERATOR_SESSION_REQUIRED"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "WORKER_SESSION_REVOCATION_CLEANUP"

  Reset-Fixture
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    $p.nonce="FOREIGN-WORKER-SYNTHETIC"
    Write-FixtureJson $PendingApprovalPath $p
  }
  Expect-FixtureException {Invoke-LocalActionApproval $syntheticCall} "LOCAL_ACTION_APPROVAL_REQUEST_CHANGED"
  Assert-Fixture ((Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json).nonce -ceq "FOREIGN-WORKER-SYNTHETIC") "WORKER_CLEANUP_PRESERVES_NEXT_REQUEST"

  # Only synthetic response files, with no transport or product operation.
  $ApprovalTimeoutSeconds=5
  foreach($variant in @("string_bool","request_id","arguments_sha256","owner_pid",
                       "owner_started_at_utc","consumer_pid","consumer_started_at_utc",
                       "time_before","time_after","time_future","time_invalid")) {
    Reset-Fixture
    $script:ResponseVariant=$variant
    $script:SleepHook={
      $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
      Publish-LocalApprovalResponse $p $true|Out-Null
      $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
      switch($script:ResponseVariant) {
        "string_bool" {$reply.approved="true"}
        "request_id" {$reply.request_id="OTHER-SYNTHETIC"}
        "arguments_sha256" {$reply.arguments_sha256=("c"*64)}
        "owner_pid" {$reply.owner_pid=$PID+1000000}
        "owner_started_at_utc" {$reply.owner_started_at_utc="OTHER-SYNTHETIC"}
        "consumer_pid" {$reply.consumer_pid=$PID+1000000}
        "consumer_started_at_utc" {$reply.consumer_started_at_utc="OTHER-SYNTHETIC-CONSUMER"}
        "time_before" {$reply.responded_at_utc=[DateTime]::Parse($p.created_at_utc).AddSeconds(-1).ToString("o")}
        "time_after" {$reply.responded_at_utc=[DateTime]::Parse($p.expires_at_utc).AddSeconds(1).ToString("o")}
        "time_future" {$reply.responded_at_utc=[DateTime]::UtcNow.AddSeconds(2).ToString("o")}
        "time_invalid" {$reply.responded_at_utc="INVALID-SYNTHETIC-DATE"}
      }
      Write-FixtureJson $ApprovalResponsePath $reply
    }
    Expect-FixtureException {Invoke-LocalActionApproval $syntheticCall} "LOCAL_ACTION_APPROVAL_RESPONSE_INVALID"
    Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
      -not (Test-Path -LiteralPath $ApprovalResponsePath)) ("INVALID_REPLY_"+$variant+"_CLEANUP")
  }
  $ApprovalTimeoutSeconds=0.5

  Reset-Fixture
  $script:ReplacementProcess=Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile","-NonInteractive","-Command","[Threading.Thread]::Sleep(15000)") -WindowStyle Hidden -PassThru
  try {
    $consumer=Get-Process -Id $script:ReplacementProcess.Id
    $marker=$consumer.StartTime.ToUniversalTime().ToString("o")
    $pending=New-FixturePending 5
    $pending.consumer_pid=$consumer.Id
    $pending.consumer_started_at_utc=$marker
    Write-FixtureJson $PendingApprovalPath $pending
    Assert-Fixture (Test-LocalApprovalRequestCurrent $pending) "DISTINCT_CONSUMER_PROCESS_ALIVE"
    $pending.consumer_started_at_utc=[DateTime]::UtcNow.AddMinutes(-1).ToString("o")
    Write-FixtureJson $PendingApprovalPath $pending
    Assert-Fixture (-not (Test-LocalApprovalRequestCurrent $pending)) "CONSUMER_START_MARKER_MISMATCH_REJECTED"
    Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "CONSUMER_REPLACED_MARKER_NO_REPLY"
    Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "CONSUMER_REPLACED_MARKER_REPLY_ABSENT"
    $pending.consumer_started_at_utc=$marker
    Write-FixtureJson $PendingApprovalPath $pending
    Assert-Fixture (Test-LocalApprovalRequestCurrent $pending) "CONSUMER_ORIGINAL_START_MARKER_RESTORED"
    Stop-Process -Id $script:ReplacementProcess.Id -Force -ErrorAction Stop
    $script:ReplacementProcess.WaitForExit(1000)|Out-Null
    Assert-Fixture (-not (Test-LocalApprovalRequestCurrent $pending)) "DEAD_CONSUMER_REQUEST_REJECTED"
    Assert-Fixture (-not (Publish-LocalApprovalResponse $pending $true)) "DEAD_CONSUMER_NEVER_PUBLISHES_REPLY"
    Assert-Fixture (-not (Test-Path -LiteralPath $ApprovalResponsePath)) "DEAD_CONSUMER_REPLY_ABSENT"
  } finally {
    if ($script:ReplacementProcess) {
      Stop-Process -Id $script:ReplacementProcess.Id -Force -ErrorAction SilentlyContinue
      $script:ReplacementProcess.Dispose()
      $script:ReplacementProcess=$null
    }
  }

  $ApprovalTimeoutSeconds=5
  $askConfig=[pscustomobject]@{approval_mode="ASK_EVERY_ACTION"}
  Reset-Fixture
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    Publish-LocalApprovalResponse $p $true|Out-Null
  }
  Assert-StarterMutationAuthorized $askConfig $syntheticCall
  Assert-Fixture $true "ASSERT_VALID_APPROVAL_AFTER_CLEANUP_CONTINUES"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "ASSERT_VALID_APPROVAL_CLEANUP"

  Reset-Fixture
  $script:SleepHook={
    $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
    Publish-LocalApprovalResponse $p $true|Out-Null
  }
  $script:CleanupRaceHook={ Remove-Item -LiteralPath $SessionPath -Force }
  Expect-FixtureException {Assert-StarterMutationAuthorized $askConfig $syntheticCall} "LOCAL_OPERATOR_SESSION_REQUIRED"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
    -not (Test-Path -LiteralPath $ApprovalResponsePath)) "REVOKE_AFTER_CLEANUP_REMOVES_OWN_APPROVAL"

  Reset-Fixture
  # One harmless fixture child supplies a genuinely live replacement PID/start.
  # It never imports the Agent, opens a transport, or executes a customer action.
  $script:ReplacementProcess=Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile","-NonInteractive","-Command","[Threading.Thread]::Sleep(15000)") -WindowStyle Hidden -PassThru
  try {
    $replacement=Get-Process -Id $script:ReplacementProcess.Id
    $script:ReplacementOwner=[pscustomobject]@{
      schema="hara.commander-operator-session.v1"
      owner_pid=$replacement.Id
      owner_started_at_utc=$replacement.StartTime.ToUniversalTime().ToString("o")
      started_at_utc=[DateTime]::UtcNow.ToString("o")
    }
    $script:SleepHook={
      $p=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
      Publish-LocalApprovalResponse $p $true|Out-Null
    }
    $script:CleanupRaceHook={ Write-FixtureJson $SessionPath $script:ReplacementOwner }
    Expect-FixtureException {Assert-StarterMutationAuthorized $askConfig $syntheticCall} "LOCAL_OPERATOR_SESSION_REQUIRED"
    $active=Get-OperatorSession
    Assert-Fixture ($null -ne $active -and $active.owner_pid -eq $script:ReplacementOwner.owner_pid) "REPLACEMENT_SESSION_IS_ACTUALLY_ACTIVE"
    Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and
      -not (Test-Path -LiteralPath $ApprovalResponsePath)) "ACTIVE_NEW_SESSION_NEVER_INHERITS_APPROVAL"
  } finally {
    if ($script:ReplacementProcess) {
      Stop-Process -Id $script:ReplacementProcess.Id -Force -ErrorAction SilentlyContinue
      $script:ReplacementProcess.Dispose()
      $script:ReplacementProcess=$null
    }
  }
  $ApprovalTimeoutSeconds=0.5

  Assert-Fixture (-not (Test-Path -LiteralPath (Join-Path $Root "NEVER_EXECUTED"))) "NO_PRODUCT_ACTION_EXECUTED"
  Assert-Fixture (@(Get-ChildItem -LiteralPath $Root -Filter "*.tmp" -File).Count -eq 0) "NO_PUBLICATION_TEMP_FILES"
  [ordered]@{
    schema="hara.commander-windows-approval-expiry-fixture.v1"
    state="PASS";checks=$script:Passed;passed_checks=@($script:Checks)
    powershell_version=$PSVersionTable.PSVersion.ToString()
    source_sha256=(Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    scope="ISOLATED_SYNTHETIC_AST_FUNCTIONS_ONLY"
    real_human_positive_approval_proven=$false;live_agent_modified=$false
    production_action_executed=$false
  }|ConvertTo-Json -Depth 5 -Compress|Write-Output
} finally {
  $script:SleepHook=$null; $script:KeyHook=$null; $script:CleanupRaceHook=$null
  if ($script:ReplacementProcess) {
    Stop-Process -Id $script:ReplacementProcess.Id -Force -ErrorAction SilentlyContinue
    $script:ReplacementProcess.Dispose()
  }
  Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}

