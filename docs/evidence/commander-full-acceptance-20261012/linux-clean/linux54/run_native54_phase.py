#!/usr/bin/env python3
"""Governed pinned actual product phases on isolated Linux54 QA VM."""
import argparse,hashlib,json,re,runpy,shlex,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("phase",choices=["upgrade","core","rollback","mcp","uninstall","install","re-enroll"])
p.add_argument("--fixture",type=Path);p.add_argument("--expected-agent-sha256",required=True);p.add_argument("--expected-installer-sha256",required=True);p.add_argument("--expected-runner-sha256",required=True);p.add_argument("--run-label",required=True)
a=p.parse_args()
R=Path("/tmp_hara/commander-win50-utf8-20261012");E=R/"docs/evidence/commander-full-acceptance-20261012/linux-clean/linux54"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev";VM="commander-linux54-clean-20261013";UUID="f1fc631b-9442-468a-82dc-e99d021ea8f5"
BASEFIX=R/"apps/commander/.generated/full-acceptance-20261012/linux54-baseline53-20261013033631-4f624d30.json"
def require(ok,code):
 if not ok:raise RuntimeError(code)
require(re.fullmatch("[0-9a-f]{64}",a.expected_agent_sha256) and re.fullmatch("[0-9a-f]{64}",a.expected_installer_sha256),"INVALID_RELEASE_PIN")
require(re.fullmatch("[a-z0-9][a-z0-9-]{0,80}",a.run_label),"INVALID_EVIDENCE_LABEL")
out=E/(a.run_label+".json");require(not out.exists(),"EVIDENCE_LABEL_ALREADY_EXISTS")
uuid=subprocess.check_output(["ssh","-o","BatchMode=yes","nucleo-a","sudo virsh -c qemu:///system domuuid "+VM],timeout=15).decode().strip()
require(uuid==UUID,"NEW_QA_UUID_MISMATCH")
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile=/tmp_hara/commander-linux54-clean-20261013/known_hosts","-i","/tmp_hara/commander-linux54-clean-20261013/qa_ed25519","commanderqa@192.168.122.81"]
def run(cmd,input=None,timeout=250):
 r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(SSH+[cmd])],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 require(r.returncode==0,"NEW_QA_TRANSPORT_OR_PREPARATION_FAILED")
 return r.stdout
run('test "$(id -u)" = 2000 && test "$(hostname)" = commander-linux-clean54 && test "$HOME" = /home/commanderqa && test -d /home/commanderqa/commander-qa')
scripts={"upgrade":"native_053_to_054_upgrade_runner.py","core":"native_lifecycle_runner.py","rollback":"native_rollback_runner.py","mcp":"native_mcp_54_receipt_contract_r2_runner.py","uninstall":"native_uninstall_runner.py","install":"native_installer_runner.py","re-enroll":"native_installer_runner.py"}
source=E/scripts[a.phase];compile(source.read_text(),str(source),"exec")
require(re.fullmatch("[0-9a-f]{64}",a.expected_runner_sha256) and hashlib.sha256(source.read_bytes()).hexdigest()==a.expected_runner_sha256,"REVIEWED_RUNNER_PIN_MISMATCH")
run("umask 077; cat > /home/commanderqa/commander-qa/"+source.name,input=source.read_bytes())
args=["python3","-I","-B","/home/commanderqa/commander-qa/"+source.name]
if a.phase in ("install","re-enroll"):
 require(a.fixture is not None,"PAIRING_FIXTURE_REQUIRED")
 read_private=runpy.run_path(str(R/"apps/commander/scripts/full_acceptance_dev_fixtures.py"))["read_private"]
 f=read_private(a.fixture);base=read_private(BASEFIX)
 require(f["environment"]=="DEV" and f["dev_origin"]==DEV and f["tenant_id"]==base["tenant_id"] and f["subject_id"]==base["subject_id"],"NEW_QA_FIXTURE_IDENTITY_MISMATCH")
 private=json.dumps({k:f[k] for k in ("environment","dev_origin","pairing_token")}).encode()
 run("umask 077; cat > /home/commanderqa/commander-qa/enrollment-private.json; chmod 600 /home/commanderqa/commander-qa/enrollment-private.json",input=private)
 run("umask 077; curl -fsS --proto '=https' --max-time 30 "+DEV+"/install/linux.sh -o /home/commanderqa/commander-qa/linux.sh")
 args+=[a.phase,"--fixture","/home/commanderqa/commander-qa/enrollment-private.json","--installer","/home/commanderqa/commander-qa/linux.sh"]
args+=["--expected-agent-sha256",a.expected_agent_sha256,"--expected-installer-sha256",a.expected_installer_sha256,"--expected-version","0.3.54"]
cmd="env HOME=/home/commanderqa XDG_CONFIG_HOME=/home/commanderqa/.config XDG_DATA_HOME=/home/commanderqa/.local/share XDG_STATE_HOME=/home/commanderqa/.local/state XDG_RUNTIME_DIR=/run/user/2000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/2000/bus HARA_COMMANDER_URL="+DEV+" "+shlex.join(args)
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(SSH+[cmd])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=450)
try:result=json.loads(r.stdout)
except Exception:raise RuntimeError("NEW_QA_PHASE_RESULT_MISSING")
result["governed_transport"]="H.A.R.A. Commander DIRECT -> Services -> SSH nucleo-a -> exclusive real Linux54 QA"
result["new_qa_vm_uuid"]=UUID;result["runner_sha256"]=hashlib.sha256(source.read_bytes()).hexdigest()
result["release_agent_pin"]=a.expected_agent_sha256;result["release_installer_pin"]=a.expected_installer_sha256
out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"phase":a.phase,"state":result.get("state"),"exit_code":r.returncode,"evidence":str(out),"checks":len(result.get("checks",[])),"cleanup_checks":result.get("cleanup_checks"),"device_id":result.get("device_id"),"customer_secrets_exposed":False}))
raise SystemExit(r.returncode)
