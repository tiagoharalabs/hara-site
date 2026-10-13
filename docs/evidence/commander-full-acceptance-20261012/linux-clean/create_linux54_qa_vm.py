#!/usr/bin/env python3
"""Create only the new isolated Linux54 QA domain from the verified official image."""
from pathlib import Path
import grp,hashlib,json,os,pwd,shutil,subprocess,uuid
NAME="commander-linux54-clean-20261013";HOST="commander-linux-clean54"
BASE=Path("/tmp_hara/commander-linux-clean-20261012/base/noble-server-cloudimg-amd64.img")
PRIVATE=Path("/tmp_hara/commander-linux54-clean-20261013")
STORAGE=Path("/var/lib/libvirt/images")/NAME
SHA="6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2"
def run(args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,**kw).stdout
if os.geteuid()!=0:raise RuntimeError("QA_VM_CREATE_ROOT_REQUIRED")
if run(["hostname"]).strip()!="nucleo-a":raise RuntimeError("QA_HYPERVISOR_SCOPE_REQUIRED")
if NAME in run(["virsh","-c","qemu:///system","list","--all","--name"]).splitlines():raise RuntimeError("QA_NEW_VM_ALREADY_EXISTS")
if STORAGE.exists() or PRIVATE.exists():raise RuntimeError("QA_NEW_PATH_ALREADY_EXISTS")
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=SHA:raise RuntimeError("QA_OFFICIAL_IMAGE_PIN_FAILED")
if shutil.disk_usage(STORAGE.parent).free<15*1024**3:raise RuntimeError("QA_VM_DISK_BUDGET_REQUIRED")
sartorius=pwd.getpwnam("sartorius");qemu=pwd.getpwnam("libvirt-qemu")
PRIVATE.mkdir(mode=0o700);os.chown(PRIVATE,sartorius.pw_uid,sartorius.pw_gid)
key=PRIVATE/"qa_ed25519"
run(["sudo","-u","sartorius","ssh-keygen","-q","-t","ed25519","-N","","-C","commander-linux54-QA-only","-f",str(key)])
pub=key.with_suffix(".pub").read_text().strip()
domain_uuid=str(uuid.uuid4());mac="52:54:00:"+":".join("%02x"%b for b in os.urandom(3))
seed=PRIVATE/"seed";seed.mkdir(mode=0o700)
userdata="""#cloud-config
hostname: commander-linux-clean54
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
"""
(seed/"user-data").write_text(userdata);(seed/"meta-data").write_text("instance-id: hara-commander-linux54-"+domain_uuid+"\nlocal-hostname: "+HOST+"\n")
run(["xorriso","-as","mkisofs","-output",str(PRIVATE/"seed.iso"),"-volid","cidata","-joliet","-rock",str(seed)])
STORAGE.mkdir(mode=0o750);os.chown(STORAGE,qemu.pw_uid,qemu.pw_gid)
shutil.copyfile(BASE,STORAGE/"root.qcow2");shutil.copyfile(PRIVATE/"seed.iso",STORAGE/"seed.iso")
for p in STORAGE.iterdir():p.chmod(0o600);os.chown(p,qemu.pw_uid,qemu.pw_gid)
run(["qemu-img","resize",str(STORAGE/"root.qcow2"),"12G"])
xml=f"""<domain type='kvm'>
 <name>{NAME}</name><uuid>{domain_uuid}</uuid>
 <memory unit='MiB'>2048</memory><currentMemory unit='MiB'>2048</currentMemory><vcpu>2</vcpu>
 <os><type arch='x86_64' machine='pc-i440fx-noble-v2'>hvm</type><boot dev='hd'/></os>
 <features><acpi/><apic/></features><cpu mode='host-passthrough'/>
 <clock offset='utc'/><on_poweroff>destroy</on_poweroff><on_reboot>restart</on_reboot><on_crash>destroy</on_crash>
 <devices><emulator>/usr/bin/qemu-system-x86_64</emulator>
 <disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='{STORAGE}/root.qcow2'/><target dev='vda' bus='virtio'/></disk>
 <disk type='file' device='cdrom'><driver name='qemu' type='raw'/><source file='{STORAGE}/seed.iso'/><target dev='hda' bus='ide'/><readonly/></disk>
 <interface type='network'><mac address='{mac}'/><source network='default'/><model type='virtio'/></interface>
 <serial type='pty'><target port='0'/></serial><console type='pty'><target type='serial' port='0'/></console>
 <memballoon model='virtio'/>
 </devices>
</domain>"""
(PRIVATE/"domain.xml").write_text(xml)
run(["virsh","-c","qemu:///system","define",str(PRIVATE/"domain.xml")])
run(["virsh","-c","qemu:///system","autostart",NAME,"--disable"])
run(["virsh","-c","qemu:///system","start",NAME])
report={"state":"PASS_NEW_ISOLATED_VM_STARTED_PENDING_CLOUD_INIT","name":NAME,"uuid":domain_uuid,"hostname":HOST,"mac":mac,"source_image_sha256":SHA,"source_image_bytes":625612288,"autostart":False,"vcpus":2,"ram_mib":2048,"disk_gib":12,"user":"commanderqa","uid":2000,"qa_private_path":str(PRIVATE),"root_storage":str(STORAGE),"prior_VM53_touched":False,"founder_workloads_touched":False}
(PRIVATE/"creation.json").write_text(json.dumps(report,indent=2)+"\n");os.chown(PRIVATE/"creation.json",sartorius.pw_uid,sartorius.pw_gid)
print(json.dumps(report))
