import importlib.util,json,base64,hashlib,argparse,re
s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
p=argparse.ArgumentParser();p.add_argument("name",choices=["native-runtime-witness-after-failed-running-053.txt","native-phase-update-running.txt","native-phase-update-stopped.txt","native-phase-negative-signature.txt","native-phase-stop.txt","native-phase-uninstall.txt","native-054-install.txt","native-054-normal-start.txt","native-054-phase-update-running.txt","native-054-phase-update-stopped.txt","native-054-phase-negative-signature.txt","native-054-phase-stop.txt","native-054-phase-uninstall.txt","native-054-update-running-followup.txt"]);a=p.parse_args()
h=b.call(b.CLONE,{"execute":"guest-file-open","arguments":{"path":b.CLEAN+chr(92)+a.name,"mode":"rb"}})
try:
 r=b.call(b.CLONE,{"execute":"guest-file-read","arguments":{"handle":h,"count":16384}});raw=base64.b64decode(r["buf-b64"]);assert len(raw)<16384,"PROOF_BOUND_EXCEEDED"
finally:b.call(b.CLONE,{"execute":"guest-file-close","arguments":{"handle":h}})
rows={}
for line in raw.decode("utf-8-sig").splitlines():
 if "=" in line:
  k,v=line.split("=",1);assert re.fullmatch("[A-Z0-9_]+",k),"PUBLIC_KEY_REQUIRED";rows[k]=v
print(json.dumps({"schema":"hara.windows-clean-native-scalar-proof.v1","vm":b.CLONE,"name":a.name,"values":rows,"raw_sha256":hashlib.sha256(raw).hexdigest(),"config_values_read":False,"signed_source_modified":False},sort_keys=True))