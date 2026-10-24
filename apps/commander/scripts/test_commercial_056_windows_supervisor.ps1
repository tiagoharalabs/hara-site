param([string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'))
$ErrorActionPreference='Stop'
$checks=New-Object Collections.Generic.List[string]
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
$priorLocal=$env:LOCALAPPDATA
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-win-supervisor-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qa | Out-Null
$env:LOCALAPPDATA=$qa
try {
$source=[IO.File]::ReadAllText((Resolve-Path $AgentPath));$cut=$source.IndexOf('if ($args -contains "--version")')
. ([scriptblock]::Create($source.Substring(0,$cut)))
$required=@('New-WindowsRelaySupervisorState','Step-WindowsRelaySupervisor','Initialize-WindowsRelayProcessType','Get-WindowsRelayDeadline')
$missing=@($required|Where-Object {-not (Get-Command $_ -ErrorAction SilentlyContinue)})
if($missing.Count){@{state='RED_WINDOWS_SUPERVISOR_ABSENT';missing=$missing}|ConvertTo-Json;exit 2}
Initialize-WindowsRelayProcessType
Check ($null -ne ('HaraRelayProcess' -as [type])) 'GUARDIAN_TYPE_COMPILES'
$script:started=New-Object Collections.Generic.List[string]
$script:events=New-Object Collections.Generic.List[object]
function Start-WindowsRelayProcess($Role,$Cfg,$Abandoned,$AgentPath){
 $script:started.Add($Role)
 return @{role=$Role;messages=(New-Object Collections.Generic.List[object]);alive=$true;quiescent=$true;seeds=@($Abandoned)}
}
function Read-WindowsRelayProgress($Process){$items=@($Process.messages.ToArray());$Process.messages.Clear();return $items}
function Stop-WindowsRelayProcess($Process){if($Process.quiescent){$Process.alive=$false;return $true};return $false}
function Test-WindowsRelayProcessAlive($Process){return $Process.alive}
function State {
 $script:started.Clear();$script:events.Clear()
 return New-WindowsRelaySupervisorState 'synthetic-agent-path.ps1' {param($Event)$script:events.Add($Event)}
}
$cfg=[pscustomobject]@{approval_mode='PERSISTENT_TRUSTED'}
$s=State
Step-WindowsRelaySupervisor $s $cfg $false 0
Check ($started.Count -eq 0) 'NO_WORKER_WITHOUT_CONSENT'
Step-WindowsRelaySupervisor $s $cfg $true 1
Check ($started.Count -eq 2) 'HEARTBEAT_AND_EXECUTOR_SEPARATE'
$s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_CONFIRMED'})
$s.children.executor.process.messages.Add(@{kind='CALL';call_id='call';request_id='request';fingerprint=('a'*64);deadline=5})
Step-WindowsRelaySupervisor $s $cfg $true 2
Check ($s.heartbeatCount -eq 1) 'CORRELATED_HEARTBEAT_PROGRESS'
$s.children.executor.process.messages.Add(@{kind='PHASE';request_id='request';phase='EXECUTING'})
Step-WindowsRelaySupervisor $s $cfg $true 6
Check ($s.restartCounts.executor -eq 1 -and $s.restartCounts.heartbeat -eq 0) 'EXECUTOR_DEADLINE_DOES_NOT_RESTART_HEARTBEAT'
Check ($s.children.executor.process.seeds.Count -eq 1 -and $s.children.executor.process.seeds[0].fingerprint -ceq ('a'*64)) 'ABANDONED_AUTHENTICATED_CLAIM_SURVIVES'
Check (@($events|Where-Object state -eq 'RECOVERED').Count -eq 0) 'PID_ALONE_NOT_RECOVERED'
$s.children.executor.process.messages.Add(@{kind='READY';delay=2})
$s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_CONFIRMED'})
Step-WindowsRelaySupervisor $s $cfg $true 7
Check (@($events|Where-Object state -eq 'RECOVERED').Count -eq 1) 'RECOVERY_NEEDS_READY_AND_NEW_CONFIRMED_HEARTBEAT'
Step-WindowsRelaySupervisor $s $cfg $false 8
Check ($s.children.Count -eq 0) 'OPERATOR_STOP_TERMINATES_JOBS'
Step-WindowsRelaySupervisor $s $cfg $false 300
Check ($s.children.Count -eq 0) 'STOP_NEVER_REACTIVATES'
$s=State;Step-WindowsRelaySupervisor $s $cfg $true 1
$s.children.executor.process.quiescent=$false
$s.children.executor.process.messages.Add(@{kind='CALL';call_id='c';request_id='r';fingerprint=('b'*64);deadline=2})
Step-WindowsRelaySupervisor $s $cfg $true 3
Check ($s.children.executor.fenced -and $s.restartCounts.executor -eq 0) 'UNREAPED_JOB_FENCES_REPLACEMENT'
$s.children.executor.process.quiescent=$true
Step-WindowsRelaySupervisor $s $cfg $false 4
$s=State;Step-WindowsRelaySupervisor $s $cfg $true 1
$s.children.executor.process.messages.Add(@{kind='READY';delay=60})
$s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_CONFIRMED'})
Step-WindowsRelaySupervisor $s $cfg $true 2
Step-WindowsRelaySupervisor $s $cfg $true 40
Check ($s.restartCounts.executor -eq 0) '429_BACKOFF_NOT_MISTAKEN_FOR_HANG'
Step-WindowsRelaySupervisor $s $cfg $false 41
$s=State;Step-WindowsRelaySupervisor $s $cfg $true 1
$s.children.heartbeat.process.messages.Add(@{kind='REVOKED';code='HTTP_403'})
Step-WindowsRelaySupervisor $s $cfg $true 2
Step-WindowsRelaySupervisor $s $cfg $true 300
Check ($s.revoked -and $s.children.Count -eq 0) 'REVOCATION_LATCH_NO_RETRY'
$s=State;Step-WindowsRelaySupervisor $s $cfg $true 1
foreach($instant in @(2,10,20)){
 $s.children.executor.process.alive=$false
 $s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_CONFIRMED'})
 Step-WindowsRelaySupervisor $s $cfg $true $instant
}
Check ($s.restartCounts.executor -eq 2 -and -not $s.children.ContainsKey('executor')) 'FINITE_RESTART_CIRCUIT'
Check (@($events|Where-Object state -eq 'DEGRADED').Count -eq 1) 'CIRCUIT_ALERT_DEDUPLICATED'
Step-WindowsRelaySupervisor $s $cfg $false 21
$s=State;Step-WindowsRelaySupervisor $s $cfg $true 1
$s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_RETRY';delay=60})
$s.children.executor.process.messages.Add(@{kind='READY';delay=60})
Step-WindowsRelaySupervisor $s $cfg $true 80
$s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_RETRY';delay=60})
$s.children.executor.process.messages.Add(@{kind='READY';delay=60})
Step-WindowsRelaySupervisor $s $cfg $true 151.1
Check ($s.restartCounts.heartbeat -eq 0 -and @($events|Where-Object state -eq 'STALLED').Count -eq 1) 'RESPONSIVE_OFFLINE_RETRY_DETECTED_WITHOUT_RESTART_STORM'
$s.children.heartbeat.process.messages.Add(@{kind='HEARTBEAT_CONFIRMED'})
$s.children.executor.process.messages.Add(@{kind='READY';delay=10})
Step-WindowsRelaySupervisor $s $cfg $true 201.1
Check (@($events|Where-Object state -eq 'RECOVERED').Count -eq 1) 'NETWORK_RESTORATION_REQUIRES_PLATFORM_CONFIRMATION'
Step-WindowsRelaySupervisor $s $cfg $false 202
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT){
 $refused=$false
 try{$p=New-Object HaraRelayProcess -ArgumentList 'shell','script','executor','1','timestamp',('a'*64),('b'*64),'{}'}catch{$refused=$_.Exception.Message.Contains('WINDOWS_JOB_REQUIRED')}
 Check $refused 'NO_PORTABLE_JOB_BYPASS'
}
$call=[pscustomobject]@{tool_id='hara.files.list';expires_at_utc=[DateTime]::UtcNow.AddSeconds(10).ToString('o')}
$deadline=Get-WindowsRelayDeadline $call 100
Check ($deadline -gt 109 -and $deadline -le 110.1) 'MONOTONIC_DEADLINE_CLAMPED_TO_PLATFORM'
@{state='PASS_SUPERVISOR_LOGIC_NOT_NATIVE_JOB_ACCEPTANCE';checks=$checks.Count;cases=$checks.ToArray();windows_native=([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT);installed=$false;network_used=$false}|ConvertTo-Json -Depth 5

} catch {
 [Console]::Error.WriteLine($_.ScriptStackTrace)
 [Console]::Error.WriteLine(($s.attempts | ConvertTo-Json -Depth 6 -Compress))
 throw
} finally {
 $env:LOCALAPPDATA=$priorLocal
 Remove-Item -LiteralPath $qa -Recurse -Force
}
