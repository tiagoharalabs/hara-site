import importlib.util,json,base64,hashlib
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
q=load("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q.VM="hara-win51-clean-20261012-r1"
b=load("b","/tmp_hara/windows_clean_qga_bridge.py")
ps=r"""$ErrorActionPreference='Stop';if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'};$ts=@(Get-ScheduledTask|Where-Object{$_.TaskName -in @('HARA Commander Agent','HARA Commander Clean QA Harness')});$tasks=@($ts|ForEach-Object{$i=Get-ScheduledTaskInfo -TaskName $_.TaskName;[ordered]@{name=$_.TaskName;state=[string]$_.State;user=[string]$_.Principal.UserId;logon=[string]$_.Principal.LogonType;runlevel=[string]$_.Principal.RunLevel;trigger_count=if($_.Triggers){@($_.Triggers).Count}else{0};action_count=@($_.Actions).Count;agent_action_expected=[bool](@($_.Actions|Where-Object{([string]$_.Arguments).Contains('C:\Users\HARAQA\AppData\Local\HARA Commander\hara-commander-agent.ps1')}).Count);last_result=$i.LastTaskResult}});$ps=@(Get-CimInstance Win32_Process|Where-Object{$_.CommandLine -and ($_.CommandLine -match 'hara-commander-agent.ps1|windows_clean_diagnose_installed.ps1')}|ForEach-Object{[ordered]@{pid=$_.ProcessId;session=$_.SessionId;created_utc=$_.CreationDate.ToUniversalTime().ToString('o');agent=[bool]($_.CommandLine -match 'hara-commander-agent.ps1');diagnostic=[bool]($_.CommandLine -match 'windows_clean_diagnose_installed.ps1')}});[ordered]@{schema='hara.windows-clean-native-system-metadata.v1';clone_uuid='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba';tasks=$tasks;pids=$ps;config_values_read=$false;commandlines_printed=$false}|ConvertTo-Json -Depth 5 -Compress"""
code,out,err=q.powershell(ps,wait=25)
report={"native_metadata":json.loads(out) if code==0 else None,"metadata_exit":code,"stderr_present":bool(err)}
h=None
try:
 h=b.call(b.CLONE,{"execute":"guest-file-open","arguments":{"path":r"C:\Users\HARAQA\AppData\Local\HARA Commander\hara-commander-agent.ps1","mode":"rb"}})
 data=bytearray()
 while True:
  r=b.call(b.CLONE,{"execute":"guest-file-read","arguments":{"handle":h,"count":16384}});data.extend(base64.b64decode(r.get("buf-b64","")))
  if r.get("eof"):break
 report["physical_agent_sha256"]=hashlib.sha256(data).hexdigest();report["physical_agent_bytes"]=len(data)
except Exception as e:report["physical_hash_read_error"]=type(e).__name__
finally:
 if h is not None:b.call(b.CLONE,{"execute":"guest-file-close","arguments":{"handle":h}})
print(json.dumps(report))
