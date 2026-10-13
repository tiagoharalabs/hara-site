import importlib.util,json
s=importlib.util.spec_from_file_location("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q=importlib.util.module_from_spec(s);s.loader.exec_module(q);q.VM="hara-win51-clean-20261012-r1"
code=r"""
$ErrorActionPreference='Stop'
if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'QA_UUID_REQUIRED'}
$Expected='C:\Users\HARAQA\AppData\Local\HARA Commander\hara-commander-agent.ps1'
$T=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
$TaskHash=$null
if($T){
 $Xml=[string](Export-ScheduledTask -TaskName 'HARA Commander Agent')
 $Sha=[Security.Cryptography.SHA256]::Create()
 try{$TaskHash=([BitConverter]::ToString($Sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Xml)))).Replace('-','').ToLowerInvariant()}finally{$Sha.Dispose()}
}
$Pids=@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object{$_.CommandLine -and $_.CommandLine.Contains($Expected) -and -not $_.CommandLine.Contains('-EncodedCommand')}|ForEach-Object{[ordered]@{pid=[int]$_.ProcessId;session=[int]$_.SessionId;started_at_utc=$_.CreationDate.ToUniversalTime().ToString('o')}})
[ordered]@{
 schema='hara.windows-clean-system-task-and-pid-proof.v1'
 observed_at_utc=[DateTime]::UtcNow.ToString('o')
 clone_uuid='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba'
 task_present=[bool]$T
 task_state=if($T){[string]$T.State}else{$null}
 task_principal=if($T){[string]$T.Principal.UserId}else{$null}
 task_logon=if($T){[string]$T.Principal.LogonType}else{$null}
 task_runlevel=if($T){[string]$T.Principal.RunLevel}else{$null}
 task_trigger_count=if($T -and $T.Triggers){@($T.Triggers).Count}else{0}
 task_action_count=if($T){@($T.Actions).Count}else{0}
 task_action_matches=[bool]($T -and @($T.Actions).Count -eq 1 -and [string]$T.Actions[0].Execute -ceq (Get-Command powershell.exe).Source -and ([string]$T.Actions[0].Arguments).Contains($Expected))
 task_xml_sha256=$TaskHash
 pids=$Pids
 config_values_read=$false
 full_commandlines_printed=$false
}|ConvertTo-Json -Depth 4 -Compress
"""
rc,out,err=q.powershell(code,wait=25)
assert rc==0 and not err,"SYSTEM_METADATA_FAILED"
print(out.strip())