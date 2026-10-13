#!/usr/bin/env python3
"""Teardown only the exact completed and uninstalled Linux54 QA VM."""
import json,subprocess
from pathlib import Path
E=Path("/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/linux-clean/linux54")
v=json.loads((E/"fresh-uninstall-054-r2.json").read_text())
if not(str(v["state"]).startswith("PASS") and all(v["cleanup_checks"].values())):raise RuntimeError("NATIVE54_UNINSTALL_NOT_COMPLETE")
code="""import json,os,stat,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
N='commander-linux54-clean-20261013';U='f1fc631b-9442-468a-82dc-e99d021ea8f5'
I=Path('/var/lib/libvirt/images')/N;P=Path('/tmp_hara')/N
def require(ok,code):
 if not ok:raise RuntimeError(code)
def virsh(*args):
 r=subprocess.run(['virsh','-c','qemu:///system',*args],capture_output=True,text=True,timeout=12);require(r.returncode==0,'OWN_QA54_LIBVIRT_ACTION_FAILED');return r.stdout.strip()
require(os.geteuid()==0,'ROOT_SCOPE_REQUIRED')
require(virsh('domuuid',N)==U,'OWN_QA54_UUID_GUARD')
xml=ET.fromstring(virsh('dumpxml',N));require(xml.findtext('name')==N and xml.findtext('uuid')==U,'OWN_QA54_XML_GUARD')
paths=[x.get('file') for x in xml.findall('./devices/disk/source') if x.get('file')]
require(set(paths)=={str(I/'root.qcow2'),str(I/'seed.iso')},'OWN_QA54_DISK_SCOPE_GUARD')
require(not virsh('snapshot-list',N,'--name'),'OWN_QA54_SNAPSHOT_GUARD')
require(not I.is_symlink() and I.is_dir() and not P.is_symlink() and P.is_dir(),'OWN_QA54_DIRECTORY_GUARD')
before=virsh('domstate',N)
if before!='shut off':
 virsh('shutdown',N)
 end=time.monotonic()+35
 while time.monotonic()<end:
  if virsh('domstate',N)=='shut off':break
  time.sleep(.5)
require(virsh('domstate',N)=='shut off','OWN_QA54_GRACEFUL_SHUTDOWN_PENDING')
require(virsh('domuuid',N)==U,'OWN_QA54_FINAL_UUID_GUARD')
virsh('undefine',N)
removed=[];preserved=[]
def own_remove(base,rel):
 p=base/rel
 if not p.exists() and not p.is_symlink():return
 s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:preserved.append(str(p));return
 p.unlink();removed.append(str(p))
for rel in ['root.qcow2','seed.iso']:own_remove(I,rel)
for rel in ['qa_ed25519','qa_ed25519.pub','known_hosts','creation.json','domain.xml','seed.iso','seed/user-data','seed/meta-data']:own_remove(P,rel)
for d in [P/'seed',P,I]:
 try:d.rmdir()
 except OSError:preserved.append(str(d))
check=subprocess.run(['virsh','-c','qemu:///system','domuuid',N],capture_output=True,text=True,timeout=12)
require(check.returncode!=0,'OWN_QA54_DOMAIN_STILL_DEFINED')
print(json.dumps({'schema':'hara.commander-linux054-owned-vm-teardown.v1','state':'PASS_OWNED_QA54_TEARDOWN','VM_name':N,'VM_uuid':U,'graceful_shutdown':True,'domain_undefined':True,'removed_owned_paths':removed,'preserved_unknown_or_nonregular_paths':preserved,'verified_base_image_removed':False,'other_domains_modified':False,'Founder_or_production_modified':False}))
"""
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a","sudo /usr/bin/python3 -I -B -"],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=70)
if r.returncode:raise RuntimeError("OWN_QA54_TEARDOWN_FAILED_OR_PENDING")
report=json.loads(r.stdout);out=E/"owned-vm-teardown.json";out.write_text(json.dumps(report,indent=2)+"\n");print(json.dumps({"state":report["state"],"evidence":str(out),"preserved_unknown_paths":len(report["preserved_unknown_or_nonregular_paths"])}))
