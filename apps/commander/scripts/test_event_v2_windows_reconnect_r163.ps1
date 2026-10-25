param([string]$SourcePath = (Join-Path $PSScriptRoot "../experimental/event_v2_windows_agent.ps1"))

# #163 P0-1: AST-selected functions and literal policy only. Never dot-source
# the Agent, import the installed baseline, use DPAPI, open a socket or install.
# Portable PowerShell is source QA; it does not attest native Windows 11.
$ErrorActionPreference = "Stop"
$SourcePath = [IO.Path]::GetFullPath($SourcePath)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw "TEST_AGENT_AST_PARSE_FAILED" }
$script:SourceFunctions = @{}
foreach ($node in $ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)) {
  $script:SourceFunctions[$node.Name] = $node
}

$script:InitialPolicy = @{}
foreach ($name in @("ReconnectBaseSeconds","ReconnectMaxSeconds","ReconnectMinimumSeconds","ReconnectStartupSpreadSeconds","StableConnectionSeconds")) {
  $assignment = @($ast.EndBlock.Statements | Where-Object {
    $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $_.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
    $_.Left.VariablePath.UserPath -eq $name
  })
  if ($assignment.Count -eq 1 -and
      $assignment[0].Right -is [System.Management.Automation.Language.CommandExpressionAst] -and
      $assignment[0].Right.Expression -is [System.Management.Automation.Language.ConstantExpressionAst]) {
    $script:InitialPolicy[$name] = $assignment[0].Right.Expression.Value
  } else {
    $script:InitialPolicy[$name] = $null
  }
  Set-Variable -Scope Script -Name $name -Value $script:InitialPolicy[$name]
}

# Import only these four function definitions; imports/CLI/other Agent helpers
# are never evaluated. Renaming delay lets the loop test observe its real calls.
foreach ($name in @("Get-EventV2RandomUnit","Get-ReconnectDelaySeconds","Get-EventV2StartupDelaySeconds","Start-EventV2ReconnectLoop")) {
  if (-not $script:SourceFunctions.ContainsKey($name)) { continue }
  $text = $script:SourceFunctions[$name].Extent.Text
  if ($name -eq "Get-ReconnectDelaySeconds") {
    $text = $text -replace '^function\s+Get-ReconnectDelaySeconds','function Invoke-TestActualReconnectDelay'
  } elseif ($name -eq "Get-EventV2RandomUnit") {
    $text = $text -replace '^function\s+Get-EventV2RandomUnit','function Invoke-TestActualRandomUnit'
  }
  . ([scriptblock]::Create($text))
}

$script:Results = [Collections.Generic.List[object]]::new()
$script:Unit = 0.5
$script:Attempts = [Collections.Generic.List[object]]::new()
$script:Events = [Collections.Generic.List[object]]::new()
$script:Sleeps = [Collections.Generic.List[double]]::new()
$script:SessionDurations = @()
$script:SessionIndex = 0
$script:TestNow = 0.0
$script:ShutdownRequested = $false

function Assert-Test($Condition,[string]$Reason) {
  if (-not $Condition) { throw ("TEST_ASSERT:"+$Reason) }
}
function Assert-Near($Actual,[double]$Expected,[string]$Reason) {
  Assert-Test ($null -ne $Actual -and -not [double]::IsNaN([double]$Actual) -and
    -not [double]::IsInfinity([double]$Actual)) ($Reason+":not-finite")
  Assert-Test ([Math]::Abs([double]$Actual-$Expected) -lt 0.000001) ($Reason+":actual="+$Actual+":expected="+$Expected)
}
function Assert-SourceApi([string]$Name) {
  Assert-Test ($script:SourceFunctions.ContainsKey($Name)) ("SOURCE_API_MISSING:"+$Name)
}
function Assert-Throws([scriptblock]$Body,[string]$Reason) {
  $blocked = $false
  try { & $Body | Out-Null } catch { $blocked = $true }
  Assert-Test $blocked $Reason
}
function Check([string]$Name,[scriptblock]$Body) {
  try {
    & $Body
    $script:Results.Add([pscustomobject]@{name=$Name;state="PASS"})
    Write-Output ("PASS "+$Name)
  } catch {
    $script:Results.Add([pscustomobject]@{name=$Name;state="FAIL";reason=$_.Exception.Message})
    Write-Output ("FAIL "+$Name+": "+$_.Exception.Message)
  }
}

