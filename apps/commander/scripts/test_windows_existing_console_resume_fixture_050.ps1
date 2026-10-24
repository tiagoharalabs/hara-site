# Synthetic lifecycle fixture; no Agent startup/loop, real tasks, network or IPC.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AgentSource,
  [ValidateSet("Frozen046","Candidate047","Candidate050")][string]$ExpectedBehavior="Frozen046"
)
$ErrorActionPreference="Stop"
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
  throw "RESUME_FIXTURE_REQUIRES_PS51"
}
$source=(Resolve-Path -LiteralPath $AgentSource).Path
$sourceSha=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceText=[IO.File]::ReadAllText($source)
if ($ExpectedBehavior -ceq "Frozen046") {
  if ($sourceSha -cne "71998b7c5e2dae4f4cbcfe80e5413ab1c6ff8e28ad903734cc1f026dfe8765aa") {
    throw "RESUME_FIXTURE_SOURCE46_NOT_FROZEN"
  }
} else {
  if ($ExpectedBehavior -ceq "Candidate050" -and $sourceSha -cne "56a9b301e13328f0f840e1d4134343d309f317add92c22c546f39718ec844b60") {
    throw "RESUME_FIXTURE_SOURCE50_NOT_PINNED"
  }
  $expectedVersion=if ($ExpectedBehavior -ceq "Candidate050") {"50"} else {"47"}
  if ($sourceText -notmatch ('(?m)^\$AgentVersion = "0[.]3[.]'+$expectedVersion+'"$')) {
    throw ("RESUME_FIXTURE_SOURCE"+$expectedVersion+"_VERSION_MISSING")
  }
}
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw "RESUME_FIXTURE_PARSE_FAILED" }
$names=@("Start-ManualOperatorConsole","Start-OperatorConsole","Get-OperatorSession",
  "Get-OperatorProcess","Test-OperatorSessionActive","Get-Utf8Sha256",
  "Invoke-WithLocalApprovalLock","Show-OperatorSession","Get-ApprovalMode")
$nodes=@($ast.FindAll({
  param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names
},$false))
foreach($node in $nodes) { Invoke-Expression $node.Extent.Text }
foreach($name in $names) {
  if (-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)) {
    throw ("RESUME_FIXTURE_FUNCTION_MISSING:"+$name)
  }
}
$script:OriginalConsole=(Get-Command Start-OperatorConsole).ScriptBlock
$fixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-existing-console-resume-fixture-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $fixtureRoot|Out-Null
$Root=$fixtureRoot
$ConfigPath=Join-Path $Root "synthetic-device.json"
$SessionPath=Join-Path $Root "synthetic-session.json"
$PendingApprovalPath=Join-Path $Root "synthetic-pending.json"
$ApprovalResponsePath=Join-Path $Root "synthetic-response.json"
$ConsoleEvents=Join-Path $Root "synthetic-events.jsonl"
$AgentTaskName="SYNTHETIC_TASK_NEVER_REGISTERED_"+[guid]::NewGuid().ToString("N")
$SessionMaxHours=12
$AgentVersion=if ($ExpectedBehavior -ceq "Frozen046") {"0.3.46"} elseif ($ExpectedBehavior -ceq "Candidate050") {"0.3.50"} else {"0.3.47"}
$script:Passed=0
$script:Checks=New-Object 'System.Collections.Generic.List[string]'
$script:States=New-Object 'System.Collections.Generic.List[object]'
$script:FixtureChild=$null
$script:DropExistingAtStartup=$false
$script:CloseOwnOnPoll=$false
$script:SwapOtherOnPoll=$false

