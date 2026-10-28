# Native checks loaded only from the pinned .58 recovery driver.
function Import-NUAgentFunctions([byte[]]$Bytes,[string[]]$Names){
  $tokens=$null;$errors=$null
  $ast=[Management.Automation.Language.Parser]::ParseInput([Text.Encoding]::UTF8.GetString($Bytes),[ref]$tokens,[ref]$errors)
  Need-NU ($errors.Count -eq 0) 'VERIFIED_0358_AGENT_PARSE_FAILED'
  foreach($name in $Names){
    $nodes=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object {$_.Name -ceq $name})
    Need-NU ($nodes.Count -eq 1) 'AGENT_FUNCTION_EXTRACTION_AMBIGUOUS'
    # Compile only the selected function body; no Agent entry point is run.
    $definition=[regex]::Replace($nodes[0].Extent.Text,('^function\s+'+[regex]::Escape($name)+'(?=[(\s])'),('function script:'+$name))
    . ([scriptblock]::Create($definition))
  }
}
function DirectoryAcl-NU([string]$Path){
  $acl=Get-Acl -LiteralPath $Path
  $raw=New-Object Security.AccessControl.RawSecurityDescriptor($acl.GetSecurityDescriptorBinaryForm(),0)
  $dacl=New-Object byte[] $raw.DiscretionaryAcl.BinaryLength
  $raw.DiscretionaryAcl.GetBinaryForm($dacl,0)
  $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|ForEach-Object {
    @{sid=$_.IdentityReference.Value;rights=[string]$_.FileSystemRights;type=[string]$_.AccessControlType;inherited=$_.IsInherited;inheritance=[string]$_.InheritanceFlags;propagation=[string]$_.PropagationFlags}
  })
  return [pscustomobject]@{owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value;group=$acl.GetGroup([Security.Principal.SecurityIdentifier]).Value;protected=$acl.AreAccessRulesProtected;flags=([int]$raw.ControlFlags -band (-bnot 0x400));dacl_base64=[Convert]::ToBase64String($dacl);rules=$rules}
}
function Test-NURepeatedDirectoryAcl([byte[]]$AgentBytes){
  Import-NUAgentFunctions $AgentBytes @('Get-Utf8Sha256','Get-EnrollmentContext','Initialize-EnrollmentState')
  $saved=@{}
  foreach($name in @('Root','ReceiptDir','OperationsDb','ConsoleEvents','PendingApprovalPath','ApprovalResponsePath')){
    $item=Get-Variable -Name $name -Scope Script -ErrorAction SilentlyContinue
    $saved[$name]=@{present=[bool]$item;value=$(if($item){$item.Value}else{$null})}
  }
  try{
    $script:Root=Join-Path $nuPrivate 'acl-regression'
    $cfg=[pscustomobject]@{base_url=$nuOrigin;device_id='QA-ACL-REGRESSION';encrypted_device_token='synthetic-local-only';tenant_id=''}
    $context=Get-EnrollmentContext $cfg
    $folder=Join-Path (Join-Path $Root 'enrollments') $context
    [void][IO.Directory]::CreateDirectory($folder)
    $before=DirectoryAcl-NU $folder
    $first=$null
    for($iteration=0;$iteration -lt 3;$iteration++){
      Need-NU ((Initialize-EnrollmentState $cfg) -ceq $context) 'ACL_REGRESSION_CONTEXT_CHANGED'
      $after=DirectoryAcl-NU $folder
      Need-NU ($after.owner -ceq $before.owner -and $after.group -ceq $before.group -and $after.protected) 'ACL_REGRESSION_OWNER_GROUP_OR_PROTECTION_CHANGED'
      Need-NU ($after.rules.Count -eq 2) 'ACL_REGRESSION_RULE_COUNT'
      foreach($sid in @($nuSid,'S-1-5-18')){
        $rule=@($after.rules|Where-Object {$_.sid -ceq $sid})
        Need-NU ($rule.Count -eq 1 -and $rule[0].rights -ceq 'FullControl' -and $rule[0].type -ceq 'Allow' -and -not $rule[0].inherited -and $rule[0].inheritance -ceq 'ContainerInherit, ObjectInherit' -and $rule[0].propagation -ceq 'None') 'ACL_REGRESSION_PRIVATE_RULES_INVALID'
      }
      if($first){Need-NU ($after.dacl_base64 -ceq $first.dacl_base64 -and $after.flags -eq $first.flags) 'ACL_REGRESSION_REPEAT_NOT_IDEMPOTENT'}else{$first=$after}
    }
    return [pscustomobject]@{state='PASS_ACCESS_ONLY_REPEATED_DIRECTORY';iterations=3;owner_preserved=$true;group_preserved=$true;dacl_protected=$true;qa_and_system_only=$true;exact_repeated_dacl=$true;product_directory_modified=$false}
  }finally{
    foreach($entry in $saved.GetEnumerator()){
      if($entry.Value.present){Set-Variable -Scope Script -Name $entry.Key -Value $entry.Value.value}else{Remove-Variable -Scope Script -Name $entry.Key -ErrorAction SilentlyContinue}
    }
  }
}
function WorkerSnapshot-NU {
  $all=@(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -OperationTimeoutSec 5)
  $matched=@($all|Where-Object {([string]$_.CommandLine).Contains($nuContext.AgentPath)})
  $main=@($matched|Where-Object {-not ([string]$_.CommandLine).Contains('--relay-worker')})
  Need-NU ($main.Count -eq 1) 'PRODUCT_SUPERVISOR_PROCESS_NOT_UNIQUE'
  $owner=Invoke-CimMethod -InputObject $main[0] -MethodName GetOwnerSid -OperationTimeoutSec 5
  Need-NU ([string]$owner.Sid -ceq $nuSid) 'SUPERVISOR_OWNER_MISMATCH'
  $result=[ordered]@{supervisor_pid=[int]$main[0].ProcessId;supervisor_created_utc=$main[0].CreationDate.ToUniversalTime().ToString('o');workers=@{}}
  foreach($row in $matched){
    if(([string]$row.CommandLine) -cmatch '--relay-worker "(heartbeat|executor|alerts)" "([0-9]+)" "[^"\r\n]+" "[0-9a-f]{64}" "[0-9a-f]{64}"$'){
      $role=$Matches[1];$parent=[int]$Matches[2]
      Need-NU (-not $result.workers.ContainsKey($role) -and $parent -eq $result.supervisor_pid -and [int]$row.ParentProcessId -eq $parent) 'WORKER_PARENT_OR_ROLE_MISMATCH'
      $workerOwner=Invoke-CimMethod -InputObject $row -MethodName GetOwnerSid -OperationTimeoutSec 5
      Need-NU ([string]$workerOwner.Sid -ceq $nuSid) 'WORKER_OWNER_MISMATCH'
      $result.workers[$role]=@{pid=[int]$row.ProcessId;created_utc=$row.CreationDate.ToUniversalTime().ToString('o')}
    }
  }
  Need-NU ($result.workers.Count -eq 3 -and $result.workers.ContainsKey('heartbeat') -and $result.workers.ContainsKey('executor') -and $result.workers.ContainsKey('alerts')) 'THREE_RELAY_WORKERS_REQUIRED'
  return [pscustomobject]$result
}
function RecoveryOutbox-NU([byte[]]$AgentBytes){
  Import-NUAgentFunctions $AgentBytes @('Get-Utf8Sha256','Get-EnrollmentContext','Initialize-WinSqlite')
  Initialize-WinSqlite
  $current=Get-CCInstalledState $nuContext
  $context=Get-EnrollmentContext $current.Config
  $folder=Join-Path (Join-Path $nuContext.Root 'enrollments') $context
  $database=Join-Path $folder 'recovery-events.sqlite3'
  Assert-CCOwnedFile $database $nuSid
  $blocked=@([HaraWinSqlite]::QueryReadOnly($database,"SELECT 1 AS n FROM recovery_meta WHERE key='access_denied'",@()))
  $counts=@([HaraWinSqlite]::QueryReadOnly($database,'SELECT state,count(*) AS n FROM recovery_events GROUP BY state',@()))
  $floor=[long]([DateTimeOffset]$script:NURecoveryStarted).ToUnixTimeMilliseconds()
  $recent=@([HaraWinSqlite]::QueryReadOnly($database,"SELECT worker,health,state,at_utc FROM recovery_events WHERE created_ms>=? ORDER BY ordinal DESC LIMIT 24",@($floor)))
  $bad=@($recent|Where-Object {[string]$_.health -cin @('STALLED','DEGRADED')})
  return [pscustomobject]@{access_blocked=($blocked.Count -gt 0);counts=$counts;new_health_events=$recent;new_stalled_or_degraded=($bad.Count -gt 0);read_only=$true}
}
function Confirm-NUWorkers([byte[]]$AgentBytes){
  $clock=[Diagnostics.Stopwatch]::StartNew();$first=$null
  while($clock.Elapsed.TotalSeconds -lt 20){
    try{$first=WorkerSnapshot-NU;break}catch{Start-Sleep -Milliseconds 500}
  }
  Need-NU ([bool]$first) 'INITIAL_RELAY_WORKERS_NOT_CONFIRMED'
  $stable=[Diagnostics.Stopwatch]::StartNew()
  while($stable.Elapsed.TotalSeconds -lt 40){
    Start-Sleep -Seconds 5
    $next=WorkerSnapshot-NU
    Need-NU ($next.supervisor_pid -eq $first.supervisor_pid -and $next.supervisor_created_utc -ceq $first.supervisor_created_utc) 'RELAY_SUPERVISOR_RESTART_DURING_ACCEPTANCE'
    foreach($role in @('heartbeat','executor','alerts')){Need-NU ($next.workers[$role].pid -eq $first.workers[$role].pid -and $next.workers[$role].created_utc -ceq $first.workers[$role].created_utc) 'RELAY_WORKER_RESTART_DURING_ACCEPTANCE'}
    Need-NU ([string](Get-CCTask $nuContext).State -ceq 'Running') 'PRODUCT_TASK_STOPPED_DURING_ACCEPTANCE'
  }
  $outbox=RecoveryOutbox-NU $AgentBytes
  Need-NU (-not $outbox.access_blocked -and -not $outbox.new_stalled_or_degraded) 'RECOVERY_OUTBOX_HEALTH_HOLD'
  return [pscustomobject]@{state='PASS_THREE_STABLE_WORKERS_AND_OUTBOX';stable_seconds=[int]$stable.Elapsed.TotalSeconds;snapshot=$first;outbox=$outbox;functional_executor_command='PENDING_ROOT_COMMANDER_PROBE';alerts_network_ack=$(if(@($outbox.counts|Where-Object {[string]$_.state -ceq 'PERSISTED' -and [long]$_.n -gt 0}).Count){'PERSISTED_EVENTS_OBSERVED'}else{'NO_PENDING_EVENT_REQUIRED'})}
}
