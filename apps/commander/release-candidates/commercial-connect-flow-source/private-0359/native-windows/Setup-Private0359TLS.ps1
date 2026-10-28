$qaTlsDeadlineUtc='2026-10-28T19:35:00Z'
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-18'){throw 'SYSTEM_REQUIRED'}
if((Get-CimInstance Win32_ComputerSystem).UserName -ine 'HARA_WIN11\CommanderQA'){throw 'COMMANDERQA_CONSOLE_REQUIRED'}
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028'
$path=Join-Path $root 'config\qa-release-r3.der'
$pin='893aeec40a123d5fd74fd312fa1ed90e4c9881e10a562cdc126026c3d848f29e'
if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin){throw 'PUBLIC_CERT_PIN_MISMATCH'}
$deadline=[DateTimeOffset]::Parse($qaTlsDeadlineUtc);if($deadline -le [DateTimeOffset]::UtcNow.AddMinutes(10) -or $deadline -gt [DateTimeOffset]::UtcNow.AddMinutes(45)){throw 'INVALID_TLS_DEADLINE'}
$old=Get-Content -Raw -LiteralPath (Join-Path $root 'results\admin-tls-r3-cleanup.json')|ConvertFrom-Json
if($old.state -cne 'PASS_ADMIN_QA_TLS_CLOSED' -or -not $old.store_verified){throw 'PRIOR_TLS_CLEANUP_NOT_PROVEN'}
$productTask=Get-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\'
if([string]$productTask.State -cne 'Running' -or [string]$productTask.Principal.UserId -notin @('HARA_WIN11\CommanderQA','CommanderQA','S-1-5-21-1207901905-1500652706-889822281-1005')){throw 'EXISTING_QA_RUNNING_TASK_REQUIRED'}
$productXml=Export-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\'
$expectedThumb='91455FF01AE18E0F3721E3D56B5382A1F4145129'

$recordPath=Join-Path $root 'backup\admin-tls-0359-preimage.json'
if(Test-Path -LiteralPath $recordPath){throw 'TLS_BOOTSTRAP_ALREADY_RECORDED'}
$cert=New-Object Security.Cryptography.X509Certificates.X509Certificate2($path)
if($cert.Thumbprint -cne $expectedThumb){throw 'PUBLIC_CERT_THUMBPRINT_MISMATCH'}
$store=New-Object Security.Cryptography.X509Certificates.X509Store('Root','LocalMachine');$store.Open('ReadWrite')
$preexisting=(@($store.Certificates.Find('FindByThumbprint',$cert.Thumbprint,$false)).Count -gt 0)
if($preexisting){$store.Close();throw 'QA_ROOT_CERT_UNEXPECTEDLY_PRESENT'}
$before=[ordered]@{schema='hara.commander.qa-administrative-tls-preimage.v1';at_utc=[DateTime]::UtcNow.ToString('o');store='LocalMachine\Root';certificate_preexisting=$preexisting;thumbprint=$cert.Thumbprint;der_sha256=$pin;cleanup_deadline_utc=$qaTlsDeadlineUtc;scope='Dedicated existing Windows QA VM only'}
[IO.File]::WriteAllText($recordPath,($before|ConvertTo-Json),[Text.Encoding]::UTF8)
$cleanup=@'
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028'
$r=[ordered]@{at_utc=[DateTime]::UtcNow.ToString('o');state='HOLD';removed=$false}
try{
 $pre=Get-Content -Raw -LiteralPath (Join-Path $root 'backup\admin-tls-0359-preimage.json')|ConvertFrom-Json
 $path=Join-Path $root 'config\qa-release-r3.der'
 if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pre.der_sha256){throw 'PUBLIC_CERT_PIN_MISMATCH'}
 $expected=New-Object Security.Cryptography.X509Certificates.X509Certificate2($path)
 $s=New-Object Security.Cryptography.X509Certificates.X509Store('Root','LocalMachine');$s.Open('ReadWrite')
 try{
  if(-not $pre.certificate_preexisting){foreach($c in @($s.Certificates.Find('FindByThumbprint',$expected.Thumbprint,$false))){if([Convert]::ToBase64String($c.RawData) -cne [Convert]::ToBase64String($expected.RawData)){throw 'CERTIFICATE_CHANGED'};$s.Remove($c);$r.removed=$true}}
  $r.expected_store_state=if($pre.certificate_preexisting){'PREEXISTING_PRESERVED'}else{'ABSENT'}
  $r.store_verified=if($pre.certificate_preexisting){@($s.Certificates.Find('FindByThumbprint',$expected.Thumbprint,$false)).Count -gt 0}else{@($s.Certificates.Find('FindByThumbprint',$expected.Thumbprint,$false)).Count -eq 0}
 }finally{$s.Close();$expected.Dispose()}
 if(-not $r.store_verified){throw 'TLS_CLEANUP_READBACK_FAILED'}
 $r.state='PASS_ADMIN_QA_TLS_CLOSED'
}catch{$r.error_type=$_.Exception.GetType().FullName}
[IO.File]::WriteAllText((Join-Path $root 'results\admin-tls-0359-cleanup.json'),($r|ConvertTo-Json),[Text.Encoding]::UTF8)
if($r.state -eq 'PASS_ADMIN_QA_TLS_CLOSED'){exit 0}else{exit 2}
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cleanup))
$task='HARA-QA059-TemporaryTLS-Cleanup-20261028'
if(Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue){throw 'CLEANUP_TASK_EXISTS'}
$a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+$encoded)
$p=New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$trigger=New-ScheduledTaskTrigger -Once -At ([DateTimeOffset]::Parse($qaTlsDeadlineUtc).LocalDateTime)
$boot=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $task -Action $a -Principal $p -Trigger @($trigger,$boot) -Settings $settings|Out-Null
try{
 if(-not $preexisting){$store.Add($cert)}
 $match=@($store.Certificates.Find('FindByThumbprint',$cert.Thumbprint,$false))
 if($match.Count -ne 1 -or [Convert]::ToBase64String($match[0].RawData) -cne [Convert]::ToBase64String($cert.RawData)){throw 'ADMIN_TRUST_READBACK_FAILED'}
 if((Export-ScheduledTask -TaskName 'HARA Commander Agent' -TaskPath '\') -cne $productXml){throw 'PRODUCT_TASK_CHANGED'}
 [ordered]@{state='ADMIN_QA_TLS_READY';store='LocalMachine\Root';certificate_preexisting=$preexisting;thumbprint=$cert.Thumbprint;der_sha256=$pin;automatic_cleanup_task=$task;cleanup_deadline_utc=$qaTlsDeadlineUtc;installer_identity='CommanderQA';product_task_changed=$false}|ConvertTo-Json -Compress
}catch{Start-ScheduledTask -TaskName $task;throw}finally{$store.Close();$cert.Dispose()}
