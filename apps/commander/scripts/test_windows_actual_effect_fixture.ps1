param(
  [Parameter(Mandatory=$true)][string]$AgentSource,
  [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedAgentSha256,
  [string]$ReportPath
)
# Import exact AST functions into a disposable scope. Never execute the Agent
# entrypoint, profile, task, network, IPC approval or installed source.
$ErrorActionPreference='Stop'
$checks=New-Object 'System.Collections.Generic.List[string]'
$observations=[ordered]@{}
$failure=$null
$fixtureRoot=$null
$sourceSha=(Get-FileHash -LiteralPath $AgentSource -Algorithm SHA256).Hash.ToLowerInvariant()
$script:ManagedWindowsSessions=@{}
function Check([bool]$Condition,[string]$Name) {
  if (-not $Condition) { throw ('ACTUAL_EFFECT_FIXTURE_ASSERT:'+ $Name) }
  $checks.Add($Name) | Out-Null
}
function Call-Tool([string]$Tool,$Payload) {
  return Invoke-Tool $cfg ([pscustomobject]@{
    tool_id=$Tool;payload=[pscustomobject]$Payload
    request_id=('SYNTHETIC-EFFECT-'+[guid]::NewGuid().ToString('N'))
  })
}
function Get-FixtureData($Envelope) { return $Envelope.result.stdout | ConvertFrom-Json }
function Check-Effect($Envelope,[bool]$Expected,[string]$Name) {
  Check ($Envelope -is [Collections.IDictionary]) ($Name+'_SINGLE_ENVELOPE')
  Check ($Envelope.state -ceq 'PASS') ($Name+'_PASS')
  Check ($Envelope.mutation_performed -is [bool] -and $Envelope.mutation_performed -ceq $Expected) ($Name+'_ACTUAL_EFFECT')
  Check ($Envelope.bridge_receipt_sha256 -match '^[0-9a-f]{64}$') ($Name+'_RECEIPT')
}
function Wait-Exit([string]$Id) {
  $deadline=[DateTime]::UtcNow.AddSeconds(8)
  do {
    $last=Read-WindowsManagedSession $Id 0 200 0
    if ($last.state -cne 'RUNNING' -and -not $last.output_pending) { return $last }
    Microsoft.PowerShell.Utility\Start-Sleep -Milliseconds 30
  } while ([DateTime]::UtcNow -lt $deadline)
  throw 'ACTUAL_EFFECT_FIXTURE_CHILD_EXIT_TIMEOUT'
}
function Expect-Denied([string]$Tool,$Payload,[string]$Name) {
  $caught=$null
  try { Call-Tool $Tool $Payload | Out-Null } catch { $caught=$_.Exception.Message }
  Check ($caught -ceq 'LOCAL_OPERATOR_SESSION_REQUIRED') ($Name+'_SOURCE_GUARD_DENIED')
}
try {
  Check ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'NATIVE_WINDOWS_POWERSHELL_51'
  Check ($sourceSha -ceq $ExpectedAgentSha256) 'EXACT_SOURCE_HASH'
  $tokens=$null;$parseErrors=$null
  $ast=[Management.Automation.Language.Parser]::ParseFile($AgentSource,[ref]$tokens,[ref]$parseErrors)
  Check ($parseErrors.Count -eq 0) 'SOURCE_PARSER_CLEAN'
  $names=@('Invoke-Tool','New-DirectResult','New-Receipt','Get-Receipt','Get-Utf8Sha256',
    'Get-ApprovalMode','Get-OperatorProcess','Get-OperatorSession','Test-OperatorSessionActive',
    'Assert-StarterMutationAuthorized','New-WindowsDirectory','Write-WindowsTextFile',
    'Get-WindowsFileInfo','Get-WindowsDirectory','Read-WindowsTextFile',
    'Invoke-WindowsOneShotProcess','Initialize-WindowsManagedProcessType',
    'Cleanup-WindowsManagedSessions','Get-WindowsManagedSession','Start-WindowsManagedSession',
    'Read-WindowsManagedSession','Send-WindowsManagedSessionInput','Stop-WindowsManagedSession',
    'List-WindowsManagedSessions')
  foreach($name in $names) {
    $found=@($ast.FindAll({param($node)
      $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name
    },$false))
    Check ($found.Count -eq 1) ('SOURCE_FUNCTION_'+$name)
    . ([scriptblock]::Create($found[0].Extent.Text))
  }
  $fixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ('hara-actual-effect-fixture-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
  $ReceiptDir=Join-Path $fixtureRoot 'synthetic-receipts'
  $SessionPath=Join-Path $fixtureRoot 'synthetic-session.json'
  $SessionMaxHours=12
  $script:WindowsSessionMaxActive=8
  $script:WindowsSessionFinishedRetentionSeconds=900
  $cfg=[pscustomobject]@{device_id='SYNTHETIC_DEVICE_ONLY';approval_mode='SESSION_TRUSTED'}
  $proc=Get-Process -Id $PID
  [IO.File]::WriteAllText($SessionPath,([ordered]@{
    schema='hara.commander-operator-session.v1';owner_pid=$PID
    owner_started_at_utc=$proc.StartTime.ToUniversalTime().ToString('o')
    started_at_utc=[DateTime]::UtcNow.ToString('o')
  } | ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
  Check (Test-OperatorSessionActive) 'ISOLATED_SESSION_VALIDATED_BY_SOURCE'

  $folder=Join-Path $fixtureRoot 'owned-directory'
  $created=Call-Tool 'hara.files.create_directory' @{path=$folder;parents=$false}
  Check-Effect $created $true 'DIRECTORY_CREATE'
  Check ((Get-FixtureData $created).created -ceq $true -and (Test-Path -LiteralPath $folder -PathType Container)) 'DIRECTORY_CREATE_EXISTS'
  $existing=Call-Tool 'hara.files.create_directory' @{path=$folder;parents=$false}
  Check-Effect $existing $false 'DIRECTORY_EXISTING_NOOP'
  Check ((Get-FixtureData $existing).created -ceq $false -and $existing.result.risk_class -ceq 'MUTATING') 'DIRECTORY_NOOP_INDEPENDENT_OF_RISK'

  $file=Join-Path $folder 'owned-file.txt'
  $written=Call-Tool 'hara.files.write' @{path=$file;content='EFFECT_WRITE';mode='rewrite'}
  Check-Effect $written $true 'FILE_WRITE'
  Check ([IO.File]::ReadAllText($file) -ceq 'EFFECT_WRITE') 'FILE_WRITE_REAL_BYTES'
  $oldHash=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
  $updated=Call-Tool 'hara.files.write' @{path=$file;content='EFFECT_CAS';mode='rewrite';expected_sha256=$oldHash}
  Check-Effect $updated $true 'FILE_CAS_WRITE'
  $beforeRejected=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
  $caught=$null
  try { Call-Tool 'hara.files.write' @{path=$file;content='MUST_NOT_WRITE';mode='rewrite';expected_sha256=$oldHash} | Out-Null }
  catch {$caught=$_.Exception.Message}
  Check ($caught -ceq 'FILE_PRECONDITION_FAILED') 'STALE_CAS_DENIED'
  Check ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $beforeRejected) 'STALE_CAS_BYTES_UNCHANGED'

  foreach($entry in @(
    @{tool='hara.files.info';payload=@{path=$file};name='FILE_INFO'},
    @{tool='hara.files.read';payload=@{path=$file};name='FILE_READ'},
    @{tool='hara.files.list';payload=@{path=$folder};name='DIRECTORY_LIST'},
    @{tool='hara.process.sessions';payload=@{};name='PROCESS_SESSIONS'}
  )) { Check-Effect (Call-Tool $entry.tool $entry.payload) $false $entry.name }

  $oneShot=Call-Tool 'hara.process.run' @{command="Write-Output 'EFFECT_ONESHOT'; exit 7";cwd=$fixtureRoot;timeout_ms=3000;max_lines=20}
  Check-Effect $oneShot $true 'PROCESS_RUN'
  $oneData=Get-FixtureData $oneShot
  Check ($oneData.text -match 'EFFECT_ONESHOT' -and $oneData.exit_code -eq 7) 'PROCESS_RUN_REAL_CHILD_NONZERO_EXIT'

  $started=Call-Tool 'hara.process.start' @{command="Write-Output 'EFFECT_READY'";cwd=$fixtureRoot;timeout_ms=1000}
  Check-Effect $started $true 'PROCESS_START'
  $id=(Get-FixtureData $started).session_id
  Check ($script:ManagedWindowsSessions.ContainsKey($id)) 'PROCESS_START_REAL_SESSION'
  $interacted=Call-Tool 'hara.process.interact' @{session_id=$id;input="Write-Output 'EFFECT_INPUT'; exit 3";timeout_ms=1000}
  Check-Effect $interacted $true 'PROCESS_INTERACT'
  $final=Wait-Exit $id
  Check ($final.exit_code -eq 3 -and $final.text -match 'EFFECT_INPUT') 'PROCESS_INTERACT_REAL_INPUT'
  Check-Effect (Call-Tool 'hara.process.output' @{session_id=$id;offset=0;length=20;timeout_ms=0}) $false 'PROCESS_OUTPUT'
  $noopKill=Call-Tool 'hara.process.kill' @{session_id=$id;force=$true}
  Check-Effect $noopKill $false 'EXITED_PROCESS_KILL_NOOP'
  Check ((Get-FixtureData $noopKill).mutation_performed -is [bool] -and (Get-FixtureData $noopKill).mutation_performed -ceq $false) 'KILL_WRAPPER_NO_PIPELINE_LEAK'
  Check ($noopKill.result.risk_class -ceq 'PROCESS_EXECUTION') 'KILL_NOOP_INDEPENDENT_OF_RISK'

  foreach($force in @($false,$true)) {
    $child=Call-Tool 'hara.process.start' @{command="Write-Output 'EFFECT_STOP_READY'";cwd=$fixtureRoot;timeout_ms=1000}
    $childId=(Get-FixtureData $child).session_id
    $stopped=Call-Tool 'hara.process.kill' @{session_id=$childId;force=$force}
    $stopName=if ($force) {'FORCE_STOP'} else {'GRACEFUL_STOP'}
    Check-Effect $stopped $true $stopName
    $terminal=Wait-Exit $childId
    Check ($terminal.state -ceq $(if($force){'KILLED'}else{'EXITED'})) ($stopName+'_REAL_CHILD_STOPPED')
    Check-Effect (Call-Tool 'hara.process.kill' @{session_id=$childId;force=$force}) $false ($stopName+'_REPEATED_NOOP')
  }
  $replayed=Call-Tool 'hara.receipts.get' @{receipt_id_or_sha256=$written.bridge_receipt_sha256}
  Check ($replayed.mutation_performed -is [bool] -and $replayed.mutation_performed -ceq $false) 'RECEIPT_READ_FALSE'

  # Revoke only our synthetic session and use the unchanged source guard. No
  # positive individual approval is forged and no console challenge is opened.
  $deniedMarker=Join-Path $fixtureRoot 'MUST_NOT_EXECUTE.txt'
  $deniedFolder=Join-Path $fixtureRoot 'MUST_NOT_CREATE'
  $live=Call-Tool 'hara.process.start' @{command="Write-Output 'EFFECT_DENIAL_READY'";cwd=$fixtureRoot;timeout_ms=1000}
  $liveId=(Get-FixtureData $live).session_id
  Remove-Item -LiteralPath $SessionPath -Force
  $receiptCount=@(Get-ChildItem -LiteralPath $ReceiptDir -File).Count
  $sessionCount=$script:ManagedWindowsSessions.Count
  $command="[IO.File]::WriteAllText('"+$deniedMarker.Replace("'","''")+"','MUST_NOT_EXECUTE')"
  Expect-Denied 'hara.process.run' @{command=$command;cwd=$fixtureRoot;timeout_ms=1000} 'DENIED_RUN'
  Expect-Denied 'hara.process.start' @{command=$command;cwd=$fixtureRoot;timeout_ms=1000} 'DENIED_START'
  Expect-Denied 'hara.process.interact' @{session_id=$liveId;input=$command;timeout_ms=0} 'DENIED_INTERACT'
  Expect-Denied 'hara.process.kill' @{session_id=$liveId;force=$true} 'DENIED_KILL'
  Expect-Denied 'hara.files.write' @{path=$file;content='MUST_NOT_WRITE';mode='rewrite'} 'DENIED_WRITE'
  Expect-Denied 'hara.files.create_directory' @{path=$deniedFolder;parents=$false} 'DENIED_DIRECTORY'
  Check (-not (Test-Path -LiteralPath $deniedMarker) -and -not (Test-Path -LiteralPath $deniedFolder)) 'DENIED_ACTIONS_NO_MARKER_OR_DIRECTORY'
  Check ([IO.File]::ReadAllText($file) -ceq 'EFFECT_CAS') 'DENIED_WRITE_BYTES_UNCHANGED'
  Check ($script:ManagedWindowsSessions.Count -eq $sessionCount) 'DENIED_START_NO_NEW_SESSION'
  Check ((Read-WindowsManagedSession $liveId 0 20 0).state -ceq 'RUNNING') 'DENIED_KILL_CHILD_REMAINS_RUNNING'
  Check (@(Get-ChildItem -LiteralPath $ReceiptDir -File).Count -eq $receiptCount) 'DENIED_ACTIONS_NO_SUCCESS_RECEIPTS'
  $observations.session_mode='SYNTHETIC_SESSION_TRUSTED'
  $observations.authorization_guard_mocked=$false
  $observations.process_and_filesystem_helpers_mocked=$false
} catch {$failure=$_.Exception.Message}
finally {
  foreach($session in @($script:ManagedWindowsSessions.Values)) {try {$session.Dispose()} catch {}}
  if ($fixtureRoot -and (Test-Path -LiteralPath $fixtureRoot)) {Remove-Item -LiteralPath $fixtureRoot -Recurse -Force}
  $report=[ordered]@{
    schema='hara.commander.windows-actual-effect-fixture.v1';state=$(if($failure){'FAIL'}else{'PASS'})
    source_sha256=$sourceSha;powershell_version=$PSVersionTable.PSVersion.ToString()
    assertions=$checks.Count;passed_checks=@($checks.ToArray());observations=$observations;error=$failure
    agent_entrypoint_executed=$false;installed_agent_modified=$false;live_profile_touched=$false
    agent_task_touched=$false;real_human_approval_proven=$false;network_transport_used=$false
    owned_children_disposed=$true;owned_fixture_directory_removed=$true
  }
  $json=$report | ConvertTo-Json -Depth 8 -Compress
  if ($ReportPath) {[IO.File]::WriteAllText($ReportPath,$json,(New-Object Text.UTF8Encoding($false)))}
  Write-Output $json
}
if ($failure) {throw $failure}
