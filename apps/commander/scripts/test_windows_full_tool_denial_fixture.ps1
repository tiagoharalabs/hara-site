# Diagnostic only: AST functions + the exact source call-dispatch try/catch.
# Does not dot-source or run Agent startup/main loop, tasks, real IPC or network.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$AgentSource)
$ErrorActionPreference="Stop"
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
  throw "FULL_TOOL_FIXTURE_REQUIRES_PS51"
}
$source=(Resolve-Path -LiteralPath $AgentSource).Path
$sourceSha=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceSha -cne "71998b7c5e2dae4f4cbcfe80e5413ab1c6ff8e28ad903734cc1f026dfe8765aa") {
  throw "FULL_TOOL_FIXTURE_SOURCE_NOT_FROZEN_046"
}
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw "FULL_TOOL_FIXTURE_PARSE_FAILED" }
$names=@("Get-OperatorProcess","Get-OperatorSession","Test-OperatorSessionActive",
  "Get-Utf8Sha256","Get-LocalActionSummary","Protect-LocalCommandPreview",
  "Get-ApprovalMode","Assert-StarterMutationAuthorized","Invoke-Tool",
  "Invoke-WindowsOneShotProcess","Start-WindowsManagedSession",
  "Cleanup-WindowsManagedSessions","Initialize-WindowsManagedProcessType",
  "New-DirectResult","Complete-Call","Write-ConsoleEvent",
  "Get-SafeErrorCode","Test-OperationalErrorCode")
$nodes=@($ast.FindAll({
  param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
  ($node.Name -match "LocalApproval|LocalActionApproval|Respond-ToLocalApprovalRequest" -or
   $node.Name -in $names)
},$false))
foreach($node in $nodes) { Invoke-Expression $node.Extent.Text }
foreach($name in $names) {
  if (-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)) {
    throw ("FULL_TOOL_FIXTURE_FUNCTION_MISSING:"+$name)
  }
}
# Take the real narrow call execution/error branch, not a reimplementation.
$branches=@($ast.FindAll({
  param($node)
  $node -is [Management.Automation.Language.TryStatementAst] -and
  $node.Body.Extent.Text -match '\$result=Invoke-Tool \$Cfg \$Call' -and
  $node.Extent.Text -match 'Complete-Call \$Cfg \$DeviceToken \$Call "FAILED"'
},$true)|Sort-Object {$_.Extent.EndOffset-$_.Extent.StartOffset})
if (-not $branches.Count) { throw "FULL_TOOL_FIXTURE_DISPATCH_AST_MISSING" }
$dispatch=$branches[0].Extent.Text
if ($dispatch -match 'while \(\$true\)|calls/next|calls/heartbeat|Get-Content -Raw -Path \$ConfigPath') {
  throw "FULL_TOOL_FIXTURE_DISPATCH_AST_TOO_BROAD"
}
Invoke-Expression ('function Invoke-FixtureCallBranch($Cfg,$Call) {'+$dispatch+'}')

$fixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-full-tool-denial-fixture-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $fixtureRoot|Out-Null
$Root=$fixtureRoot
$PendingApprovalPath=Join-Path $Root "synthetic-pending.json"
$ApprovalResponsePath=Join-Path $Root "synthetic-response.json"
$SessionPath=Join-Path $Root "synthetic-session.json"
$ConsoleEvents=Join-Path $Root "synthetic-console-events.jsonl"
$OperationsDb=Join-Path $Root "synthetic-operations.sqlite3"
$SessionMaxHours=12
$ApprovalTimeoutSeconds=5
$script:ManagedWindowsSessions=@{}
$script:WindowsSessionMaxActive=8
$script:WindowsSessionFinishedRetentionSeconds=900
$script:SleepHook=$null
$script:Passed=0
$script:Checks=New-Object 'System.Collections.Generic.List[string]'
$script:CompletionBodies=New-Object 'System.Collections.Generic.List[object]'
$script:ActivityEvents=New-Object 'System.Collections.Generic.List[object]'
$script:PublishedNegative=$false
$script:PublicationDeadlineValid=$false
$DeviceToken="SYNTHETIC_TOKEN_NEVER_SENT"

