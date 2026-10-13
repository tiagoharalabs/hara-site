$ErrorActionPreference="Stop"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne "d35599c8-b9ea-45e5-9ae9-fa047e84b8ba"){throw "QA_UUID_REQUIRED"}
$Name="HARA Commander Clean QA Harness"
if((Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue).State -eq "Running"){throw "QA_HARNESS_RUNNING"}
if(Get-ScheduledTask -TaskName "HARA Commander Agent" -ErrorAction SilentlyContinue){throw "CLEAN_TASK_REQUIRED"}
$Child=Join-Path $Box "native-054-install-child.ps1"
$Body=@'
$ErrorActionPreference="Stop";$ProgressPreference="SilentlyContinue"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
$SpecPath=Join-Path $Box "phase-054-private.json"
$Out=Join-Path $Box "native-054-install.txt"
$Log=Join-Path $Box "native-054-install.private.log"
$Result=$false;$Child=$null;$Failure=$null
function Put([string]$V){[IO.File]::AppendAllText($Out,$V+[char]10)}
function Hash([string]$P){return [string](& certutil.exe -hashfile $P SHA256 2>$null|Where-Object{$_ -cmatch "^[0-9a-fA-F]{64}$"}|Select-Object -First 1)}
[IO.File]::WriteAllText($Out,"PHASE=install-054"+[char]10)
try{
 if($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw "QA_PS51_REQUIRED"}
 if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne "d35599c8-b9ea-45e5-9ae9-fa047e84b8ba"){throw "QA_UUID_REQUIRED"}
 $Identity=[Security.Principal.WindowsIdentity]::GetCurrent()
 if($Identity.IsSystem -or $env:USERNAME -cne "HARAQA" -or $env:LOCALAPPDATA -cne "C:\Users\HARAQA\AppData\Local"){throw "ACTUAL_QA_PROFILE_REQUIRED"}
 $Root=Join-Path $env:LOCALAPPDATA "HARA Commander"
 if(Test-Path -LiteralPath $Root){throw "CLEAN_PROFILE_REQUIRED"}
 $Spec=Get-Content -LiteralPath $SpecPath -Raw|ConvertFrom-Json
 $Dev="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
 if($Spec.dev_origin -cne $Dev -or [string]::IsNullOrWhiteSpace([string]$Spec.pairing_token)){throw "NORMAL_QA_PAIRING_REQUIRED"}
 $Manifest=Join-Path $Box "dev-054-manifest.json"
 $Installer=Join-Path $Box "windows-054-r1.ps1"
 Invoke-WebRequest -UseBasicParsing -Uri ($Dev+"/release/agent-manifest.json") -OutFile $Manifest -TimeoutSec 30 -MaximumRedirection 0
 if((Hash $Manifest) -cne "ff88de00063b45bb38cf872d73cb70ba6cdb036a2a883afcbf6eb4057ad522d3"){throw "FINAL_054_MANIFEST_REQUIRED"}
 Invoke-WebRequest -UseBasicParsing -Uri ($Dev+"/install/windows.ps1") -OutFile $Installer -TimeoutSec 30 -MaximumRedirection 0
 if((Hash $Installer) -cne "ea9f046bebf9ed85feefae05590ac915a75e9b491aefe1833d40bf316d414cc7"){throw "FINAL_054_INSTALLER_REQUIRED"}
 . (Join-Path $Box "windows_clean_console_api.ps1")
 $Runner=Join-Path $Box "native-054-signed-installer-child.ps1"
 $RunnerBody='$ErrorActionPreference=''Stop'';$global:LASTEXITCODE=0;$env:HARA_COMMANDER_URL='''+$Dev+''';$env:HARA_COMMANDER_APPROVAL_MODE=''SESSION_TRUSTED'';try{& '''+$Installer+''' -Action install *> '''+$Log+''';if(-not $? -or $LASTEXITCODE -ne 0){exit 1};exit 0}catch{[IO.File]::WriteAllText('''+(Join-Path $Box 'native-054-install.error.private.txt')+''',([string]$_.Exception.Message));exit 1}'
 [IO.File]::WriteAllText($Runner,$RunnerBody,(New-Object Text.UTF8Encoding($false)))
 $Exe=(Get-Command powershell.exe).Source
 $Child=[CleanConsoleInput]::Launch('"'+$Exe+'" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "'+$Runner+'"')
 Start-Sleep -Milliseconds 1600
 $Typed=[CleanConsoleInput]::Type($Child,([string]$Spec.pairing_token+[char]13))
 $Spec.pairing_token=$null
 [IO.File]::WriteAllText($SpecPath,($Spec|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
 if(-not $Typed){throw "SECURE_NORMAL_PAIRING_INPUT_FAILED"}
 $Deadline=[DateTime]::UtcNow.AddSeconds(150)
 do{$ExitCode=[CleanConsoleInput]::ExitCode($Child);if($ExitCode -ne 259){break};Start-Sleep -Milliseconds 250}while([DateTime]::UtcNow -lt $Deadline)
 Put ("NATIVE_EXIT_CODE="+$ExitCode)
 if($ExitCode -eq 259){throw "SIGNED_INSTALL_TIMEOUT"}
 if($ExitCode -ne 0){throw "SIGNED_INSTALL_FAILED"}
 $Agent=Join-Path $Root "hara-commander-agent.ps1";$Config=Join-Path $Root "device.json"
 $AgentSHA=Hash $Agent
 if($AgentSHA -cne "fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62"){throw "INSTALLED_054_HASH_REQUIRED"}
 $Cfg=Get-Content -LiteralPath $Config -Raw|ConvertFrom-Json
 if($Cfg.base_url -cne $Dev -or $Cfg.approval_mode -cne "SESSION_TRUSTED"){throw "INSTALLED_DEV_SESSION_MODE_REQUIRED"}
 $Secure=ConvertTo-SecureString ([string]$Cfg.encrypted_device_token)
 try{if($Secure.Length -le 0){throw "QA_DPAPI_TOKEN_REQUIRED"}}finally{$Secure.Dispose()}
 $Cfg=$null
 $Status=Get-Content -LiteralPath (Join-Path $Root "runtime-status.json") -Raw|ConvertFrom-Json
 if([string]$Status.agent_version -cne "0.3.54" -or [string]::IsNullOrWhiteSpace([string]$Status.started_at_utc)){throw "INSTALLED_054_STARTUP_STATUS_REQUIRED"}
 $Markers=@(Get-Content -LiteralPath $Log|Where-Object{$_ -cmatch '^(HARA_COMMANDER_[A-Z_]+|SERVER_DEVICE_REVOKE|SECRET_MATERIAL_EXPOSED|DEVICE_TOKEN_EXPOSED)=[A-Z_0-9]+$'})
 if($Markers -notcontains "HARA_COMMANDER_DEVICE_ENROLLMENT=PASS" -or $Markers -notcontains "HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS"){throw "SIGNED_INSTALL_MARKERS_REQUIRED"}
 Put ("QA_SID="+$Identity.User.Value)
 Put ("ACTUAL_LOCALAPPDATA="+$env:LOCALAPPDATA)
 Put ("POWERSHELL_VERSION="+$PSVersionTable.PSVersion.ToString())
 Put ("AGENT_SHA256="+$AgentSHA)
 Put ("INSTALLER_SHA256="+(Hash $Installer))
 Put ("CONFIG_SHA256="+(Hash $Config))
 Put ("RUNTIME_VERSION="+[string]$Status.agent_version)
 Put ("RUNTIME_STARTED_AT_UTC="+[string]$Status.started_at_utc)
 foreach($Line in $Markers){Put $Line}
 Put ("LOCAL_OPERATOR_FILE_PRESENT="+[string](Test-Path -LiteralPath (Join-Path $Root "operator-session.json")))
 Put "QA_DPAPI_TOKEN_READABLE=TRUE"
 Put "NORMAL_HTTPS_PINNED=TRUE"
 Put "CLEAN_PROFILE_AT_START=TRUE"
 Put "SECURE_INPUT_TYPED=TRUE"
 $Result=$true
}catch{$Message=[string]$_.Exception.Message;$Failure=if($Message -cmatch "^[A-Z][A-Z0-9_]+$"){$Message}else{"QA_NATIVE_INSTALL_EXCEPTION"}}
finally{
 if($Child){try{if(-not $Result -and [CleanConsoleInput]::ExitCode($Child) -eq 259){Stop-Process -Id $Child -Force -ErrorAction SilentlyContinue}}finally{[CleanConsoleInput]::Release($Child)}}
 Put ("COLLECTION_ERROR="+[string]$Failure)
 Put ("MINIMAL_PHASE_COMPLETE="+[string]$Result)
}
if(-not $Result){exit 1};exit 0
'@
[IO.File]::WriteAllText($Child,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Child+'"')
$Qa=Get-LocalUser -Name HARAQA
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 4)) -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{state="NORMAL_SIGNED_054_INSTALL_PHASE_STARTED";signed_source_modified=$false}|ConvertTo-Json -Compress
