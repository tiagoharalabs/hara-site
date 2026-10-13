#!/usr/bin/env python3
"""Create only the owned capacity1000 VM; run on nucleo-a as root via authorized SSH."""
from pathlib import Path
import hashlib,json,os,pwd,shutil,subprocess,uuid,time
from datetime import datetime,timezone
NAME="commander-capacity1000-20261013"
HOST="commander-capacity1000"
BASE=Path("/tmp_hara/commander-linux-clean-20261012/base/noble-server-cloudimg-amd64.img")
PRIVATE=Path("/tmp_hara/commander-capacity1000-20261013")
STORAGE=Path("/var/lib/libvirt/images")/NAME
SHA="6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2"
GIB=1024**3
def require(value,code):
 if not value:raise RuntimeError(code)
def run(args,**kw):
 p=subprocess.run(args,capture_output=True,text=True,timeout=kw.pop("timeout",120),**kw)
 require(p.returncode==0,"CAPACITY_VM_"+Path(args[0]).name.upper().replace("-","_")+"_FAILED")
 return p.stdout
def memory_available():
 return int(next(l.split()[1] for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemAvailable:")))*1024
def preflight():
 observed=time.time();available=memory_available()
 require(available>=76*GIB,"CAPACITY_VM_HOST_MEMORY_FLOOR")
 require(os.cpu_count()>=12 and os.getloadavg()[0]<os.cpu_count()*.65,"CAPACITY_VM_HOST_CPU_FLOOR")
 require(shutil.disk_usage(STORAGE.parent).free>=32*GIB,"CAPACITY_VM_HOST_DISK_FLOOR")
 cg=Path("/sys/fs/cgroup/cgroup.controllers")
 require(cg.is_file() and {"cpu","memory","pids"}<=set(cg.read_text().split()),"CAPACITY_VM_CGROUP_REQUIRED")
 return {"at_unix":observed,"memory_available_bytes":available,"nominal_vm_bytes":60*GIB,"required_remaining_bytes":16*GIB}
def write(path,value,uid,gid,mode=0o600):
 path.write_text(value);path.chmod(mode);os.chown(path,uid,gid)
def main():
 require(os.geteuid()==0,"CAPACITY_VM_CREATE_ROOT_REQUIRED")
 require(run(["hostname"]).strip()=="nucleo-a","CAPACITY_VM_HYPERVISOR_SCOPE")
 require(NAME not in run(["virsh","-c","qemu:///system","list","--all","--name"]).splitlines(),"CAPACITY_VM_ALREADY_EXISTS")
 require(not STORAGE.exists() and not PRIVATE.exists(),"CAPACITY_VM_PATH_ALREADY_EXISTS")
 first=preflight()
 require(BASE.stat().st_size==625612288 and hashlib.sha256(BASE.read_bytes()).hexdigest()==SHA,"CAPACITY_VM_OFFICIAL_IMAGE_PIN")
 info=json.loads(run(["qemu-img","info","--output=json",str(BASE)]))
 require(info["format"]=="qcow2" and not info.get("backing-filename"),"CAPACITY_VM_STANDALONE_BASE_REQUIRED")
 sartorius=pwd.getpwnam("sartorius");qemu=pwd.getpwnam("libvirt-qemu")
 PRIVATE.mkdir(mode=0o700);os.chown(PRIVATE,sartorius.pw_uid,sartorius.pw_gid)
 key=PRIVATE/"qa_ed25519"
 run(["sudo","-u","sartorius","ssh-keygen","-q","-t","ed25519","-N","","-C","commander-capacity1000-QA-only","-f",str(key)])
 pub=key.with_suffix(".pub").read_text().strip()
 domain_uuid=str(uuid.uuid4());mac="52:54:00:"+":".join("%02x"%b for b in os.urandom(3))
 seed=PRIVATE/"seed";seed.mkdir(mode=0o700)
 userdata="""#cloud-config
hostname: commander-capacity1000
manage_etc_hosts: true
users:
  - name: commanderqa
    uid: 2000
    shell: /bin/bash
    lock_passwd: true
    groups: [adm, sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - """+pub+"""
ssh_pwauth: false
disable_root: true
package_update: false
runcmd:
  - [loginctl, enable-linger, commanderqa]
  - [install, -d, -o, commanderqa, -g, commanderqa, -m, '0700', /home/commanderqa/commander-qa]
  - [sh, -c, 'echo "commanderqa soft nofile 8192" > /etc/security/limits.d/commander-capacity1000.conf']
  - [sh, -c, 'echo "commanderqa hard nofile 8192" >> /etc/security/limits.d/commander-capacity1000.conf']
"""
 write(seed/"user-data",userdata,sartorius.pw_uid,sartorius.pw_gid)
 write(seed/"meta-data","instance-id: hara-commander-capacity1000-"+domain_uuid+"\nlocal-hostname: "+HOST+"\n",sartorius.pw_uid,sartorius.pw_gid)
 run(["xorriso","-as","mkisofs","-output",str(PRIVATE/"seed.iso"),"-volid","cidata","-joliet","-rock",str(seed)])
 STORAGE.mkdir(mode=0o750);os.chown(STORAGE,qemu.pw_uid,qemu.pw_gid)
 run(["qemu-img","convert","-O","qcow2",str(BASE),str(STORAGE/"root.qcow2")])
 require(not json.loads(run(["qemu-img","info","--output=json",str(STORAGE/"root.qcow2")])).get("backing-filename"),"CAPACITY_VM_DISK_BACKING_FORBIDDEN")
 shutil.copyfile(PRIVATE/"seed.iso",STORAGE/"seed.iso")
 for p in STORAGE.iterdir():p.chmod(0o600);os.chown(p,qemu.pw_uid,qemu.pw_gid)
 run(["qemu-img","resize",str(STORAGE/"root.qcow2"),"24G"])
 xml=f"""<domain type='kvm'>
<name>{NAME}</name><uuid>{domain_uuid}</uuid>
<memory unit='MiB'>61440</memory><currentMemory unit='MiB'>61440</currentMemory><vcpu>8</vcpu>
<memtune><hard_limit unit='MiB'>65536</hard_limit></memtune>
<cputune><global_period>100000</global_period><global_quota>600000</global_quota></cputune>
<os><type arch='x86_64' machine='pc-i440fx-noble-v2'>hvm</type><boot dev='hd'/></os>
<features><acpi/><apic/></features><cpu mode='host-passthrough'/>
<clock offset='utc'/><on_poweroff>destroy</on_poweroff><on_reboot>restart</on_reboot><on_crash>destroy</on_crash>
<devices><emulator>/usr/bin/qemu-system-x86_64</emulator>
<disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='{STORAGE}/root.qcow2'/><target dev='vda' bus='virtio'/></disk>
<disk type='file' device='cdrom'><driver name='qemu' type='raw'/><source file='{STORAGE}/seed.iso'/><target dev='hda' bus='ide'/><readonly/></disk>
<interface type='network'><mac address='{mac}'/><source network='default'/><model type='virtio'/></interface>
<serial type='pty'><target port='0'/></serial><console type='pty'><target type='serial' port='0'/></console>
<memballoon model='virtio'/>
</devices></domain>"""
 write(PRIVATE/"domain.xml",xml,sartorius.pw_uid,sartorius.pw_gid)
 fresh=preflight();require(time.time()-fresh["at_unix"]<=120,"CAPACITY_VM_PREFLIGHT_STALE")
 run(["virsh","-c","qemu:///system","define",str(PRIVATE/"domain.xml")])
 run(["virsh","-c","qemu:///system","autostart",NAME,"--disable"])
 run(["virsh","-c","qemu:///system","start",NAME])
 report={"state":"PASS_OWN_VM_STARTED_CLOUD_INIT_PENDING","at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
  "name":NAME,"uuid":domain_uuid,"hostname":HOST,"mac":mac,"source_image_sha256":SHA,"source_image_bytes":625612288,
  "autostart":False,"vcpus":8,"ram_mib":61440,"disk_gib":24,"user":"commanderqa","uid":2000,
  "private_path":str(PRIVATE),"root_storage":str(STORAGE),"resource_preflight_initial":first,
  "resource_preflight_immediately_before_define":fresh,"other_domains_touched":False,"actual_agent_count":0}
 write(PRIVATE/"creation.json",json.dumps(report,indent=2)+"\n",sartorius.pw_uid,sartorius.pw_gid)
 print(json.dumps(report,sort_keys=True))
if __name__=="__main__":
 try:main()
 except Exception as e:
  print(json.dumps({"state":"FAIL","safe_code":str(e) if isinstance(e,RuntimeError) else type(e).__name__,
                   "own_domain_only":True,"unclaimed_success":False}));raise SystemExit(1)