function Assert-Fixture([bool]$Condition,[string]$Code) {
  if (-not $Condition) { throw ("FULL_TOOL_FIXTURE_ASSERT:"+$Code) }
  $script:Passed++;$script:Checks.Add($Code)
}
function Write-FixtureJson([string]$Path,$Value) {
  [IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
}
function Reset-Fixture {
  foreach($file in @(Get-ChildItem -LiteralPath $Root -File)) { Remove-Item -LiteralPath $file.FullName -Force }
  $proc=Get-Process -Id $PID
  Write-FixtureJson $SessionPath ([ordered]@{
    schema="hara.commander-operator-session.v1";owner_pid=$PID
    owner_started_at_utc=$proc.StartTime.ToUniversalTime().ToString("o")
    started_at_utc=[DateTime]::UtcNow.ToString("o")
  })
  $script:CompletionBodies.Clear();$script:ActivityEvents.Clear()
  $script:PublishedNegative=$false;$script:PublicationDeadlineValid=$false
  $script:SleepHook=$null
}
# Only transport and telemetry-store boundary mocks: payloads remain in memory.
# No source Send-Json/network implementation was imported.
function Send-Json([string]$Url,[string]$Token,$Body,[int]$Timeout=25) {
  if ($Url -cne "https://synthetic.invalid/api/device/calls/complete") {
    throw "FULL_TOOL_FIXTURE_UNEXPECTED_TRANSPORT"
  }
  $script:CompletionBodies.Add($Body)
  return [pscustomobject]@{ok=$true}
}
function Write-LocalActivityEvent($Entry) { $script:ActivityEvents.Add($Entry) }
function New-Receipt { throw "FULL_TOOL_FIXTURE_UNEXPECTED_SUCCESS_RECEIPT" }
function Start-Sleep {
  param([int]$Milliseconds=0,[double]$Seconds=0)
  if ($script:SleepHook) {
    $hook=$script:SleepHook;$script:SleepHook=$null
    & $hook|Out-Null
  }
  if ($Milliseconds -gt 0) { Microsoft.PowerShell.Utility\Start-Sleep -Milliseconds $Milliseconds }
  elseif ($Seconds -gt 0) { Microsoft.PowerShell.Utility\Start-Sleep -Seconds $Seconds }
}

try {
  Assert-Fixture ($dispatch -match 'Write-ConsoleEvent "EXECUTING" \$Call "EXECUTING"') "SOURCE_DISPATCH_INCLUDES_EXECUTING"
  $cfg=[pscustomobject]@{
    approval_mode="ASK_EVERY_ACTION";device_id="SYNTHETIC_DEVICE_ONLY"
    base_url="https://synthetic.invalid";architecture="SYNTHETIC"
  }
  foreach($tool in @("hara.process.run","hara.process.start")) {
    Reset-Fixture
    $marker=Join-Path $Root ("MUST_NOT_EXECUTE_"+$tool.Replace(".","_")+".txt")
    $command="[IO.File]::WriteAllText('"+$marker.Replace("'","''")+"','UNEXPECTED_FIXTURE_EXECUTION')"
    $call=[pscustomobject]@{
      call_id=("SYNTHETIC-CALL-"+$tool);request_id=("SYNTHETIC-REQUEST-"+$tool)
      tool_id=$tool
      payload=[pscustomobject]@{command=$command;cwd=$Root;timeout_ms=1000;max_lines=20}
    }
    $script:SleepHook={
      $pending=Get-Content -Raw -LiteralPath $PendingApprovalPath|ConvertFrom-Json
      $script:PublicationDeadlineValid=[DateTime]::UtcNow -lt [DateTime]::Parse($pending.expires_at_utc).ToUniversalTime()
      $script:PublishedNegative=Publish-LocalApprovalResponse $pending $false
      $reply=Get-Content -Raw -LiteralPath $ApprovalResponsePath|ConvertFrom-Json
      if ($reply.approved -isnot [bool] -or $reply.approved -cne $false) {
        throw "FULL_TOOL_FIXTURE_NEGATIVE_REPLY_INVALID"
      }
    }
    Write-ConsoleEvent "RECEIVED" $call "PENDING"
    Invoke-FixtureCallBranch $cfg $call
    $prefix=$tool.Replace("hara.process.","").ToUpperInvariant()
    Assert-Fixture $script:PublicationDeadlineValid ($prefix+"_NEGATIVE_BEFORE_DEADLINE")
    Assert-Fixture $script:PublishedNegative ($prefix+"_NEGATIVE_REPLY_PUBLISHED")
    Assert-Fixture ($script:CompletionBodies.Count -eq 1) ($prefix+"_COMPLETE_CALLED_ONCE")
    $completion=$script:CompletionBodies[0]
    Assert-Fixture ($completion.state -ceq "FAILED") ($prefix+"_COMPLETE_STATE_FAILED")
    Assert-Fixture ($completion.error_code -ceq "HUMAN_ACTION_APPROVAL_DENIED") ($prefix+"_COMPLETE_HUMAN_DENIED_CODE")
    Assert-Fixture ($completion.result.state -ceq "DENIED" -and $completion.result.mutation_performed -ceq $false) ($prefix+"_RESULT_DENIED_NO_MUTATION")
    Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) ($prefix+"_OWNED_IPC_CLEANUP")
    Assert-Fixture (-not (Test-Path -LiteralPath $marker)) ($prefix+"_COMMAND_NEVER_EXECUTED")
    Assert-Fixture ($script:ManagedWindowsSessions.Count -eq 0) ($prefix+"_NO_MANAGED_PROCESS_CREATED")
    $events=@(Get-Content -LiteralPath $ConsoleEvents|ForEach-Object {$_|ConvertFrom-Json})
    Assert-Fixture (@($events|Where-Object {$_.event -ceq "EXECUTING"}).Count -eq 1) ($prefix+"_EXECUTING_EVENT_PRESENT")
    Assert-Fixture (@($events|Where-Object {$_.event -ceq "DENIED" -and $_.error_code -ceq "HUMAN_ACTION_APPROVAL_DENIED"}).Count -eq 1) ($prefix+"_DENIED_EVENT_PRESENT")
    Assert-Fixture (@($events|Where-Object {$_.event -ceq "PASS"}).Count -eq 0) ($prefix+"_NO_PASS_EVENT")
    if ($tool -ceq "hara.process.start") {
      Assert-Fixture ($null -ne ("HaraWindowsProcessSession" -as [type])) "START_REAL_CSHARP_WRAPPER_COMPILED_BEFORE_DENIAL"
    }
  }
  [ordered]@{
    schema="hara.commander-windows-full-tool-denial-fixture.v1"
    state="PASS";checks=$script:Passed;passed_checks=@($script:Checks)
    source_sha256=$sourceSha;powershell_version=$PSVersionTable.PSVersion.ToString()
    scope="FROZEN046_AST_FULL_TOOLS_AND_EXACT_DISPATCH_TRY_CATCH"
    transport_mocked=$true;local_activity_store_mocked=$true
    agent_main_loop_executed=$false;agent_task_touched=$false
    real_human_approval_proven=$false;live_profile_touched=$false
    production_action_executed=$false
  }|ConvertTo-Json -Depth 5 -Compress|Write-Output
} finally {
  $script:SleepHook=$null
  foreach($session in @($script:ManagedWindowsSessions.Values)) {
    try { $session.Child.Kill() } catch {}
    try { $session.Dispose() } catch {}
  }
  Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}
