from pathlib import Path
import json,subprocess,os,re,time,shlex
from datetime import datetime,timezone
r=Path("/tmp_hara/commander-win50-utf8-20261012")
own=Path("/tmp_hara/commander-capacity1000-20261013/private");own.mkdir(parents=True,exist_ok=True,mode=0o700)
def call(args,timeout=30):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert p.returncode==0,"CAPACITY_BOOT_"+Path(args[0]).name.upper()+"_FAILED"
 return p.stdout
for leaf in ("qa_ed25519","creation.json"):
 call(["scp","-q","-o","BatchMode=yes","-o","ConnectTimeout=8","nucleo-a:/tmp_hara/commander-capacity1000-20261013/"+leaf,str(own/leaf)])
 (own/leaf).chmod(0o600)
creation=json.loads((own/"creation.json").read_text())
assert creation["name"]=="commander-capacity1000-20261013" and creation["uuid"]=="c8bcefb4-3f25-41b0-a07a-58c0d7956662"
raw=call(["ssh","-o","BatchMode=yes","nucleo-a","sudo","-n","virsh","-c","qemu:///system","domifaddr",creation["name"],"--source","lease","--full"])
mac=creation["mac"];line=next(l for l in raw.splitlines() if mac in l.lower())
ip=re.search(r"192\.168\.122\.[0-9]{1,3}",line).group(0)
host="commanderqa@"+ip
args=["ssh","-J","nucleo-a","-o","BatchMode=yes","-o","ConnectTimeout=8","-o","StrictHostKeyChecking=accept-new","-o","UserKnownHostsFile="+str(own/"known_hosts"),"-i",str(own/"qa_ed25519"),host]
state=call(args+["cloud-init","status","--wait"],timeout=90).strip()
(own/"known_hosts").chmod(0o600)
probe="import json,os,resource;from pathlib import Path;m={l.split()[0].rstrip(':'):int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.split()[0] in ('MemTotal:','MemAvailable:')};print(json.dumps({'hostname':os.uname().nodename,'uid':os.getuid(),'cpu_count':os.cpu_count(),'memory':m,'open_files':resource.getrlimit(resource.RLIMIT_NOFILE),'cgroup_v2':Path('/sys/fs/cgroup/cgroup.controllers').is_file()}))"
metadata=json.loads(call(args+["python3","-c",shlex.quote(probe)]))
systemd=call(args+["systemctl","--user","show","-p","ControlGroup","--value"]).strip()
info=call(["ssh","-o","BatchMode=yes","nucleo-a","sudo","-n","virsh","-c","qemu:///system","dominfo",creation["name"]])
assert "Autostart:      disable" in info or "Autostart:      disabled" in info or re.search(r"Autostart:\s+disable",info)
assert metadata["hostname"]=="commander-capacity1000" and metadata["uid"]==2000 and metadata["cpu_count"]==8 and systemd
report={"schema":"hara.commander-real1000-own-vm-boot.v1","state":"PASS_OWN_VM_BOOT_NO_PRODUCT_AGENTS",
 "at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"creation":creation,"ip":ip,"guest_user":"commanderqa",
 "cloud_init":state,"guest":metadata,"user_systemd_controlgroup_present":bool(systemd),
 "ssh_private_key_path":str(own/"qa_ed25519"),"ssh_known_hosts_path":str(own/"known_hosts"),
 "key_contents_exported":False,"VM_autostart":False,"agent_count":0,"tenant_count":0}
e=r/"docs/evidence/commander-full-acceptance-20261012/capacity-1000"
(e/"owned-vm-creation.json").write_text(json.dumps(creation,indent=2,sort_keys=True)+"\n")
(e/"owned-vm-boot.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps(report,sort_keys=True))
