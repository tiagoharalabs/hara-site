param([Parameter(Mandatory=$true)][string]$AgentPath)
$ErrorActionPreference='Stop'
$expectedSha='a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'
$result=[ordered]@{schema='hara.commander.windows-user-context-native.v1';state='HOLD';checks=@();stage='PREFLIGHT';installed=$false;paired=$false;network_used=$false;prior_user_dpapi_tested=$false;policy_changed=$false;cleanup=@{task_absent=$false;directory_absent=$false;child_exited=$true}}
$root=$null;$taskName=$null;$child=$null;$taskRegistered=$false
$checks=New-Object Collections.Generic.List[string]
function Check([bool]$Value,[string]$Name){if(-not $Value){throw ('QA_FAILED_'+$Name)};$checks.Add($Name)}
function Error-Code($E){
 $code=if([string]$E.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){[string]$E.Exception.Message}else{'NATIVE_OPERATION_FAILED'}
 @{code=$code;type=$E.Exception.GetType().FullName;hresult=('0x{0:X8}' -f ($E.Exception.HResult -band 0xffffffffL));category=[string]$E.CategoryInfo.Category}
}
function Task-Exists([string]$Name){
 $errors=@();$t=Get-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction SilentlyContinue -ErrorVariable errors
 foreach($e in $errors){if($e.CategoryInfo.Category -ne 'ObjectNotFound'){throw $e}}
 return $t
}
try {
 Check ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT -and $PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'WINDOWS_POWERSHELL_51'
 Check ([string](Get-ExecutionPolicy) -cne 'Bypass') 'NO_BYPASS_POLICY'
 $identity=[Security.Principal.WindowsIdentity]::GetCurrent();$sid=$identity.User.Value
 Check ($sid -ne 'S-1-5-18' -and $identity.Name.Split('\')[-1] -ieq 'CommanderQA') 'EXPECTED_QA_IDENTITY'
 $principal=New-Object Security.Principal.WindowsPrincipal($identity)
 Check (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'UNELEVATED_TOKEN'
 Check ((Get-Process -Id $PID).SessionId -gt 0 -and (Test-Path ('Registry::HKEY_USERS\'+$sid))) 'INTERACTIVE_SESSION_AND_LOADED_PROFILE'
 $AgentPath=(Resolve-Path -LiteralPath $AgentPath).Path
 Check ((Get-FileHash -LiteralPath $AgentPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $expectedSha) 'EXACT_AGENT_ARTIFACT'
 $result.source_sha256=$expectedSha;$result.ps_version=$PSVersionTable.PSVersion.ToString();$result.execution_policy=[string](Get-ExecutionPolicy)
 $result.stage='ACL'
 $root=Join-Path ([IO.Path]::GetTempPath()) ('hara-qa056-context-'+[guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $root | Out-Null
 $acl=New-Object Security.AccessControl.DirectorySecurity
 $acl.SetOwner($identity.User);$acl.SetAccessRuleProtection($true,$false)
 $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity.User,[Security.AccessControl.FileSystemRights]::FullControl,([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
 $acl.AddAccessRule($rule);Set-Acl -LiteralPath $root -AclObject $acl
 $observed=Get-Acl -LiteralPath $root
 $rules=@($observed.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
 Check ($observed.AreAccessRulesProtected -and $observed.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $sid -and $rules.Count -eq 1 -and $rules[0].IdentityReference.Value -ceq $sid -and $rules[0].AccessControlType -eq 'Allow' -and $rules[0].FileSystemRights -eq [Security.AccessControl.FileSystemRights]::FullControl -and -not $rules[0].IsInherited) 'TEMP_DIRECTORY_OWNER_ONLY_DACL'
 $result.stage='DPAPI_CROSS_PROCESS'
 Add-Type -AssemblyName System.Security
 $plain=New-Object byte[] 32;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();try{$rng.GetBytes($plain)}finally{$rng.Dispose()}
 $sha=[Security.Cryptography.SHA256]::Create();try{$plainHash=[BitConverter]::ToString($sha.ComputeHash($plain)).Replace('-','')}finally{$sha.Dispose()}
 $cipher=[Security.Cryptography.ProtectedData]::Protect($plain,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
 [IO.File]::WriteAllBytes((Join-Path $root 'cipher.bin'),$cipher)
 $dpapiScript=Join-Path $root 'dpapi-child.ps1'
 [IO.File]::WriteAllText($dpapiScript,@'
param([string]$Root,[string]$ExpectedSid,[string]$ExpectedHash)
$ErrorActionPreference='Stop'
if([string](Get-ExecutionPolicy) -ceq 'Bypass'){throw 'BYPASS_REFUSED'}
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if($sid -cne $ExpectedSid -or -not (Test-Path ('Registry::HKEY_USERS\'+$sid))){throw 'QA_CHILD_CONTEXT_MISMATCH'}
Add-Type -AssemblyName System.Security
$clear=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $Root 'cipher.bin')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
$sha=[Security.Cryptography.SHA256]::Create();try{$hash=[BitConverter]::ToString($sha.ComputeHash($clear)).Replace('-','')}finally{$sha.Dispose()}
if($hash -cne $ExpectedHash){throw 'QA_CHILD_DPAPI_HASH_MISMATCH'}
$reply=[Security.Cryptography.ProtectedData]::Protect($clear,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
[IO.File]::WriteAllBytes((Join-Path $Root 'reply.bin'),$reply)
[Array]::Clear($clear,0,$clear.Length)
[IO.File]::WriteAllText((Join-Path $Root 'dpapi-ok.json'),' {"same_user":true,"profile_loaded":true,"decrypted_expected_payload":true} ')
'@,(New-Object Text.UTF8Encoding($true)))
 $child=New-Object Diagnostics.Process
 $child.StartInfo.FileName=Join-Path $PSHOME 'powershell.exe'
 $child.StartInfo.Arguments='-NoLogo -NoProfile -NonInteractive -File "'+$dpapiScript+'" -Root "'+$root+'" -ExpectedSid "'+$sid+'" -ExpectedHash "'+$plainHash+'"'
 $child.StartInfo.UseShellExecute=$false;$child.StartInfo.CreateNoWindow=$true
 $child.StartInfo.RedirectStandardOutput=$true;$child.StartInfo.RedirectStandardError=$true
 Check ($child.Start()) 'DPAPI_CHILD_STARTED'
 $childOut=$child.StandardOutput.ReadToEndAsync();$childErr=$child.StandardError.ReadToEndAsync()
 if(-not $child.WaitForExit(30000)){$child.Kill();$child.WaitForExit(5000)|Out-Null;throw 'DPAPI_CHILD_TIMEOUT'}
 $result.dpapi_child_exit_code=$child.ExitCode
 Check ($child.ExitCode -eq 0 -and (Test-Path -LiteralPath (Join-Path $root 'dpapi-ok.json'))) 'DPAPI_CHILD_DECRYPTED_PARENT_PAYLOAD'
 $reply=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $root 'reply.bin')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
 $sha=[Security.Cryptography.SHA256]::Create();try{$replyHash=[BitConverter]::ToString($sha.ComputeHash($reply)).Replace('-','')}finally{$sha.Dispose()}
 Check ($replyHash -ceq $plainHash) 'DPAPI_PARENT_DECRYPTED_CHILD_PAYLOAD'
 [Array]::Clear($plain,0,$plain.Length);[Array]::Clear($reply,0,$reply.Length)
 $child.Dispose();$child=$null
 $result.stage='TASK_REGISTER'
 $taskName='HARA-QA056-Context-'+[guid]::NewGuid().ToString('N')
 if(Task-Exists $taskName){throw 'TASK_NAME_COLLISION'}
 $taskScript=Join-Path $root 'task-child.ps1'
 [IO.File]::WriteAllText($taskScript,@'
param([string]$Root,[string]$ExpectedSid)
$ErrorActionPreference='Stop'
$id=[Security.Principal.WindowsIdentity]::GetCurrent()
if($id.User.Value -cne $ExpectedSid -or [string](Get-ExecutionPolicy) -ceq 'Bypass'){throw 'QA_TASK_CONTEXT_MISMATCH'}
$p=New-Object Security.Principal.WindowsPrincipal($id)
if($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or (Get-Process -Id $PID).SessionId -le 0 -or -not (Test-Path ('Registry::HKEY_USERS\'+$ExpectedSid))){throw 'QA_TASK_CONTEXT_NOT_LIMITED_INTERACTIVE'}
$r=@{same_user=$true;profile_loaded=$true;unelevated=$true;interactive=$true;pid=$PID;started=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')}
[IO.File]::WriteAllText((Join-Path $Root 'task-ok.new'),($r|ConvertTo-Json -Compress))
[IO.File]::Move((Join-Path $Root 'task-ok.new'),(Join-Path $Root 'task-ok.json'))
'@,(New-Object Text.UTF8Encoding($true)))
 $a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -File "'+$taskScript+'" -Root "'+$root+'" -ExpectedSid "'+$sid+'"')
 $p=New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
 $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 45) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
 Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $a -Principal $p -Settings $settings | Out-Null
 $taskRegistered=$true
 $t=Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop
 Check ([string]$t.Principal.LogonType -eq 'Interactive' -and [string]$t.Principal.RunLevel -eq 'Limited' -and (-not $t.Triggers -or @($t.Triggers).Count -eq 0)) 'TASK_REGISTERED_LIMITED_INTERACTIVE_ON_DEMAND'
 $result.stage='TASK_RUN'
 Start-ScheduledTask -TaskName $taskName -TaskPath '\'
 $clock=[Diagnostics.Stopwatch]::StartNew()
 while($clock.Elapsed.TotalSeconds -lt 45){
  $t=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
  if((Test-Path -LiteralPath (Join-Path $root 'task-ok.json')) -and [string]$t.State -ne 'Running'){break}
  Start-Sleep -Milliseconds 200
 }
 $info=Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
 Check ((Test-Path -LiteralPath (Join-Path $root 'task-ok.json')) -and [string]$t.State -ne 'Running' -and $info.LastTaskResult -eq 0) 'TASK_REAL_EXECUTION_EXIT_ZERO'
 $marker=Get-Content -Raw -LiteralPath (Join-Path $root 'task-ok.json') | ConvertFrom-Json
 Check ($marker.same_user -and $marker.profile_loaded -and $marker.unelevated -and $marker.interactive) 'TASK_REAL_USER_CONTEXT'
 $result.state='PASS_NATIVE_WINDOWS_USER_CONTEXT_NOT_RELEASE_APPROVAL';$result.stage='COMPLETE'
} catch {$result.error=Error-Code $_;$result.state=('HOLD_'+$result.stage)}
finally {
 if($child){try{if(-not $child.HasExited){$child.Kill();$child.WaitForExit(5000)|Out-Null};$result.cleanup.child_exited=$child.HasExited;$child.Dispose()}catch{$result.cleanup.child_exited=$false}}
 if($taskName){try{
  $t=Task-Exists $taskName
  if($t){if([string]$t.State -eq 'Running'){Stop-ScheduledTask -TaskName $taskName -TaskPath '\'};Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false}
  $result.cleanup.task_absent=(-not [bool](Task-Exists $taskName))
 }catch{$result.cleanup.task_absent=$false;$result.cleanup.task_error=Error-Code $_}}
 else{$result.cleanup.task_absent=$true}
 if($root){try{Remove-Item -LiteralPath $root -Recurse -Force;$result.cleanup.directory_absent=(-not (Test-Path -LiteralPath $root))}catch{$result.cleanup.directory_absent=$false;$result.cleanup.directory_error=Error-Code $_}}
 else{$result.cleanup.directory_absent=$true}
 if(-not $result.cleanup.task_absent -or -not $result.cleanup.directory_absent -or -not $result.cleanup.child_exited){$result.state='HOLD_CLEANUP'}
 $result.checks=$checks.ToArray();$result.check_count=$checks.Count
 $result.limits=@('Platform fixture only; does not install, pair or test product enrollment.','Same new QA account DPAPI only; no old-account migration or cross-account secrecy claim.','Owner-only DACL inspection; no hostile second-account access attempt.','Temporary on-demand task only; not the product task lifecycle or reboot recovery.')
 $result | ConvertTo-Json -Depth 6
}
if($result.state -eq 'PASS_NATIVE_WINDOWS_USER_CONTEXT_NOT_RELEASE_APPROVAL'){exit 0}else{exit 7}
