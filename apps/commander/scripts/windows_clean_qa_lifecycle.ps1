[CmdletBinding()]
param([string]$Parameters='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1\phase-private.json')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
if($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1 -or $PSVersionTable.PSEdition -cne 'Desktop'){throw 'NATIVE_DESKTOP_PS51_REQUIRED'}
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$CloneUuid='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba'
$Dev='https://hara-commander-dev-v2.tiago-sartori.workers.dev'
$AgentSha='f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299'
$InstallerSha='dd92242225cf518e104f8f574aa9f661e6e3c9647f2cdce2afdb6ba88d0d9710'
$ManifestSha='eebd7f4b209158b4a9a02b986365291c14e70bcad45106271078b2a373b6a257'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne $CloneUuid){throw 'CLONE_UUID_REQUIRED'}
$Identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if($Identity.IsSystem -or $Identity.Name -notmatch '\\HARAQA$'){throw 'ACTUAL_QA_PROFILE_REQUIRED'}
if($env:LOCALAPPDATA -cne 'C:\Users\HARAQA\AppData\Local'){throw 'ACTUAL_QA_LOCALAPPDATA_REQUIRED'}
$Spec=Get-Content -Raw -LiteralPath $Parameters|ConvertFrom-Json
if($Spec.dev_origin -cne $Dev){throw 'DEV_ORIGIN_REQUIRED'}
$Phase=[string]$Spec.phase
if($Phase -notin @('install','inspect','start','stop','update-stopped','update-running','negative-signature','uninstall')){throw 'UNKNOWN_QA_PHASE'}
. (Join-Path $Box 'windows_clean_console_api.ps1')
$InstalledRoot=Join-Path $env:LOCALAPPDATA 'HARA Commander'
$Agent=Join-Path $InstalledRoot 'hara-commander-agent.ps1'
$Config=Join-Path $InstalledRoot 'device.json'
$Installer=Join-Path $Box 'windows-053-r2.ps1'
$Log=Join-Path $Box ('phase-'+$Phase+'.private.log')
$Result=Join-Path $Box ('phase-'+$Phase+'.json')
function Snapshot {
 $task=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
 $cfg=if(Test-Path -LiteralPath $Config){Get-Content -Raw -LiteralPath $Config|ConvertFrom-Json}else{$null}
 $dpapi=$false
 if($cfg){try{$secure=ConvertTo-SecureString ([string]$cfg.encrypted_device_token);$dpapi=$secure.Length -gt 0;$secure.Dispose()}catch{}}
 $runtime=Join-Path $InstalledRoot 'runtime-status.json'
 $status=if(Test-Path -LiteralPath $runtime){Get-Content -Raw -LiteralPath $runtime|ConvertFrom-Json}else{$null}
 $session=Join-Path $InstalledRoot 'operator-session.json'
 $local=if(Test-Path -LiteralPath $session){Get-Content -Raw -LiteralPath $session|ConvertFrom-Json}else{$null}
 $active=$false
 if($local -and $local.owner_pid){$p=Get-Process -Id ([int]$local.owner_pid) -ErrorAction SilentlyContinue;$active=[bool]($p -and $p.StartTime.ToUniversalTime().ToString('o') -eq [string]$local.owner_started_at_utc)}
 $principal=if($task){[string]$task.Principal.UserId}else{''}
 $principalQa=$principal -ceq $Identity.Name -or $principal -ceq ([string]$Identity.User) -or $principal -ceq 'HARAQA'
 $actionExpected=[bool]($task -and @($task.Actions).Count -eq 1 -and [string]$task.Actions[0].Execute -ceq (Get-Command powershell.exe).Source -and ([string]$task.Actions[0].Arguments).Contains($Agent))
 $taskDigest=$null
 if($task){$sha=[Security.Cryptography.SHA256]::Create();try{$taskDigest=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes((Export-ScheduledTask -TaskName $task.TaskName))))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}}
 [ordered]@{root_present=(Test-Path -LiteralPath $InstalledRoot);config_present=[bool]$cfg;config_sha256=if($cfg){(Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null};dev_origin_correct=[bool]($cfg -and $cfg.base_url -ceq $Dev);approval_mode=if($cfg){[string]$cfg.approval_mode}else{$null};qa_dpapi_token_readable=$dpapi;agent_present=(Test-Path -LiteralPath $Agent);agent_sha256=if(Test-Path -LiteralPath $Agent){(Get-FileHash -LiteralPath $Agent -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null};task_present=[bool]$task;task_state=if($task){[string]$task.State}else{$null};task_trigger_count=if($task -and $task.Triggers){@($task.Triggers).Count}else{0};task_principal=if($task){[string]$task.Principal.UserId}else{$null};task_principal_is_qa=$principalQa;task_action_matches_installed_qa_agent=$actionExpected;task_xml_sha256=$taskDigest;runtime_version=if($status){[string]$status.agent_version}else{$null};runtime_started_at_utc=if($status){[string]$status.started_at_utc}else{$null};local_operator_session_active=$active;local_operator_owner_pid=if($local){[int]$local.owner_pid}else{$null};local_operator_owner_started_at_utc=if($local){[string]$local.owner_started_at_utc}else{$null}}
}
$Before=Snapshot
$NativeExit=$null;$Typed=$false;$ChildPid=$null;$ErrorCode=$null;$NegativeError=$null;$Server=$null;$OriginalConfig=$null;$InstallerVerified=$false
$Pass=$false
function Stop-TrackedChild {
 if($ChildPid){try{if([CleanConsoleInput]::ExitCode($ChildPid) -eq 259){Stop-Process -Id $ChildPid -Force -ErrorAction SilentlyContinue}}catch{}}
}
function Stop-NegativeServer {
 if($Server){try{if(-not $Server.HasExited){$Server.Kill();$Server.WaitForExit(3000)|Out-Null}}catch{}}
}
try {
try {
 if($Phase -notin @('install','inspect')){
  if(-not $Before.dev_origin_correct -or $Before.approval_mode -cne 'SESSION_TRUSTED' -or -not $Before.qa_dpapi_token_readable){throw 'INSTALLED_QA_DEV_CONFIG_REQUIRED'}
  if($Before.agent_sha256 -cne $AgentSha){throw 'INSTALLED_QA_SIGNED_AGENT_REQUIRED'}
  if(-not $Before.task_present -or -not $Before.task_principal_is_qa -or -not $Before.task_action_matches_installed_qa_agent -or $Before.task_trigger_count -ne 0){throw 'INSTALLED_QA_MANUAL_TASK_REQUIRED'}
 }
 if($Phase -eq 'start' -and $Before.local_operator_session_active){throw 'OPERATOR_SESSION_ALREADY_ACTIVE'}
 if($Phase -eq 'install'){
  if($Before.root_present -or $Before.task_present){throw 'CLEAN_INSTALL_COLLISION'}
  if([string]::IsNullOrWhiteSpace([string]$Spec.pairing_token)){throw 'DEV_ONE_TIME_PAIRING_REQUIRED'}
  Invoke-WebRequest -Uri ($Dev+'/release/agent-manifest.json') -OutFile (Join-Path $Box 'dev-053-manifest.json') -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
  if((Get-FileHash -LiteralPath (Join-Path $Box 'dev-053-manifest.json')).Hash.ToLowerInvariant() -cne $ManifestSha){throw 'DEV_FINAL_SIGNED_MANIFEST_NOT_PUBLISHED'}
  Invoke-WebRequest -Uri ($Dev+'/install/windows.ps1') -OutFile $Installer -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
 }
 if($Phase -notin @('inspect','start','stop')){
  if((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -cne $InstallerSha){throw 'SIGNED_INSTALLER_SHA_REQUIRED'}
  $InstallerVerified=$true
 }
 if($Phase -eq 'update-stopped' -and $Before.task_state -eq 'Running'){throw 'MANUALLY_STOPPED_TASK_REQUIRED'}
 if($Phase -eq 'update-running' -and $Before.task_state -ne 'Running'){throw 'RUNNING_TASK_REQUIRED'}
 if($Phase -eq 'negative-signature'){
  if($Before.task_state -eq 'Running' -or $Before.local_operator_session_active){throw 'NEGATIVE_SIGNATURE_REQUIRES_STOPPED_QA'}
  $Assets=Join-Path $Box 'negative-signature-assets'
  New-Item -ItemType Directory -Path $Assets -Force|Out-Null
  Copy-Item -LiteralPath $Agent -Destination (Join-Path $Assets 'windows.ps1') -Force
  foreach($Name in @('agent-manifest.json','agent-manifest.sig.json')){Invoke-WebRequest -Uri ($Dev+'/release/'+$Name) -OutFile (Join-Path $Assets $Name) -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0}
  if((Get-FileHash -LiteralPath (Join-Path $Assets 'agent-manifest.json')).Hash.ToLowerInvariant() -cne $ManifestSha){throw 'FINAL_SIGNED_MANIFEST_REQUIRED_FOR_NEGATIVE'}
  [IO.File]::AppendAllText((Join-Path $Assets 'agent-manifest.json'),"`n",(New-Object Text.UTF8Encoding($false)))
  $Ready=Join-Path $Box 'negative-server.ready'
  Remove-Item -LiteralPath $Ready -Force -ErrorAction SilentlyContinue
  $ServerScript=Join-Path $Box 'negative-signature-server.ps1'
  $ServerBody='$ErrorActionPreference=''Stop'';$h=New-Object Net.HttpListener;$h.Prefixes.Add(''http://127.0.0.1:18553/'');$h.Start();[IO.File]::WriteAllText('''+$Ready+''',''READY'');try{while($h.IsListening){$c=$h.GetContext();$name=switch($c.Request.Url.AbsolutePath){''/agent/windows.ps1''{''windows.ps1''};''/release/agent-manifest.json''{''agent-manifest.json''};''/release/agent-manifest.sig.json''{''agent-manifest.sig.json''};default{$null}};if($name){$b=[IO.File]::ReadAllBytes((Join-Path '''+$Assets+''' $name));$c.Response.StatusCode=200;$c.Response.ContentLength64=$b.Length;$c.Response.OutputStream.Write($b,0,$b.Length)}else{$c.Response.StatusCode=404};$c.Response.Close()}}finally{$h.Stop();$h.Close()}'
  [IO.File]::WriteAllText($ServerScript,$ServerBody,(New-Object Text.UTF8Encoding($false)))
  $Server=Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList ('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$ServerScript+'"') -WindowStyle Hidden -PassThru
  $ServerDeadline=[DateTime]::UtcNow.AddSeconds(8)
  while(-not(Test-Path -LiteralPath $Ready) -and [DateTime]::UtcNow -lt $ServerDeadline){Start-Sleep -Milliseconds 100}
  if(-not(Test-Path -LiteralPath $Ready)){throw 'NEGATIVE_LOOPBACK_SERVER_NOT_READY'}
  $OriginalConfig=[IO.File]::ReadAllBytes($Config)
  $NegativeCfg=Get-Content -LiteralPath $Config -Raw|ConvertFrom-Json
  $NegativeCfg.base_url='http://127.0.0.1:18553'
  [IO.File]::WriteAllText($Config,($NegativeCfg|ConvertTo-Json),(New-Object Text.UTF8Encoding($true)))
  $NegativeCfg=$null
 }
 if($Phase -ne 'inspect'){
  $Action=if($Phase -match '^update-' -or $Phase -eq 'negative-signature'){'update'}else{$Phase}
  $Target=if($Action -in @('start','stop')){$Agent}else{$Installer}
  $Child=Join-Path $Box ('child-'+$Phase+'.ps1')
  $cmd=if($Action -in @('start','stop')){'& '''+$Target+''' '+$Action}else{'& '''+$Target+''' -Action '+$Action}
  $body='$ErrorActionPreference=''Stop'';$global:LASTEXITCODE=0;$env:HARA_COMMANDER_URL='''+$Dev+''';$env:HARA_COMMANDER_APPROVAL_MODE=''SESSION_TRUSTED'';try{'+$cmd+' *> '''+$Log+''';if(-not $? -or $LASTEXITCODE -ne 0){exit 1};exit 0}catch{[IO.File]::WriteAllText('''+(Join-Path $Box ('error-'+$Phase+'.private.txt'))+''',([string]$_.Exception.Message));exit 1}'
  [IO.File]::WriteAllText($Child,$body,(New-Object Text.UTF8Encoding($false)))
  $Exe=(Get-Command powershell.exe).Source
  $ChildPid=[CleanConsoleInput]::Launch('"'+$Exe+'" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "'+$Child+'"')
  if($Phase -eq 'install'){
   Start-Sleep -Milliseconds 1600
   $Typed=[CleanConsoleInput]::Type($ChildPid,([string]$Spec.pairing_token+"`r"))
   $Spec.pairing_token=$null
   [IO.File]::WriteAllText($Parameters,($Spec|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
   if(-not $Typed){throw 'NATIVE_SECURE_PAIRING_INPUT_FAILED'}
  }
  $Deadline=[DateTime]::UtcNow.AddSeconds($(if($Phase -eq 'start'){15}else{150}))
  do{$NativeExit=[CleanConsoleInput]::ExitCode($ChildPid);if($NativeExit -ne 259){break};Start-Sleep -Milliseconds 250}while([DateTime]::UtcNow -lt $Deadline)
  if($Phase -eq 'start'){
   $Started=Snapshot
   if($NativeExit -ne 259 -or -not $Started.local_operator_session_active -or $Started.local_operator_owner_pid -ne $ChildPid){throw 'MANUAL_OPERATOR_START_FAILED'}
  }elseif($NativeExit -eq 259){Stop-Process -Id $ChildPid -Force -ErrorAction SilentlyContinue;throw 'INSTALLER_PHASE_TIMEOUT'}
  elseif($Phase -eq 'negative-signature'){
   $ErrorFile=Join-Path $Box ('error-'+$Phase+'.private.txt')
   $NegativeError=if(Test-Path -LiteralPath $ErrorFile){[IO.File]::ReadAllText($ErrorFile)}else{$null}
   if($NativeExit -ne 1 -or $NegativeError -cne 'AGENT_RELEASE_SIGNATURE_INVALID'){throw 'NEGATIVE_SIGNATURE_DID_NOT_REJECT_EXPECTED_CODE'}
  }elseif($NativeExit -ne 0){throw 'REAL_SIGNED_INSTALLER_PHASE_FAILED'}
 }
} catch {
 $message=[string]$_.Exception.Message
 $ErrorCode=if($message -cmatch '^[A-Z][A-Z0-9_]+$'){$message}else{'QA_PHASE_EXCEPTION'}
}finally{
 try {
  if($OriginalConfig){try{[IO.File]::WriteAllBytes($Config,$OriginalConfig);$OriginalConfig=$null}catch{$ErrorCode='NEGATIVE_CONFIG_RESTORE_FAILED'}}
 } finally {
  Stop-NegativeServer
  if($ErrorCode){Stop-TrackedChild}
 }
}
try {
$After=Snapshot
$Markers=@()
if(Test-Path -LiteralPath $Log){$Markers=@(Get-Content -LiteralPath $Log|Where-Object{$_ -cmatch '^(HARA_COMMANDER_[A-Z_]+|SERVER_DEVICE_REVOKE|DEVICE_TOKEN_EXPOSED)=[A-Z_0-9]+$'})}
$Pass=-not $ErrorCode
switch($Phase){
 'inspect'{$Pass=$Pass -and -not $Before.root_present -and -not $Before.task_present}
 'install'{$Pass=$Pass -and $After.agent_sha256 -ceq $AgentSha -and $After.qa_dpapi_token_readable -and $After.dev_origin_correct -and $After.approval_mode -ceq 'SESSION_TRUSTED' -and $After.runtime_version -ceq '0.3.53' -and $After.task_present -and $After.task_state -ceq 'Running' -and $After.task_principal_is_qa -and $After.task_action_matches_installed_qa_agent -and $After.task_trigger_count -eq 0 -and -not $After.local_operator_session_active -and $Markers -contains 'HARA_COMMANDER_DEVICE_ENROLLMENT=PASS' -and $Markers -contains 'HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS'}
 'stop'{$Pass=$Pass -and -not $After.local_operator_session_active -and $After.task_state -ne 'Running'}
 'start'{$Pass=$Pass -and $After.local_operator_session_active -and $After.local_operator_owner_pid -eq $ChildPid -and $After.task_state -eq 'Running' -and $NativeExit -eq 259}
 'update-stopped'{$Pass=$Pass -and $After.task_state -ne 'Running' -and $After.agent_sha256 -ceq $AgentSha -and $Before.config_sha256 -ceq $After.config_sha256 -and $Markers -contains 'HARA_COMMANDER_AGENT_UPDATE_RUNTIME_ATTESTATION=SKIPPED_MANUAL_STOP'}
 'update-running'{$Pass=$Pass -and $After.task_state -eq 'Running' -and $After.agent_sha256 -ceq $AgentSha -and $Before.config_sha256 -ceq $After.config_sha256 -and $Markers -contains 'HARA_COMMANDER_AGENT_STARTUP_ATTESTATION=PASS'}
 'negative-signature'{$Pass=$Pass -and $Before.config_sha256 -ceq $After.config_sha256 -and $Before.agent_sha256 -ceq $After.agent_sha256 -and $Before.task_xml_sha256 -ceq $After.task_xml_sha256 -and $After.task_state -ne 'Running' -and -not $After.local_operator_session_active -and $NegativeError -ceq 'AGENT_RELEASE_SIGNATURE_INVALID'}
 'uninstall'{$Pass=$Pass -and -not $After.root_present -and -not $After.task_present -and $Markers -contains 'SERVER_DEVICE_REVOKE=PASS'}
}
if(-not $Pass -and -not $ErrorCode){$ErrorCode='QA_PHASE_POSTCONDITION_FAILED'}
$Report=[ordered]@{schema='hara.windows-clean-real-installer-phase.v1';state=if($Pass){'PASS'}else{'FAIL'};phase=$Phase;error_code=$ErrorCode;negative_signature_error_code=if($NegativeError -ceq 'AGENT_RELEASE_SIGNATURE_INVALID'){$NegativeError}else{$null};negative_assets_loopback_fixture_only=($Phase -eq 'negative-signature');clone_uuid=$CloneUuid;qa_identity=$Identity.Name;qa_localappdata=$env:LOCALAPPDATA;powershell_version=$PSVersionTable.PSVersion.ToString();preexisting_os_cloned=$true;clean_profile_verified_at_install=if($Phase -eq 'install'){$Pass}else{$null};signed_installer_hash_verified=$InstallerVerified;expected_signed_installer_sha256=$InstallerSha;final_manifest_sha256=$ManifestSha;native_console_pairing_typed=$Typed;native_exit_code=$NativeExit;child_pid=$ChildPid;before=$Before;after=$After;markers=$Markers;configuration_or_token_contents_printed=$false;founder_identity_used=$false;raw_logs_private=$true;utc=[DateTime]::UtcNow.ToString('o')}
[IO.File]::WriteAllText($Result,($Report|ConvertTo-Json -Depth 8 -Compress),(New-Object Text.UTF8Encoding($false)))
} catch {
 $Pass=$false
 $Safe=[ordered]@{schema='hara.windows-clean-real-installer-phase.v1';state='FAIL';phase=$Phase;error_code='QA_POSTCONDITION_OR_REPORT_EXCEPTION';clone_uuid=$CloneUuid;child_pid=$ChildPid;configuration_or_token_contents_printed=$false;raw_logs_private=$true}
 [IO.File]::WriteAllText($Result,($Safe|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
}
} finally {
 Stop-NegativeServer
 if(-not $Pass){
  Stop-TrackedChild
  if($Phase -eq 'start' -and $Before.task_principal_is_qa -and $Before.task_action_matches_installed_qa_agent){Stop-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue}
 }
 if($ChildPid){try{[CleanConsoleInput]::Release($ChildPid)}catch{}}
 if($Server){$Server.Dispose()}
}
if(-not $Pass){exit 1}
exit 0
