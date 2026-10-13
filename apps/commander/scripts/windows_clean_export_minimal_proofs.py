import importlib.util,json,base64,hashlib
from pathlib import Path
s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
def read(name):
 h=b.call(b.CLONE,{"execute":"guest-file-open","arguments":{"path":b.CLEAN+chr(92)+name,"mode":"rb"}})
 try:
  r=b.call(b.CLONE,{"execute":"guest-file-read","arguments":{"handle":h,"count":65536}});raw=base64.b64decode(r["buf-b64"]);assert len(raw)<8192,"BOUNDED_PUBLIC_PROOF_REQUIRED"
 finally:b.call(b.CLONE,{"execute":"guest-file-close","arguments":{"handle":h}})
 return raw.decode("utf-8-sig")
for name in ("native-minimal-installed.txt","native-normal-start.txt"):
 text=read(name)
 # Every output line is an explicit public scalar or a signed client's whitelisted marker.
 rows={}
 for line in text.splitlines():
  if "=" in line:
   k,v=line.split("=",1);assert k.replace("_","").isalnum();rows[k]=v
 print(json.dumps({"name":name,"values":rows,"raw_sha256":hashlib.sha256(text.encode()).hexdigest()}))
