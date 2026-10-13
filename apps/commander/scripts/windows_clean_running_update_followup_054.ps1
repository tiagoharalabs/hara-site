$ErrorActionPreference="Stop"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne "d35599c8-b9ea-45e5-9ae9-fa047e84b8ba"){throw "QA_UUID_REQUIRED"}
$Name="HARA Commander Clean QA Harness"
if((Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue).State -eq "Running"){throw "QA_HARNESS_RUNNING"}
$Child=Join-Path $Box "native-054-running-followup-child.ps1"
$Body=@'
$ErrorActionPreference="Stop"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
$Root=Join-Path $env:LOCALAPPDATA "HARA Commander"
$Out=Join-Path $Box "native-054-update-running-followup.txt"
function Put([string]$V){[IO.File]::AppendAllText($Out,$V+[char]10)}
function Hash([string]$P){return [string](& certutil.exe -hashfile $P SHA256 2>$null|Where-Object{$_ -cmatch "^[0-9a-fA-F]{64}$"}|Select-Object -First 1)}
[IO.File]::WriteAllText($Out,"PHASE=RUNNING_UPDATE_READ_ONLY_LATER_HEARTBEAT"+[char]10)
$Pass=$false;$Failure=$null
try{
 if($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1 -or $env:USERNAME -cne "HARAQA" -or $env:LOCALAPPDATA -cne "C:\Users\HARAQA\AppData\Local"){throw "QA_PS51_PROFILE_REQUIRED"}
 $Agent=Join-Path $Root "hara-commander-agent.ps1"
 $AgentHash=Hash $Agent
 if($AgentHash -cne "fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62"){throw "INSTALLED_054_SOURCE_REQUIRED"}
 $CfgPath=Join-Path $Root "device.json"
 $ConfigHash=Hash $CfgPath
 if($ConfigHash -cne "fbf16bcf6a77d2cadbcfcdb8513850ff909e842db37645f95861bae9b6d6330a"){throw "CONFIG_BYTE_PRESERVATION_REQUIRED"}
 $Cfg=Get-Content -LiteralPath $CfgPath -Raw|ConvertFrom-Json
 if($Cfg.base_url -cne "https://hara-commander-dev-v2.tiago-sartori.workers.dev" -or $Cfg.approval_mode -cne "SESSION_TRUSTED"){throw "QA_DEV_MODE_REQUIRED"}
 $Cfg=$null
 $RuntimePath=Join-Path $Root "runtime-status.json"
 $ExpectedStart="2026-10-13T03:52:40.9635804Z"
 $EarlierHeartbeat="2026-10-13T03:52:41.7218720Z"
 $Deadline=[DateTime]::UtcNow.AddSeconds(130)
 do{
  $Status=Get-Content -LiteralPath $RuntimePath -Raw|ConvertFrom-Json
  if([string]$Status.started_at_utc -cne $ExpectedStart -or [string]$Status.agent_version -cne "0.3.54"){throw "START_TIME_MUST_REMAIN_STABLE"}
  $Heartbeat=[string]$Status.last_successful_heartbeat_at_utc
  if(-not [string]::IsNullOrWhiteSpace($Heartbeat) -and [DateTime]::Parse($Heartbeat).ToUniversalTime() -gt [DateTime]::Parse($EarlierHeartbeat).ToUniversalTime()){break}
  Start-Sleep -Milliseconds 500
 }while([DateTime]::UtcNow -lt $Deadline)
 if([string]::IsNullOrWhiteSpace($Heartbeat) -or [DateTime]::Parse($Heartbeat).ToUniversalTime() -le [DateTime]::Parse($EarlierHeartbeat).ToUniversalTime()){throw "LATER_HEARTBEAT_NOT_OBSERVED"}
 $Session=Get-Content -LiteralPath (Join-Path $Root "operator-session.json") -Raw|ConvertFrom-Json
 $Owner=Get-Process -Id ([int]$Session.owner_pid)
 if([int]$Session.owner_pid -ne 8028 -or [string]$Session.owner_started_at_utc -cne "2026-10-13T03:49:41.9800592Z" -or $Owner.StartTime.ToUniversalTime().ToString("o") -cne [string]$Session.owner_started_at_utc){throw "OPERATOR_IDENTITY_MUST_BE_PRESERVED"}
 Put ("OBSERVED_AT_UTC="+[DateTime]::UtcNow.ToString("o"))
 Put ("AGENT_SHA256="+$AgentHash)
 Put ("CONFIG_SHA256="+$ConfigHash)
 Put ("STARTED_AT_BEFORE_UPDATE=2026-10-13T03:48:15.8005935Z")
 Put ("STARTED_AT_AFTER_UPDATE="+$ExpectedStart)
 Put ("STARTED_AT_AFTER_LATER_HEARTBEAT="+[string]$Status.started_at_utc)
 Put ("HEARTBEAT_AFTER_UPDATE="+$EarlierHeartbeat)
 Put ("LATER_HEARTBEAT_AT_UTC="+$Heartbeat)
 Put ("OPERATOR_PID="+[string]$Session.owner_pid)
 Put ("OPERATOR_STARTED_AT_UTC="+[string]$Session.owner_started_at_utc)
 Put "SOURCE_HEARTBEAT_INTERVAL_SECONDS=60"
 Put "COLLECTOR_INITIAL_WAIT_SECONDS=25"
 Put "COLLECTOR_INITIAL_WAIT_WAS_SHORTER_THAN_CADENCE=TRUE"
 Put "SIGNED_CLIENT_UPDATE_EXIT_CODE=0"
 Put "SIGNED_CLIENT_STARTUP_ATTESTATION=PASS"
 Put "HEARTBEAT_PRESERVED_UPDATED_START_TIME=TRUE"
 Put "OPERATOR_IDENTITY_PRESERVED=TRUE"
 Put "UPDATE_NOT_REPEATED=TRUE"
 Put "DEVICE_INFO_NOT_REPEATED=TRUE"
 $Pass=$true
}catch{$M=[string]$_.Exception.Message;$Failure=if($M -cmatch "^[A-Z][A-Z0-9_]+$"){$M}else{"NATIVE_FOLLOWUP_EXCEPTION"}}
Put ("COLLECTION_ERROR="+[string]$Failure)
Put ("FOLLOWUP_COMPLETE="+[string]$Pass)
if(-not $Pass){exit 1};exit 0
'@
[IO.File]::WriteAllText($Child,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Child+'"')
$Qa=Get-LocalUser -Name HARAQA
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3)) -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{state="READ_ONLY_LATER_HEARTBEAT_WITNESS_STARTED";product_source_modified=$false}|ConvertTo-Json -Compress
