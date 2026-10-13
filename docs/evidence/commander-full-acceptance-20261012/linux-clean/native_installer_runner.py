#!/usr/bin/env python3
"""Run the immutable installer on the exclusive Linux QA guest with real systemd."""
import argparse, hashlib, json, os, pty, re, select, stat, subprocess, time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

EXPECTED_INSTALLER = "534e14433da9f86eb4342c6d9400e89ecf164545605e02e22f1646510284aba5"
EXPECTED_AGENT = "3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7"
DEV = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
p=argparse.ArgumentParser()
p.add_argument("action",choices=["install","re-enroll"])
p.add_argument("--fixture",type=Path,required=True)
p.add_argument("--installer",type=Path,required=True)
p.add_argument("--expected-installer-sha256",default=EXPECTED_INSTALLER)
p.add_argument("--expected-agent-sha256",default=EXPECTED_AGENT)
p.add_argument("--expected-version",choices=["0.3.43","0.3.53"],default="0.3.43")
a=p.parse_args()
assert re.fullmatch("[0-9a-f]{64}",a.expected_installer_sha256) and re.fullmatch("[0-9a-f]{64}",a.expected_agent_sha256)
EXPECTED_INSTALLER=a.expected_installer_sha256;EXPECTED_AGENT=a.expected_agent_sha256
assert os.getuid()==2000 and Path("/etc/hostname").read_text().strip()=="commander-linux-clean"
assert stat.S_IMODE(a.fixture.stat().st_mode)==0o600
fixture=json.loads(a.fixture.read_text())
assert fixture["dev_origin"]==DEV and fixture["environment"]=="DEV"
assert hashlib.sha256(a.installer.read_bytes()).hexdigest()==EXPECTED_INSTALLER
prior_values={}
if a.action=="re-enroll":
 prior_config=Path.home()/".config/hara-commander/device.env"
 prior_values=dict(line.split("=",1) for line in prior_config.read_text().splitlines() if "=" in line)
 assert prior_values["HARA_COMMANDER_URL"]==DEV
token=fixture["pairing_token"]
env=dict(os.environ,HARA_COMMANDER_URL=DEV)
# Install keeps the product's default ASK_EVERY_ACTION.
env.pop("HARA_COMMANDER_APPROVAL_MODE",None)
pid,fd=pty.fork()
if pid==0:
 os.execvpe("bash",["bash",str(a.installer),a.action],env)
buf=bytearray();sent=False;status=None;deadline=time.monotonic()+180
while time.monotonic()<deadline:
 readable,_,_=select.select([fd],[],[],0.1)
 if readable:
  try:chunk=os.read(fd,65536)
  except OSError:chunk=b""
  if chunk:
   buf.extend(chunk)
   if not sent and b"Pairing token:" in buf:
    os.write(fd,(token+"\n").encode());sent=True
 done,s=os.waitpid(pid,os.WNOHANG)
 if done:status=s;break
if status is None:
 os.kill(pid,9);_,status=os.waitpid(pid,0)
try:
 while True:
  chunk=os.read(fd,65536)
  if not chunk:break
  buf.extend(chunk)
except OSError:pass
os.close(fd)
rc=os.waitstatus_to_exitcode(status)
config=Path.home()/".config/hara-commander/device.env"
values={}
if config.is_file():
 for line in config.read_text().splitlines():
  if "=" in line:
   k,v=line.split("=",1);values[k]=v
out=buf.decode("utf-8","replace").replace(token,"[PAIRING_TOKEN_REDACTED]")
for key in ("HARA_DEVICE_TOKEN","HARA_OPERATOR_SESSION_TOKEN"):
 if values.get(key):out=out.replace(values[key],"[DEVICE_TOKEN_REDACTED]")
agent=Path.home()/".local/share/hara-commander/hara-commander-agent"
result={
 "schema":"hara.commander-linux-clean-native-installer.v1","action":a.action,
 "state":"PASS" if rc==0 else "FAIL","exit_code":rc,"pairing_prompt_received":sent,
 "approval_mode":values.get("HARA_COMMANDER_APPROVAL_MODE"),
 "device_id":values.get("HARA_DEVICE_ID"),"device_token_exposed":False,
 "human_action_approval_generated":False,"systemctl_backend":"real","backend":"remote_DEV_worker",
 "installer_sha256":hashlib.sha256(a.installer.read_bytes()).hexdigest(),
 "agent_sha256":hashlib.sha256(agent.read_bytes()).hexdigest() if agent.is_file() else None,
 "expected_version":a.expected_version,
 "output":out
}
if rc==0:
 assert result["agent_sha256"]==EXPECTED_AGENT
 assert subprocess.check_output(["python3",str(agent),"--version"],text=True).strip()==a.expected_version
 assert result["approval_mode"]=="ASK_EVERY_ACTION"
 assert stat.S_IMODE(config.stat().st_mode)==0o600
 if prior_values:
  assert values["HARA_DEVICE_ID"]!=prior_values["HARA_DEVICE_ID"]
  req=Request(DEV+"/api/device/heartbeat",data=json.dumps({"device_id":prior_values["HARA_DEVICE_ID"],"platform":"LINUX","architecture":"x86_64","agent_version":a.expected_version}).encode(),method="POST",headers={"authorization":"Bearer "+prior_values["HARA_DEVICE_TOKEN"],"content-type":"application/json","user-agent":"HARA-Commander-LinuxClean-DEV/1"})
  try:
   with urlopen(req,timeout=20) as response:old_status=response.status
  except HTTPError as error:old_status=error.code
  assert old_status in (401,403)
  result["old_authority_rejected"]=True;result["old_credential_http_status"]=old_status;result["prior_device_id"]=prior_values["HARA_DEVICE_ID"]
print(json.dumps(result))
raise SystemExit(rc)