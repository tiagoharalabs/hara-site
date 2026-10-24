param([string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'))
$ErrorActionPreference='Stop'
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
if([string](Get-ExecutionPolicy) -ceq 'Bypass'){throw 'BYPASS_POLICY_REFUSED'}
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-056-job-native-'+[guid]::NewGuid().ToString('N'))
$prior=$env:LOCALAPPDATA
$checks=New-Object Collections.Generic.List[string]
$job=$null;$parent=$null
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function Await-Marker([string]$Path){
 $end=[Diagnostics.Stopwatch]::StartNew()
 while($end.Elapsed.TotalSeconds -lt 15){if(Test-Path -LiteralPath $Path){return (Get-Content -Raw -LiteralPath $Path|ConvertFrom-Json)};Start-Sleep -Milliseconds 50}
 throw 'FIXTURE_START_NOT_CONFIRMED_POLICY_OR_STARTUP_HOLD'
}
function Gone($Identity){
 try {$p=Get-Process -Id ([int]$Identity.pid) -ErrorAction Stop;return $p.StartTime.ToUniversalTime().ToString('o') -cne [string]$Identity.started}
 catch {return $true}
}
try {
 New-Item -ItemType Directory -Path $qa | Out-Null;$env:LOCALAPPDATA=$qa
 $AgentPath=(Resolve-Path $AgentPath).Path
 $source=[IO.File]::ReadAllText($AgentPath);$cut=$source.IndexOf('if ($args -contains "--version")')
 . ([scriptblock]::Create($source.Substring(0,$cut)))
 Initialize-WindowsRelayProcessType
 $worker=Join-Path $qa 'worker-fixture.ps1';$grand=Join-Path $qa 'grandchild-fixture.ps1'
 [IO.File]::WriteAllText($grand,"Start-Sleep -Seconds 600`n",(New-Object Text.UTF8Encoding($true)))
 [IO.File]::WriteAllText($worker,@'
$ErrorActionPreference='Stop'
$hello=[Console]::In.ReadLine()|ConvertFrom-Json
if($hello.nonce -cne [string]$args[5]){throw 'BAD_HANDSHAKE'}
$child=New-Object Diagnostics.Process
$child.StartInfo.FileName=Join-Path $PSHOME 'powershell.exe'
$child.StartInfo.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+(Join-Path $PSScriptRoot 'grandchild-fixture.ps1')+'"'
$child.StartInfo.UseShellExecute=$false;$child.StartInfo.CreateNoWindow=$true
if(-not $child.Start()){throw 'FIXTURE_CHILD_FAILED'}
$marker=@{worker=@{pid=$PID;started=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')};child=@{pid=$child.Id;started=$child.StartTime.ToUniversalTime().ToString('o')}}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'marker.new'),($marker|ConvertTo-Json -Depth 5))
[IO.File]::Move((Join-Path $PSScriptRoot 'marker.new'),(Join-Path $PSScriptRoot 'marker.json'))
[Console]::Out.WriteLine('HARA_RELAY_PROGRESS={"schema":"hara.commander.relay-progress.v1","kind":"READY"}')
Start-Sleep -Seconds 600
'@,(New-Object Text.UTF8Encoding($true)))
 # No policy flags, task registration, install, network or enrollment. A policy
 # that refuses generated fixtures stays HOLD; do not bypass or unblock it.
 $nonce=('a'*64);$context=('b'*64)
 $handshake=@{schema='hara.commander.relay-worker-handshake.v1';nonce=$nonce;abandoned=@()}|ConvertTo-Json -Compress
 $started=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
 $job=New-Object HaraRelayProcess -ArgumentList (Join-Path $PSHOME 'powershell.exe'),$worker,'executor',([string]$PID),$started,$context,$nonce,$handshake
 $marker=Await-Marker (Join-Path $qa 'marker.json')
 Check ($job.IsAlive -and -not $job.IsQuiescent) 'ASSIGNED_JOB_HANDSHAKE_AND_DESCENDANT_RUNNING'
 Check ($job.Stop()) 'TERMINATE_JOB_CONFIRMS_ZERO_ACTIVE_PROCESSES'
 Check ((Gone $marker.worker) -and (Gone $marker.child)) 'WORKER_AND_DESCENDANT_REAPED'
 $job.Dispose();$job=$null
 Remove-Item -LiteralPath (Join-Path $qa 'marker.json')
 $parentScript=Join-Path $qa 'guardian-fixture.ps1'
 [IO.File]::WriteAllText($parentScript,@'
param([string]$Agent,[string]$Worker)
$ErrorActionPreference='Stop'
$s=[IO.File]::ReadAllText($Agent);$cut=$s.IndexOf('if ($args -contains "--version")')
. ([scriptblock]::Create($s.Substring(0,$cut)))
Initialize-WindowsRelayProcessType
$nonce='a'*64;$context='b'*64
$hello=@{schema='hara.commander.relay-worker-handshake.v1';nonce=$nonce;abandoned=@()}|ConvertTo-Json -Compress
$j=New-Object HaraRelayProcess -ArgumentList (Join-Path $PSHOME 'powershell.exe'),$Worker,'executor',([string]$PID),((Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')),$context,$nonce,$hello
while(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'marker.json'))){Start-Sleep -Milliseconds 20}
[Diagnostics.Process]::GetCurrentProcess().Kill()
'@,(New-Object Text.UTF8Encoding($true)))
 $parent=New-Object Diagnostics.Process
 $parent.StartInfo.FileName=Join-Path $PSHOME 'powershell.exe'
 $parent.StartInfo.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+$parentScript+'" -Agent "'+$AgentPath+'" -Worker "'+$worker+'"'
 $parent.StartInfo.UseShellExecute=$false;$parent.StartInfo.CreateNoWindow=$true
 Check ($parent.Start()) 'ABRUPT_GUARDIAN_FIXTURE_STARTED'
 $marker=Await-Marker (Join-Path $qa 'marker.json')
 Check ($parent.WaitForExit(15000)) 'GUARDIAN_ABRUPT_EXIT_CONFIRMED'
 $wait=[Diagnostics.Stopwatch]::StartNew()
 while($wait.Elapsed.TotalSeconds -lt 5 -and (-not (Gone $marker.worker) -or -not (Gone $marker.child))){Start-Sleep -Milliseconds 50}
 Check ((Gone $marker.worker) -and (Gone $marker.child)) 'KILL_ON_JOB_CLOSE_PREVENTS_ORPHAN_TREE'
 @{state='PASS_NATIVE_WINDOWS_JOB_TREE_NOT_RELEASE_APPROVAL';checks=$checks.Count;cases=$checks.ToArray();source_sha256=(Get-FileHash $AgentPath -Algorithm SHA256).Hash.ToLowerInvariant();ps_version=$PSVersionTable.PSVersion.ToString();execution_policy=[string](Get-ExecutionPolicy);installed=$false;paired=$false;network_used=$false}|ConvertTo-Json -Depth 5
} finally {
 if($job){$job.Stop()|Out-Null;$job.Dispose()}
 if($parent){if(-not $parent.HasExited){$parent.Kill();$parent.WaitForExit(1000)|Out-Null};$parent.Dispose()}
 $env:LOCALAPPDATA=$prior
 if(Test-Path -LiteralPath $qa){Remove-Item -LiteralPath $qa -Recurse -Force}
}
