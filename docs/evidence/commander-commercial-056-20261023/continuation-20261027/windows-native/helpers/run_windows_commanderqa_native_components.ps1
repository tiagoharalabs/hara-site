param(
 [Parameter(Mandatory=$true)][string]$AgentPath,
 [Parameter(Mandatory=$true)][string]$JobFixturePath,
 [Parameter(Mandatory=$true)][string]$UserFixturePath,
 [Parameter(Mandatory=$true)][string]$OutputDirectory,
 [Parameter(Mandatory=$true)][string]$PolicyPreimagePath
)
$ErrorActionPreference='Stop'
$report=[ordered]@{schema='hara.commander.windows-native-components.v1';started_utc=[DateTime]::UtcNow.ToString('o');state='HOLD_PREFLIGHT';installed=$false;paired=$false;network_used=$false;cases=@();parser=@();policy_restore_owner='OUTER_BOOTSTRAP_FINALLY';global_task_readback=@{};cleanup=@{runner_children_exited=$true}}
$running=New-Object Collections.Generic.List[Diagnostics.Process]
$runDir=$null
function Fingerprint([string]$Text){$s=[Security.Cryptography.SHA256]::Create();try{return [BitConverter]::ToString($s.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))).Replace('-','').ToLowerInvariant()}finally{$s.Dispose()}}
function Global-Task-Readback {
 try {
  $t=Get-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\' -ErrorAction Stop
  $xml=Export-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\' -ErrorAction Stop
  return @{observed=$true;exists=$true;state=[string]$t.State;xml_sha256=(Fingerprint $xml)}
 } catch {
  if($_.CategoryInfo.Category -eq 'ObjectNotFound'){return @{observed=$true;exists=$false}}
  return @{observed=$false;category=[string]$_.CategoryInfo.Category;hresult=('0x{0:X8}' -f ($_.Exception.HResult -band 0xffffffffL))}
 }
}
function Save-New([string]$Path,[string]$Text){
 $f=New-Object IO.FileStream($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$b=(New-Object Text.UTF8Encoding($false)).GetBytes($Text);$f.Write($b,0,$b.Length)}finally{$f.Dispose()}
}
function Invoke-Case([string]$Name,[string]$Script,[string]$Arguments,[int]$Deadline,[string]$ExpectedState,[int]$ExpectedChecks){
 $r=[ordered]@{name=$Name;state='HOLD';exit_code=$null;timed_out=$false;parsed_result=$null}
 $p=New-Object Diagnostics.Process;$didStart=$false
 $p.StartInfo.FileName=Join-Path $PSHOME 'powershell.exe'
 $p.StartInfo.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+$Script+'" '+$Arguments
 $p.StartInfo.UseShellExecute=$false;$p.StartInfo.CreateNoWindow=$true
 $p.StartInfo.RedirectStandardOutput=$true;$p.StartInfo.RedirectStandardError=$true
 $clock=[Diagnostics.Stopwatch]::StartNew()
 try {
  if(-not $p.Start()){throw 'CHILD_START_FAILED'}
  $didStart=$true;$running.Add($p)
  $out=$p.StandardOutput.ReadToEndAsync();$err=$p.StandardError.ReadToEndAsync()
  if(-not $p.WaitForExit($Deadline*1000)){$r.timed_out=$true;$p.Kill();$p.WaitForExit(5000)|Out-Null}
  if(-not $p.HasExited){throw 'CHILD_STOP_NOT_CONFIRMED'}
  $r.exit_code=$p.ExitCode
  if(-not $out.Wait(5000) -or -not $err.Wait(5000)){throw 'HOLD_CAPTURE_CLOSE_TIMEOUT'}
  $stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
  Save-New (Join-Path $runDir ($Name+'.stdout.txt')) $stdout
  Save-New (Join-Path $runDir ($Name+'.stderr.txt')) $stderr
  $r.stdout_sha256=Fingerprint $stdout;$r.stderr_sha256=Fingerprint $stderr
  $r.stdout_bytes=[Text.Encoding]::UTF8.GetByteCount($stdout);$r.stderr_bytes=[Text.Encoding]::UTF8.GetByteCount($stderr)
  if($r.timed_out){$r.state='HOLD_TIMEOUT_FIXTURE_CLEANUP_NEEDS_READBACK'}
  elseif($p.ExitCode -ne 0){$r.state='HOLD_NONZERO_EXIT';try{$r.parsed_result=$stdout|ConvertFrom-Json}catch{}}
  elseif($ExpectedState){
   $value=$stdout|ConvertFrom-Json
   $count=if($Name -eq 'job-native'){$value.checks}else{$value.check_count}
   $r.parsed_result=$value
   if($value.state -cne $ExpectedState -or $count -ne $ExpectedChecks){$r.state='HOLD_RESULT_CONTRACT'}else{$r.state='PASS'}
  }elseif($Name -eq 'agent-version'){$r.state=if($stdout -match '\b0\.3\.56\b'){'PASS_VERSION_EXIT_ZERO'}else{'HOLD_VERSION_OUTPUT'}}else{$r.state='PASS_SELF_TEST_EXIT_ZERO'}
 }catch{$r.state=if($_.Exception.Message -ceq 'HOLD_CAPTURE_CLOSE_TIMEOUT'){'HOLD_CAPTURE_CLOSE_TIMEOUT'}else{'HOLD_RUNNER_CASE'};$r.error_type=$_.Exception.GetType().FullName;$r.error_category=[string]$_.CategoryInfo.Category}
 finally {
  $r.elapsed_seconds=[Math]::Round($clock.Elapsed.TotalSeconds,3)
  if($didStart){try{if(-not $p.HasExited){$p.Kill();$p.WaitForExit(5000)|Out-Null};if(-not $p.HasExited){$report.cleanup.runner_children_exited=$false}}catch{$report.cleanup.runner_children_exited=$false}}else{$p.Dispose()}
 }
 return $r
}
try {
 if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
 $id=[Security.Principal.WindowsIdentity]::GetCurrent();$sid=$id.User.Value
 $principal=New-Object Security.Principal.WindowsPrincipal($id)
 if($sid -eq 'S-1-5-18' -or $id.Name.Split('\')[-1] -ine 'CommanderQA' -or $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or (Get-Process -Id $PID).SessionId -le 0 -or -not (Test-Path ('Registry::HKEY_USERS\'+$sid))){throw 'EXPECTED_STANDARD_INTERACTIVE_QA_CONTEXT_REQUIRED'}
 foreach($path in @($AgentPath,$JobFixturePath,$UserFixturePath,$OutputDirectory,$PolicyPreimagePath)){if(-not [IO.Path]::IsPathRooted($path) -or $path.StartsWith('\\') -or $path.Contains('"')){throw 'LOCAL_ABSOLUTE_PATH_REQUIRED'}}
 if(-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)){throw 'PREPARED_OUTPUT_DIRECTORY_REQUIRED'}
 if((Get-Item -LiteralPath $OutputDirectory).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'OUTPUT_REPARSE_POINT_REFUSED'}
 $policy=Get-Content -Raw -LiteralPath $PolicyPreimagePath|ConvertFrom-Json
 if($policy.schema -cne 'hara.commander.qa-currentuser-policy-preimage.v1' -or $policy.user_sid -cne $sid -or @('Undefined','Restricted','AllSigned','RemoteSigned','Unrestricted') -cnotcontains [string]$policy.current_user){throw 'POLICY_PREIMAGE_REQUIRED'}
 if([string](Get-ExecutionPolicy -Scope CurrentUser) -cne 'RemoteSigned' -or [string](Get-ExecutionPolicy -Scope Process) -cne 'Undefined' -or [string](Get-ExecutionPolicy) -cne 'RemoteSigned'){throw 'EXPLICIT_CURRENTUSER_REMOTESIGNED_REQUIRED'}
 $report.policy=@{prior_current_user=[string]$policy.current_user;observed_current_user=[string](Get-ExecutionPolicy -Scope CurrentUser);observed_process=[string](Get-ExecutionPolicy -Scope Process);observed_effective=[string](Get-ExecutionPolicy);changed_by_runner=$false;restoration_not_proven_by_this_child=$true}
 $runDir=Join-Path $OutputDirectory ('native-components-'+[guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $runDir | Out-Null
 $report.global_task_readback.before=Global-Task-Readback
 $sources=@(
  @{name='agent';path=$AgentPath;sha='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'},
  @{name='job-native';path=$JobFixturePath;sha='e4210dc8346456d928ecbf645a963a6e8710aeca4f30a69d643e7c3c9c56f710'},
  @{name='user-context-native';path=$UserFixturePath;sha='4a7a9c42b198caba5143ccd7928b2b8d7b03696126e3f6374a0f540bd9e03cfd'}
 )
 foreach($s in $sources){
  if((Get-FileHash -LiteralPath $s.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $s.sha){throw ('SOURCE_PIN_MISMATCH_'+$s.name)}
  $tokens=$null;$errors=$null
  [Management.Automation.Language.Parser]::ParseFile($s.path,[ref]$tokens,[ref]$errors)|Out-Null
  $report.parser+=@{name=$s.name;sha256=$s.sha;error_count=@($errors).Count;error_ids=@($errors|ForEach-Object{$_.ErrorId});state=$(if(@($errors).Count -eq 0){'PASS'}else{'HOLD'})}
 }
 $report.state='RUNNING_NATIVE_COMPONENTS'
 if($report.parser[0].state -eq 'PASS'){$report.cases+=Invoke-Case 'agent-version' $AgentPath '--version' 20 '' 0;$report.cases+=Invoke-Case 'agent-self-test' $AgentPath '--self-test' 60 '' 0}
 if($report.parser[0].state -eq 'PASS' -and $report.parser[1].state -eq 'PASS'){$report.cases+=Invoke-Case 'job-native' $JobFixturePath ('-AgentPath "'+$AgentPath+'"') 90 'PASS_NATIVE_WINDOWS_JOB_TREE_NOT_RELEASE_APPROVAL' 6}
 if($report.parser[2].state -eq 'PASS'){$report.cases+=Invoke-Case 'user-context-native' $UserFixturePath ('-AgentPath "'+$AgentPath+'"') 105 'PASS_NATIVE_WINDOWS_USER_CONTEXT_NOT_RELEASE_APPROVAL' 13}
 $good=@($report.cases|Where-Object{$_.state -eq 'PASS' -or $_.state -eq 'PASS_SELF_TEST_EXIT_ZERO' -or $_.state -eq 'PASS_VERSION_EXIT_ZERO'}).Count
 $report.state=if($good -eq 4 -and @($report.parser|Where-Object{$_.state -eq 'PASS'}).Count -eq 3){'PASS_NATIVE_COMPONENTS_PENDING_BOOTSTRAP_CLOSEOUT'}else{'HOLD_NATIVE_COMPONENTS'}
}catch{$report.state='HOLD_RUNNER';$report.error=@{code=$(if([string]$_.Exception.Message -cmatch '^[A-Za-z0-9_-]{1,120}$'){[string]$_.Exception.Message}else{'NATIVE_OPERATION_FAILED'});type=$_.Exception.GetType().FullName;category=[string]$_.CategoryInfo.Category}}
finally {
 foreach($p in $running){try{if(-not $p.HasExited){$p.Kill();$p.WaitForExit(5000)|Out-Null};if(-not $p.HasExited){$report.cleanup.runner_children_exited=$false};$p.Dispose()}catch{$report.cleanup.runner_children_exited=$false}}
 $after=Global-Task-Readback;$report.global_task_readback.after=$after
 $before=$report.global_task_readback.before
 $report.global_task_readback.unchanged=if($before -and $before.observed -and $after.observed){$before.exists -eq $after.exists -and (-not $before.exists -or ($before.xml_sha256 -ceq $after.xml_sha256 -and $before.state -ceq $after.state))}else{$null}
 if($report.global_task_readback.unchanged -eq $false){$report.state='HOLD_GLOBAL_TASK_CHANGED'}
 if(-not $report.cleanup.runner_children_exited){$report.state='HOLD_RUNNER_CHILD_CLEANUP'}
 $report.finished_utc=[DateTime]::UtcNow.ToString('o')
 $report.limits=@('Components only: no install, enrollment, cloud calls or original-account DPAPI acceptance.','Original product task is read only; unavailable readback requires independent native verification.','Timeout requires native inspection of fixture descendants and temporary tasks; parent exit is not cleanup proof.','Outer bootstrap must prove CurrentUser policy restoration and removal of its unique launch task.')
 $json=$report|ConvertTo-Json -Depth 12
 if($runDir){Save-New (Join-Path $runDir 'result.json') $json}
 $json
}
if($report.state -eq 'PASS_NATIVE_COMPONENTS_PENDING_BOOTSTRAP_CLOSEOUT'){exit 0}else{exit 7}
