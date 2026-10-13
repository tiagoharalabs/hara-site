#!/usr/bin/env python3
"""External lifecycle checks; only immutable installed Agent and native systemd are used."""
import argparse, hashlib, json, os, pty, re, select, signal, stat, subprocess, time
from pathlib import Path
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
PIN="3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7"
HOME_QA=Path("/home/commanderqa")
DATA=HOME_QA/".local/share/hara-commander"
AGENT=DATA/"hara-commander-agent"
INSTALLER=HOME_QA/"commander-qa/linux.sh"
CONFIG=HOME_QA/".config/hara-commander/device.env"
SESSION=DATA/"operator-session.json"
SERVICE="hara-commander-agent.service"
parser=argparse.ArgumentParser();parser.add_argument("--expected-agent-sha256",default=PIN);parser.add_argument("--expected-version",default="0.3.43",choices=["0.3.43","0.3.53"])
a=parser.parse_args();assert re.fullmatch("[0-9a-f]{64}",a.expected_agent_sha256);PIN=a.expected_agent_sha256
checks=[]
owner=None
assert os.getuid()==2000 and Path("/etc/hostname").read_text().strip()=="commander-linux-clean"
def config():
 values={}
 for raw in CONFIG.read_text().splitlines():
  if "=" in raw:k,v=raw.split("=",1);values[k]=v
 assert values["HARA_COMMANDER_URL"]==DEV
 return values
def run(argv,timeout=45):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 values=config()
 text=p.stdout+p.stderr
 for name in ("HARA_DEVICE_TOKEN","HARA_OPERATOR_SESSION_TOKEN"):
  if values.get(name):text=text.replace(values[name],"[REDACTED]")
 return p.returncode,text
def assert_check(name,ok,extra=None):
 if not ok:raise AssertionError(name)
 checks.append({"check":name,"state":"PASS",**(extra or {})})
def active():return subprocess.run(["systemctl","--user","is-active","--quiet",SERVICE]).returncode==0
def enabled():return subprocess.run(["systemctl","--user","is-enabled","--quiet",SERVICE],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def mcp(name,args):
 p=subprocess.Popen(["python3",str(AGENT),"mcp"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 requests=[{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"commander-linux-clean-native","version":"1"}}},
           {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":name,"arguments":args}}]
 out,err=p.communicate("".join(json.dumps(x)+"\n" for x in requests),timeout=40)
 responses=[json.loads(x) for x in out.splitlines() if x.strip()]
 return next(x for x in responses if x.get("id")==2)
def wait_for(predicate,seconds=15):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if predicate():return True
  time.sleep(.2)
 return False
def session_start():
 pid,fd=pty.fork()
 if pid==0:os.execvpe("python3",["python3",str(AGENT),"start"],os.environ.copy())
 assert wait_for(lambda: SESSION.is_file() and active()),"CLI_START_FAILED"
 return pid,fd
def session_finish(pid,fd):
 # Close through the product's stop command, not a forged local session file.
 rc,out=run(["python3",str(AGENT),"stop"],timeout=30)
 assert_check("native-cli-stop-session",rc==0 and not SESSION.exists() and not active())
 assert wait_for(lambda: os.waitpid(pid,os.WNOHANG)[0]==pid),"CLI_CONSOLE_DID_NOT_EXIT"
 os.close(fd)
result={"schema":"hara.commander-linux-clean-native-lifecycle.v1","backend":"remote_DEV_worker","systemctl_backend":"real","checks":checks,"human_action_approval_generated":False}
try:
 values=config()
 if not active():
  rc,out=run(["systemctl","--user","start",SERVICE])
  assert_check("native-real-systemd-restore-baseline-after-incomplete-run",rc==0)
 assert_check("installed-default-ASK",values["HARA_COMMANDER_APPROVAL_MODE"]=="ASK_EVERY_ACTION")
 assert_check("installed-source-pin",hashlib.sha256(AGENT.read_bytes()).hexdigest()==PIN)
 assert_check("installed-service-active-disabled",active() and not enabled())
 assert_check("installed-no-operator-session",not SESSION.exists())
 target=HOME_QA/"commander-qa/MUST_NOT_EXIST_NO_SESSION"
 assert not target.exists()
 reply=mcp("start_process",{"command":"touch "+str(target),"cwd":str(HOME_QA),"timeout_ms":1000})
 code=None
 payload=reply.get("result",{})
 for item in payload.get("content",[]):
  if item.get("type")=="text":
   try:code=json.loads(item["text"]).get("code") or code
   except (ValueError,TypeError):pass
 assert_check("default-ASK-no-session-mutation-denied",payload.get("isError") is True and code=="LOCAL_OPERATOR_SESSION_REQUIRED" and not target.exists(),{"denial_code":code})
 rc,out=run(["python3",str(AGENT),"stop"],timeout=30)
 assert_check("native-cli-stop-installed-service",rc==0 and not active() and not enabled())
 rc,out=run(["bash",str(INSTALLER),"update"],timeout=120)
 assert_check("offline-signed-update-preserves-offline",rc==0 and "UPDATE_SERVICE_WAS_ACTIVE=FALSE" in out and not active() and not enabled())
 assert_check("offline-update-preserves-source",hashlib.sha256(AGENT.read_bytes()).hexdigest()==PIN)
 pid,fd=session_start();owner=(pid,fd)
 assert_check("native-cli-start-real-operator-session",active() and SESSION.is_file() and not enabled())
 reply=mcp("get_device_info",{})
 payload=reply.get("result",{})
 assert_check("native-MCP-readonly-device-info",not payload.get("isError") and payload.get("structuredContent",{}).get("state")=="PASS")
 before=json.loads((DATA/"runtime-status.json").read_text()).get("started_at_utc")
 rc,out=run(["bash",str(INSTALLER),"update"],timeout=120)
 after=json.loads((DATA/"runtime-status.json").read_text()).get("started_at_utc")
 assert_check("active-signed-update-startup-attestation",rc==0 and "UPDATE_SERVICE_WAS_ACTIVE=TRUE" in out and "STARTUP_ATTESTATION=PASS" in out and active() and before!=after)
 assert_check("active-update-preserves-source-policy",hashlib.sha256(AGENT.read_bytes()).hexdigest()==PIN and config()["HARA_COMMANDER_APPROVAL_MODE"]=="ASK_EVERY_ACTION" and not enabled())
 session_finish(pid,fd);owner=None
 result.update(state="PASS_NATIVE_LINUX_LIFECYCLE_CORE",device_id=values["HARA_DEVICE_ID"],agent_version=a.expected_version,config_mode=oct(stat.S_IMODE(CONFIG.stat().st_mode)),agent_mode=oct(stat.S_IMODE(AGENT.stat().st_mode)),manual_agent_boot=True)
except Exception as error:
 result.update(state="FAIL_NATIVE_LINUX_LIFECYCLE_CORE",error_type=type(error).__name__,error_code=str(error) if isinstance(error,AssertionError) else "NATIVE_PHASE_FAILED")
finally:
 if owner is not None:
  try:
   run(["python3",str(AGENT),"stop"],timeout=30)
   os.close(owner[1])
  except Exception:pass
print(json.dumps(result))
raise SystemExit(0 if result["state"].startswith("PASS") else 1)
