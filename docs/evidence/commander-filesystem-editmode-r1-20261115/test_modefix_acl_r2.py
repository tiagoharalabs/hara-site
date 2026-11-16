#!/usr/bin/env python3
"""POSIX ACL preservation regression for isolated H.A.R.A. Commander candidate R2."""
import os,stat,hashlib,json,tempfile,subprocess,runpy
from pathlib import Path
ROOT=Path(os.environ.get("HARA_MODEFIX_SOURCE_DIR","/home/sartorius/hara-commander-modefix-20261115"))
with tempfile.TemporaryDirectory(prefix="qa-r2-acl-",dir=ROOT) as tmp:
 d=Path(tmp);os.environ["XDG_DATA_HOME"]=str(d/"data");os.environ["XDG_CONFIG_HOME"]=str(d/"config")
 p=d/"script.sh";p.write_text("old");p.chmod(0o750)
 uid=65534 if os.geteuid()==0 else 1000
 s=subprocess.run(["setfacl","-m",f"u:{uid}:r--",str(p)],capture_output=True,text=True)
 assert s.returncode==0,("SETFACL_FAILED",s.returncode,s.stderr[-160:])
 def capture():
  return {"acl":subprocess.check_output(["getfacl","-cp",str(p)],text=True),
          "xattr":os.getxattr(p,"system.posix_acl_access"),
          "mode":stat.S_IMODE(p.stat().st_mode),
          "uid":p.stat().st_uid,"gid":p.stat().st_gid,
          "bytes":p.read_bytes()}
 before=capture()
 agent=runpy.run_path(str(ROOT/"agent.candidate.r2.py"),run_name="acl_r2_candidate")
 receipt=agent["filesystem_edit"]({"call_id":"acl-r2-isolated"},str(p),"old","new",False,hashlib.sha256(b"old").hexdigest())
 after=capture()
 assert after["bytes"]==b"new" and before["bytes"]==b"old"
 for key in ("acl","xattr","mode","uid","gid"): assert before[key]==after[key],key
 assert receipt["xattrs_preserved"] and receipt["xattr_count"]>=1
 meta,data=agent["_load_preimage"](receipt["preimage_id"])
 assert meta["mode"]==before["mode"] and data==b"old"
 print(json.dumps({"state":"PASS_POSIX_ACL_EXACT","uid":os.geteuid(),"acl_identity_uid":uid,
 "mode":oct(before["mode"]),"xattr_count":receipt["xattr_count"],
 "acl_sha256":hashlib.sha256(before["acl"].encode()).hexdigest(),
 "acl_xattr_sha256":hashlib.sha256(before["xattr"]).hexdigest()}))