# Test boundary stubs. A loop can call only the synthetic session and clock;
# no installed Agent, configuration, DPAPI, disk mutation or network is used.
function Get-EventV2RandomUnit { return $script:Unit }
function Get-ReconnectDelaySeconds($Attempt) {
  Assert-SourceApi "Get-ReconnectDelaySeconds"
  $script:Attempts.Add($Attempt)
  return Invoke-TestActualReconnectDelay -Attempt $Attempt
}
function Get-EventV2Config { return [pscustomobject]@{base_url="https://synthetic.invalid";device_id="SYNTHETIC"} }
function Get-DeviceToken($Cfg) { return "synthetic-test-only-not-a-device-token" }
function Get-SafeErrorCode($Record) { return [string]$Record.Exception.Message }
function Try-SetRuntimeStatus($ErrorCode,$ErrorAt) { return $true }
function Set-EventV2Status($Connected,$ConnectedAtUtc,$DisconnectedAtUtc,$ErrorCode) {}
function Get-EventV2Monotonic { return $script:TestNow }
function Import-StableAgentFunctions { throw "TEST_FORBIDDEN_INSTALLED_AGENT_IMPORT" }
function Connect-EventV2Client { throw "TEST_FORBIDDEN_NETWORK" }
function Invoke-ConnectedSession($Cfg,[string]$Token) {
  $script:Events.Add([pscustomobject]@{kind="CONNECT";at=$script:TestNow})
  if ($script:SessionIndex -ge $script:SessionDurations.Count) {
    throw "WINDOWS_EVENT_V2_LOCAL_SHUTDOWN_REQUESTED"
  }
  $script:TestNow += [double]$script:SessionDurations[$script:SessionIndex]
  $script:SessionIndex += 1
  throw "SYNTHETIC_CONNECTION_FAILED"
}
function Start-Sleep($Milliseconds,$Seconds) {
  if ($script:Sleeps.Count -ge 32) { throw "TEST_RECONNECT_LOOP_DID_NOT_STOP" }
  $duration = if ($null -ne $Milliseconds) { [double]$Milliseconds/1000.0 } else { [double]$Seconds }
  $script:Sleeps.Add($duration)
  $script:Events.Add([pscustomobject]@{kind="SLEEP";seconds=$duration})
  $script:TestNow += $duration
}
function Invoke-TestLoop($Durations) {
  Assert-SourceApi "Start-EventV2ReconnectLoop"
  $script:Unit = 0.5
  $script:SessionDurations = @($Durations)
  $script:SessionIndex = 0
  $script:TestNow = 0.0
  $script:ShutdownRequested = $false
  $script:Attempts.Clear(); $script:Sleeps.Clear(); $script:Events.Clear()
  Start-EventV2ReconnectLoop
}

