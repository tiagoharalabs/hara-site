from pathlib import Path
import importlib.util,json,subprocess,inspect,hashlib,os,xml.etree.ElementTree as ET
from datetime import datetime,timezone
root=Path("/tmp_hara/commander-win50-utf8-20261012")
private=Path("/tmp_hara/commander-capacity1000-20261013/private")
config=private/"ssh_config"
text="""Host cap1000
  HostName 192.168.122.108
  User commanderqa
  IdentityFile /tmp_hara/commander-capacity1000-20261013/private/qa_ed25519
  IdentitiesOnly yes
  ProxyJump nucleo-a
  UserKnownHostsFile /tmp_hara/commander-capacity1000-20261013/private/known_hosts
  StrictHostKeyChecking yes
  BatchMode yes
  ConnectTimeout 8
  ServerAliveInterval 15
  ServerAliveCountMax 2
  ControlMaster no
Host *
  Include /home/sartorius/.ssh/config
"""
fd=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,"w") as h:h.write(text)
def call(args,stdin=None,timeout=30):
 p=subprocess.run(args,input=stdin,text=True,capture_output=True,timeout=timeout)
 assert p.returncode==0,"CAPACITY_VM_PREP_"+Path(args[0]).name.upper()+"_FAILED"
 return p.stdout
raw=call(["ssh","-o","BatchMode=yes","nucleo-a","sudo","-n","virsh","-c","qemu:///system","dumpxml","commander-capacity1000-20261013"])
xml=ET.fromstring(raw)
assert xml.findtext("uuid")=="c8bcefb4-3f25-41b0-a07a-58c0d7956662"
for name in ("memory","currentMemory"):
 node=xml.find(name);assert node.attrib["unit"]=="KiB" and int(node.text)==61440*1024
assert xml.findtext("vcpu")=="8"
nominal=61440*1024**2
script=root/"apps/commander/scripts/commander_real_1000_capacity_plan.py"
spec=importlib.util.spec_from_file_location("capacity_vm_preflight",script)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
guestcode="import json,os,resource,time\nfrom pathlib import Path\nfrom datetime import datetime,timezone\n"+inspect.getsource(m.require)+"\n"+inspect.getsource(m.local_resources)+"""
require(os.getuid()==2000 and os.uname().nodename=="commander-capacity1000","CAPACITY_OWN_GUEST")
base=Path("/home/commanderqa/hara-capacity1000")
base.mkdir(mode=0o700,exist_ok=False)
print(json.dumps(local_resources("Guest"),sort_keys=True))
"""
guest=json.loads(call(["ssh","-F",str(config),"cap1000","python3","-"],guestcode))
guest["nominal_vm_memory_bytes"]=nominal;guest["libvirt_nominal_memory_verified"]=True
guest["bound_domain_uuid"]="c8bcefb4-3f25-41b0-a07a-58c0d7956662"
verdict=m.guest_stage_preflight(guest,100)
e=root/"docs/evidence/commander-full-acceptance-20261012/capacity-1000"
report={"schema":"hara.commander-real1000-guest-preflight.v1","state":"PASS_NATIVE_GUEST_STAGE100_RESOURCE_ONLY",
 "at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"resource_snapshot":guest,
 "libvirt_memory_pin":{"uuid":guest["bound_domain_uuid"],"memory_kib":61440*1024,
 "current_memory_kib":61440*1024,"vcpus":8,"xml_sha256":hashlib.sha256(raw.encode()).hexdigest()},
 "resource_verdict":verdict,"private_ssh_config":str(config),"manager_base":"/home/commanderqa/hara-capacity1000",
 "agent_count":0,"tenant_count":0}
(e/"owned-vm-native-preflight.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
p=e/"preparation-regression.json";x=json.loads(p.read_text());x["native_review_history"]={"prior_checks":70,"prior_source_sha256":x["source_sha256"]};x["tests"]["checks"]=72;x["source_sha256"]={"planner":hashlib.sha256(script.read_bytes()).hexdigest(),"test":hashlib.sha256((root/"apps/commander/scripts/test_real_1000_capacity_plan.py").read_bytes()).hexdigest()};x["review_fixes"]["guest_kernel_reserved_memory_max_bytes"]=1536*1024**2;x["review_fixes"]["paired_libvirt_nominal_memory_pin_required"]=True;x["guest_preflight"]="PASS_NATIVE_STAGE100_RESOURCE_ONLY";x["review_at_utc"]=report["at_utc"];p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
p=e/"README.md";s=p.read_text().replace("70 checks","72 checks").replace("70checks","72checks");s=s.replace("Esta preparação não criou VM, fixture, conexão ou chamada de produto.","O plano foi preparado sem carga. Depois da revisão, criou-se uma VM própria60GiB/8CPU/24GiB, com cloud-init/SSH/user-systemd e preflight nativos aprovados; ainda0Agents/0tenants.");p.write_text(s)
print(json.dumps(report,sort_keys=True))
