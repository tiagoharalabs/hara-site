#!/usr/bin/env python3
"""Existing-user VM canary controller. Apply requires explicit root release."""
import argparse,base64,importlib.util,json
from pathlib import Path
HOST=Path("/tmp_hara/commander-win47-private-rc-20261012-r4")
GUEST=r"C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-047-rc-r2"
sp=importlib.util.spec_from_file_location("qga","/tmp_hara/commander-win11-qga-readiness-20261011.py")
q=importlib.util.module_from_spec(sp);sp.loader.exec_module(q)
def emit(v):print(json.dumps(v,sort_keys=True))
def start(action):
 pidfile=HOST/("canary-"+action.lower()+"-pid.json")
 assert not pidfile.exists(),"CANARY_ORCHESTRATOR_ALREADY_STARTED"
 out=r"C:\Users\Public\Documents\HARA_VM47_R4_Canary_"+action+".json"
 user=r"""$ErrorActionPreference='Stop'
try{
 if([Security.Principal.WindowsIdentity]::GetCurrent().IsSystem){throw 'CANARY_REAL_INTERACTIVE_USER_REQUIRED'}
 if((Get-FileHash -LiteralPath '@GUEST@\windows_047_signed_user_canary_r4.ps1' -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'b8b0fb8010dbe734ee4f52807714824a8a8ccf94c24f05a4da473171eca18327'){throw 'CANARY_REVIEWED_HELPER_CHANGED'}
 if((Get-FileHash -LiteralPath '@GUEST@\windows_047_private_rc_validate.ps1' -Algorithm SHA256).Hash.ToLowerInvariant() -cne '60431aa16d1a1090a2b5038677e16115f2b8664fe3b6a27ba324b5774f1be7ec'){throw 'CANARY_REVIEWED_VALIDATOR_CHANGED'}
 $result=& '@GUEST@\windows_047_signed_user_canary_r4.ps1' -Action '@ACTION@' -BundleRoot '@GUEST@'
 [IO.File]::WriteAllText('@OUT@',[string]$result,(New-Object Text.UTF8Encoding($false)))
}catch{
 $code=[string]$_.Exception.Message
 if($code -notmatch '^[A-Z][A-Z0-9_]{1,100}$'){$code='CANARY_ORCHESTRATOR_USER_FAILED'}
 [IO.File]::WriteAllText('@OUT@',([pscustomobject]@{state='FAIL';reason=$code}|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
}
""".replace("@GUEST@",GUEST).replace("@ACTION@",action).replace("@OUT@",out)
 enc=base64.b64encode(user.encode("utf-16le")).decode("ascii")
 outer=r"""$ErrorActionPreference='Stop'
$user=(Get-CimInstance Win32_ComputerSystem).UserName
if(-not $user){throw 'CANARY_USER_NOT_LOGGED_ON'}
$name='HARA_VM47_R4_PrivateCanary_@ACTION@'
$out='@OUT@'
if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'CANARY_EPHEMERAL_TASK_COLLISION'}
if(Test-Path -LiteralPath $out){throw 'CANARY_EPHEMERAL_OUTPUT_COLLISION'}
$action=New-ScheduledTaskAction -Execute powershell.exe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand '+'@ENC@')
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
try{
 Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Force|Out-Null
 Start-ScheduledTask -TaskName $name
 for($i=0;$i -lt 240;$i++){if(Test-Path -LiteralPath $out){break};Start-Sleep -Milliseconds 250}
 if(-not(Test-Path -LiteralPath $out)){throw 'CANARY_USER_OUTPUT_TIMEOUT'}
 Get-Content -LiteralPath $out -Raw
}finally{
 Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
 Remove-Item -LiteralPath $out -Force -ErrorAction SilentlyContinue
}
""".replace("@ACTION@",action).replace("@OUT@",out).replace("@ENC@",enc)
 start=q.guest_call({"execute":"guest-exec","arguments":{"path":q.EXE,"arg":["-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-EncodedCommand",base64.b64encode(outer.encode("utf-16le")).decode("ascii")],"capture-output":True}})
 report={"state":"STARTED","action":action,"guest_pid":start["pid"],"any_action_autoapproved":False}
 pidfile.write_text(json.dumps(report,sort_keys=True)+"\n");emit(report)
def status(action):
 outfile=HOST/("canary-"+action.lower()+"-result.json")
 if outfile.exists():emit(json.loads(outfile.read_text()));return
 pid=json.loads((HOST/("canary-"+action.lower()+"-pid.json")).read_text())["guest_pid"]
 r=q.guest_call({"execute":"guest-exec-status","arguments":{"pid":pid}})
 if not r.get("exited"):emit({"state":"RUNNING","action":action,"guest_pid":pid});return
 dec=lambda k:base64.b64decode(r.get(k,"") or "").decode("utf-8","replace").strip()
 out=dec("out-data");err=dec("err-data")
 try:report=json.loads(out)
 except Exception:report={"state":"FAIL","reason":"CANARY_GUEST_OUTPUT_INVALID"}
 result={"schema":"hara.commander-win47-user-canary-qga-result.v1","action":action,"exit_code":r.get("exitcode"),"result":report,"stderr_present":bool(err),"output_truncated":r.get("out-truncated",False) or r.get("err-truncated",False),"any_action_autoapproved":False}
 outfile.write_text(json.dumps(result,sort_keys=True)+"\n");emit(result)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("verb",choices=["start","status"]);p.add_argument("--action",choices=["Inspect","Apply"],default="Inspect")
 a=p.parse_args();{"start":start,"status":status}[a.verb](a.action)

