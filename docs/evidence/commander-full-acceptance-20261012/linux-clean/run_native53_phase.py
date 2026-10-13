#!/usr/bin/env python3
"""Governed Services-to-isolated-QA bridge; actual signed product phases only."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("phase",choices=["upgrade","core","rollback","mcp","uninstall","install","re-enroll"]);p.add_argument("--fixture",type=Path);a=p.parse_args()
R=Path("/tmp_hara/commander-win50-utf8-20261012");E=R/"docs/evidence/commander-full-acceptance-20261012/linux-clean"
SHA="db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e";ISHA="dae0a39f12a02920261a8051834d5b8426866a07e8a0d0acb9676c6605c8e3f8"
ssh=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile=/tmp_hara/commander-linux-clean-20261012/known_hosts","-i","/tmp_hara/commander-linux-clean-20261012/qa_ed25519","commanderqa@192.168.122.180"]
def run(cmd,input=None,timeout=250):
 r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(ssh+[cmd])],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if r.returncode:raise RuntimeError("ISOLATED_QA_TRANSPORT_OR_PHASE_FAILED")
 return r.stdout
run('test "$(id -u)" = 2000 && test "$(hostname)" = commander-linux-clean && test -d /home/commanderqa/commander-qa')
scripts={"upgrade":"native_043_to_053_upgrade_runner.py","core":"native_lifecycle_runner.py","rollback":"native_rollback_runner.py","mcp":"native_mcp_53_runner.py","uninstall":"native_uninstall_runner.py","install":"native_installer_runner.py","re-enroll":"native_installer_runner.py"}
source=E/scripts[a.phase];compile(source.read_text(),str(source),"exec")
run("umask 077; cat > /home/commanderqa/commander-qa/"+source.name,input=source.read_bytes())
args=["python3","-I","-B","/home/commanderqa/commander-qa/"+source.name]
if a.phase in ("core","rollback","mcp"):args+=["--expected-agent-sha256",SHA,"--expected-version","0.3.53"]
if a.phase=="uninstall":args+=["--expected-version","0.3.53"]
if a.phase in ("install","re-enroll"):
 assert a.fixture and a.fixture.is_file() and a.fixture.stat().st_mode&0o777==0o600
 f=json.loads(a.fixture.read_text());assert f["environment"]=="DEV" and f["dev_origin"]=="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
 private=json.dumps({k:f[k] for k in ("environment","dev_origin","pairing_token")}).encode()
 run("umask 077; cat > /home/commanderqa/commander-qa/enrollment-private.json; chmod 600 /home/commanderqa/commander-qa/enrollment-private.json",input=private)
 run("umask 077; curl -fsS --max-time 30 https://hara-commander-dev-v2.tiago-sartori.workers.dev/install/linux.sh -o /home/commanderqa/commander-qa/linux.sh")
 args+=[a.phase,"--fixture","/home/commanderqa/commander-qa/enrollment-private.json","--installer","/home/commanderqa/commander-qa/linux.sh","--expected-installer-sha256",ISHA,"--expected-agent-sha256",SHA,"--expected-version","0.3.53"]
cmd="env XDG_RUNTIME_DIR=/run/user/2000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/2000/bus "+shlex.join(args)
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(ssh+[cmd])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
try:result=json.loads(r.stdout)
except Exception:raise RuntimeError("ISOLATED_QA_PHASE_RESULT_MISSING")
result["governed_transport"]="H.A.R.A. Commander DIRECT -> Services -> SSH nucleo-a -> exclusive real Linux QA"
out=E/("native-053-"+a.phase+".json")
if out.exists():
 old=json.loads(out.read_text());suffix=str(old.get("device_id") or "prior").replace("/","_")
 out.rename(out.with_name(out.stem+"-"+suffix+"-previous.json"))
out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"phase":a.phase,"state":result.get("state"),"exit_code":r.returncode,"evidence":str(out),"checks":len(result.get("checks",[])),"cleanup_checks":result.get("cleanup_checks"),"device_id":result.get("device_id"),"customer_secrets_exposed":False}))
raise SystemExit(r.returncode)
