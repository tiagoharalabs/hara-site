#!/usr/bin/env python3
"""Sign EXACT immutable commercial v5 public assets only in private Services custody.

This is NOT a Cloudflare promotion. No private material is emitted or copied.
The trusted archive and manifest hashes are fixed review inputs; no arbitrary
file or modified release may be signed with this command.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,os,stat,tarfile
from pathlib import Path
from datetime import datetime,timezone
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa
ARCHIVE_SHA="3ade217145e32899da47bedb43272897ee020e44658ae2b197b0eda61880970d"
MANIFEST_SHA="2ec2b3ccddc0fbc5edb577c926315358dbcb558812d3492ec9a68894038ff381"
PUB_FINGERPRINT="93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
KEY=Path.home()/".config/hara-commander-release/v2/release-signing-private.jwk"
REL="apps/commander/public"
FILESET={"agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1"}
def err(s):raise RuntimeError("V5_RELEASE_"+s)
def sha(b:bytes):return hashlib.sha256(b).hexdigest()
def und(s:str):return base64.urlsafe_b64decode(s+"="*((-len(s))%4))
def enc(b:bytes):return base64.urlsafe_b64encode(b).decode().rstrip("=")
def integer(v:str):return int.from_bytes(und(v),"big")
def load(path:Path):return json.loads(path.read_bytes())
def safe_stage(path:Path):
 if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
  err("STAGING_UNSAFE_LOCATION")
 if not str(path).startswith("/tmp_hara/hara-commander-v5-"):
  err("STAGING_LOCATION_NOT_ALLOWED")
def inspect(stage:Path):
 p=stage/REL
 if not p.is_dir():err("FILES_NOT_PREPARED")
 manifest_raw=(p/"release/agent-manifest.json").read_bytes()
 if sha(manifest_raw)!=MANIFEST_SHA:err("MANIFEST_SHA_CHANGED")
 obj=json.loads(manifest_raw)
 if obj.get("agent_version")!="0.3.43" or obj.get("schema")!="hara.commander-agent-release.v1":
  err("MANIFEST_VERSION_CHANGED")
 if {r.get("path") for r in obj.get("files",[])}!=FILESET:err("MANIFEST_FILESET_CHANGED")
 for row in obj["files"]:
  f=p/row["path"]
  if f.is_symlink() or not f.is_file():err("FILE_MISSING_OR_SYMLINK")
  b=f.read_bytes()
  if len(b)!=row["bytes"] or sha(b)!=row["sha256"]:
   err("DIGEST_MISMATCH:"+row["path"])
 pub=load(p/"release/release-signing-public.jwk")
 fingerprint=sha(json.dumps(pub,sort_keys=True,separators=(",",":")).encode())
 if fingerprint!=PUB_FINGERPRINT or pub.get("kid")!="commander-release-v2":
  err("PUBLIC_TRUST_ROOT_MISMATCH")
 if any(k in pub for k in ("d","p","q","dp","dq","qi")):err("PUBLIC_KEY_PRIVATE_FIELDS")
 for rel in ("install/linux.sh","install/windows.ps1"):
  script=(p/rel).read_text()
  if "commander-release-v2" not in script:err("INSTALLER_TRUST_PIN_CHANGED")
 return p,pub,manifest_raw
def prepare(archive:Path,stage:Path):
 safe_stage(stage)
 if stage.exists():err("STAGE_ALREADY_EXISTS")
 if archive.is_symlink() or not archive.is_file() or sha(archive.read_bytes())!=ARCHIVE_SHA:
  err("FROZEN_ARCHIVE_SHA_MISMATCH")
 stage.mkdir(mode=0o700)
 with tarfile.open(archive,'r:gz') as inp:
  members=inp.getmembers()
  if len(members)!=27 or any(m.issym() or m.islnk() or not(m.isfile() or m.isdir()) for m in members):
   err("ARCHIVE_UNEXPECTED_MEMBER")
  inp.extractall(stage,filter="data")
 p,pub,data=inspect(stage)
 if (p/"release/agent-manifest.sig.json").exists():err("UNEXPECTED_SIGNATURE")
 print(json.dumps({"stage":"PREPARED_UNSIGNED","frozen_archive_sha256":ARCHIVE_SHA,
                   "manifest_sha256":sha(data),"file_count":4,"private_key_used":False,
                   "cloud_mutation":False}))
def private_key(pub:dict):
 if not KEY.is_file() or KEY.is_symlink():err("CUSTODIED_KEY_NOT_FOUND")
 s=KEY.stat()
 if stat.S_IMODE(s.st_mode)!=0o600 or s.st_uid!=os.getuid():err("CUSTODY_PERMISSIONS_DENIED")
 v=load(KEY)
 if any(v.get(x)!=pub.get(x) for x in ("n","e","kid")):err("KEYPAIR_MISMATCH")
 if not all(x in v for x in ("d","p","q","dp","dq","qi")):err("PRIVATE_KEY_INCOMPLETE")
 key=rsa.RSAPrivateNumbers(
   p=integer(v["p"]),q=integer(v["q"]),d=integer(v["d"]),
   dmp1=integer(v["dp"]),dmq1=integer(v["dq"]),iqmp=integer(v["qi"]),
   public_numbers=rsa.RSAPublicNumbers(integer(pub["e"]),integer(pub["n"]))
 ).private_key()
 if key.key_size!=3072:err("KEY_SIZE_MISMATCH")
 return key
def verify(stage:Path):
 p,pub,data=inspect(stage)
 s=p/"release/agent-manifest.sig.json"
 if not s.is_file() or s.is_symlink():err("SIGNATURE_MISSING")
 sig=load(s)
 if sig.get("alg")!="RS256" or sig.get("kid")!="commander-release-v2" or sig.get("schema")!="hara.commander-release-signature.v1" or sig.get("manifest_sha256")!=MANIFEST_SHA:
  err("SIGNATURE_METADATA_MISMATCH")
 public=rsa.RSAPublicNumbers(integer(pub["e"]),integer(pub["n"])).public_key()
 if public.key_size!=3072:err("PUBLIC_KEY_SIZE_MISMATCH")
 try:public.verify(und(sig["signature"]),data,padding.PKCS1v15(),hashes.SHA256())
 except Exception:err("SIGNATURE_CRYPTOGRAPHIC_INVALID")
 return {"state":"SIGNED_OFFLINE_VERIFIED","kid":"commander-release-v2",
         "manifest_sha256":MANIFEST_SHA,"signature_file_sha256":sha(s.read_bytes()),
         "assets_sha":{q:sha((p/q).read_bytes()) for q in sorted(FILESET)},
         "production_mutation":False,"private_key_exported":False}
def sign(stage:Path):
 p,pub,data=inspect(stage)
 target=p/"release/agent-manifest.sig.json"
 if target.exists():err("SIGNATURE_ALREADY_EXISTS")
 key=private_key(pub)
 payload={"alg":"RS256","kid":"commander-release-v2","manifest_sha256":MANIFEST_SHA,
          "schema":"hara.commander-release-signature.v1",
          "signature":enc(key.sign(data,padding.PKCS1v15(),hashes.SHA256()))}
 content=(json.dumps(payload,sort_keys=True,indent=2)+"\n").encode()
 old=os.umask(0o077)
 try:
  with target.open("xb") as handle:handle.write(content)
 finally:os.umask(old)
 del key,payload
 receipt=verify(stage)
 receipt["signed_at_utc"]=datetime.now(timezone.utc).isoformat()
 (stage/"SIGNING_RECEIPT.json").write_text(json.dumps(receipt,indent=2)+"\n")
 print(json.dumps(receipt))
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("action",choices=("prepare","sign","verify"))
 parser.add_argument("--stage",required=True,type=Path)
 parser.add_argument("--archive",type=Path)
 a=parser.parse_args();safe_stage(a.stage)
 if a.action=="prepare":
  if a.archive is None:err("ARCHIVE_REQUIRED")
  prepare(a.archive,a.stage)
 elif a.action=="sign":sign(a.stage)
 else:print(json.dumps(verify(a.stage)))
if __name__=="__main__":main()
