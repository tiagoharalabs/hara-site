#!/usr/bin/env python3
"""Inject one real QA process crash to exercise immutable installer rollback."""
import argparse,hashlib,json,os,re,subprocess,time
from pathlib import Path
Q=Path("/home/commanderqa")
D=Q/".local/share/hara-commander"
A=D/"hara-commander-agent"
C=Q/".config/hara-commander/device.env"
F=Q/"commander-qa"
U=Q/".config/systemd/user/hara-commander-agent.service.d"
DROP=U/"90-qa-rollback-fault.conf"
MARK=F/"crash-once.marker"
FAULT=F/"qa_crash_once.py"
S="hara-commander-agent.service"
PIN="3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7"
parser=argparse.ArgumentParser();parser.add_argument("--expected-agent-sha256",default=PIN);parser.add_argument("--expected-version",default="0.3.43",choices=["0.3.43","0.3.53"])
a=parser.parse_args();assert re.fullmatch("[0-9a-f]{64}",a.expected_agent_sha256);PIN=a.expected_agent_sha256
assert os.getuid()==2000 and Path("/etc/hostname").read_text().strip()=="commander-linux-clean"
assert not DROP.exists() and not MARK.exists()
values=dict(line.split("=",1) for line in C.read_text().splitlines() if "=" in line)
assert values["HARA_COMMANDER_URL"]=="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
assert hashlib.sha256(A.read_bytes()).hexdigest()==PIN
def ctl(*args):return subprocess.run(["systemctl","--user",*args],capture_output=True,text=True,timeout=20)
def active():return ctl("is-active","--quiet",S).returncode==0
fault="""import os,signal,time
from pathlib import Path
p=Path('/home/commanderqa/commander-qa/crash-once.marker')
if p.exists():
 p.unlink()
 pid=int(os.environ['MAINPID'])
 child=os.fork()
 if child==0:
  time.sleep(.5)
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
  os._exit(0)
"""
result={"schema":"hara.commander-linux-clean-native-rollback.v1","backend":"remote_DEV_worker","systemctl_backend":"real","fault":"one SIGKILL against real QA Agent after successful systemd startup","signed_agent_edited":False,"signed_installer_edited":False,"same_version_update":True,"agent_version":a.expected_version}
try:
 assert ctl("start",S).returncode==0 and active()
 FAULT.write_text(fault);FAULT.chmod(0o600)
 U.mkdir(parents=True,exist_ok=True)
 DROP.write_text("[Service]\nExecStartPost=/usr/bin/python3 "+str(FAULT)+"\nRestartSec=5\n");DROP.chmod(0o600)
 assert ctl("daemon-reload").returncode==0
 MARK.write_text("exclusive QA crash-once\n");MARK.chmod(0o600)
 p=subprocess.run(["bash",str(F/"linux.sh"),"update"],capture_output=True,text=True,timeout=150)
 text=p.stdout+p.stderr
 for name in ("HARA_DEVICE_TOKEN","HARA_OPERATOR_SESSION_TOKEN"):
  if values.get(name):text=text.replace(values[name],"[REDACTED]")
 result.update(update_exit_code=p.returncode,output=text,fault_consumed=not MARK.exists(),service_active_after_rollback=active(),agent_sha256=hashlib.sha256(A.read_bytes()).hexdigest(),rollback_backup_consumed=not Path(str(A)+".rollback").exists())
 ok=p.returncode==7 and "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=PASS" in text and not MARK.exists() and active() and result["agent_sha256"]==PIN and result["rollback_backup_consumed"]
 result["state"]="PASS_NATIVE_SIGNED_UPDATE_ROLLBACK" if ok else "FAIL_NATIVE_SIGNED_UPDATE_ROLLBACK"
except Exception as e:
 result.update(state="FAIL_NATIVE_SIGNED_UPDATE_ROLLBACK",error_type=type(e).__name__)
finally:
 DROP.unlink(missing_ok=True);MARK.unlink(missing_ok=True)
 try:U.rmdir()
 except OSError:pass
 ctl("daemon-reload")
 ctl("start",S)
 result["qa_fault_removed"]=not DROP.exists() and not MARK.exists()
 result["real_agent_source_intact"]=hashlib.sha256(A.read_bytes()).hexdigest()==PIN
print(json.dumps(result))
raise SystemExit(0 if result["state"].startswith("PASS") else 1)
