#!/usr/bin/env python3
"""Install actual signed53 HTTPS baseline on exclusive clean54 guest only."""
import argparse,hashlib,json,shlex,stat,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);a=p.parse_args()
R=Path("/tmp_hara/commander-win50-utf8-20261012")
E=R/"docs/evidence/commander-full-acceptance-20261012/linux-clean/linux54"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
SHA="db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e"
ISHA="dae0a39f12a02920261a8051834d5b8426866a07e8a0d0acb9676c6605c8e3f8"
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile=/tmp_hara/commander-linux54-clean-20261013/known_hosts","-i","/tmp_hara/commander-linux54-clean-20261013/qa_ed25519","commanderqa@192.168.122.81"]
def run(cmd,input=None,timeout=250):
 r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(SSH+[cmd])],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if r.returncode:raise RuntimeError("NEW_QA_TRANSPORT_OR_PREPARATION_FAILED")
 return r.stdout
assert not (E/"baseline-053-install.json").exists(),"BASELINE_ALREADY_RECORDED"
assert a.fixture.is_file() and not a.fixture.is_symlink() and stat.S_IMODE(a.fixture.stat().st_mode)==0o600
import runpy
read_private=runpy.run_path(str(R/"apps/commander/scripts/full_acceptance_dev_fixtures.py"))["read_private"]
f=read_private(a.fixture);assert f["environment"]=="DEV" and f["dev_origin"]==DEV
old=R/"apps/commander/.generated/full-acceptance-20261012/linux-install-20261012234227-4f4e7600.json"
assert f["tenant_id"]!=json.loads(old.read_text())["tenant_id"],"OLD_SOAK_TENANT_REUSE_DENIED"
run('test "$(id -u)" = 2000 && test "$(hostname)" = commander-linux-clean54 && test "$HOME" = /home/commanderqa && test -d /home/commanderqa/commander-qa && test ! -e /home/commanderqa/.config/hara-commander/device.env && test ! -e /home/commanderqa/.local/share/hara-commander/hara-commander-agent')
s=E/"native_installer_runner.py";compile(s.read_text(),str(s),"exec")
run("umask 077; cat > /home/commanderqa/commander-qa/native_installer_runner.py",input=s.read_bytes())
private=json.dumps({k:f[k] for k in ("environment","dev_origin","pairing_token")}).encode()
run("umask 077; cat > /home/commanderqa/commander-qa/enrollment-private.json; chmod 600 /home/commanderqa/commander-qa/enrollment-private.json",input=private)
run("umask 077; curl -fsS --max-time 30 "+DEV+"/install/linux.sh -o /home/commanderqa/commander-qa/linux.sh")
args=["python3","-I","-B","/home/commanderqa/commander-qa/native_installer_runner.py","install","--fixture","/home/commanderqa/commander-qa/enrollment-private.json","--installer","/home/commanderqa/commander-qa/linux.sh","--expected-installer-sha256",ISHA,"--expected-agent-sha256",SHA,"--expected-version","0.3.53"]
cmd="env XDG_RUNTIME_DIR=/run/user/2000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/2000/bus "+shlex.join(args)
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(SSH+[cmd])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
try:result=json.loads(r.stdout)
except Exception:raise RuntimeError("NEW_QA_BASELINE_RESULT_MISSING")
result["governed_transport"]="H.A.R.A. Commander DIRECT -> Services -> SSH nucleo-a -> exclusive real Linux54 QA"
result["new_qa_vm_uuid"]="f1fc631b-9442-468a-82dc-e99d021ea8f5"
result["fixture_reuses_soak53_tenant"]=False
result["runner_sha256"]=hashlib.sha256(s.read_bytes()).hexdigest()
out=E/"baseline-053-install.json";out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"state":result.get("state"),"exit_code":r.returncode,"evidence":str(out),"device_id":result.get("device_id"),"approval_mode":result.get("approval_mode"),"agent_sha256":result.get("agent_sha256"),"public_wrapper_sha256":result.get("public_wrapper_sha256"),"customer_secrets_exposed":False}))
raise SystemExit(r.returncode)
