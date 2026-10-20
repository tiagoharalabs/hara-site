#!/usr/bin/env python3
"""Read-only, fail-closed audit of PUBLIC HARA Commander signed distribution.
No installation, no writing customer content, no device enrollment.
Expected public key read from source installer in local QA clone.
Network read GET is bounded; redirects disabled; hashes only in report.
"""
import base64,hashlib,hmac,json,re,sys,urllib.error,urllib.request
from datetime import datetime,timezone
from pathlib import Path

BASE="https://commander.haralabs.com.br"
ASSETS=[
"/install/linux.sh","/agent/linux.py",
"/install/windows.ps1","/agent/windows.ps1",
"/release/agent-manifest.json","/release/agent-manifest.sig.json",
]
ROOT=Path(__file__).resolve().parents[3]
INSTALLER=ROOT/"apps/commander/public/install/linux.sh"
def b64ud(value):
 return base64.urlsafe_b64decode(value+"="*((4-len(value)%4)%4))
def download(path):
 url=BASE+path
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*a,**kw):return None
 opener=urllib.request.build_opener(NoRedirect())
 request=urllib.request.Request(url,headers={"user-agent":"HARA-Commander-QA-Published-Integrity/1","accept":"application/octet-stream"})
 with opener.open(request,timeout=9) as response:
  if response.status!=200:raise RuntimeError("UNEXPECTED_HTTP_STATUS")
  raw=response.read(4*1024*1024+1)
  if len(raw)>4*1024*1024:raise RuntimeError("PUBLIC_ASSET_TOO_LARGE")
  return raw
def pinned_key(text,key):
 m=re.search(r'^'+re.escape(key)+r'="([^"]+)"',text,re.M)
 if not m:raise RuntimeError("RELEASE_KEY_MISSING")
 return m.group(1)
def verify(manifest,signature,code):
 obj=json.loads(signature)
 kid=pinned_key(code,"RELEASE_SIGNING_KID")
 n=int.from_bytes(b64ud(pinned_key(code,"RELEASE_SIGNING_N")),"big")
 e=int.from_bytes(b64ud(pinned_key(code,"RELEASE_SIGNING_E")),"big")
 if obj.get("schema")!="hara.commander-release-signature.v1" or obj.get("alg")!="RS256" or obj.get("kid")!=kid:return False
 if obj.get("manifest_sha256")!=hashlib.sha256(manifest).hexdigest():return False
 sig=b64ud(obj.get("signature",""))
 size=(n.bit_length()+7)//8
 if len(sig)!=size:return False
 em=pow(int.from_bytes(sig,"big"),e,n).to_bytes(size,"big")
 di=bytes.fromhex("3031300d060960864801650304020105000420")+hashlib.sha256(manifest).digest()
 pad=size-len(di)-3
 return pad>=8 and hmac.compare_digest(em,b"\x00\x01"+(b"\xff"*pad)+b"\x00"+di)
def main():
 data={}
 for path in ASSETS:
  try:
   raw=download(path)
   data[path]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"status":"FETCHED"}
   data[path]["_raw"]=raw
  except Exception as error:data[path]={"status":"FETCH_ERROR","category":type(error).__name__}
 manifest_bytes=data["/release/agent-manifest.json"].get("_raw")
 signature_bytes=data["/release/agent-manifest.sig.json"].get("_raw")
 out={"schema":"hara.commander.public-release-integrity-review.v1",
      "observed_at_utc":datetime.now(timezone.utc).isoformat(),"url":BASE,
      "read_only":True,"device_enrollment":False,"service_changed":False}
 if manifest_bytes and signature_bytes:
  m=json.loads(manifest_bytes)
  sig_source=INSTALLER.read_text()
  live_installer_source=data["/install/linux.sh"].get("_raw",b"").decode("utf-8",errors="replace")
  sig_info=json.loads(signature_bytes)
  live_kid=pinned_key(live_installer_source,"RELEASE_SIGNING_KID")
  source_kid=pinned_key(sig_source,"RELEASE_SIGNING_KID")
  out["live_linux_installer"]={
    "pinned_signing_kid":live_kid,
    "published_signature_kid":sig_info.get("kid"),
    "kid_matches":live_kid==sig_info.get("kid"),
    "manifest_signature_valid_for_LIVE_installer":verify(manifest_bytes,signature_bytes,live_installer_source),
    "source_repo_installer_kid":source_kid,
    "live_installer_differs_from_repo":hashlib.sha256(live_installer_source.encode()).hexdigest()!=hashlib.sha256(sig_source.encode()).hexdigest(),
  }
  out["manifest"]={"version":m.get("agent_version"),"sha256":hashlib.sha256(manifest_bytes).hexdigest(),
   "signature_valid_against_REPO_v1_key":verify(manifest_bytes,signature_bytes,sig_source),
   "expected_files":[{"path":x.get("path"),"expected_sha256":x.get("sha256")} for x in m.get("files",[])]}
  for x in m.get("files",[]):
   path="/"+str(x.get("path",""))
   if path in data:data[path]["expected_sha256"]=x.get("sha256");data[path]["matches_manifest"]=data[path].get("sha256")==x.get("sha256")
 for path,info in data.items():
  raw=info.pop("_raw",None)
  if path=="/agent/linux.py" and raw:
   v=re.search(rb'^AGENT_VERSION\s*=\s*["\']([^"\']+)["\']',raw,re.M)
   info["source_agent_version"]=v.group(1).decode("ascii") if v else "NOT_READABLE_BY_REGEX"
 out["assets"]=data
 out["all_manifested_assets_match"]=bool(manifest_bytes and all(x.get("matches_manifest") for x in data.values() if "expected_sha256" in x))
 out["can_pass_live_installer_release_gate"]=out["all_manifested_assets_match"] and bool(out.get("live_linux_installer",{}).get("manifest_signature_valid_for_LIVE_installer"))
 dest=Path(__file__).with_name("public-integrity-results.json")
 dest.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps(out,indent=2,ensure_ascii=False))
 return 2 if not out["can_pass_live_installer_release_gate"] else 0
if __name__=="__main__":sys.exit(main())