function Assert-Fixture([bool]$Condition,[string]$Code) {
  if (-not $Condition) { throw ("RESUME_FIXTURE_ASSERT:"+$Code) }
  $script:Passed++;$script:Checks.Add($Code)
}
function Write-FixtureJson([string]$Path,$Value) {
  [IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
}
# Task APIs are completely mocked and reject every nonsynthetic task name.
function Get-ScheduledTask {
  [CmdletBinding()]param([string]$TaskName)
  if ($TaskName -cne $AgentTaskName) { throw "RESUME_FIXTURE_REAL_TASK_NAME_DENIED" }
  return [pscustomobject]@{State=$script:TaskState;Triggers=@()}
}
function Start-ScheduledTask {
  [CmdletBinding()]param([string]$TaskName)
  if ($TaskName -cne $AgentTaskName) { throw "RESUME_FIXTURE_REAL_TASK_NAME_DENIED" }
  $script:Started++;$script:TaskState="Running"
}
function Stop-ScheduledTask {
  [CmdletBinding()]param([string]$TaskName)
  if ($TaskName -cne $AgentTaskName) { throw "RESUME_FIXTURE_REAL_TASK_NAME_DENIED" }
  $script:Stopped++;$script:TaskState="Ready"
}
function Start-Sleep {
  param([double]$Seconds=0,[int]$Milliseconds=0)
  if ($Seconds -gt 0 -and $script:DropExistingAtStartup) {
    $script:DropExistingAtStartup=$false
    Remove-Item -LiteralPath $SessionPath -Force
  }
  if ($Milliseconds -gt 0 -and $script:CloseOwnOnPoll) {
    $script:CloseOwnOnPoll=$false
    Remove-Item -LiteralPath $SessionPath -Force
  } elseif ($Milliseconds -gt 0 -and $script:SwapOtherOnPoll) {
    $script:SwapOtherOnPoll=$false
    Write-FixtureJson $SessionPath $script:ExistingFixtureSession
  }
}
# Synthetic console boundary adapters only; no approval or transport is invoked.
function Write-ConsoleEvent { param([string]$Event,$Call=$null,[string]$State="",[string]$ErrorCode="",[string]$ReceiptSha="") }
function Set-DeviceOffline { param($Cfg=$null) return $true }
function Respond-ToLocalApprovalRequest {
  if (Test-Path -LiteralPath $PendingApprovalPath) { throw "RESUME_FIXTURE_UNEXPECTED_APPROVAL_REQUEST" }
}
function Start-OperatorConsole([ref]$SessionOpened=$null) {
  $script:ConsoleCalled++
  & $script:OriginalConsole $SessionOpened
}

try {
  $cfg=[pscustomobject]@{
    approval_mode="ASK_EVERY_ACTION";device_id="SYNTHETIC_EXISTING_OPERATOR_DEVICE"
    base_url="https://synthetic.invalid";architecture="SYNTHETIC"
  }
  Write-FixtureJson $ConfigPath $cfg
  # An actual harmless sleeping child makes the other owner's session valid.
  $script:FixtureChild=Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList @("-NoProfile","-NonInteractive","-Command","[Threading.Thread]::Sleep(30000)") -WindowStyle Hidden -PassThru
  $owner=Get-Process -Id $script:FixtureChild.Id
  $session=[pscustomobject]@{
    schema="hara.commander-operator-session.v1";owner_pid=$owner.Id
    owner_started_at_utc=$owner.StartTime.ToUniversalTime().ToString("o")
    started_at_utc=[DateTime]::UtcNow.ToString("o")
    device_id=$cfg.device_id;authorization="LOCAL_OPERATOR_TERMINAL"
  }
  Write-FixtureJson $SessionPath $session
  $script:ExistingFixtureSession=$session
  $sessionSha=(Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash
  $configSha=(Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
  Assert-Fixture ($null -ne (Get-OperatorSession)) "EXISTING_OPERATOR_SESSION_GENUINELY_ACTIVE"
  foreach($initialState in @("Ready","Running")) {
    $script:TaskState=$initialState;$script:Started=0;$script:Stopped=0;$script:ConsoleCalled=0
    $errorCode=$null
    try { Start-ManualOperatorConsole } catch { $errorCode=$_.Exception.Message }
    $prefix=$initialState.ToUpperInvariant()
    if ($ExpectedBehavior -ceq "Frozen046") {
      Assert-Fixture ($errorCode -ceq "OPERATOR_SESSION_ALREADY_ACTIVE") ($prefix+"_FROZEN_ALREADY_ACTIVE_REPRODUCED")
      Assert-Fixture ($script:ConsoleCalled -eq 1) ($prefix+"_FROZEN_CONSOLE_CALLED")
      if ($initialState -ceq "Ready") {
        Assert-Fixture ($script:Started -eq 1 -and $script:Stopped -eq 1 -and $script:TaskState -ceq "Ready") "FROZEN046_RESUMED_AGENT_STOP_BUG_REPRODUCED"
      } else {
        Assert-Fixture ($script:Started -eq 0 -and $script:Stopped -eq 0 -and $script:TaskState -ceq "Running") "FROZEN046_RUNNING_AGENT_NOT_STOPPED"
      }
    } else {
      Assert-Fixture ($null -eq $errorCode) ($prefix+"_CANDIDATE_RESUME_RETURNS")
      Assert-Fixture ($script:ConsoleCalled -eq 0) ($prefix+"_CANDIDATE_EXISTING_CONSOLE_NOT_REPLACED")
      Assert-Fixture ($script:Stopped -eq 0 -and $script:TaskState -ceq "Running") ($prefix+"_CANDIDATE_AGENT_REMAINS_RUNNING")
      Assert-Fixture ($script:Started -eq $(if ($initialState -ceq "Ready") {1} else {0})) ($prefix+"_CANDIDATE_STARTS_ONLY_READY_AGENT")
    }
    Assert-Fixture ((Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash -ceq $sessionSha) ($prefix+"_SESSION_IDENTITY_UNCHANGED")
    Assert-Fixture ((Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash -ceq $configSha) ($prefix+"_DEVICE_CONFIG_UNCHANGED")
    Assert-Fixture ((Get-ApprovalMode (Get-Content -Raw -LiteralPath $ConfigPath|ConvertFrom-Json)) -ceq "ASK_EVERY_ACTION") ($prefix+"_ASK_EVERY_ACTION_PRESERVED")
    Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) ($prefix+"_NO_APPROVAL_IPC_CREATED")
    $script:States.Add([ordered]@{
      initial_task_state=$initialState;final_task_state=$script:TaskState
      started=$script:Started;stopped=$script:Stopped;console_called=$script:ConsoleCalled
      error_code=$errorCode
    })
  }
  if ($ExpectedBehavior -in @("Candidate047","Candidate050")) {
    # Existing console closes during the Task-start sleep: fresh lookup must
    # open this caller's own console, rather than reporting stale ACTIVE.
    Write-FixtureJson $SessionPath $script:ExistingFixtureSession
    $script:TaskState="Ready";$script:Started=0;$script:Stopped=0;$script:ConsoleCalled=0
    $script:DropExistingAtStartup=$true;$script:CloseOwnOnPoll=$true
    $errorCode=$null
    $hostOutput=(& {try {Start-ManualOperatorConsole} catch {$script:ScenarioError=$_.Exception.Message}} 6>&1|Out-String)
    $errorCode=$script:ScenarioError;$script:ScenarioError=$null
    Assert-Fixture ($null -eq $errorCode) "CLOSE_DURING_TASK_START_NEW_CONSOLE_RETURNS"
    Assert-Fixture ($script:ConsoleCalled -eq 1) "CLOSE_DURING_TASK_START_FRESH_CONSOLE_OPENED"
    Assert-Fixture ($script:Started -eq 1 -and $script:Stopped -eq 1 -and $script:TaskState -ceq "Ready") "OWN_CONSOLE_CLOSE_STOPS_OWN_TRIGGERLESS_TASK"
    Assert-Fixture ($hostOutput -notmatch "HARA_COMMANDER_AGENT=RESUMED") "CLOSE_DURING_TASK_START_NO_STALE_RESUMED_MESSAGE"
    Assert-Fixture ($null -eq (Get-OperatorSession)) "OWN_CONSOLE_CLOSE_REMOVES_OWN_SESSION"

    # A different active session replaces our console before its loop ends.
    # Source finally must preserve both that session and the running worker.
    Remove-Item -LiteralPath $SessionPath -Force -ErrorAction SilentlyContinue
    $script:TaskState="Ready";$script:Started=0;$script:Stopped=0;$script:ConsoleCalled=0
    $script:SwapOtherOnPoll=$true
    try {Start-ManualOperatorConsole} catch {$script:ScenarioError=$_.Exception.Message}
    $errorCode=$script:ScenarioError;$script:ScenarioError=$null
    Assert-Fixture ($null -eq $errorCode) "FOREIGN_SESSION_REPLACEMENT_CONSOLE_RETURNS"
    Assert-Fixture ($script:Started -eq 1 -and $script:Stopped -eq 0 -and $script:TaskState -ceq "Running") "FOREIGN_SESSION_REPLACEMENT_PRESERVES_RUNNING_TASK"
    Assert-Fixture ($script:ConsoleCalled -eq 1) "FOREIGN_SESSION_REPLACEMENT_ACTUAL_CONSOLE_PATH_USED"
    Assert-Fixture ((Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash -ceq $sessionSha) "FOREIGN_SESSION_REPLACEMENT_IDENTITY_PRESERVED"
    Assert-Fixture ((Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash -ceq $configSha -and (Get-ApprovalMode $cfg) -ceq "ASK_EVERY_ACTION") "RACE_DEVICE_IDENTITY_AND_POLICY_UNCHANGED"
  }
  [ordered]@{
    schema="hara.commander-windows-existing-console-resume-fixture.v1"
    state="PASS";checks=$script:Passed;passed_checks=@($script:Checks)
    expected_behavior=$ExpectedBehavior;scenarios=$script:States.ToArray()
    source_sha256=$sourceSha;powershell_version=$PSVersionTable.PSVersion.ToString()
    scope="SYNTHETIC_TASK_APIS_REAL_AST_MANUAL_AND_OPERATOR_SESSION_FUNCTIONS"
    frozen046_bug_reproduced=($ExpectedBehavior -ceq "Frozen046")
    task_apis_mocked=$true;console_event_and_offline_boundaries_mocked=$true
    agent_main_loop_executed=$false
    real_task_touched=$false;live_profile_touched=$false
    real_human_approval_proven=$false;production_action_executed=$false
  }|ConvertTo-Json -Depth 6 -Compress|Write-Output
} finally {
  if ($script:FixtureChild) {
    Stop-Process -Id $script:FixtureChild.Id -Force -ErrorAction SilentlyContinue
    $script:FixtureChild.Dispose()
  }
  Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}
