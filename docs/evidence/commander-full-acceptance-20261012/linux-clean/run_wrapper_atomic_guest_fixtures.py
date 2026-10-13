#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shlex,subprocess
root=Path("/tmp_hara/commander-win50-utf8-20261012")
ev=root/"docs/evidence/commander-full-acceptance-20261012/linux-clean"
key="/tmp_hara/commander-linux-clean-20261012/qa_ed25519"
known="/tmp_hara/commander-linux-clean-20261012/known_hosts"
ssh=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile="+known,"-i",key,"commanderqa@192.168.122.180"]
def run(cmd,input=None):
 return subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(ssh+[cmd])],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=True)
guard=run("test \"$(id -u)\" = 2000 && test \"$(hostname)\" = commander-linux-clean && test -d /home/commanderqa/commander-qa")
for local,name in ((ev/"linux-installer-atomic-candidate.sh","linux-installer-atomic-candidate.sh"),(root/"apps/commander/scripts/test_linux_installer_wrapper_ownership.py","test_linux_installer_wrapper_ownership.py")):
 run("umask 077; cat > /home/commanderqa/commander-qa/"+name,input=local.read_bytes())
r=run("python3 -I -B /home/commanderqa/commander-qa/test_linux_installer_wrapper_ownership.py --installer /home/commanderqa/commander-qa/linux-installer-atomic-candidate.sh")
result=json.loads(r.stdout)
assert result["state"]=="PASS" and result["skips"]==[] and result["host_uid"]==2000
assert result["installer_sha256"]==hashlib.sha256((ev/"linux-installer-atomic-candidate.sh").read_bytes()).hexdigest()
(ev/"wrapper-atomic-real-fs-uid2000.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"state":"PASS","scope":result["scope"],"checks":result["checks"],"skips":result["skips"],"host_uid":result["host_uid"],"installer_sha256":result["installer_sha256"],"evidence":str(ev/"wrapper-atomic-real-fs-uid2000.json"),"agent_or_installer_executed":False,"baseline_mutated":False}))
