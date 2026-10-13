$ErrorActionPreference="Stop"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne "d35599c8-b9ea-45e5-9ae9-fa047e84b8ba"){throw "QA_UUID_REQUIRED"}
$Name="HARA Commander Clean QA Harness"
if((Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue).State -eq "Running"){throw "QA_HARNESS_RUNNING"}
$Child=Join-Path $Box "runtime-witness-child.ps1"
$Body=@'
$ErrorActionPreference="Stop"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
$Root=Join-Path $env:LOCALAPPDATA "HARA Commander"
$Out=Join-Path $Box "native-runtime-witness-after-failed-running-053.txt"
if($env:USERNAME -cne "HARAQA"){throw "QA_USER_REQUIRED"}
function Put([string]$S){[IO.File]::AppendAllText($Out,$S+[char]10)}
function Hash([string]$P){[string](& certutil.exe -hashfile $P SHA256 2>$null|Where-Object{$_ -cmatch "^[0-9a-fA-F]{64}$"}|Select-Object -First 1)}
[IO.File]::WriteAllText($Out,"WITNESS=AFTER_FAILED_RUNNING_UPDATE_AND_NORMAL_STOP"+[char]10)
Put ("OBSERVED_AT_UTC="+[DateTime]::UtcNow.ToString("o"))
Put ("QA_SID="+[Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
Put ("ACTUAL_LOCALAPPDATA="+$env:LOCALAPPDATA)
Put ("AGENT_SHA256="+(Hash (Join-Path $Root "hara-commander-agent.ps1")))
Put ("CONFIG_SHA256="+(Hash (Join-Path $Root "device.json")))
$Status=Join-Path $Root "runtime-status.json"
Put ("RUNTIME_FILE_PRESENT="+[string](Test-Path -LiteralPath $Status -PathType Leaf))
if(Test-Path -LiteralPath $Status -PathType Leaf){
 $S=Get-Content -LiteralPath $Status -Raw|ConvertFrom-Json
 foreach($Key in @("schema_version","agent_version","started_at_utc","last_successful_heartbeat_at_utc","last_runtime_error_code","last_runtime_error_at_utc","updated_at_utc")){
  $V=[string]$S.$Key
  if($V -cmatch "^[A-Za-z0-9_.:+-]*$"){Put ($Key.ToUpperInvariant()+"="+$V)}else{Put ($Key.ToUpperInvariant()+"=REDACTED_NON_IDENTIFIER")}
 }
 Put ("RUNTIME_SHA256="+(Hash $Status))
}
Put ("OPERATOR_SESSION_FILE_PRESENT="+[string](Test-Path -LiteralPath (Join-Path $Root "operator-session.json") -PathType Leaf))
Put "EXPECTED_NONCE=NOT_IMPLEMENTED_IN_FROZEN_053"
Put "START_IDENTITY_NOT_IN_RUNTIME_REPORT=TRUE"
Put "SOURCE_MODIFIED=FALSE"
Put "WITNESS_COMPLETE=TRUE"
'@
[IO.File]::WriteAllText($Child,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Child+'"')
$Qa=Get-LocalUser -Name HARAQA
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)) -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{state="READ_ONLY_QA_WITNESS_STARTED";source_modified=$false}|ConvertTo-Json -Compress
