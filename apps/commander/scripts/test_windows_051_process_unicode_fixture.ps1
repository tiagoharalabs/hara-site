param(
  [Parameter(Mandatory=$true)][string]$AgentPath,
  [string]$ReportPath
)
$ErrorActionPreference="Stop"
$checks=New-Object System.Collections.Generic.List[object]
$ownedSessions=New-Object System.Collections.Generic.List[object]
$observations=[ordered]@{}
$failure=$null
function Check([string]$Name,[bool]$Passed) {
  $checks.Add([ordered]@{name=$Name;passed=$Passed}) | Out-Null
  if (-not $Passed) {throw ("PROCESS_UNICODE_FIXTURE_FAILED:"+$Name)}
}
function Source-Function($Ast,[string]$Name) {
  $found=@($Ast.FindAll({
    param($Node)
    $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -ceq $Name
  },$true))
  if ($found.Count -ne 1) {throw ("SOURCE_FUNCTION_NOT_UNIQUE:"+$Name)}
  return $found[0].Extent.Text
}
function Byte-Sha256([byte[]]$Bytes) {
  $a=[Security.Cryptography.SHA256]::Create()
  try {return ([BitConverter]::ToString($a.ComputeHash($Bytes))).Replace("-","").ToLowerInvariant()}
  finally {$a.Dispose()}
}
function Assert-StarterMutationAuthorized($Cfg,$Call) {
  if (-not $Cfg.fixture -or [string]$Call.fixture -cne "PROCESS_UNICODE_ISOLATED") {throw "FIXTURE_AUTHORIZATION_DENIED"}
}
function Wait-ManagedFixtureExit($Session,[int]$DeadlineMs=8000) {
  $deadline=[DateTime]::UtcNow.AddMilliseconds($DeadlineMs)
  $last=$Session.Snapshot(0,200,0)
  while ([DateTime]::UtcNow -lt $deadline) {
    if ([string]$last.state -eq "EXITED" -and -not [bool]$last.output_pending) {return $last}
    $next=$Session.Snapshot([int]$last.total_lines,200,200)
    $last=$Session.Snapshot(0,200,0)
    if ([string]$last.state -eq "RUNNING") {Start-Sleep -Milliseconds 20}
  }
  return $last
}
$agentBytes=[IO.File]::ReadAllBytes($AgentPath)
$source=[Text.Encoding]::UTF8.GetString($agentBytes)
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$parseErrors)
# ASCII command constructs Unicode in the child: no HTTP or non-ASCII payload
# can affect this independent process encoding control.
$command='$ProgressPreference=''SilentlyContinue''; Write-Output (''Ol''+[char]0x00E1+'' - a''+[char]0x00E7+[char]0x00E3+''o - ''+[char]::ConvertFromUtf32(0x1F680))'
$expected="Ol"+[char]0x00E1+" - a"+[char]0x00E7+[char]0x00E3+"o - "+[char]::ConvertFromUtf32(0x1F680)
try {
  Check "native_windows_powershell_51" ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1)
  Check "source_parser_clean" ($parseErrors.Count -eq 0)
  foreach($name in @("Get-Utf8Sha256","Invoke-WindowsOneShotProcess","Initialize-WindowsManagedProcessType")) {
    . ([scriptblock]::Create((Source-Function $ast $name)))
  }
  $single=Invoke-WindowsOneShotProcess @{fixture=$true} @{fixture="PROCESS_UNICODE_ISOLATED"} $command $env:TEMP 10000 200
  $singleText=([string]$single.text).TrimEnd([char]13,[char]10)
  $observations.one_shot=[ordered]@{
    state=$single.state
    exit_code=$single.exit_code
    output_text=$singleText
    utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($singleText))
    expected_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($expected))
    exact=($singleText -ceq $expected)
    command_sha256=$single.command_sha256
    expected_command_sha256=Get-Utf8Sha256 $command
  }
  Initialize-WindowsManagedProcessType
  $session=New-Object HaraWindowsProcessSession -ArgumentList @("FIXTURE_PROCESS_UNICODE",$env:TEMP,($command+"; exit 0"))
  $ownedSessions.Add($session) | Out-Null
  $managed=Wait-ManagedFixtureExit $session 8000
  $managedText=([string]$managed.text).TrimEnd([char]13,[char]10)
  $observations.managed=[ordered]@{
    state=$managed.state
    exit_code=$managed.exit_code
    output_pending=$managed.output_pending
    total_lines=$managed.total_lines
    output_text=$managedText
    utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($managedText))
    expected_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($expected))
    exact=($managedText -ceq $expected)
  }
  Check "one_shot_exits_zero" ([string]$single.state -eq "EXITED" -and $single.exit_code -eq 0)
  Check "one_shot_keeps_original_command_sha" ([string]$single.command_sha256 -ceq (Get-Utf8Sha256 $command))
  Check "managed_exits_zero_and_drains" ([string]$managed.state -eq "EXITED" -and $managed.exit_code -eq 0 -and -not [bool]$managed.output_pending)
  Check "one_shot_preserves_unicode_without_json_transport" ($singleText -ceq $expected)
  Check "managed_preserves_unicode_without_json_transport" ($managedText -ceq $expected)
  $literalExpected=$expected+" "+[char]0x65E5+[char]0x672C+[char]0x8A9E
  $literalCommand="Write-Output '"+$literalExpected+"'; exit 0"
  foreach($kind in @("constructor_literal","interaction_literal")) {
    $initial=if($kind -ceq "constructor_literal"){$literalCommand}else{"Write-Output 'READY'"}
    $child=New-Object HaraWindowsProcessSession -ArgumentList @(("FIXTURE_"+$kind),$env:TEMP,$initial)
    $ownedSessions.Add($child)|Out-Null
    if($kind -ceq "interaction_literal"){$child.Input($literalCommand)}
    $snapshot=Wait-ManagedFixtureExit $child 8000
    $actual=([string]$snapshot.text).TrimEnd([char]13,[char]10)
    if($kind -ceq "interaction_literal"){$actual=($actual -split "\n")[-1]}
    $observations[$kind]=[ordered]@{state=$snapshot.state;exit_code=$snapshot.exit_code;output_pending=$snapshot.output_pending;actual_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($actual));expected_utf8_base64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($literalExpected));exact=($actual -ceq $literalExpected)}
    Check ($kind+"_exits_zero_and_drains") ([string]$snapshot.state -ceq "EXITED" -and $snapshot.exit_code -eq 0 -and -not $snapshot.output_pending)
    Check ($kind+"_preserves_unicode") ($actual -ceq $literalExpected)
  }

} catch {$failure=$_.Exception.Message}
finally {
  foreach($session in $ownedSessions) {$session.Dispose()}
  $report=[ordered]@{
    schema="hara.commander.windows-process-unicode-fixture.v1"
    state=$(if ($failure) {"FAIL"} else {"PASS"})
    source_sha256=(Byte-Sha256 $agentBytes)
    source_path=$AgentPath
    powershell_version=$PSVersionTable.PSVersion.ToString()
    parent_input_encoding=[Console]::InputEncoding.WebName
    parent_output_encoding=[Console]::OutputEncoding.WebName
    parent_pipeline_encoding=$OutputEncoding.WebName
    assertions=$checks.Count
    checks=@($checks.ToArray())
    observations=$observations
    error=$failure
    command_payload_ascii=$false
    independent_ascii_and_literal_unicode_controls=$true
    json_transport_used=$false
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
