#!/usr/bin/env python3
"""Offline regression proof for the release gate; no network and no signer."""
import json,shutil,subprocess,sys,tempfile
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
GATE=APP/"scripts/validate_public_signed_release.py"
FIXTURE=APP/"release-bundles/commercial-0.3.43-v2"
NEEDED=("release/agent-manifest.json","release/agent-manifest.sig.json","release/release-signing-public.jwk","agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1")
def run(root,floor):
 p=subprocess.run([sys.executable,"-I","-B",str(GATE),"--root",str(root),"--min-version",floor],capture_output=True,text=True,timeout=20)
 obj=json.loads(p.stdout)
 assert p.returncode in (0,5),(p.returncode,p.stderr[-300:])
 return p.returncode,obj
def main():
 assert all((FIXTURE/f).is_file() for f in NEEDED)
 completed=0
 with tempfile.TemporaryDirectory(prefix="hara-signed-release-test-") as d:
  root=Path(d)
  for name in NEEDED:
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(FIXTURE/name,p)
  code,res=run(root,"0.3.43")
  assert code==0 and res["integrity_pass"] and res["installer_signer_key_match"] and res["cross_platform_version_match"]
  completed+=1
  code,res=run(root,"0.3.55")
  assert code==5 and res["integrity_pass"] and not res["floor_met"]
  completed+=1
  with (root/"install/linux.sh").open("ab") as out:out.write(b"\n# Unapproved post-signature change\n")
  code,res=run(root,"0.3.43")
  assert code==5 and not res["integrity_pass"] and not res["files"]["install/linux.sh"]["manifest_sha_match"]
  completed+=1
  shutil.copy2(FIXTURE/"install/linux.sh",root/"install/linux.sh")
  obj=json.loads((root/"release/release-signing-public.jwk").read_text())
  key=obj["n"];obj["n"]="A"+key[1:] if key[0]!="A" else "B"+key[1:]
  (root/"release/release-signing-public.jwk").write_text(json.dumps(obj))
  code,res=run(root,"0.3.43")
  assert code==5 and not res["signature_rs256_valid"]
  completed+=1
 print(json.dumps({"schema":"hara.release-integrity-offline-regression.v1","state":"PASS","cases":completed,"signed_bundle_control":"PASS","release_floor_hold":"PASS","tampered_asset_denied":"PASS","tampered_key_denied":"PASS"}))
 return 0
if __name__=="__main__":raise SystemExit(main())