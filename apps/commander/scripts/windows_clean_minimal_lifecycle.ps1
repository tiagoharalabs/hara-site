param([string]$Phase='update-running')
$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
if($Phase -notin @('update-running','update-stopped','negative-signature','stop','uninstall')){throw 'UNKNOWN_PHASE'}
$Name='HARA Commander Clean QA Harness'
$Old=Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if($Old -and [string]$Old.State -eq 'Running'){throw 'QA_HARNESS_RUNNING'}
$Child=Join-Path $Box 'native-lifecycle-child.ps1'
$Body=@'
param([string]$Phase)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Root=Join-Path $env:LOCALAPPDATA 'HARA Commander'
$Agent=Join-Path $Root 'hara-commander-agent.ps1';$Config=Join-Path $Root 'device.json';$Installer=Join-Path $Box 'windows-053-r2.ps1'
$Dev='https://hara-commander-dev-v2.tiago-sartori.workers.dev'
$Out=Join-Path $Box ('native-phase-'+$Phase+'.txt');$Log=Join-Path $Box ('native-phase-'+$Phase+'.private.log')
function Hash([string]$Path){if(Test-Path -LiteralPath $Path){return [string](& certutil.exe -hashfile $Path SHA256 2>$null|Where-Object{$_ -cmatch '^[0-9a-fA-F]{64}$'}|Select-Object -First 1)};return 'ABSENT'}
function Put([string]$Line){[IO.File]::AppendAllText($Out,$Line+"`n")}
[IO.File]::WriteAllText($Out,'PHASE='+$Phase+"`nQA_USERNAME="+[string]$env:USERNAME+"`n")
$Original=$null;$Server=$null;$Failure=$null;$NativeExit=$null;$ErrorActual=$null
try{
 if($env:USERNAME -cne 'HARAQA' -or $Phase -notin @('update-running','update-stopped','negative-signature','stop','uninstall')){throw 'QA_PHASE_REQUIRED'}
 $beforeAgent=Hash $Agent;$beforeCfg=Hash $Config
 Put ('AGENT_SHA256_BEFORE='+$beforeAgent);Put ('CONFIG_SHA256_BEFORE='+$beforeCfg)
 if($beforeAgent -cne 'f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299' -or (Hash $Installer) -cne 'dd92242225cf518e104f8f574aa9f661e6e3c9647f2cdce2afdb6ba88d0d9710'){throw 'FROZEN_SOURCE_REQUIRED'}
 $cfg=Get-Content -LiteralPath $Config -Raw|ConvertFrom-Json
 if($cfg.base_url -cne $Dev -or $cfg.approval_mode -cne 'SESSION_TRUSTED'){throw 'QA_DEV_CONFIG_REQUIRED'}
 if($Phase -eq 'negative-signature'){
  if(Test-Path -LiteralPath (Join-Path $Root 'operator-session.json')){throw 'STOPPED_SESSION_REQUIRED'}
  $Assets=Join-Path $Box 'negative-minimal-assets';New-Item -Path $Assets -ItemType Directory -Force|Out-Null
  Copy-Item -LiteralPath $Agent -Destination (Join-Path $Assets 'windows.ps1') -Force
  foreach($Name in @('agent-manifest.json','agent-manifest.sig.json')){Invoke-WebRequest -UseBasicParsing -Uri ($Dev+'/release/'+$Name) -OutFile (Join-Path $Assets $Name) -TimeoutSec 30 -MaximumRedirection 0}
  if((Hash (Join-Path $Assets 'agent-manifest.json')) -cne 'eebd7f4b209158b4a9a02b986365291c14e70bcad45106271078b2a373b6a257'){throw 'FINAL_MANIFEST_REQUIRED'}
  [IO.File]::AppendAllText((Join-Path $Assets 'agent-manifest.json'),"`n",(New-Object Text.UTF8Encoding($false)))
  $Ready=Join-Path $Box 'negative-minimal.ready';Remove-Item -LiteralPath $Ready -Force -ErrorAction SilentlyContinue
  $ServerFile=Join-Path $Box 'negative-minimal-server.ps1'
  $ServerBody='$ErrorActionPreference=''Stop'';$h=New-Object Net.HttpListener;$h.Prefixes.Add(''http://127.0.0.1:18553/'');$h.Start();[IO.File]::WriteAllText('''+$Ready+''',''READY'');try{while($h.IsListening){$c=$h.GetContext();$n=switch($c.Request.Url.AbsolutePath){''/agent/windows.ps1''{''windows.ps1''};''/release/agent-manifest.json''{''agent-manifest.json''};''/release/agent-manifest.sig.json''{''agent-manifest.sig.json''};default{$null}};if($n){$b=[IO.File]::ReadAllBytes((Join-Path '''+$Assets+''' $n));$c.Response.StatusCode=200;$c.Response.ContentLength64=$b.Length;$c.Response.OutputStream.Write($b,0,$b.Length)}else{$c.Response.StatusCode=404};$c.Response.Close()}}finally{$h.Stop();$h.Close()}'
  [IO.File]::WriteAllText($ServerFile,$ServerBody,(New-Object Text.UTF8Encoding($false)))
  $Server=Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$ServerFile+'"') -WindowStyle Hidden -PassThru
  $Deadline=[DateTime]::UtcNow.AddSeconds(8);while(-not(Test-Path $Ready) -and [DateTime]::UtcNow -lt $Deadline){Start-Sleep -Milliseconds 100};if(-not(Test-Path $Ready)){throw 'LOOPBACK_SERVER_FAILED'}
  $Original=[IO.File]::ReadAllBytes($Config);$cfg.base_url='http://127.0.0.1:18553';[IO.File]::WriteAllText($Config,($cfg|ConvertTo-Json),(New-Object Text.UTF8Encoding($true)));$cfg=$null
 }
 $global:LASTEXITCODE=0
 try{
  if($Phase -eq 'stop'){& $Agent stop *> $Log}
  else{$Action=if($Phase -eq 'uninstall'){'uninstall'}else{'update'};& $Installer -Action $Action *> $Log}
  $NativeExit=$LASTEXITCODE
 }catch{$ErrorActual=[string]$_.Exception.Message;$NativeExit=1;[IO.File]::WriteAllText((Join-Path $Box ('native-phase-'+$Phase+'.error.private.txt')),$ErrorActual)}
 if($Phase -eq 'negative-signature'){if($ErrorActual -cne 'AGENT_RELEASE_SIGNATURE_INVALID'){throw 'NEGATIVE_SIGNATURE_WRONG_FAILURE'};Put ('SIGNED_INSTALLER_REJECTION_CODE='+$ErrorActual)}
 elseif($NativeExit -ne 0){throw 'SIGNED_CLIENT_PHASE_FAILED'}
}catch{$msg=[string]$_.Exception.Message;$Failure=if($msg -cmatch '^[A-Z][A-Z0-9_]+$'){$msg}else{'MINIMAL_PHASE_EXCEPTION'}}
finally{
 try{if($Original){try{[IO.File]::WriteAllBytes($Config,$Original)}catch{$Failure='CONFIG_RESTORE_FAILED'}}}finally{if($Server){try{if(-not $Server.HasExited){$Server.Kill();$Server.WaitForExit(3000)|Out-Null}}finally{$Server.Dispose()}}}
}
Put ('NATIVE_EXIT_CODE='+[string]$NativeExit)
Put ('AGENT_SHA256_AFTER='+(Hash $Agent));Put ('CONFIG_SHA256_AFTER='+(Hash $Config))
if(Test-Path $Log){Get-Content -LiteralPath $Log|Where-Object{$_ -cmatch '^(HARA_COMMANDER_[A-Z_]+|SERVER_DEVICE_REVOKE|SESSION_WAS_ACTIVE|SECRET_MATERIAL_EXPOSED|DEVICE_TOKEN_EXPOSED)=[A-Z_0-9]+$'}|ForEach-Object{Put ([string]$_)}}
Put ('OPERATOR_SESSION_FILE_PRESENT='+[string](Test-Path -LiteralPath (Join-Path $Root 'operator-session.json')))
Put ('ROOT_PRESENT='+[string](Test-Path -LiteralPath $Root))
Put ('COLLECTION_ERROR='+[string]$Failure)
Put ('MINIMAL_PHASE_COMPLETE='+[string](-not $Failure))
if($Failure){exit 1};exit 0
'@
[IO.File]::WriteAllText($Child,$Body,(New-Object Text.UTF8Encoding($false)))
$Action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Child+'" -Phase '+$Phase)
$Qa=Get-LocalUser -Name HARAQA
$Principal=New-ScheduledTaskPrincipal -UserId ([string]$Qa.SID) -LogonType Interactive -RunLevel Highest
$Settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
Register-ScheduledTask -TaskName $Name -Action $Action -Principal $Principal -Settings $Settings -Force|Out-Null
Start-ScheduledTask -TaskName $Name
[ordered]@{state='NATIVE_SIGNED_LIFECYCLE_PHASE_STARTED';phase=$Phase;source_modified=$false}|ConvertTo-Json -Compress
