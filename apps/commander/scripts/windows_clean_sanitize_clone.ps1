[CmdletBinding()]
param([string]$ExpectedCloneUuid='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$actual=([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant()
if($actual -cne $ExpectedCloneUuid.ToLowerInvariant()){throw 'CLONE_UUID_REQUIRED_NO_MUTATION'}
if(-not[Security.Principal.WindowsIdentity]::GetCurrent().IsSystem){throw 'CLONE_SYSTEM_BOOTSTRAP_REQUIRED'}
$up=@(Get-NetAdapter -ErrorAction SilentlyContinue|Where-Object{$_.Status -eq 'Up'})
if($up.Count){throw 'CLONE_NETWORK_MUST_BE_ABSENT_BEFORE_SANITIZATION'}
$Root='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$qa='HARAQA'
if(Get-LocalUser -Name $qa -ErrorAction SilentlyContinue){throw 'CLONE_QA_ACCOUNT_COLLISION'}
# All effects below are limited to the UUID-guarded clone, initially without NICs.
$removedTasks=0
foreach($t in @(Get-ScheduledTask|Where-Object{$_.TaskName -eq 'HARA Commander Agent' -or $_.TaskName -match '^HARA_VM\d+|^HARA.*Commander|^HARA.*Probe'})){
 Stop-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -ErrorAction SilentlyContinue
 Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false -ErrorAction Stop
 $removedTasks++
}
foreach($p in @(Get-CimInstance Win32_Process|Where-Object{$_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine -match '(?i)-File\s+.*(?:hara-commander-agent\.ps1|operator-visible-wrapper\.ps1|operator-console-\d+)'})){
 Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
}
# Log off only sessions in this independent clone before deleting inherited profiles.
$sessionIds=@(Get-CimInstance Win32_Process|Where-Object{$_.SessionId -gt 0}|Select-Object -ExpandProperty SessionId -Unique)
foreach($id in $sessionIds){& logoff.exe ([string]$id) 2>$null}
$deadline=[DateTime]::UtcNow.AddSeconds(15)
do{
 $loaded=@(Get-CimInstance Win32_UserProfile|Where-Object{-not $_.Special -and $_.Loaded})
 if(-not $loaded.Count){break};Start-Sleep -Milliseconds 250
}while([DateTime]::UtcNow -lt $deadline)
if($loaded.Count){throw 'CLONE_INHERITED_PROFILE_STILL_LOADED'}
$removedProfiles=0
foreach($profile in @(Get-CimInstance Win32_UserProfile|Where-Object{-not $_.Special})){
 Remove-CimInstance -InputObject $profile -ErrorAction Stop
 $removedProfiles++
}
$disabledUsers=0
foreach($u in @(Get-LocalUser|Where-Object{[string]$_.SID -notmatch '-(?:500|501|503|504)$' -and $_.Enabled})){
 Disable-LocalUser -SID $u.SID -ErrorAction Stop;$disabledUsers++
}
foreach($path in @('C:\ProgramData\HaraLabs\CommanderWinLab','C:\Program Files\HARA Commander','C:\Program Files (x86)\HARA Commander')){
 if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop}
}
$founderResidues=@(Get-CimInstance Win32_UserProfile|Where-Object{-not $_.Special})
if($founderResidues.Count){throw 'CLONE_PROFILE_RESIDUES_PRESENT'}
$stillTasks=@(Get-ScheduledTask|Where-Object{$_.TaskName -eq 'HARA Commander Agent'})
if($stillTasks.Count){throw 'CLONE_COMMANDER_TASK_RESIDUE_PRESENT'}
New-Item -ItemType Directory -Path $Root -Force|Out-Null
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))
foreach($sid in @('S-1-5-18','S-1-5-32-544')){
 $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
}
Set-Acl -LiteralPath $Root -AclObject $acl
$random=New-Object byte[] 24;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();try{$rng.GetBytes($random)}finally{$rng.Dispose()}
$password='Qa!'+([Convert]::ToBase64String($random)).Replace('+','x').Replace('/','y')+'9'
$secure=ConvertTo-SecureString $password -AsPlainText -Force
$user=New-LocalUser -Name $qa -Password $secure -Description 'Temporary isolated Commander DEV acceptance' -PasswordNeverExpires -ErrorAction Stop
$admins=Get-LocalGroup -SID 'S-1-5-32-544'
Add-LocalGroupMember -Group $admins.Name -Member $qa
$acl=Get-Acl -LiteralPath $Root
$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier([string]$user.SID)),'ReadAndExecute','ContainerInherit,ObjectInherit','None','Allow')))
Set-Acl -LiteralPath $Root -AclObject $acl
# Autologon is confined to the private clone and removed by VM cleanup. The
# credential is never emitted; the clone's old local users remain disabled.
$winlogon='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Set-ItemProperty -LiteralPath $winlogon -Name AutoAdminLogon -Value '1'
Set-ItemProperty -LiteralPath $winlogon -Name DefaultUserName -Value $qa
Set-ItemProperty -LiteralPath $winlogon -Name DefaultDomainName -Value 'HARAQA5312'
Set-ItemProperty -LiteralPath $winlogon -Name DefaultPassword -Value $password
Set-ItemProperty -LiteralPath $winlogon -Name ForceAutoLogon -Value '1'
$secret=[pscustomobject]@{qa_name=$qa;qa_password_system_dpapi=($secure|ConvertFrom-SecureString);qa_sid=[string]$user.SID;clone_uuid=$actual}
[IO.File]::WriteAllText((Join-Path $Root 'qa-private.json'),($secret|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
$password=$null;$secure.Dispose();$secret=$null
Rename-Computer -NewName 'HARAQA5312' -Force -ErrorAction Stop
$proof=[ordered]@{schema='hara.windows-clean-clone-sanitization.v1';state='PASS_CLONE_SANITIZED_BEFORE_NETWORK';clone_uuid=$actual;network_up_adapters=0;inherited_commander_tasks_removed=$removedTasks;inherited_profiles_removed=$removedProfiles;inherited_local_users_disabled=$disabledUsers;qa_account_created=$true;qa_name=$qa;founder_configuration_contents_read=$false;founder_device_tokens_used=$false;configuration_or_password_printed=$false;preexisting_os_cloned=$true;commander_profile_and_enrollment_clean=$true;next_gate='REBOOT_QA_PROFILE_THEN_DEV_NETWORK'}
[IO.File]::WriteAllText((Join-Path $Root 'sanitized-before-network.json'),($proof|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
$proof|ConvertTo-Json -Compress
