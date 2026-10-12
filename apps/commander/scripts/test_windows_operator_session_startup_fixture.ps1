# PS5.1 regression fixture: real source AST, synthetic profile and task adapters.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$AgentSource,
  [ValidateSet("Frozen047","Patched047Preview","Candidate049")][string]$ExpectedBehavior="Frozen047",
  [string]$ExpectedSourceSha256=""
)
$ErrorActionPreference="Stop"
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw "STARTUP_FIXTURE_REQUIRES_PS51" }
$source=(Resolve-Path -LiteralPath $AgentSource).Path
$sourceSha=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceText=[IO.File]::ReadAllText($source)
if ($ExpectedBehavior -ceq "Frozen047") {
  if ($sourceSha -cne "254517c46acf47102ebed5fe31fcb5d880ca0de47b98debeebdcaf4b1b324e36") { throw "STARTUP_FIXTURE_SOURCE47_NOT_FROZEN" }
} elseif ($ExpectedBehavior -ceq "Patched047Preview") {
  if ($sourceSha -cne "18aa91a75232752dc7e29b24423c8acbb886ac78ca83393503a282a66696f9ee") { throw "STARTUP_FIXTURE_PREVIEW_SOURCE_NOT_PINNED" }
} else {
  if ($ExpectedSourceSha256 -notmatch '^[0-9a-f]{64}$' -or $sourceSha -cne $ExpectedSourceSha256) { throw "STARTUP_FIXTURE_SOURCE49_NOT_PINNED" }
  if ($sourceText -notmatch '(?m)^\$AgentVersion = "0[.]3[.]49"$') { throw "STARTUP_FIXTURE_SOURCE49_VERSION_MISSING" }
}
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw "STARTUP_FIXTURE_PARSE_FAILED" }
$names=@("Get-OperatorProcess","Get-OperatorSession","Test-OperatorSessionActive","Start-ManualOperatorConsole")
$nodes=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -in $names},$false))
foreach($node in $nodes) { Invoke-Expression $node.Extent.Text }
foreach($name in $names) { if (-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)) { throw ("STARTUP_FIXTURE_FUNCTION_MISSING:"+$name) } }
# Only the real top-level start dispatch is copied into the child, never the
# profile initialization, agent loop, network, Task registration or UI code.
$dispatch=@($ast.EndBlock.Statements|Where-Object {
  $_ -is [Management.Automation.Language.IfStatementAst] -and $_.Extent.Text -match '^if \(\$args -contains "--session-start"' -and $_.Extent.Text -match 'Start-ManualOperatorConsole; exit 0'
})
if ($dispatch.Count -ne 1) { throw "STARTUP_FIXTURE_START_DISPATCH_NOT_UNIQUE" }
$fixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ("hara-operator-startup-fixture-"+[guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $fixtureRoot|Out-Null
$Root=$fixtureRoot
$SessionPath=Join-Path $Root "synthetic-operator.json"
$ConfigPath=Join-Path $Root "synthetic-config.json"
$PendingApprovalPath=Join-Path $Root "synthetic-pending.json"
$ApprovalResponsePath=Join-Path $Root "synthetic-response.json"
$AgentTaskName="SYNTHETIC_NEVER_REGISTERED_"+[guid]::NewGuid().ToString("N")
$SessionMaxHours=12
$script:Passed=0
$script:Checks=New-Object 'System.Collections.Generic.List[string]'
$script:Scenarios=New-Object 'System.Collections.Generic.List[object]'
$script:ExpectedPid=76543
$script:ProcessLookupCalls=0
$script:TaskState="Ready"
$script:TaskStarts=0;$script:TaskStops=0;$script:ConsoleCalls=0
$script:ProcessMetadata=$null
$script:LookupThrows=$false
$script:FixtureLookupError="SYNTHETIC_PROCESS_EXIT_RACE"
function Assert-Fixture([bool]$Condition,[string]$Code) {
  if (-not $Condition) { throw ("STARTUP_FIXTURE_ASSERT:"+$Code) }
  $script:Passed++;$script:Checks.Add($Code)
}
function Write-FixtureJson([string]$Path,$Value) {
  [IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
}
# Calls enter the real Get-OperatorProcess from the source; only the operating
# system process lookup is replaced. No fixture creates or stops a process.
function Get-Process {
  [CmdletBinding()]param([int]$Id)
  if ($Id -ne $script:ExpectedPid) { throw "STARTUP_FIXTURE_UNEXPECTED_PROCESS_LOOKUP" }
  $script:ProcessLookupCalls++
  if ($script:LookupThrows) { throw $script:FixtureLookupError }
  return $script:ProcessMetadata
}
function Get-ScheduledTask {
  [CmdletBinding()]param([string]$TaskName)
  if ($TaskName -cne $AgentTaskName) { throw "STARTUP_FIXTURE_REAL_TASK_DENIED" }
  return [pscustomobject]@{State=$script:TaskState;Triggers=@()}
}
function Start-ScheduledTask {
  [CmdletBinding()]param([string]$TaskName)
  if ($TaskName -cne $AgentTaskName) { throw "STARTUP_FIXTURE_REAL_TASK_DENIED" }
  $script:TaskStarts++;$script:TaskState="Running"
}
function Stop-ScheduledTask {
  [CmdletBinding()]param([string]$TaskName)
  if ($TaskName -cne $AgentTaskName) { throw "STARTUP_FIXTURE_REAL_TASK_DENIED" }
  $script:TaskStops++;$script:TaskState="Ready"
}
function Start-Sleep { param([int]$Seconds=0,[int]$Milliseconds=0) }
# Console creation is a boundary adapter. The stale session must not authorize
# reuse; the caller may request a fresh console, but this fixture opens none.
function Start-OperatorConsole([ref]$SessionOpened=$null) { $script:ConsoleCalls++ }
function Invoke-WithLocalApprovalLock([scriptblock]$Action) { throw "STARTUP_FIXTURE_UNEXPECTED_LOCK_BOUNDARY" }

try {
  $cfg=[ordered]@{device_id="SYNTHETIC_STARTUP_DEVICE";approval_mode="ASK_EVERY_ACTION";base_url="https://synthetic.invalid"}
  Write-FixtureJson $ConfigPath $cfg
  $configSha=(Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
  $started=[DateTime]::UtcNow.AddMinutes(-1)
  $ownerStarted=$started.AddMinutes(-2)
  $goodMarker=$ownerStarted.ToUniversalTime().ToString("o")
  $cases=@(
    @{Name="START_TIME_NULL";Pid=76543;Kind="NullStart";Throws047=$true},
    @{Name="START_TIME_MISSING";Pid=76543;Kind="MissingStart";Throws047=$true},
    @{Name="START_TIME_GETTER_THROWS";Pid=76543;Kind="ThrowingGetter";Throws047=$true},
    @{Name="PROCESS_EXIT_BEFORE_LOOKUP";Pid=76543;Kind="LookupThrows";Throws047=$false},
    @{Name="PROCESS_LOOKUP_NULL";Pid=76543;Kind="NoProcess";Throws047=$false},
    @{Name="OWNER_PID_INVALID_TEXT";Pid="not-a-pid";Kind="Good";Throws047=$true},
    @{Name="OWNER_PID_OVERFLOW";Pid="2147483648";Kind="Good";Throws047=$true},
    @{Name="OWNER_PID_ZERO";Pid=0;Kind="Good";Throws047=$false},
    @{Name="OWNER_PID_ONE";Pid=1;Kind="Good";Throws047=$false},
    @{Name="PID_REUSE_MARKER_MISMATCH";Pid=76543;Kind="Reused";Throws047=$false},
    @{Name="START_TIME_NOT_DATETIME";Pid=76543;Kind="WrongType";Throws047=$true},
    @{Name="VALID_ALIVE_DATETIME";Pid=76543;Kind="Good";Throws047=$false;Valid=$true}
  )
  foreach($case in $cases) {
    $session=[ordered]@{schema="hara.commander-operator-session.v1";owner_pid=$case.Pid;owner_started_at_utc=$goodMarker;started_at_utc=$started.ToUniversalTime().ToString("o");device_id=$cfg.device_id;authorization="LOCAL_OPERATOR_TERMINAL"}
    Write-FixtureJson $SessionPath $session
    $sessionSha=(Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash
    $script:LookupThrows=$false;$script:ProcessLookupCalls=0
    switch ($case.Kind) {
      "NullStart" {$script:ProcessMetadata=[pscustomobject]@{Id=76543;StartTime=$null}}
      "MissingStart" {$script:ProcessMetadata=[pscustomobject]@{Id=76543}}
      "ThrowingGetter" {
        $script:ProcessMetadata=[pscustomobject]@{Id=76543}
        Add-Member -InputObject $script:ProcessMetadata -MemberType ScriptProperty -Name StartTime -Value { throw "SYNTHETIC_START_TIME_GETTER_EXIT_RACE" }
      }
      "LookupThrows" {$script:ProcessMetadata=$null;$script:LookupThrows=$true}
      "NoProcess" {$script:ProcessMetadata=$null}
      "Reused" {$script:ProcessMetadata=[pscustomobject]@{Id=76543;StartTime=$ownerStarted.AddMinutes(1)}}
      "WrongType" {$script:ProcessMetadata=[pscustomobject]@{Id=76543;StartTime="not-datetime"}}
      default {$script:ProcessMetadata=[pscustomobject]@{Id=76543;StartTime=$ownerStarted}}
    }
    $errorId=$null;$lookup=$null
    try { $lookup=Get-OperatorSession } catch { $errorId=$_.FullyQualifiedErrorId }
    $frozenException=($ExpectedBehavior -ceq "Frozen047" -and $case.Throws047)
    if ($frozenException) {
      Assert-Fixture ($null -ne $errorId) ($case.Name+"_FROZEN047_FAILURE_REPRODUCED")
      Assert-Fixture ($null -eq $lookup) ($case.Name+"_FROZEN047_NO_SESSION_RETURNED")
    } else {
      Assert-Fixture ($null -eq $errorId) ($case.Name+"_NO_LOOKUP_EXCEPTION")
      Assert-Fixture (($null -ne $lookup) -eq [bool]$case.Valid) ($case.Name+$(if ($case.Valid) {"_VALID_SESSION_PRESERVED"} else {"_DENIED_NULL"}))
    }
    $active=$null;$activeError=$null
    try { $active=Test-OperatorSessionActive } catch { $activeError=$_.FullyQualifiedErrorId }
    if ($frozenException) { Assert-Fixture ($null -ne $activeError) ($case.Name+"_FROZEN047_ACTIVE_CHECK_FAILURE_REPRODUCED") }
    else { Assert-Fixture ($null -eq $activeError -and $active -eq [bool]$case.Valid) ($case.Name+"_ACTIVE_PREDICATE_FAILS_CLOSED") }
    Assert-Fixture ((Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash -ceq $sessionSha) ($case.Name+"_SESSION_NOT_REWRITTEN")
    Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) ($case.Name+"_NO_APPROVAL_IPC")
    $script:Scenarios.Add([ordered]@{name=$case.Name;lookup_error_id=$errorId;active_error_id=$activeError;session_returned=($null-ne $lookup);expected_valid=[bool]$case.Valid;process_lookup_calls=$script:ProcessLookupCalls})
  }

  # Reproduce the real source top-level `start` dispatch in a child whose only
  # side effects are fixture files. The screenshot's null metadata crashes .47
  # before any Task API; .48 must request a fresh console without reusing it.
  $childSource=Join-Path $Root "synthetic-top-level-start.ps1"
  $childTrace=Join-Path $Root "synthetic-top-level-start-result.json"
  $qRoot=$Root.Replace("'","''");$qTrace=$childTrace.Replace("'","''")
  $definitions=($nodes|ForEach-Object {$_.Extent.Text}) -join "`r`n"
  $childPrelude=@'
$ErrorActionPreference="Stop"
$Root='__ROOT__'
$ConfigPath=Join-Path $Root "synthetic-config.json"
$SessionPath=Join-Path $Root "synthetic-operator.json"
$SessionMaxHours=12
$AgentTaskName="SYNTHETIC_NEVER_REGISTERED_CHILD"
$Trace='__TRACE__'
$script:TaskStarts=0;$script:TaskStops=0;$script:ConsoleCalls=0
$script:TaskState="Ready"
function Get-Process { [CmdletBinding()]param([int]$Id) if($Id -ne 76543){throw "STARTUP_FIXTURE_REAL_PID_DENIED"}; return [pscustomobject]@{Id=76543;StartTime=$null} }
function Get-ScheduledTask { [CmdletBinding()]param([string]$TaskName) if($TaskName -cne $AgentTaskName){throw "STARTUP_FIXTURE_REAL_TASK_DENIED"}; return [pscustomobject]@{State=$script:TaskState;Triggers=@()} }
function Start-ScheduledTask { [CmdletBinding()]param([string]$TaskName) if($TaskName -cne $AgentTaskName){throw "STARTUP_FIXTURE_REAL_TASK_DENIED"}; $script:TaskStarts++;$script:TaskState="Running" }
function Stop-ScheduledTask { [CmdletBinding()]param([string]$TaskName) if($TaskName -cne $AgentTaskName){throw "STARTUP_FIXTURE_REAL_TASK_DENIED"}; $script:TaskStops++ }
function Start-Sleep { param([int]$Seconds=0,[int]$Milliseconds=0) }
function Invoke-WithLocalApprovalLock([scriptblock]$Action) { throw "STARTUP_FIXTURE_UNEXPECTED_LOCK_BOUNDARY" }
function Write-FixtureTrace([string]$ErrorId="") {
  [IO.File]::WriteAllText($Trace,([ordered]@{error_id=$ErrorId;task_starts=$script:TaskStarts;task_stops=$script:TaskStops;console_calls=$script:ConsoleCalls;task_state=$script:TaskState;args_start_dispatch=$true}|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
}
function Start-OperatorConsole([ref]$SessionOpened=$null) { $script:ConsoleCalls++;Write-FixtureTrace }
$args=@("start")
try {
'@
  $childPrelude=$childPrelude.Replace("__ROOT__",$qRoot).Replace("__TRACE__",$qTrace)
  $childTail=@'
} catch { Write-FixtureTrace ([string]$_.FullyQualifiedErrorId); exit 17 }
throw 'STARTUP_FIXTURE_TOP_LEVEL_DISPATCH_NOT_ENTERED'
'@
  $childText=$definitions+"`r`n"+$childPrelude+"`r`n"+$dispatch[0].Extent.Text+"`r`n"+$childTail
  Write-FixtureJson $SessionPath ([ordered]@{schema="hara.commander-operator-session.v1";owner_pid=76543;owner_started_at_utc=$goodMarker;started_at_utc=$started.ToUniversalTime().ToString("o");device_id=$cfg.device_id;authorization="LOCAL_OPERATOR_TERMINAL"})
  $childSessionSha=(Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash
  [IO.File]::WriteAllText($childSource,$childText,(New-Object Text.UTF8Encoding($false)))
  $childTokens=$null;$childParseErrors=$null
  [void][Management.Automation.Language.Parser]::ParseFile($childSource,[ref]$childTokens,[ref]$childParseErrors)
  Assert-Fixture ($childParseErrors.Count -eq 0) "ACTUAL_START_DISPATCH_CHILD_PARSES"
  & (Join-Path $PSHOME "powershell.exe") -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $childSource|Out-Null
  $childExit=$LASTEXITCODE
  Assert-Fixture (Test-Path -LiteralPath $childTrace -PathType Leaf) "ACTUAL_START_DISPATCH_CHILD_TRACE_EXISTS"
  $childResult=Get-Content -Raw -LiteralPath $childTrace|ConvertFrom-Json
  if ($ExpectedBehavior -ceq "Frozen047") {
    Assert-Fixture ($childExit -eq 17 -and [string]$childResult.error_id -match 'InvokeMethodOnNull') "FROZEN047_ACTUAL_TOP_LEVEL_START_NULL_FAILURE_REPRODUCED"
    Assert-Fixture ($childResult.task_starts -eq 0 -and $childResult.console_calls -eq 0) "FROZEN047_ACTUAL_START_CRASH_BEFORE_TASK_OR_CONSOLE"
  } else {
    Assert-Fixture ($childExit -eq 0 -and [string]::IsNullOrEmpty([string]$childResult.error_id)) "CANDIDATE_ACTUAL_TOP_LEVEL_START_NULL_METADATA_RETURNS"
    Assert-Fixture ($childResult.task_starts -eq 1 -and $childResult.console_calls -eq 1 -and $childResult.task_state -ceq "Running") "CANDIDATE_INVALID_STALE_SESSION_REQUESTS_FRESH_CONSOLE_BOUNDARY"
  }
  Assert-Fixture ($childResult.task_stops -eq 0) "ACTUAL_START_DISPATCH_NO_TASK_STOP"
  Assert-Fixture ((Get-FileHash -LiteralPath $SessionPath -Algorithm SHA256).Hash -ceq $childSessionSha) "ACTUAL_START_DISPATCH_STALE_IDENTITY_NOT_REAUTHORIZED_OR_REWRITTEN"
  Assert-Fixture ((Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash -ceq $configSha) "DEVICE_CONFIG_ASK_EVERY_ACTION_UNCHANGED"
  Assert-Fixture (-not (Test-Path -LiteralPath $PendingApprovalPath) -and -not (Test-Path -LiteralPath $ApprovalResponsePath)) "FIXTURE_NO_APPROVAL_IPC_CREATED"
  [ordered]@{
    schema="hara.commander-windows-operator-session-startup-fixture.v1";state="PASS"
    checks=$script:Passed;passed_checks=$script:Checks.ToArray();scenarios=$script:Scenarios.ToArray()
    expected_behavior=$ExpectedBehavior;source_sha256=$sourceSha;powershell_version=$PSVersionTable.PSVersion.ToString()
    actual_start_dispatch_child=$childResult;actual_start_dispatch_child_exit_code=$childExit
    source_function_and_start_dispatch_ast_real=$true;process_lookup_and_task_and_console_boundaries_mocked=$true
    source_main_loop_executed=$false;real_task_touched=$false;live_profile_touched=$false
    real_human_approval_proven=$false;production_action_executed=$false
    scope="REAL_AST_SESSION_LOOKUP_AND_TOP_LEVEL_START_DISPATCH_SYNTHETIC_PROFILE_AND_BOUNDARIES"
  }|ConvertTo-Json -Depth 8 -Compress|Write-Output
} finally {
  Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}
