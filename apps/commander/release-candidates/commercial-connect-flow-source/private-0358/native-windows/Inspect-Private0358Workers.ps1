[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$NativeReceiptPath)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$nuSid='S-1-5-21-1207901905-1500652706-889822281-1005'
$nuContext=$null;$wdGuard=$null;$wdReceiptAdmitted=$false
$wdController='C:\Users\CommanderQA\Desktop\HARA Commander Conexao QA\Connect-Commander.ps1'
$wdRecovery='C:\ProgramData\HARA-QA\windows-install-0356-20261028\config\upgrade-0358\Invoke-Private0358Recovery.ps1'
$wdResults='C:\ProgramData\HARA-QA\windows-install-0356-20261028\results'
$wdAgentSha='bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d'
$wdReport=[ordered]@{schema='hara.commander.windows-worker-readonly-diagnostic.v1';state='HOLD';started_utc=[DateTime]::UtcNow.ToString('o');product_files_changed=$false;product_task_changed=$false;worker_started_or_stopped=$false;raw_command_lines_exported=$false;raw_worker_stderr_available=$false;snapshots=@()}
function Need-NU([bool]$Okay,[string]$Code){if(-not $Okay){throw $Code}}
function Snapshot-WD {
  $snapshot=[ordered]@{at_utc=[DateTime]::UtcNow.ToString('o');processes=@()}
  $task=Get-CCTask $nuContext
  $info=Get-ScheduledTaskInfo -TaskName $nuContext.TaskName -TaskPath '\'
  $snapshot.task=@{state=[string]$task.State;last_result=[long]$info.LastTaskResult;last_run_utc=$info.LastRunTime.ToUniversalTime().ToString('o')}
  if(Test-Path -LiteralPath $nuContext.RuntimePath){
    Assert-CCOwnedFile $nuContext.RuntimePath $nuSid
    $runtime=Get-Content -LiteralPath $nuContext.RuntimePath -Raw|ConvertFrom-Json
    $snapshot.runtime=@{}
    foreach($name in @('agent_version','started_at_utc','last_successful_heartbeat_at_utc','updated_at_utc','last_runtime_error_at_utc')){$snapshot.runtime[$name]=[string]$runtime.$name}
    if([string]$runtime.last_runtime_error_code -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){$snapshot.runtime.last_runtime_error_code=[string]$runtime.last_runtime_error_code}
  }
  $all=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -OperationTimeoutSec 5)
  foreach($row in $all){
    $command=[string]$row.CommandLine
    if(-not $command.Contains($nuContext.AgentPath)){continue}
    $item=[ordered]@{pid=[int]$row.ProcessId;parent_pid=[int]$row.ParentProcessId;created_utc=$row.CreationDate.ToUniversalTime().ToString('o');session_id=[int]$row.SessionId;role='SUPERVISOR';strict_worker_match=$false}
    if($command.Contains('--relay-worker')){
      $item.role='UNPARSED_WORKER'
      if($command -cmatch '--relay-worker\s+"?(heartbeat|executor|alerts)"?\s+"?([0-9]+)"?'){$item.role=$Matches[1];$item.parent_argument=[int]$Matches[2]}
      $item.strict_worker_match=($command -cmatch '--relay-worker "(heartbeat|executor|alerts)" "([0-9]+)" "[^"\r\n]+" "[0-9a-f]{64}" "[0-9a-f]{64}"$')
    }
    try{$owner=Invoke-CimMethod -InputObject $row -MethodName GetOwnerSid -OperationTimeoutSec 5;$item.owner_sid=[string]$owner.Sid}catch{$item.owner_observation_error=$_.Exception.GetType().Name}
    $snapshot.processes+=@([pscustomobject]$item)
    $command=$null
  }
  return [pscustomobject]$snapshot
}
try{
  Need-NU ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ceq $nuSid -and $env:USERPROFILE -ceq 'C:\Users\CommanderQA') 'EXPECTED_QA_IDENTITY_REQUIRED'
  $NativeReceiptPath=[IO.Path]::GetFullPath($NativeReceiptPath)
  Need-NU ([IO.Path]::GetDirectoryName($NativeReceiptPath) -ieq $wdResults -and [IO.Path]::GetFileName($NativeReceiptPath) -cmatch '^[A-Za-z0-9_.-]+\.json$' -and -not(Test-Path -LiteralPath $NativeReceiptPath)) 'WORKER_DIAGNOSTIC_RECEIPT_REFUSED'
  Need-NU ((Get-FileHash -LiteralPath $wdController -Algorithm SHA256).Hash.ToLowerInvariant() -ceq '2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da') 'CONTROLLER_PIN_MISMATCH'
  . $wdController
  Assert-CCNoReparse $wdResults
  $wdReceiptAdmitted=$true
  $nuContext=New-CCContext 'https://commander.haralabs.com.br' '' 'ASK_EVERY_ACTION'
  $wdGuard=Enter-CCGuard $nuContext
  $state=Get-CCInstalledState $nuContext
  Need-NU ($state.Version -ceq '0.3.58' -and $state.AgentSha -ceq $wdAgentSha -and $state.DeviceId -ceq 'HARA-DEVICE-a544f7b1-3ee1-49f7-aa55-f559376d5d12') 'EXACT_INSTALLED_0358_BINDING_REQUIRED'
  $wdConfigSha=$state.ConfigSha
  $wdTaskXml=Export-ScheduledTask -TaskName $nuContext.TaskName -TaskPath '\'
  for($iteration=0;$iteration -lt 3;$iteration++){
    $wdReport.snapshots+=@(Snapshot-WD)
    if($iteration -lt 2){Start-Sleep -Seconds 4}
  }
  # Load only reviewed diagnostic function definitions, never its main program.
  Need-NU ((Get-FileHash -LiteralPath $wdRecovery -Algorithm SHA256).Hash.ToLowerInvariant() -ceq 'a06f95f316b5f7f69a33fc2ad85db6731452fbbf5ee99592fd6d38320095e58c') 'RECOVERY_DRIVER_PIN_MISMATCH'
  $tokens=$null;$errors=$null
  $ast=[Management.Automation.Language.Parser]::ParseFile($wdRecovery,[ref]$tokens,[ref]$errors)
  Need-NU ($errors.Count -eq 0) 'RECOVERY_DRIVER_PARSE_FAILED'
  foreach($name in @('Import-NUAgentFunctions','RecoveryOutbox-NU')){
    $nodes=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object {$_.Name -ceq $name})
    Need-NU ($nodes.Count -eq 1) 'DIAGNOSTIC_FUNCTION_EXTRACTION_AMBIGUOUS'
    $definition=[regex]::Replace($nodes[0].Extent.Text,('^function\s+'+[regex]::Escape($name)+'(?=[(\s])'),('function script:'+$name))
    . ([scriptblock]::Create($definition))
  }
  $prior=Get-Content -LiteralPath (Join-Path $wdResults 'upgrade-0358-native.json') -Raw|ConvertFrom-Json
  Need-NU ([string]$prior.schema -ceq 'hara.commander.windows-private-0358-upgrade.v1' -and $prior.recovery_started_utc) 'PREVIOUS_RECOVERY_RECEIPT_REQUIRED'
  $script:NURecoveryStarted=[DateTime]::Parse([string]$prior.recovery_started_utc).ToUniversalTime()
  try{
    $wdReport.outbox=RecoveryOutbox-NU ([IO.File]::ReadAllBytes($nuContext.AgentPath))
    # Expanded metadata-only history includes the last transitions before start.
    $current=Get-CCInstalledState $nuContext
    $folder=Join-Path (Join-Path $nuContext.Root 'enrollments') (Get-EnrollmentContext $current.Config)
    $database=Join-Path $folder 'recovery-events.sqlite3'
    $wdReport.outbox.latest_events=@([HaraWinSqlite]::QueryReadOnly($database,'SELECT worker,health,state,at_utc,attempts FROM recovery_events ORDER BY ordinal DESC LIMIT 12',@()))
  }catch{
    $message=[string]$_.Exception.Message
    $wdReport.outbox_error=@{type=$_.Exception.GetType().Name;code=$(if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){$message}else{'READONLY_OUTBOX_OBSERVATION_FAILED'})}
  }
  $after=Get-CCInstalledState $nuContext
  $wdReport.preservation=@{agent=($after.AgentSha -ceq $wdAgentSha);config=($after.ConfigSha -ceq $wdConfigSha);task_definition=((Export-ScheduledTask -TaskName $nuContext.TaskName -TaskPath '\') -ceq $wdTaskXml)}
  Need-NU ($wdReport.preservation.agent -and $wdReport.preservation.config -and $wdReport.preservation.task_definition) 'READONLY_DIAGNOSTIC_PRESERVATION_UNCONFIRMED'
  $wdReport.state='READONLY_DIAGNOSTIC_COMPLETE'
}catch{
  $message=[string]$_.Exception.Message
  $wdReport.error_code=if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){$message}else{'WORKER_DIAGNOSTIC_FAILED'}
  $wdReport.error_type=$_.Exception.GetType().Name
}finally{
  if($wdGuard){$wdGuard.ReleaseMutex();$wdGuard.Dispose()}
  $state=$null;$after=$null;$wdReport.finished_utc=[DateTime]::UtcNow.ToString('o')
  $wdJson=$wdReport|ConvertTo-Json -Depth 12 -Compress
  if($wdReceiptAdmitted){
    $bytes=[Text.Encoding]::UTF8.GetBytes($wdJson)
    $stream=New-Object IO.FileStream($NativeReceiptPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
  }
}
$wdJson
if($wdReport.state -ceq 'READONLY_DIAGNOSTIC_COMPLETE'){exit 0}
exit 2
