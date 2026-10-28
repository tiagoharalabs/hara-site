$ErrorActionPreference='Stop'
$base='C:\ProgramData\HARA-QA\native-0356-activeqa-20261027'
$source=Join-Path $base 'source';$results=Join-Path $base 'results'
$taskName=$null;$taskCreated=$false
$r=[ordered]@{schema='hara.commander.qa-native-bootstrap.v1';started_utc=[DateTime]::UtcNow.ToString('o');state='HOLD_PREFLIGHT';installed=$false;paired=$false;global_product_task_mutated=$false;cleanup=@{bootstrap_task_absent=$true};limits=@('Component tests only; no installation, cloud pairing or release approval.','Cold VM checkpoint remains a separate result; this execution does not turn a prior HOLD into PASS.')}
function Hash-Text([string]$Text){$h=[Security.Cryptography.SHA256]::Create();try{[BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function Save-New([string]$Path,[string]$Text){$f=New-Object IO.FileStream($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$b=[Text.Encoding]::UTF8.GetBytes($Text);$f.Write($b,0,$b.Length)}finally{$f.Dispose()}}
function Global-Readback {$t=Get-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\' -ErrorAction Stop;@{state=[string]$t.State;xml_sha256=(Hash-Text (Export-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\' -ErrorAction Stop))}}
try {
 if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-18' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'SYSTEM_POWERSHELL51_REQUIRED'}
 if(Test-Path -LiteralPath (Join-Path $base 'bootstrap-result.json')){throw 'BOOTSTRAP_ALREADY_RECORDED_NO_REPLAY'}
 foreach($n in @('policy-before.json','policy-bootstrap-result.json','runner-output.json','runner-outer.stderr.txt')){if(Test-Path -LiteralPath (Join-Path $results $n)){throw 'PRIOR_QA_RUN_PRESENT_NO_REPLAY'}}
 $qa=Get-LocalUser -Name 'CommanderQA' -ErrorAction Stop
 if(-not $qa.Enabled){throw 'QA_ACCOUNT_DISABLED'}
 $sid=$qa.SID.Value
 $console=[string](Get-CimInstance Win32_ComputerSystem).UserName
 if($console.Split('\')[-1] -ine 'CommanderQA'){throw 'QA_CONSOLE_LOGIN_REQUIRED'}
 $profile=Get-CimInstance Win32_UserProfile -Filter ("SID='"+$sid+"'")
 if(-not $profile.Loaded){throw 'QA_PROFILE_NOT_LOADED'}
 $r.global_before=Global-Readback
 if($r.global_before.state -cne 'Disabled'){throw 'ORIGINAL_PRODUCT_TASK_MUST_REMAIN_DISABLED'}
 $pins=@{
  'agent-windows-0.3.56.ps1'='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620';
  'test_commercial_056_windows_job_native.ps1'='e4210dc8346456d928ecbf645a963a6e8710aeca4f30a69d643e7c3c9c56f710';
  'test_windows_commanderqa_user_context_native.ps1'='4a7a9c42b198caba5143ccd7928b2b8d7b03696126e3f6374a0f540bd9e03cfd';
  'run_windows_commanderqa_native_components.ps1'='912ba13f77ca5e72128af1c1f79e8fec7e0b92454f0a82dd1d01e9ca53f65cb6'
 }
 $r.parser=@()
 foreach($name in $pins.Keys){
  $path=Join-Path $source $name
  if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pins[$name]){throw 'SOURCE_PIN_MISMATCH'}
  $tokens=$null;$errors=$null;[Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)|Out-Null
  $r.parser+=@{name=$name;sha256=$pins[$name];errors=@($errors|ForEach-Object{$_.ErrorId})}
  if($errors.Count -gt 0){throw 'NATIVE_PARSE_ERROR'}
 }
 $userCode=@'
$ErrorActionPreference='Stop'
$base='C:\ProgramData\HARA-QA\native-0356-activeqa-20261027'
$source=Join-Path $base 'source';$results=Join-Path $base 'results'
$out=[ordered]@{schema='hara.commander.qa-policy-bootstrap-result.v1';state='HOLD';runner_exit=$null;policy_changed=$false;policy_restored=$false}
$prior=$null;$setAttempted=$false
function Save-New([string]$Path,[string]$Text){$f=New-Object IO.FileStream($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$b=[Text.Encoding]::UTF8.GetBytes($Text);$f.Write($b,0,$b.Length)}finally{$f.Dispose()}}
try {
 $id=[Security.Principal.WindowsIdentity]::GetCurrent();$p=New-Object Security.Principal.WindowsPrincipal($id)
 if($id.Name.Split('\')[-1] -ine 'CommanderQA' -or $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or (Get-Process -Id $PID).SessionId -le 0){throw 'QA_LIMITED_INTERACTIVE_REQUIRED'}
 $prior=[string](Get-ExecutionPolicy -Scope CurrentUser)
 if(@('Undefined','Restricted','AllSigned','RemoteSigned','Unrestricted') -cnotcontains $prior -or [string](Get-ExecutionPolicy -Scope Process) -cne 'Undefined'){throw 'UNEXPECTED_POLICY_BASELINE'}
 $pre=@{schema='hara.commander.qa-currentuser-policy-preimage.v1';at_utc=[DateTime]::UtcNow.ToString('o');user_sid=$id.User.Value;current_user=$prior;policies=@(Get-ExecutionPolicy -List|Select-Object Scope,ExecutionPolicy)}
 Save-New (Join-Path $results 'policy-before.json') ($pre|ConvertTo-Json -Depth 5)
 $setAttempted=$true
 Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force -ErrorAction Stop
 $out.policy_changed=($prior -cne 'RemoteSigned');$out.prior_current_user=$prior
 $out.applied_current_user=[string](Get-ExecutionPolicy -Scope CurrentUser);$out.effective_after_apply=[string](Get-ExecutionPolicy)
 if($out.applied_current_user -cne 'RemoteSigned' -or $out.effective_after_apply -cne 'RemoteSigned'){throw 'POLICY_EFFECTIVE_HOLD'}
 $lines=& (Join-Path $PSHOME 'powershell.exe') -NoLogo -NoProfile -NonInteractive -File (Join-Path $source 'run_windows_commanderqa_native_components.ps1') -AgentPath (Join-Path $source 'agent-windows-0.3.56.ps1') -JobFixturePath (Join-Path $source 'test_commercial_056_windows_job_native.ps1') -UserFixturePath (Join-Path $source 'test_windows_commanderqa_user_context_native.ps1') -OutputDirectory $results -PolicyPreimagePath (Join-Path $results 'policy-before.json') 2> (Join-Path $results 'runner-outer.stderr.txt')
 $out.runner_exit=$LASTEXITCODE
 Save-New (Join-Path $results 'runner-output.json') ($lines -join "`n")
 $out.state=if($out.runner_exit -eq 0){'PASS_RUNNER_PENDING_POLICY_RESTORE'}else{'HOLD_RUNNER_RESULT'}
}catch{$out.state='HOLD_USER_BOOTSTRAP';$out.error=@{type=$_.Exception.GetType().FullName;category=[string]$_.CategoryInfo.Category;code=$(if([string]$_.Exception.Message -cmatch '^[A-Z0-9_]{1,100}$'){[string]$_.Exception.Message}else{'NATIVE_OPERATION_FAILED'})}}
finally {
 if($setAttempted){try{Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy $prior -Force -ErrorAction Stop;$out.restored_current_user=[string](Get-ExecutionPolicy -Scope CurrentUser);$out.policy_restored=($out.restored_current_user -ceq $prior)}catch{$out.policy_restored=$false}}
 else{$out.policy_restored=$true}
 if(-not $out.policy_restored){$out.state='HOLD_POLICY_RESTORE'}elseif($out.state -eq 'PASS_RUNNER_PENDING_POLICY_RESTORE'){$out.state='PASS_RUNNER_AND_POLICY_RESTORE'}
 $out.finished_utc=[DateTime]::UtcNow.ToString('o')
 Save-New (Join-Path $results 'policy-bootstrap-result.json') ($out|ConvertTo-Json -Depth 6)
}
if($out.state -eq 'PASS_RUNNER_AND_POLICY_RESTORE'){exit 0}else{exit 7}
'@
 $taskName='HARA-QA056-NativeBootstrap-'+[guid]::NewGuid().ToString('N')
 $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($userCode))
 $a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -EncodedCommand '+$encoded)
 $principal=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
 $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 7) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
 Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $a -Principal $principal -Settings $settings | Out-Null
 $taskCreated=$true;$r.cleanup.bootstrap_task_absent=$false;$r.bootstrap_task_name=$taskName
 Start-ScheduledTask -TaskName $taskName -TaskPath '\'
 $clock=[Diagnostics.Stopwatch]::StartNew()
 while($clock.Elapsed.TotalSeconds -lt 360){$t=Get-ScheduledTask -TaskName $taskName -TaskPath '\';if((Test-Path -LiteralPath (Join-Path $results 'policy-bootstrap-result.json')) -and [string]$t.State -ne 'Running'){break};Start-Sleep -Milliseconds 500}
 $t=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
 if([string]$t.State -eq 'Running'){throw 'BOOTSTRAP_TIMEOUT_TASK_STILL_RUNNING'}
 $r.bootstrap_task_result=(Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\').LastTaskResult
 $r.user_bootstrap=Get-Content -Raw -LiteralPath (Join-Path $results 'policy-bootstrap-result.json')|ConvertFrom-Json
 if(Test-Path -LiteralPath (Join-Path $results 'runner-output.json')){$r.runner=Get-Content -Raw -LiteralPath (Join-Path $results 'runner-output.json')|ConvertFrom-Json}
 $r.state=if($r.bootstrap_task_result -eq 0 -and $r.user_bootstrap.state -ceq 'PASS_RUNNER_AND_POLICY_RESTORE' -and $r.runner.state -ceq 'PASS_NATIVE_COMPONENTS_PENDING_BOOTSTRAP_CLOSEOUT'){'PASS_NATIVE_COMPONENTS_NOT_RELEASE_APPROVAL'}else{'HOLD_NATIVE_COMPONENTS'}
}catch{$r.state='HOLD_BOOTSTRAP';$r.error=@{type=$_.Exception.GetType().FullName;category=[string]$_.CategoryInfo.Category;code=$(if([string]$_.Exception.Message -cmatch '^[A-Z0-9_]{1,100}$'){[string]$_.Exception.Message}else{'NATIVE_OPERATION_FAILED'})}}
finally {
 if($taskCreated){try{$t=Get-ScheduledTask -TaskName $taskName -TaskPath '\';if([string]$t.State -ne 'Running'){Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false;$r.cleanup.bootstrap_task_absent=(@(Get-ScheduledTask -TaskPath '\'|Where-Object{$_.TaskName -ceq $taskName}).Count -eq 0)}}catch{$r.cleanup.bootstrap_task_absent=$false}}
 try{$r.global_after=Global-Readback;$r.global_unchanged=($r.global_before.xml_sha256 -ceq $r.global_after.xml_sha256 -and $r.global_before.state -ceq $r.global_after.state)}catch{$r.global_unchanged=$false}
 if(-not $r.global_unchanged -or -not $r.cleanup.bootstrap_task_absent){$r.state='HOLD_BOOTSTRAP_CLOSEOUT'}
 $r.finished_utc=[DateTime]::UtcNow.ToString('o')
 $json=$r|ConvertTo-Json -Depth 18
 Save-New (Join-Path $base 'bootstrap-result.json') $json
 $json
}
if($r.state -eq 'PASS_NATIVE_COMPONENTS_NOT_RELEASE_APPROVAL'){exit 0}else{exit 7}
