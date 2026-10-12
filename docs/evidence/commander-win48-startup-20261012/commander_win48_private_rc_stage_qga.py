#!/usr/bin/env python3
"""Stage and validate a frozen private RC47 bundle; never install it."""
import argparse,base64,hashlib,importlib.util,json
from pathlib import Path
HOST=Path("/tmp_hara/commander-win48-private-rc-20261012-r1")
BUNDLE=HOST/"commercial-0.3.48-v8-rc"
GUEST=r"C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-048-rc-r2"
sp=importlib.util.spec_from_file_location("qga","/tmp_hara/commander-win11-qga-readiness-20261011.py")
q=importlib.util.module_from_spec(sp);sp.loader.exec_module(q)
FILES=("README.md","agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1","release/SHA256SUMS","release/agent-manifest.json","release/agent-manifest.sig.json","release/release-signing-public.jwk")
def emit(v):print(json.dumps(v,sort_keys=True))
def stage():
 assert hashlib.sha256((BUNDLE/"release/agent-manifest.json").read_bytes()).hexdigest()=="5e65b1862c40bc9164609cdcd1401bb55e02e409b44f1b58bca15151e40de32c"
 entries=[(rel,BUNDLE/rel) for rel in FILES]+[("windows_048_private_rc_validate.ps1",HOST/"windows_048_private_rc_validate.ps1")]
 rows=[]
 for rel,p in entries:
  assert p.is_file() and not p.is_symlink(),"SOURCE_NOT_REGULAR"
  data=p.read_bytes();rows.append({"path":rel,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
 ps=r"$ErrorActionPreference='Stop';$r='"+GUEST+r"';if(Test-Path -LiteralPath $r){throw 'PRIVATE_RC_STAGE_COLLISION'};New-Item -ItemType Directory -Path $r -Force|Out-Null;foreach($d in @('agent','install','release')){New-Item -ItemType Directory -Path (Join-Path $r $d)|Out-Null};'CREATED'"
 rc,out,err=q.powershell(ps,wait=7);assert rc==0 and not err and out=="CREATED","GUEST_CREATE_FAILED"
 for rel,p in entries:
  data=p.read_bytes();dest=GUEST+"\\"+rel.replace("/","\\")
  h=q.guest_call({"execute":"guest-file-open","arguments":{"path":dest,"mode":"wb"}});h=h if isinstance(h,int) else h["handle"]
  try:
   for i in range(0,len(data),24576):
    part=data[i:i+24576];w=q.guest_call({"execute":"guest-file-write","arguments":{"handle":h,"buf-b64":base64.b64encode(part).decode("ascii")}})
    assert w.get("count")==len(part),"GUEST_PARTIAL_WRITE"
  finally:q.guest_call({"execute":"guest-file-close","arguments":{"handle":h}})
 names=",".join("'"+x["path"].replace("/","\\")+"'" for x in rows)
 ps=r"$ErrorActionPreference='Stop';$r='"+GUEST+r"';$rows=@();foreach($rel in @("+names+r")){$p=Join-Path $r $rel;$tok=$null;$errors=$null;if($rel -like '*.ps1'){[Management.Automation.Language.Parser]::ParseFile($p,[ref]$tok,[ref]$errors)|Out-Null};$rows+=[pscustomobject]@{path=$rel.Replace('\','/');bytes=(Get-Item -LiteralPath $p).Length;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant();parse_errors=$(if($rel -like '*.ps1'){@($errors).Count}else{0})}};[pscustomobject]@{state='PASS';powershell_version=$PSVersionTable.PSVersion.ToString();files=$rows}|ConvertTo-Json -Depth 4 -Compress"
 rc,out,err=q.powershell(ps,wait=7);assert rc==0 and not err,"GUEST_STAGE_VERIFY_FAILED"
 report=json.loads(out);actual={x["path"]:x for x in report["files"]}
 for row in rows:
  got=actual[row["path"]];assert got["sha256"]==row["sha256"] and got["bytes"]==row["bytes"] and got["parse_errors"]==0,"GUEST_HASH_OR_PARSER_MISMATCH"
 report.update({"schema":"hara.commander-win48-private-rc-stage.v1","installed_agent_modified":False,"agent_transport_started":False})
 (HOST/"stage.json").write_text(json.dumps(report,sort_keys=True)+"\n")
 emit(report)
def start():
 assert (HOST/"stage.json").exists(),"STAGE_REQUIRED"
 assert not (HOST/"validate-pid.json").exists(),"VALIDATION_RUN_COLLISION"
 pid=q.guest_call({"execute":"guest-exec","arguments":{"path":q.EXE,"arg":["-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",GUEST+"\\windows_048_private_rc_validate.ps1","-BundleRoot",GUEST,"-SelfTest"],"capture-output":True}})["pid"]
 report={"state":"STARTED","guest_pid":pid,"installed_agent_modified":False,"agent_transport_started":False}
 (HOST/"validate-pid.json").write_text(json.dumps(report,sort_keys=True)+"\n");emit(report)
def status():
 output=HOST/"validation.json"
 if output.exists():emit(json.loads(output.read_text()));return
 pid=json.loads((HOST/"validate-pid.json").read_text())["guest_pid"]
 r=q.guest_call({"execute":"guest-exec-status","arguments":{"pid":pid}})
 if not r.get("exited"):emit({"state":"RUNNING","guest_pid":pid});return
 dec=lambda k:base64.b64decode(r.get(k,"") or "").decode("utf-8","replace").strip()
 report={"schema":"hara.commander-win48-private-rc-guest-result.v1","state":"PASS" if r.get("exitcode")==0 else "FAIL","exit_code":r.get("exitcode"),"stdout":dec("out-data"),"stderr":dec("err-data"),"out_truncated":r.get("out-truncated",False),"err_truncated":r.get("err-truncated",False),"installed_agent_modified":False,"agent_transport_started":False}
 output.write_text(json.dumps(report,sort_keys=True)+"\n");emit(report)
if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("action",choices=["stage","start","status"])
 a=parser.parse_args();{"stage":stage,"start":start,"status":status}[a.action]()

