param(
  [Parameter(Mandatory=$true)][string]$AgentPath,
  [ValidateSet("Diagnostic","Candidate052")][string]$ExpectedBehavior="Diagnostic",
  [string]$ReportPath
)
$ErrorActionPreference="Stop"
$checks=New-Object System.Collections.Generic.List[object]
$ownedSessions=New-Object System.Collections.Generic.List[object]
$results=[ordered]@{}
$failure=$null
function Check([string]$Name,[bool]$Passed) {
  $checks.Add([ordered]@{name=$Name;passed=$Passed}) | Out-Null
  if (-not $Passed) { throw ("MANAGED_INPUT_FIXTURE_FAILED:"+$Name) }
}
function Source-Function($Ast,[string]$Name) {
  $found=@($Ast.FindAll({
    param($Node)
    $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -ceq $Name
  },$true))
  if ($found.Count -ne 1) { throw ("SOURCE_FUNCTION_NOT_UNIQUE:"+$Name) }
  return $found[0].Extent.Text
}
function Byte-Sha256([byte[]]$Bytes) {
  $a=[Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($a.ComputeHash($Bytes))).Replace("-","").ToLowerInvariant() }
  finally {$a.Dispose()}
}
function Wait-ManagedFixtureExit($Session,[int]$DeadlineMs=8000) {
  $deadline=[DateTime]::UtcNow.AddMilliseconds($DeadlineMs)
  $last=$Session.Snapshot(0,200,0)
  while ([DateTime]::UtcNow -lt $deadline) {
    if ([string]$last.state -eq "EXITED" -and -not [bool]$last.output_pending) { return $last }
    # Snapshot returns after any available line. Advance the offset and keep
    # polling until exit and both streams are drained, rather than asserting
    # exit after the first batch of asynchronous output.
    $next=$Session.Snapshot([int]$last.total_lines,200,200)
    $last=$Session.Snapshot(0,200,0)
    if ([string]$last.state -eq "RUNNING") { Start-Sleep -Milliseconds 20 }
  }
  return $last
}
function Get-WindowsManagedSession([string]$Id) {
  if ($Id -cne "FIXTURE_CAPTURE_ONLY") {throw "FIXTURE_SESSION_DENIED"}
  return $script:CaptureSession
}
function Assert-StarterMutationAuthorized($Cfg,$Call) {
  if (-not $Cfg.fixture -or [string]$Call.fixture -cne "MANAGED_INPUT_ISOLATED") {throw "FIXTURE_AUTHORIZATION_DENIED"}
  $script:ConsentGuardInvoked=$true
}
$script:CaptureSession=New-Object PSObject
$script:CaptureSession | Add-Member -MemberType ScriptMethod -Name Input -Value {
  param([string]$Value)
  $script:CapturedText=$Value
}
$script:CaptureSession | Add-Member -MemberType ScriptMethod -Name Snapshot -Value {
  param($Offset,$Length,$WaitMs)
  return @{state="RUNNING";total_lines=1;text="CAPTURE_ONLY"}
}
$agentBytes=[IO.File]::ReadAllBytes($AgentPath)
$agentSource=[Text.Encoding]::UTF8.GetString($agentBytes)
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($agentSource,[ref]$tokens,[ref]$parseErrors)
# Exact, independently specified ASCII payload from the live failed interaction.
$payload='1..120 | ForEach-Object { ''HARA49_LINE_{0:D3}'' -f $_ }; Write-Output ''HARA49_INTERACTION_PASS''; exit 0'
try {
  Check "native_windows_powershell_51" ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1)
  Check "source_parser_clean" ($parseErrors.Count -eq 0)
  $wrapper=Source-Function $ast "Send-WindowsManagedSessionInput"
  $initializer=Source-Function $ast "Initialize-WindowsManagedProcessType"
  . ([scriptblock]::Create($wrapper))
  $script:CapturedText=$null;$script:ConsentGuardInvoked=$false
  $snapshot=Send-WindowsManagedSessionInput @{fixture=$true} @{fixture="MANAGED_INPUT_ISOLATED"} "FIXTURE_CAPTURE_ONLY" $payload 0
  $results.wrapper_source=[ordered]@{
    captured_text=$script:CapturedText
    captured_length=([string]$script:CapturedText).Length
    expected_length=$payload.Length
    exact=([string]$script:CapturedText -ceq $payload)
    guard_invoked=$script:ConsentGuardInvoked
  }
  Check "original_wrapper_calls_consent_guard" $script:ConsentGuardInvoked
  if ($ExpectedBehavior -eq "Candidate052") {
    Check "current_wrapper_preserves_exact_payload" ([string]$script:CapturedText -ceq $payload)
  }
  # This local candidate is created only in the fixture process. It never edits
  # the source file, installed Agent, runtime session or consent policy.
  $candidate=$wrapper.Replace("function Send-WindowsManagedSessionInput(","function Send-WindowsManagedSessionInputCandidate(")
  $candidate=[regex]::Replace($candidate,'\$Input\b','$InputText')
  . ([scriptblock]::Create($candidate))
  $script:CapturedText=$null;$script:ConsentGuardInvoked=$false
  $snapshot=Send-WindowsManagedSessionInputCandidate @{fixture=$true} @{fixture="MANAGED_INPUT_ISOLATED"} "FIXTURE_CAPTURE_ONLY" $payload 0
  $results.wrapper_candidate=[ordered]@{
    captured_text=$script:CapturedText
    captured_length=([string]$script:CapturedText).Length
    expected_length=$payload.Length
    exact=([string]$script:CapturedText -ceq $payload)
    guard_invoked=$script:ConsentGuardInvoked
  }
  Check "renamed_wrapper_preserves_exact_payload" ([string]$script:CapturedText -ceq $payload)
  Check "renamed_wrapper_calls_consent_guard" $script:ConsentGuardInvoked
  . ([scriptblock]::Create($initializer))
  Initialize-WindowsManagedProcessType
  $session=New-Object HaraWindowsProcessSession -ArgumentList @("FIXTURE_NATIVE_DIRECT",$env:TEMP,"Write-Output 'HARA49_TERMINAL_READY'")
  $ownedSessions.Add($session) | Out-Null
  $ready=$session.Snapshot(0,200,3000)
  if ([string]$ready.text -notmatch "HARA49_TERMINAL_READY") {$ready=$session.Snapshot(0,200,3000)}
  Check "direct_child_initial_command_runs" ([string]$ready.text -match "HARA49_TERMINAL_READY")
  $session.Input($payload)
  $afterInput=Wait-ManagedFixtureExit $session 8000
  $results.direct_child_before_extra_blank=[ordered]@{
    state=$afterInput.state
    exit_code=$afterInput.exit_code
    total_lines=$afterInput.total_lines
    output_pending=$afterInput.output_pending
    generated_output=$afterInput.text
    marker=([string]$afterInput.text -match "HARA49_INTERACTION_PASS")
    line_120=([string]$afterInput.text -match "HARA49_LINE_120")
    requires_extra_blank=$false
  }
  if ([string]$afterInput.state -eq "RUNNING") {
    $session.Input("")
    $afterBlank=Wait-ManagedFixtureExit $session 8000
    $results.direct_child_after_extra_blank=[ordered]@{
      state=$afterBlank.state
      exit_code=$afterBlank.exit_code
      total_lines=$afterBlank.total_lines
      output_pending=$afterBlank.output_pending
      generated_output=$afterBlank.text
      marker=([string]$afterBlank.text -match "HARA49_INTERACTION_PASS")
      line_120=([string]$afterBlank.text -match "HARA49_LINE_120")
    }
    $results.direct_child_before_extra_blank.requires_extra_blank=([string]$afterBlank.state -eq "EXITED")
    $finalSnapshot=$afterBlank
  } else {$finalSnapshot=$afterInput}
  Check "direct_child_streams_fully_drained" (-not [bool]$finalSnapshot.output_pending)
  Check "direct_child_payload_eventually_exits_zero" ([string]$finalSnapshot.state -eq "EXITED" -and $finalSnapshot.exit_code -eq 0)
  Check "direct_child_preserves_120_output_lines" (@(([string]$finalSnapshot.text -split "\n") | Where-Object {$_ -match "^HARA49_LINE_[0-9]{3}$"}).Count -eq 120)
  Check "direct_child_interaction_marker_present" ([string]$finalSnapshot.text -match "HARA49_INTERACTION_PASS")
  $results.diagnosis=if (-not $results.wrapper_source.exact) {
    if ($results.direct_child_before_extra_blank.requires_extra_blank) {"AUTOMATIC_INPUT_VARIABLE_LOSS_AND_STDIN_BLANK_REQUIRED"}
    else {"AUTOMATIC_INPUT_VARIABLE_LOSS"}
  } elseif ($results.direct_child_before_extra_blank.requires_extra_blank) {"STDIN_BLANK_REQUIRED"} else {"SOURCE_AND_DIRECT_CHILD_PAYLOAD_VALID"}
} catch {$failure=$_.Exception.Message}
finally {
  foreach($session in $ownedSessions) {$session.Dispose()}
  $report=[ordered]@{
    schema="hara.commander.windows-managed-input-fixture.v1"
    state=$(if ($failure) {"FAIL"} else {"PASS"})
    source_sha256=(Byte-Sha256 $agentBytes)
    source_path=$AgentPath
    expected_behavior=$ExpectedBehavior
    powershell_version=$PSVersionTable.PSVersion.ToString()
    assertions=$checks.Count
    checks=@($checks.ToArray())
    observations=$results
    error=$failure
    agent_entrypoint_executed=$false
    installed_agent_modified=$false
    session_or_consent_state_modified=$false
    owned_children_disposed=$true
  }
  $json=$report | ConvertTo-Json -Depth 8 -Compress
  if ($ReportPath) {[IO.File]::WriteAllText($ReportPath,$json,(New-Object Text.UTF8Encoding($false)))}
  Write-Output $json
}
if ($failure) {throw $failure}
