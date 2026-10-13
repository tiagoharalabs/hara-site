#!/usr/bin/env python3
"""Real filesystem tests for the exact wrapper helper embedded in the installer."""
import argparse,contextlib,errno,hashlib,io,json,os,stat,subprocess,tempfile,time
from unittest import mock
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--installer",type=Path,required=True);a=p.parse_args()
source=a.installer.read_text()
program=source.split("<<'PYHARAWRAPPER'\n",1)[1].split("\nPYHARAWRAPPER",1)[0]
scope={"__name__":"installer_wrapper_test"};exec(compile(program,"installer-wrapper-helper","exec"),scope)
checks=[];skips=[]
manage=scope["manage"];legacy=scope["LEGACY_BODY"];managed=scope["MANAGED_BODY"]
def call(mode,path,preimages,external=False):
 with contextlib.redirect_stdout(io.StringIO()):return manage(mode,path,preimages,external)
def check(name,ok):
 assert ok,name
 checks.append(name)
def fresh(root):
 root.mkdir(mode=0o700);(root/"bin").mkdir(mode=0o700);(root/"data").mkdir(mode=0o700)
 return root/"bin/hara",root/"data/installer-preimages"
with tempfile.TemporaryDirectory(prefix="hara-wrapper-real-fs-") as directory:
 root=Path(directory)
 w,pre=fresh(root/"fresh")
 check("fresh-owned-file-created",call("install",w,pre)=="FRESH_CREATED" and w.read_bytes()==managed and stat.S_IMODE(w.stat().st_mode)==0o700 and w.stat().st_uid==os.getuid())
 inode=w.stat().st_ino
 check("managed-repeat-preserves-identity",call("install",w,pre)=="ALREADY_MANAGED" and w.stat().st_ino==inode)
 check("managed-uninstall-removes-only-owned-wrapper",call("uninstall",w,pre)=="MANAGED_REMOVED" and not w.exists())
 w,pre=fresh(root/"legacy")
 w.write_bytes(legacy);w.chmod(0o700);legacy_inode=w.stat().st_ino
 check("legacy-content-pin-is-immutable-043",hashlib.sha256(w.read_bytes()).hexdigest()==scope["LEGACY_SHA256"])
 check("legacy-migrates-to-current-owned-marker",call("install",w,pre)=="LEGACY_MIGRATED" and w.read_bytes()==managed)
 snapshot=pre/("hara-wrapper-"+scope["LEGACY_SHA256"]+".preimage")
 check("legacy-preimage-is-displaced-actual-inode",snapshot.stat().st_ino==legacy_inode)
 check("legacy-preimage-preserves-exact-bytes-and-mode",snapshot.read_bytes()==legacy and stat.S_IMODE(snapshot.stat().st_mode)==0o600 and snapshot.stat().st_uid==os.getuid())
 metadata=json.loads(snapshot.with_suffix(".json").read_text())
 check("legacy-preimage-metadata-binds-owner-and-marker",metadata["owner_uid"]==os.getuid() and metadata["preimage_sha256"]==scope["LEGACY_SHA256"] and metadata["target_sha256"]==scope["MANAGED_SHA256"])
 check("migrated-wrapper-uninstall-removes-it",call("uninstall",w,pre)=="MANAGED_REMOVED" and not w.exists())
 w,pre=fresh(root/"legacy-direct-uninstall")
 w.write_bytes(legacy);w.chmod(0o700)
 check("legacy-direct-uninstall-exact-hash-removed",call("uninstall",w,pre)=="LEGACY_REMOVED" and not w.exists())
 for label,body in (("unrelated",b"#!/bin/sh\necho unrelated\n"),("marker-only-unrelated",b"# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\necho unrelated\n"),("modified-legacy",legacy+b"# personal change\n"),("modified-managed",managed+b"# personal change\n")):
  w,pre=fresh(root/label);w.write_bytes(body);w.chmod(0o600);before=w.lstat()
  check(label+"-preserved-install",call("install",w,pre)=="PRESERVED_UNRELATED" and w.read_bytes()==body and w.lstat().st_ino==before.st_ino)
  check(label+"-preserved-uninstall",call("uninstall",w,pre)=="PRESERVED_UNRELATED" and w.read_bytes()==body and stat.S_IMODE(w.stat().st_mode)==0o600)
 for label,exists in (("symlink-existing",True),("symlink-dangling",False)):
  w,pre=fresh(root/label);outside=root/(label+"-outside")
  if exists:outside.write_bytes(b"untouched target\n")
  w.symlink_to(outside)
  for mode in ("install","uninstall"):
   check(label+"-"+mode+"-not-followed",call(mode,w,pre)=="PRESERVED_SYMLINK" and w.is_symlink() and (outside.read_bytes()==b"untouched target\n" if exists else not outside.exists()))
 w,pre=fresh(root/"directory");w.mkdir()
 check("directory-leaf-preserved",call("install",w,pre)=="PRESERVED_NONREGULAR" and call("uninstall",w,pre)=="PRESERVED_NONREGULAR" and w.is_dir())
 w,pre=fresh(root/"fifo");os.mkfifo(w,0o600)
 check("FIFO-leaf-refused-without-opening",call("install",w,pre)=="PRESERVED_NONREGULAR" and stat.S_ISFIFO(w.lstat().st_mode))
 w,pre=fresh(root/"global-cli")
 check("global-unrelated-hara-not-shadowed",call("install",w,pre,True)=="PRESERVED_EXTERNAL_COMMAND" and not w.exists())
 w,pre=fresh(root/"preimage-collision");w.write_bytes(legacy);w.chmod(0o700);pre.mkdir(mode=0o700)
 collision=pre/("hara-wrapper-"+scope["LEGACY_SHA256"]+".preimage");collision.write_bytes(b"do not overwrite\n");collision.chmod(0o600)
 try:call("install",w,pre)
 except RuntimeError:pass
 else:raise AssertionError("PREIMAGE_COLLISION_ACCEPTED")
 check("preimage-collision-fails-before-replacing-legacy",w.read_bytes()==legacy and collision.read_bytes()==b"do not overwrite\n")
 # Fault injection remains confined to these private temporary QA fixtures.
 original_rename=scope["rename_noreplace"]
 for mode in ("install","uninstall"):
  for replacement in ("file","symlink"):
   label="swap-before-capture-"+mode+"-"+replacement
   w,pre=fresh(root/label);w.write_bytes(legacy);w.chmod(0o700)
   old_inode=w.stat().st_ino;saved=w.parent/"old-private-fixture";outside=w.parent/"new-link-target"
   outside.write_bytes(b"new user file contents\n")
   fired=[False]
   def swap_before(sfd,src,tfd,dst):
    if src==w.name and not fired[0]:
     fired[0]=True;w.rename(saved)
     if replacement=="file":w.write_bytes(b"new user file contents\n")
     else:w.symlink_to(outside)
    return original_rename(sfd,src,tfd,dst)
   scope["rename_noreplace"]=swap_before
   try:state=call(mode,w,pre)
   finally:scope["rename_noreplace"]=original_rename
   check(label+"-preserves-both-inodes",state=="PRESERVED_RACED" and saved.stat().st_ino==old_inode and saved.read_bytes()==legacy and (w.read_bytes()==b"new user file contents\n" if replacement=="file" else w.is_symlink() and outside.read_bytes()==b"new user file contents\n"))
 for mode in ("install","uninstall"):
  w,pre=fresh(root/("restore-occupied-"+mode));w.write_bytes(legacy);w.chmod(0o700)
  saved=w.parent/"original-wrapper";fired=[False]
  def occupied_restore(sfd,src,tfd,dst):
   if src==w.name and not fired[0]:
    fired[0]=True;w.rename(saved);w.write_bytes(b"displaced concurrent file\n")
    original_rename(sfd,src,tfd,dst)
    w.write_bytes(b"newest user pathname\n")
    return
   return original_rename(sfd,src,tfd,dst)
  scope["rename_noreplace"]=occupied_restore
  try:state=call(mode,w,pre)
  finally:scope["rename_noreplace"]=original_rename
  retained=list(w.parent.glob(".hara-cli-wrapper-displaced-*"))
  check("restore-occupied-"+mode+"-preserves-all-three-files",state=="PRESERVED_RACED_DISPLACED" and saved.read_bytes()==legacy and w.read_bytes()==b"newest user pathname\n" and len(retained)==1 and retained[0].read_bytes()==b"displaced concurrent file\n")
  # The retained raced inode is outside the install data deletion scope.
  check("restore-occupied-"+mode+"-retention-outside-owned-data",not retained[0].is_relative_to(pre.parent))
 for phase in ("capture","preimage"):
  w,pre=fresh(root/("native-noreplace-"+phase));w.write_bytes(legacy);w.chmod(0o700);fired=[False];collision=[None]
  def collision_before(sfd,src,tfd,dst):
   target_capture=src==w.name
   if not fired[0] and (target_capture if phase=="capture" else src.startswith(".hara-cli-wrapper-displaced-")):
    fired[0]=True
    collision[0]=(w.parent if phase=="capture" else pre)/dst
    collision[0].write_bytes(b"must never be overwritten\n")
   return original_rename(sfd,src,tfd,dst)
  scope["rename_noreplace"]=collision_before
  try:
   try:call("install",w,pre)
   except OSError as error:check("native-"+phase+"-NOREPLACE-reports-collision",error.errno==errno.EEXIST)
   else:raise AssertionError("NATIVE_NOREPLACE_COLLISION_ACCEPTED")
  finally:scope["rename_noreplace"]=original_rename
  check("native-"+phase+"-NOREPLACE-preserves-both-files",w.read_bytes()==legacy and collision[0].read_bytes()==b"must never be overwritten\n")
 w,pre=fresh(root/"parent-redirection");w.write_bytes(legacy);w.chmod(0o700)
 anchored=w.parent.with_name("bound-bin");foreign=w.parent.with_name("foreign-bin");foreign.mkdir(mode=0o700);(foreign/"hara").write_bytes(b"foreign directory must remain unchanged\n");fired=[False]
 def redirect_parent(sfd,src,tfd,dst):
  if src==w.name and not fired[0]:
   fired[0]=True;w.parent.rename(anchored);w.parent.symlink_to(foreign,target_is_directory=True)
  return original_rename(sfd,src,tfd,dst)
 scope["rename_noreplace"]=redirect_parent
 try:state=call("install",w,pre)
 finally:scope["rename_noreplace"]=original_rename
 check("dirfd-remains-bound-after-parent-rename-and-symlink",state=="LEGACY_MIGRATED" and (anchored/"hara").read_bytes()==managed and (foreign/"hara").read_bytes()==b"foreign directory must remain unchanged\n" and w.parent.is_symlink())
 w,pre=fresh(root/"parent-already-symlink");w.parent.rename(w.parent.with_name("real-bin"));w.parent.symlink_to(w.parent.with_name("real-bin"),target_is_directory=True)
 check("directory-symlink-refused-before-write",call("install",w,pre)=="PRESERVED_PARENT_UNSAFE" and not w.exists())
 original_publish=scope["new_wrapper_at"]
 for mode in ("fresh","legacy"):
  w,pre=fresh(root/("publish-occupied-"+mode))
  if mode=="legacy":w.write_bytes(legacy);w.chmod(0o700)
  def publish_with_new_target(wfd,name):
   w.write_bytes(b"new user target before atomic publication\n")
   return original_publish(wfd,name)
  scope["new_wrapper_at"]=publish_with_new_target
  try:state=call("install",w,pre)
  finally:scope["new_wrapper_at"]=original_publish
  check("atomic-publish-"+mode+"-never-clobbers-new-target",state==("PRESERVED_RACED" if mode=="fresh" else "PRESERVED_RACED_TARGET") and w.read_bytes()==b"new user target before atomic publication\n")
  if mode=="legacy":check("atomic-publish-legacy-retains-actual-old-inode",next(pre.glob("*.preimage")).read_bytes()==legacy)
 w,pre=fresh(root/"writer-descriptor");w.write_bytes(legacy);w.chmod(0o700)
 with w.open("r+b") as retained_writer:
  old_inode=os.fstat(retained_writer.fileno()).st_ino
  check("legacy-migration-commits-real-inode",call("install",w,pre)=="LEGACY_MIGRATED" and next(pre.glob("*.preimage")).stat().st_ino==old_inode)
  retained_writer.seek(0);retained_writer.write(b"preserved open writer\n");retained_writer.flush()
  check("retained-preimage-keeps-actual-inode-writer-data",next(pre.glob("*.preimage")).read_bytes().startswith(b"preserved open writer\n") and w.read_bytes()==managed)
 for replacement in ("fifo","symlink"):
  w,pre=fresh(root/("swap-between-stat-open-"+replacement));w.write_bytes(legacy);w.chmod(0o700)
  saved=w.parent/"reviewed-old";outside=w.parent/"unrelated-target";outside.write_bytes(b"unrelated safe contents\n");fired=[False];real_open=os.open
  def swap_open(name,flags,*args,**kwargs):
   if name==w.name and flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK and not fired[0]:
    fired[0]=True;w.rename(saved)
    if replacement=="fifo":os.mkfifo(w,0o600)
    else:w.symlink_to(outside)
   return real_open(name,flags,*args,**kwargs)
  started=time.monotonic()
  with mock.patch.object(os,"open",swap_open):state=call("install",w,pre)
  check("stat-open-"+replacement+"-race-is-bounded-and-preserves-data",state=="PRESERVED_RACED" and time.monotonic()-started<1 and saved.read_bytes()==legacy and outside.read_bytes()==b"unrelated safe contents\n" and (stat.S_ISFIFO(w.lstat().st_mode) if replacement=="fifo" else w.is_symlink()))
 check("helper-has-no-path-replace-or-unlink-final-leaf","os.replace(" not in program and "os.unlink(" not in program and "renameat2" in program and "os.O_TMPFILE" in program)
 w,pre=fresh(root/"hardlink");w.write_bytes(legacy);w.chmod(0o700);other=w.parent/"unrelated-hardlink";os.link(w,other)
 check("hardlinked-legacy-preserved-without-changing-other-path-mode",call("install",w,pre)=="PRESERVED_HARDLINK" and call("uninstall",w,pre)=="PRESERVED_HARDLINK" and w.stat().st_ino==other.stat().st_ino and stat.S_IMODE(other.stat().st_mode)==0o700 and other.read_bytes()==legacy)
 w,pre=fresh(root/"shared-parent");w.write_bytes(legacy);w.chmod(0o700);w.parent.chmod(0o777)
 check("shared-writable-wrapper-parent-preserved",call("install",w,pre)=="PRESERVED_PARENT_UNSAFE" and w.read_bytes()==legacy)
 for label,legacy_initial in (("fresh",False),("legacy",True)):
  w,pre=fresh(root/("owner-masking-umask-"+label));pre.mkdir(mode=0o700)
  if legacy_initial:w.write_bytes(legacy);w.chmod(0o700)
  previous_umask=os.umask(0o777)
  try:state=call("install",w,pre)
  finally:os.umask(previous_umask)
  check("custom-umask-"+label+"-still-creates-executable-owned-wrapper",state==("LEGACY_MIGRATED" if legacy_initial else "FRESH_CREATED") and w.read_bytes()==managed and stat.S_IMODE(w.stat().st_mode)==0o700)
  if legacy_initial:check("custom-umask-metadata-is-private-readable",stat.S_IMODE(next(pre.glob("*.json")).stat().st_mode)==0o600)
 for failure in ("publish","metadata"):
  w,pre=fresh(root/("downstream-failure-"+failure));w.write_bytes(legacy);w.chmod(0o700);old_inode=w.stat().st_ino
  key="new_wrapper_at" if failure=="publish" else "write_new_file_at";original=scope[key]
  def downstream_failure(*args,**kwargs):
   if failure=="publish" or args[1].endswith(".json"):raise OSError(errno.ENOSPC,"private fixture injected failure")
   return original(*args,**kwargs)
  scope[key]=downstream_failure
  try:
   try:call("install",w,pre)
   except OSError:pass
   else:raise AssertionError("DOWNSTREAM_FAULT_NOT_REPORTED")
  finally:scope[key]=original
  check("downstream-"+failure+"-failure-restores-original-inode-and-mode",w.stat().st_ino==old_inode and w.read_bytes()==legacy and stat.S_IMODE(w.stat().st_mode)==0o700)
 w,pre=fresh(root/"failed-publish-new-target");w.write_bytes(legacy);w.chmod(0o700);old_inode=w.stat().st_ino
 def failed_publish_with_new_target(*args,**kwargs):
  w.write_bytes(b"concurrent final pathname preserved\n")
  raise OSError(errno.ENOSPC,"private fixture injected publication error")
 scope["new_wrapper_at"]=failed_publish_with_new_target
 try:
  try:call("install",w,pre)
  except OSError:pass
  else:raise AssertionError("PUBLICATION_FAULT_NOT_REPORTED")
 finally:scope["new_wrapper_at"]=original_publish
 check("failed-publication-never-restores-over-new-target",w.read_bytes()==b"concurrent final pathname preserved\n" and next(pre.glob("*.preimage")).stat().st_ino==old_inode and next(pre.glob("*.preimage")).read_bytes()==legacy)
 if Path("/dev/shm").is_dir():
  with tempfile.TemporaryDirectory(prefix="hara-private-cross-filesystem-",dir="/dev/shm") as cross_directory:
   cross_root=Path(cross_directory);cross_root.chmod(0o700)
   w,unused=fresh(root/"cross-filesystem");w.write_bytes(legacy);w.chmod(0o700);old_inode=w.stat().st_ino
   if w.stat().st_dev!=cross_root.stat().st_dev:
    try:call("install",w,cross_root/"installer-preimages")
    except RuntimeError as error:check("cross-filesystem-refused-explicitly",str(error)=="CLI_WRAPPER_CROSS_FILESYSTEM_UNSUPPORTED")
    else:raise AssertionError("CROSS_FILESYSTEM_ACCEPTED")
    check("cross-filesystem-refused-before-capture",w.stat().st_ino==old_inode and w.read_bytes()==legacy and not list(w.parent.glob(".hara-cli-wrapper-displaced-*")))
   else:skips.append("separate-real-filesystem-unavailable")
 else:skips.append("separate-real-filesystem-unavailable")
 original_read=scope["read_owned_regular_at"]
 for occupied in (False,True):
  w,pre=fresh(root/("post-capture-read-error-"+str(occupied)));w.write_bytes(legacy);w.chmod(0o700);old_inode=w.stat().st_ino
  def captured_read_error(dfd,name):
   if name.startswith(".hara-cli-wrapper-displaced-"):
    if occupied:w.write_bytes(b"new pathname during read failure\n")
    raise OSError(errno.EIO,"private fixture injected captured read failure")
   return original_read(dfd,name)
  scope["read_owned_regular_at"]=captured_read_error
  out=io.StringIO()
  try:
   try:
    with contextlib.redirect_stdout(out):manage("install",w,pre)
   except OSError as error:assert error.errno==errno.EIO
   else:raise AssertionError("CAPTURED_READ_FAULT_NOT_REPORTED")
  finally:scope["read_owned_regular_at"]=original_read
  if not occupied:
   check("post-capture-read-error-restores-original-inode",w.stat().st_ino==old_inode and w.read_bytes()==legacy)
  else:
   retained=list(w.parent.glob(".hara-cli-wrapper-displaced-*"))
   check("post-capture-read-error-preserves-new-target-and-reports-retained-inode",w.read_bytes()==b"new pathname during read failure\n" and len(retained)==1 and retained[0].stat().st_ino==old_inode and retained[0].read_bytes()==legacy and retained[0].name in out.getvalue())
 w,pre=fresh(root/"foreign-owner");w.write_bytes(legacy);w.chmod(0o600)
 if os.getuid()!=0 and subprocess.run(["sudo","-n","chown","0:0",str(w)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
  check("foreign-UID-file-preserved-before-content-read",call("install",w,pre)=="PRESERVED_UNOWNED" and call("uninstall",w,pre)=="PRESERVED_UNOWNED" and w.lstat().st_uid==0)
 else:skips.append("foreign-UID-real-chown-unavailable")
check("declared-enrollment-and-control-plane-metadata-is-053",source.count('"agent_version":"0.3.53"')==2 and source.count('"agent_version": "0.3.53"')==1 and '"agent_version":"0.3.43"' not in source and '"agent_version": "0.3.43"' not in source)
print(json.dumps({"schema":"hara.commander-wrapper-real-filesystem-tests.v1","state":"PASS","scope":"UNIT_REAL_FS_NOT_EXTERNAL_ACCEPTANCE","checks":len(checks),"scenarios":checks,"skips":skips,"host_uid":os.getuid(),"installer_sha256":hashlib.sha256(a.installer.read_bytes()).hexdigest(),"network_operations":0,"backend_mock_used":False,"systemctl_shim_used":False}))