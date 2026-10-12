import argparse,base64,hashlib,importlib.util,json
from pathlib import Path
HOST=Path("/tmp_hara/commander-win48-startup-fixture-20261012")
GUEST=r"C:\ProgramData\HaraLabs\CommanderWinLab\20261012\startup48-fixture-r1"
s=importlib.util.spec_from_file_location("qga","/tmp_hara/commander-win11-qga-readiness-20261011.py")
q=importlib.util.module_from_spec(s);s.loader.exec_module(q)
PINS={"frozen47.ps1":"254517c46acf47102ebed5fe31fcb5d880ca0de47b98debeebdcaf4b1b324e36","candidate048.ps1":"f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805","test_windows_operator_session_startup_fixture.ps1":"eb17d0b29f2214acc471a6eab2ea4141bc24c8e2a7b6aaab8a1bd6e9f981f3c9","test_windows_local_approval_expiry.ps1":"3cfe01817a58127fc5dcd08c1143ae1b92fdd0b95e0248689e8bbecf32e2d7cf","test_windows_full_tool_denial_fixture.ps1":"c20dc4230693cfb603b0aa6720d4fdc8064a7c3cdddc077e9d58a8a369cfde0f","test_windows_existing_console_resume_fixture.ps1":"1d2617d0c436e1564ab81f1b6abdcb57f275cabb8f52d6ca0ab634f226923d0a"}
JOBS={"frozen47":("test_windows_operator_session_startup_fixture.ps1",["-AgentSource",GUEST+r"\frozen47.ps1","-ExpectedBehavior","Frozen047"]),"startup48":("test_windows_operator_session_startup_fixture.ps1",["-AgentSource",GUEST+r"\candidate048.ps1","-ExpectedBehavior","Candidate048","-ExpectedSourceSha256",PINS["candidate048.ps1"]]),"core48":("test_windows_local_approval_expiry.ps1",["-AgentSource",GUEST+r"\candidate048.ps1"]),"denial48":("test_windows_full_tool_denial_fixture.ps1",["-AgentSource",GUEST+r"\candidate048.ps1"]),"resume48":("test_windows_existing_console_resume_fixture.ps1",["-AgentSource",GUEST+r"\candidate048.ps1","-ExpectedBehavior","Candidate048"])}
def emit(x):print(json.dumps(x,sort_keys=True))
def stage():
 for name,pin in PINS.items():assert hashlib.sha256((HOST/name).read_bytes()).hexdigest()==pin,"HOST_PIN_MISMATCH"
 rc,out,err=q.powershell("$ErrorActionPreference='Stop';$r='"+GUEST+"';if(Test-Path -LiteralPath $r){throw 'FIXTURE_GUEST_COLLISION'};New-Item -ItemType Directory -Path $r|Out-Null;'CREATED'",wait=7)
 assert rc==0 and out=="CREATED" and not err,"GUEST_DIRECTORY_FAILED"
 for name in PINS:
  data=(HOST/name).read_bytes()
  h=q.guest_call({"execute":"guest-file-open","arguments":{"path":GUEST+"\\"+name,"mode":"wb"}})
  h=h if isinstance(h,int) else h["handle"]
  try:
   for i in range(0,len(data),24576):
    b=data[i:i+24576];w=q.guest_call({"execute":"guest-file-write","arguments":{"handle":h,"buf-b64":base64.b64encode(b).decode("ascii")}});assert w.get("count")==len(b)
  finally:q.guest_call({"execute":"guest-file-close","arguments":{"handle":h}})
 names=",".join("'"+n+"'" for n in PINS)
 ps="$ErrorActionPreference='Stop';$rows=@();foreach($n in @("+names+")){$p=Join-Path '"+GUEST+"' $n;$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseFile($p,[ref]$t,[ref]$e)|Out-Null;$rows+=[pscustomobject]@{file=$n;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant();parse_errors=@($e).Count}};[pscustomobject]@{state='PASS';powershell_version=$PSVersionTable.PSVersion.ToString();files=$rows;installed_agent_modified=$false}|ConvertTo-Json -Depth 4 -Compress"
 rc,out,err=q.powershell(ps,wait=7);assert rc==0 and not err,"GUEST_PARSER_FAILED"
 r=json.loads(out)
 for f in r["files"]:assert f["sha256"]==PINS[f["file"]] and f["parse_errors"]==0,"GUEST_HASH_PARSER_FAILED"
 (HOST/"stage.json").write_text(json.dumps(r,sort_keys=True)+"\n");emit(r)
def start(job):
 assert (HOST/"stage.json").exists()
 p=HOST/(job+"-pid.json");assert not p.exists(),"JOB_COLLISION"
 name,args=JOBS[job]
 r=q.guest_call({"execute":"guest-exec","arguments":{"path":q.EXE,"arg":["-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",GUEST+"\\"+name]+args,"capture-output":True}})
 report={"state":"STARTED","job":job,"guest_pid":r["pid"],"installed_agent_modified":False}
 p.write_text(json.dumps(report,sort_keys=True)+"\n");emit(report)
def status(job):
 f=HOST/(job+"-result.json")
 if f.exists():emit(json.loads(f.read_text()));return
 pid=json.loads((HOST/(job+"-pid.json")).read_text())["guest_pid"]
 r=q.guest_call({"execute":"guest-exec-status","arguments":{"pid":pid}})
 if not r.get("exited"):emit({"state":"RUNNING","job":job});return
 out=base64.b64decode(r.get("out-data","") or "").decode("utf-8","replace");err=base64.b64decode(r.get("err-data","") or "")
 summary=None
 for line in reversed(out.splitlines()):
  if line.strip().startswith("{"):
   try:summary=json.loads(line.strip());break
   except ValueError:pass
 report={"schema":"hara.commander-win48-isolated-ps51-fixture.v1","job":job,"state":"PASS" if r.get("exitcode")==0 and summary else "FAIL","exit_code":r.get("exitcode"),"stderr_present":bool(err),"stderr_sha256":hashlib.sha256(err).hexdigest(),"stdout_sha256":hashlib.sha256(out.encode()).hexdigest(),"output_truncated":r.get("out-truncated",False) or r.get("err-truncated",False),"summary":summary,"raw_stdout_exposed":False,"installed_agent_modified":False}
 f.write_text(json.dumps(report,sort_keys=True)+"\n");emit(report)
p=argparse.ArgumentParser();p.add_argument("action",choices=["stage","start","status"]);p.add_argument("--job",choices=list(JOBS));a=p.parse_args()
if a.action=="stage":stage()
else:{"start":start,"status":status}[a.action](a.job)
