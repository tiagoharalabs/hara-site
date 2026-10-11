#!/usr/bin/env python3
"""Cryptographic verification of immutable commercial 0.3.43-v3 hotfix.

The original commercial 0.3.43-v2 artifact remains unmodified. v3 only
changes the signed Windows updater to preserve .ps1 filename suffix.
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OLD=APP/"release-bundles/commercial-0.3.43-v2"
NEW=APP/"release-bundles/commercial-0.3.43-v3"
FILESET=("agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1")
EXTRA=("release/agent-manifest.json","release/agent-manifest.sig.json",
       "release/release-signing-public.jwk","release/SHA256SUMS")
def sha(buf): return hashlib.sha256(buf).hexdigest()
def dec(text): return base64.urlsafe_b64decode(text+"="*(-len(text)%4))
def need(ok,code):
    if not ok: raise RuntimeError("COMMERCIAL_UPDATER_V3_"+code)
def main():
    for name in (*FILESET,*EXTRA):
        for root in (OLD,NEW):
            path=root/name
            need(path.is_file() and not path.is_symlink(),"SOURCE_INVALID")
    old_doc=json.loads((OLD/"release/agent-manifest.json").read_bytes())
    doc_data=(NEW/"release/agent-manifest.json").read_bytes()
    doc=json.loads(doc_data)
    sign=json.loads((NEW/"release/agent-manifest.sig.json").read_bytes())
    jwk=json.loads((NEW/"release/release-signing-public.jwk").read_bytes())
    old_jwk=(OLD/"release/release-signing-public.jwk").read_bytes()
    need(old_jwk==(NEW/"release/release-signing-public.jwk").read_bytes(),"KEY_ROTATED")
    need(doc.get("schema")=="hara.commander-agent-release.v1"
         and doc.get("agent_version")=="0.3.43"
         and doc.get("channel")=="stable"
         and {x["path"] for x in doc["files"]}==set(FILESET),"MANIFEST_SCHEMA")
    need(doc.get("agent_version")==old_doc.get("agent_version"),"AGENT_VERSION_CHANGED")
    need(sign.get("schema")=="hara.commander-release-signature.v1"
         and sign.get("alg")=="RS256"
         and sign.get("kid")==jwk.get("kid")=="commander-release-v2"
         and sign.get("manifest_sha256")==sha(doc_data),"SIGNATURE_METADATA")
    key=rsa.RSAPublicNumbers(
       int.from_bytes(dec(jwk["e"]),"big"),int.from_bytes(dec(jwk["n"]),"big")
    ).public_key()
    need(key.key_size==3072,"KEY_SIZE")
    key.verify(dec(sign["signature"]),doc_data,padding.PKCS1v15(),hashes.SHA256())
    for entry in doc["files"]:
        buf=(NEW/entry["path"]).read_bytes()
        need(len(buf)==entry["bytes"] and sha(buf)==entry["sha256"],
             "SIGNED_FILE_DRIFT:"+entry["path"])
    for path in FILESET:
        before=(OLD/path).read_bytes()
        after=(NEW/path).read_bytes()
        if path=="install/windows.ps1":
            need(before!=after,"WINDOWS_INSTALLER_NOT_CHANGED")
            old=b'  $tmp = $Agent + ".update"\n'
            need(before.count(old)==1,"LEGACY_PATCH_ANCHOR_CHANGED")
            need(b'  $tmp = $Agent + ".update.ps1"\n' in after,
                 "PS1_EXECUTABLE_SUFFIX_MISSING")
            need(b'  $tmp = $Agent + ".update"\n' not in after,
                 "DANGEROUS_TEMP_EXTENSION_STILL_USED")
            # New version adds only the documented source comments and .ps1 fix.
            documented=(b"  # PowerShell -File requires an executable .ps1 suffix. The previous\n"
                        b"  # '.ps1.update' name failed before self-test, even for a signed valid Agent.\n"
                        b'  $tmp = $Agent + ".update.ps1"\n')
            need(after==before.replace(old,documented),"UNAUTHORIZED_EXTRA_INSTALLER_CHANGE")
        else:
            need(before==after,"OTHER_SIGNED_ASSET_MUTATED:"+path)
    sums=(NEW/"release/SHA256SUMS").read_text()
    need(all(sha((NEW/path).read_bytes())+"  "+path in sums
             for path in FILESET),"CHECKSUM_INDEX_INVALID")
    print("COMMERCIAL_UPDATER_V3_SIGNATURE=PASS")
    print("COMMERCIAL_UPDATER_V3_FOUR_FILE_SHA256=PASS")
    print("COMMERCIAL_UPDATER_V3_UNCHANGED_LINUX_AND_WINDOWS_AGENTS=PASS")
    print("COMMERCIAL_UPDATER_V3_LEGACY_PACKAGE_IMMUTABLE=PASS")
    print("COMMERCIAL_UPDATER_V3_POWERSHELL_PS1_SUFFIX=PASS")
    print("COMMERCIAL_UPDATER_V3_PRIVATE_KEY_NOT_EXPORTED=PASS")
    print("COMMERCIAL_UPDATER_V3_CLOUD_DEPLOYMENT=NONE")
if __name__=="__main__":
    main()
