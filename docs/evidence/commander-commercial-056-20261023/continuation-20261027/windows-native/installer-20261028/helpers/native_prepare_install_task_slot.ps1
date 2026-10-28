$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-18'){throw 'SYSTEM_REQUIRED'}
if((Get-CimInstance Win32_ComputerSystem).UserName -ine 'HARA_WIN11\CommanderQA'){throw 'COMMANDERQA_CONSOLE_REQUIRED'}
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028';$backup=Join-Path $root 'backup'
$name='HARA Commander Agent';$cfgPath=Join-Path $root 'config\install-config.json'
$preflight=Get-Content -Raw -LiteralPath (Join-Path $root 'results\preflight-r4-result.json')|ConvertFrom-Json
if($preflight.state -cne 'PASS_NATIVE_PREFLIGHT' -or $preflight.exit_code -ne 0 -or $preflight.wrapper.state -cne 'PASS_PREFLIGHT'){throw 'NATIVE_PREFLIGHT_REQUIRED'}
if(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json'){throw 'QA_ALREADY_ENROLLED'}
function Hash-Text([string]$Text){$h=[Security.Cryptography.SHA256]::Create();try{[BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function Save-New([string]$Path,[string]$Text){$s=New-Object IO.FileStream($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$b=[Text.Encoding]::UTF8.GetBytes($Text);$s.Write($b,0,$b.Length);$s.Flush($true)}finally{$s.Dispose()}}
$old=Get-ScheduledTask -TaskName $name -TaskPath '\'
if([string]$old.State -cne 'Disabled' -or [string]$old.Principal.UserId -cne 'sarti'){throw 'OLD_TASK_PREIMAGE_MISMATCH'}
$xml=Export-ScheduledTask -TaskName $name -TaskPath '\'
if((Hash-Text $xml) -cne '1afc226ed51490342dfb2be28f7b7a4fd2c25122c9f11c8b69b2bb48e3e3f8b9'){throw 'OLD_TASK_XML_CHANGED'}
$service=New-Object -ComObject Schedule.Service;$service.Connect();$original=$service.GetFolder('\').GetTask($name)
$sddl=$original.GetSecurityDescriptor(7)
Save-New (Join-Path $backup 'sarti-agent-task.xml') $xml
Save-New (Join-Path $backup 'sarti-agent-task.sddl') $sddl
Save-New (Join-Path $backup 'config-before-task-slot.json') ([IO.File]::ReadAllText($cfgPath))
$meta=@{at_utc=[DateTime]::UtcNow.ToString('o');task=$name;principal='sarti';state='Disabled';xml_sha256=(Hash-Text $xml);sddl_sha256=(Hash-Text $sddl);source_files_retained=$true;task_execution_performed=$false}
Save-New (Join-Path $backup 'task-migration-preimage.json') ($meta|ConvertTo-Json)
try{
 Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false
 if(Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue){throw 'TASK_SLOT_NOT_EMPTY'}
 $cfg=Get-Content -Raw -LiteralPath $cfgPath|ConvertFrom-Json
 $cfg.task_slot_clearance='EMPTY_FOR_COMMANDERQA';$cfg.task_slot_verified_utc=[DateTime]::UtcNow.ToString('o')
 [IO.File]::WriteAllText($cfgPath,($cfg|ConvertTo-Json),[Text.Encoding]::UTF8)
 $r=[ordered]@{state='INSTALL_TASK_SLOT_READY';at_utc=[DateTime]::UtcNow.ToString('o');old_task_archived=$true;old_task_was_disabled=$true;old_xml_sha256=$meta.xml_sha256;old_sddl_sha256=$meta.sddl_sha256;global_task_absent=$true;account='CommanderQA';identity_account='openai-reviewer@haralabs.com.br';installed=$false;paired=$false;next_required='LEGITIMATE_REVIEWER_PAIRING_TOKEN'}
 [IO.File]::WriteAllText((Join-Path $root 'results\task-slot-ready.json'),($r|ConvertTo-Json),[Text.Encoding]::UTF8)
 $r|ConvertTo-Json -Compress
}catch{
 if(-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)){
  Register-ScheduledTask -TaskName $name -Xml $xml|Out-Null
  Disable-ScheduledTask -TaskName $name|Out-Null
  $restored=$service.GetFolder('\').GetTask($name);$restored.SetSecurityDescriptor($sddl,0)
 }
 [IO.File]::WriteAllText($cfgPath,[IO.File]::ReadAllText((Join-Path $backup 'config-before-task-slot.json')),[Text.Encoding]::UTF8)
 throw
}
