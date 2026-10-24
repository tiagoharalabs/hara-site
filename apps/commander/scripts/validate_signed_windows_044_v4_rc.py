#!/usr/bin/env python3
"""Offline cryptographic and scope validation of isolated Windows 0.3.44-v4 RC."""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OLD=APP/"release-bundles/commercial-0.3.43-v3"
NEW=APP/"release-bundles/commercial-0.3.44-v4-rc"
FILES=("agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1")

def need(ok,name):
 if not ok:raise AssertionError("WINDOWS044_RC_"+name)
def sha(x):return hashlib.sha256(x).hexdigest()
def unb64(t):return base64.urlsafe_b64decode(t+"="*(-len(t)%4))

def main():
 for rel in (*FILES,"release/agent-manifest.json","release/agent-manifest.sig.json",
             "release/release-signing-public.jwk","release/SHA256SUMS"):
  for root in (OLD,NEW):
   p=root/rel
   need(p.is_file() and not p.is_symlink(),"FILE_MISSING_OR_SYMLINK:"+rel)
 raw=(NEW/"release/agent-manifest.json").read_bytes()
 m=json.loads(raw)
 old=json.loads((OLD/"release/agent-manifest.json").read_bytes())
 jwk=json.loads((NEW/"release/release-signing-public.jwk").read_bytes())
 sig=json.loads((NEW/"release/agent-manifest.sig.json").read_bytes())
 need(m.get("agent_version")=="0.3.44" and m.get("channel")=="stable","MANIFEST_VERSION")
 need(old.get("agent_version")=="0.3.43","OLD_MANIFEST_VERSION")
 need(m.get("schema")=="hara.commander-agent-release.v1","MANIFEST_SCHEMA")
 need(sig.get("schema")=="hara.commander-release-signature.v1" and sig.get("alg")=="RS256"
      and sig.get("manifest_sha256")==sha(raw) and sig.get("kid")==jwk.get("kid"),
      "SIGNATURE_ENVELOPE")
 need((NEW/"release/release-signing-public.jwk").read_bytes()
      ==(OLD/"release/release-signing-public.jwk").read_bytes(),"KEY_NOT_IDENTICAL")
 key=rsa.RSAPublicNumbers(int.from_bytes(unb64(jwk["e"]),"big"),
                          int.from_bytes(unb64(jwk["n"]),"big")).public_key()
 need(key.key_size==3072,"RSA_KEY_SIZE")
 key.verify(unb64(sig["signature"]),raw,padding.PKCS1v15(),hashes.SHA256())
 rows=m.get("files",[])
 need({x.get("path") for x in rows}==set(FILES),"MANIFEST_FILES")
 for row in rows:
  blob=(NEW/row["path"]).read_bytes()
  need(len(blob)==row["bytes"] and sha(blob)==row["sha256"],"FILE_DIGEST:"+row["path"])
 need((OLD/"agent/linux.py").read_bytes()==(NEW/"agent/linux.py").read_bytes(),"LINUX_AGENT_CHANGED")
 need((OLD/"install/linux.sh").read_bytes()==(NEW/"install/linux.sh").read_bytes(),"LINUX_INSTALLER_CHANGED")
 old_win=(OLD/"install/windows.ps1").read_bytes()
 new_win=(NEW/"install/windows.ps1").read_bytes()
 need(old_win.count(b'agent_version="0.3.43"')==3,"WIN_INSTALLER_VERSION_ANCHORS")
 need(new_win==old_win.replace(b'agent_version="0.3.43"',b'agent_version="0.3.44"'),
      "WINDOWS_INSTALLER_EXTRA_MUTATION")
 windows=(NEW/"agent/windows.ps1").read_bytes()
 need(sha(windows)=="3a397ffa7f8a13e69ea88eb1293267397a473927d87f59cef6d8a1a5d5e8f6e3","IMMUTABLE_SIGNED_V44_AGENT_SHA")
 need(b'$AgentVersion = "0.3.44"' in windows,"WINDOWS_SOURCE_VERSION")
 need(b'WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED' not in windows,"UNSUPPORTED_APPROVAL_GATE")
 need(b'Invoke-LocalActionApproval' in windows
      and b'Respond-ToLocalApprovalRequest' in windows,"APPROVAL_FEATURE_MISSING")
 need(b'HaraWindowsProcessSession' in windows
      and b'PROCESS_SESSION_CAPACITY' in windows,"PROCESS_MANAGER_MISSING")
 need(b'FILE_PRECONDITION_FAILED' in windows
      and b'FILESYSTEM_SYMLINK_DENIED' in windows,"SAFE_FILE_WRITES_MISSING")
 need((NEW/"release/SHA256SUMS").read_text()==''.join(
      f'{row["sha256"]}  {row["path"]}\n' for row in rows),"CHECKSUM_INDEX")
 need('0.3.43-v4' not in str(NEW),"DESTINATION_INVALID")
 print(json.dumps({"schema":"hara.commander-windows044-rc-signature-validation.v1",
   "state":"PASS","agent_version":"0.3.44","signature":"RS256_RSA3072",
   "four_files_authenticated":True,"linux_agent_byte_identical":True,
   "linux_installer_byte_identical":True,"old_v3_preserved":True,
   "production_deployment":False,"customer_agent_modified":False},sort_keys=True))
if __name__=="__main__":main()
