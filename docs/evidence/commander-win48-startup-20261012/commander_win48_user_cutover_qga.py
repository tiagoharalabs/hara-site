#!/usr/bin/env python3
"""Existing-user VM canary controller. Apply requires explicit root release."""
import argparse,base64,importlib.util,json
from pathlib import Path
HOST=Path("/tmp_hara/commander-win48-private-rc-20261012-r1")
GUEST=r"C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-048-rc-r1"
sp=importlib.util.spec_from_file_location("qga","/tmp_hara/commander-win11-qga-readiness-20261011.py")
q=importlib.util.module_from_spec(sp);sp.loader.exec_module(q)
def emit(v):print(json.dumps(v,sort_keys=True))
def start(action):
 pidfile=HOST/("cutover-"+action.lower()+"-"+args.control_sha[:16]+"-pid.json")
 assert not pidfile.exists(),"CANARY_ORCHESTRATOR_ALREADY_STARTED"
 out=r"C:\Users\Public\Documents\HARA_VM48_R1_Canary_"+action+".json"
 user=r"""$ErrorActionPreference='Stop'
try{
 if([Security.Principal.WindowsIdentity]::GetCurrent().IsSystem){throw 'CANARY_REAL_INTERACTIVE_USER_REQUIRED'}
 if((Get-FileHash -LiteralPath '@GUEST@\windows_048_signed_user_cutover_r1.ps1' -Algorithm SHA256).Hash.ToLowerInvariant() -cne '71d617c2a665b0787612192bab0f5b0bfc11f401ee75a4c2d660ab01a4ea18fb'){throw 'CANARY_REVIEWED_HELPER_CHANGED'}
 if((Get-FileHash -LiteralPath '@GUEST@\windows_048_private_rc_validate.ps1' -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'ec9215034431c2478d435be5a7f0f799198394fd81e096cb0cd6fa8c286dce4d'){throw 'CANARY_REVIEWED_VALIDATOR_CHANGED'}
 $result=& '@GUEST@\windows_048_signed_user_cutover_r1.ps1' -Action '@ACTION@' -BundleRoot '@GUEST@' -RootSource47NoMutanteOutstandingPlausiblyActive -RootControlPlaneMetadataSha256 '@CONTROL_SHA@' -RootControlPlaneObservedAtUtc '@CONTROL_AT@' -HistoricalProductSessionsCount 0 -HistoricalProductSessionsReceiptSha256 '0f6b76d01407dbe77d031d6dd5c0ca9e528cee4321c4d8eabf19a74dfb49058f' -FreshInspectObservedAtUtc '@INSPECT_AT@' -FreshInspectSha256 '@INSPECT_SHA@'
 [IO.File]::WriteAllText('@OUT@',[string]$result,(New-Object Text.UTF8Encoding($false)))
}catch{
 $code=[string]$_.Exception.Message
 if($code -notmatch '^[A-Z][A-Z0-9_]{1,100}$'){$code='CANARY_ORCHESTRATOR_USER_FAILED'}
 [IO.File]::WriteAllText('@OUT@',([pscustomobject]@{state='FAIL';reason=$code}|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
}
""".replace("@GUEST@",GUEST).replace("@ACTION@",action).replace("@OUT@",out).replace("@CONTROL_SHA@",args.control_sha).replace("@CONTROL_AT@",args.control_at).replace("@INSPECT_AT@",args.inspect_at).replace("@INSPECT_SHA@",args.inspect_sha)
 enc=base64.b64encode(user.encode("utf-16le")).decode("ascii")
 outer=r"""$ErrorActionPreference='Stop'
$user=(Get-CimInstance Win32_ComputerSystem).UserName
if(-not $user){throw 'CANARY_USER_NOT_LOGGED_ON'}
$name='HARA_VM48_R1_PrivateCanary_@ACTION@'
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
 outfile=HOST/("cutover-"+action.lower()+"-"+args.control_sha[:16]+"-result.json")
 if outfile.exists():emit(json.loads(outfile.read_text()));return
 pid=json.loads((HOST/("cutover-"+action.lower()+"-"+args.control_sha[:16]+"-pid.json")).read_text())["guest_pid"]
 r=q.guest_call({"execute":"guest-exec-status","arguments":{"pid":pid}})
 if not r.get("exited"):emit({"state":"RUNNING","action":action,"guest_pid":pid});return
 dec=lambda k:base64.b64decode(r.get(k,"") or "").decode("utf-8","replace").strip()
 out=dec("out-data");err=dec("err-data")
 try:report=json.loads(out)
 except Exception:report={"state":"FAIL","reason":"CANARY_GUEST_OUTPUT_INVALID"}
 result={"schema":"hara.commander-win48-user-canary-qga-result.v1","action":action,"exit_code":r.get("exitcode"),"result":report,"stderr_present":bool(err),"output_truncated":r.get("out-truncated",False) or r.get("err-truncated",False),"any_action_autoapproved":False}
 outfile.write_text(json.dumps(result,sort_keys=True)+"\n");emit(result)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("verb",choices=["start","status"]);p.add_argument("--action",choices=["Inspect","Apply"],default="Inspect")
 p.add_argument("--control-sha",required=True);p.add_argument("--control-at",required=True);p.add_argument("--inspect-at",default="");p.add_argument("--inspect-sha",default="");args=p.parse_args()
 import re
 assert re.fullmatch("[a-f0-9]{64}",args.control_sha)
 assert re.fullmatch("[0-9T:Z.-]+",args.control_at)
 assert not args.inspect_at or re.fullmatch("[0-9T:Z.-]+",args.inspect_at)
 assert not args.inspect_sha or re.fullmatch("[a-f0-9]{64}",args.inspect_sha)
 {"start":start,"status":status}[args.verb](args.action)