Check "AST_source_parses_without_importing_Agent_or_CLI" {
  Assert-Test ($parseErrors.Count -eq 0) "agent source did not parse"
  Assert-Test ($script:SourceFunctions.ContainsKey("Import-StableAgentFunctions")) "fixture source not the full Agent"
}
foreach ($api in @("Get-EventV2RandomUnit","Get-ReconnectDelaySeconds","Get-EventV2StartupDelaySeconds","Start-EventV2ReconnectLoop")) {
  Check ("source_API_"+$api) { Assert-SourceApi $api }
}
Check "source_CLI_calls_encapsulated_loop_without_duplicate_top_level_loop" {
  $topLoops = @($ast.EndBlock.Statements | Where-Object {$_ -is [System.Management.Automation.Language.WhileStatementAst]})
  Assert-Test ($topLoops.Count -eq 0) "CLI still owns an independent reconnect loop"
  $commands = @($ast.EndBlock.Statements | Where-Object {
    $_ -is [System.Management.Automation.Language.PipelineAst] -and
    $_.PipelineElements.Count -eq 1 -and
    $_.PipelineElements[0] -is [System.Management.Automation.Language.CommandAst] -and
    $_.PipelineElements[0].GetCommandName() -eq "Start-EventV2ReconnectLoop"
  })
  Assert-Test ($commands.Count -eq 1) "CLI does not invoke the tested reconnect loop exactly once"
}
foreach ($pair in @(
  @("ReconnectBaseSeconds",60.0),@("ReconnectMaxSeconds",120.0),
  @("ReconnectMinimumSeconds",1.0),@("ReconnectStartupSpreadSeconds",120.0)
)) {
  Check ("source_policy_"+$pair[0]) { Assert-Near $script:InitialPolicy[$pair[0]] $pair[1] "wrong client policy constant" }
}
Check "production_random_unit_uses_crypto_and_stays_in_half_open_interval" {
  Assert-SourceApi "Get-EventV2RandomUnit"
  $definition = $script:SourceFunctions["Get-EventV2RandomUnit"].Extent.Text
  Assert-Test ($definition -match 'RandomNumberGenerator') "cryptographic RNG absent"
  Assert-Test ($definition -notmatch '\bGet-Random\b') "non-cryptographic RNG present"
  for ($n=0;$n -lt 128;$n++) {
    $value = Invoke-TestActualRandomUnit
    Assert-Test ($value -isnot [bool] -and $value -ge 0 -and $value -lt 1) "crypto random outside [0,1)"
  }
}
foreach ($row in @(
  @(0,0.0,1.0),@(0,0.5,30.5),@(1,0.5,60.5),@(2,0.5,60.5),
  @(31,0.5,60.5),@(0,0.999,59.941),@(1,0.999,119.881)
)) {
  Check ("delay_attempt_"+$row[0]+"_entropy_"+$row[1]) {
    $script:Unit = $row[1]
    Assert-Near (Get-ReconnectDelaySeconds -Attempt $row[0]) $row[2] "reconnect formula or first-attempt semantics"
  }
}
foreach ($row in @(@(0.0,0.0),@(0.5,60.0),@(0.999,119.88))) {
  Check ("startup_spread_entropy_"+$row[0]) {
    Assert-SourceApi "Get-EventV2StartupDelaySeconds"
    $script:Unit = $row[0]
    Assert-Near (Get-EventV2StartupDelaySeconds) $row[1] "startup spread"
  }
}
foreach ($attempt in @($false,$true,-1,0.0,1.5,[double]::NaN,[double]::PositiveInfinity,$null,"0")) {
  Check ("invalid_attempt_"+[string]$attempt+"_type_"+$(if($null -eq $attempt){"null"}else{$attempt.GetType().Name})) {
    $script:Unit = 0.5
    Assert-Throws { Get-ReconnectDelaySeconds -Attempt $attempt } "coerced invalid attempt was accepted"
  }
}
foreach ($entropy in @([double]::NaN,[double]::PositiveInfinity,[double]::NegativeInfinity,-0.001,1.0,$false,$true,$null,"0.5")) {
  Check ("invalid_entropy_delay_"+[string]$entropy+"_type_"+$(if($null -eq $entropy){"null"}else{$entropy.GetType().Name})) {
    $script:Unit = $entropy
    Assert-Throws { Get-ReconnectDelaySeconds -Attempt 0 } "invalid random unit was accepted by reconnect"
  }
  Check ("invalid_entropy_startup_"+[string]$entropy+"_type_"+$(if($null -eq $entropy){"null"}else{$entropy.GetType().Name})) {
    Assert-SourceApi "Get-EventV2StartupDelaySeconds"
    $script:Unit = $entropy
    Assert-Throws { Get-EventV2StartupDelaySeconds } "invalid random unit was accepted by startup"
  }
}
Check "loop_spreads_initial_connection_once_before_first_upgrade" {
  Invoke-TestLoop @()
  Assert-Test (($script:Sleeps -join ",") -eq "60") "startup spreading missing or repeated"
  Assert-Test ($script:Events.Count -eq 2 -and $script:Events[0].kind -eq "SLEEP" -and $script:Events[1].kind -eq "CONNECT") "Upgrade happened before startup delay"
  Assert-Near $script:Events[1].at 60.0 "first Upgrade timestamp"
}
Check "loop_first_retry_uses_zero_then_increments_after_delay" {
  Invoke-TestLoop @(0.0,0.0,0.0)
  Assert-Test (($script:Attempts -join ",") -eq "0,1,2") ("wrong retry indices:"+($script:Attempts -join ","))
  Assert-Test (($script:Sleeps -join ",") -eq "60,30.5,60.5,60.5") ("wrong retry/startup sleeps:"+($script:Sleeps -join ","))
  Assert-Test $script:ShutdownRequested "local shutdown sentinel was not honored"
}
Check "loop_stable_60_second_session_resets_retry_to_zero" {
  Invoke-TestLoop @(0.0,0.0,60.0)
  Assert-Test (($script:Attempts -join ",") -eq "0,1,0") ("stable reset used wrong indices:"+($script:Attempts -join ","))
  Assert-Test (($script:Sleeps -join ",") -eq "60,30.5,60.5,30.5") "stable reset lost the first-attempt delay"
}

$failed = @($script:Results | Where-Object {$_.state -eq "FAIL"})
[ordered]@{schema="hara.commander.event-v2.windows-reconnect-test.v1";scope="SOURCE_ONLY_AST_PORTABLE_PWSH";
  native_windows_acceptance=$false;tests=$script:Results.Count;pass=$script:Results.Count-$failed.Count;
  fail=$failed.Count;failures=@($failed)} | ConvertTo-Json -Depth 5 -Compress
if ($failed.Count -gt 0) { exit 1 }
