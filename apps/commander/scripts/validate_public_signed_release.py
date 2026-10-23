#!/usr/bin/env python3
"""Fail-closed, read-only public signed Agent release gate.
No keys, tokens, cookies, pairing or device actions. R1 2026-10-23.
Exit 0 only when signature, byte sizes/hashes, version parity and floors pass.
"""
import argparse,base64,hashlib,json,re,sys,urllib.request
from pathlib import Path
REQUIRED=("agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1")
def sha(data):return hashlib.sha256(data).hexdigest()
def b64(s):return base64.urlsafe_b64decode(s+"="*((-len(s))%4))
def main():
 p=argparse.ArgumentParser()
 g=p.add_mutually_exclusive_group(required=True)
 g.add_argument("--root",type=Path)
 g.add_argument("--url")
 p.add_argument("--min-version",default="0.3.55")
 args=p.parse_args()
 root=args.root; url=args.url
 def read(f):
  if root:return (root/f).read_bytes()
  req=urllib.request.Request(url.rstrip("/")+"/"+f,headers={"User-Agent":"HARA-Commander-signed-release-gate-r1","Cache-Control":"no-cache"})
  with urllib.request.urlopen(req,timeout=25) as r:return r.read()
 result={"schema":"hara.commander.signed-release-gate.v1","origin":"LOCAL_BUNDLE" if root else "LIVE_PUBLIC","files":{},"state":"HOLD"}
 try:
  manifest_bytes=read("release/agent-manifest.json")
  m=json.loads(manifest_bytes)
  sig=json.loads(read("release/agent-manifest.sig.json"))
  pub=json.loads(read("release/release-signing-public.jwk"))
  result["manifest_version"]=m.get("agent_version")
  result["signer_kid"]=sig.get("kid")
  sign=b64(sig["signature"]);n=int.from_bytes(b64(pub["n"]),"big");e=int.from_bytes(b64(pub["e"]),"big")
  k=(n.bit_length()+7)//8
  prefix=bytes.fromhex("3031300d060960864801650304020105000420")+hashlib.sha256(manifest_bytes).digest()
  expected=b"\x00\x01"+b"\xff"*(k-len(prefix)-3)+b"\x00"+prefix
  valid=(sig.get("alg")=="RS256" and pub.get("kty")=="RSA" and sig.get("kid")==pub.get("kid") and sig.get("manifest_sha256")==sha(manifest_bytes) and len(sign)==k and pow(int.from_bytes(sign,"big"),e,n).to_bytes(k,"big")==expected)
  result["signature_rs256_valid"]=valid
  by_path={x["path"]:x for x in m.get("files",[])}
  for f in REQUIRED:
   file=read(f);entry=by_path.get(f,{})
   item={"sha256":sha(file),"size":len(file),"manifest_sha_match":entry.get("sha256")==sha(file),"manifest_size_match":entry.get("bytes")==len(file)}
   result["files"][f]=item
  linux=read("agent/linux.py").decode("utf-8",errors="replace")
  windows=read("agent/windows.ps1").decode("utf-8",errors="replace")
  lin=re.search(r'^AGENT_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"',linux,re.M)
  win=re.search(r'^\$AgentVersion\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"',windows,re.M)
  result["linux_version"]=lin.group(1) if lin else None
  result["windows_version"]=win.group(1) if win else None
  result["cross_platform_version_match"]=bool(result["linux_version"]==result["windows_version"]==m.get("agent_version"))
  def ver(v):
   if not isinstance(v,str) or not re.fullmatch(r"\d+\.\d+\.\d+",v):return (-1,-1,-1)
   return tuple(map(int,v.split(".")))
  result["min_version"]=args.min_version
  result["floor_met"]=ver(result["linux_version"])>=ver(args.min_version) and ver(result["windows_version"])>=ver(args.min_version)
  l_inst=read("install/linux.sh").decode(errors="replace")
  w_inst=read("install/windows.ps1").decode(errors="replace")
  result["installer_signer_kid_match"]=(m.get("agent_version") is not None and sig.get("kid") in l_inst and sig.get("kid") in w_inst)
  n_linux=re.search(r'^RELEASE_SIGNING_N="([^"]+)"',l_inst,re.M)
  e_linux=re.search(r'^RELEASE_SIGNING_E="([^"]+)"',l_inst,re.M)
  n_windows=re.search(r'^\$ReleaseSigningN\s*=\s*"([^"]+)"',w_inst,re.M)
  e_windows=re.search(r'^\$ReleaseSigningE\s*=\s*"([^"]+)"',w_inst,re.M)
  result["installer_signer_key_match"]=bool(n_linux and e_linux and n_windows and e_windows and n_linux.group(1)==pub.get("n")==n_windows.group(1) and e_linux.group(1)==pub.get("e")==e_windows.group(1))
  integrity=valid and all(f["manifest_sha_match"] and f["manifest_size_match"] for f in result["files"].values())
  result["integrity_pass"]=integrity
  result["state"]="PASS" if integrity and result["cross_platform_version_match"] and result["floor_met"] and result["installer_signer_kid_match"] and result["installer_signer_key_match"] else "HOLD"
 except Exception as exc:
  result["error"]=type(exc).__name__+": "+str(exc)[:160]
 print(json.dumps(result,sort_keys=True))
 return 0 if result["state"]=="PASS" else 5
if __name__=="__main__":raise SystemExit(main())