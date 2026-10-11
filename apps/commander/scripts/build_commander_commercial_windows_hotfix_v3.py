#!/usr/bin/env python3
"""Build a separately versioned, v2-RS256 commercial installer-only hotfix.

Preserve immutable 0.3.43-v2 signed bundle, original signed Linux and Windows
Agents, and the existing root trust anchor. Only fix the Windows temporary
filename required for PowerShell -File. Uses the existing custodied signing key
in Services; never exports it. No public deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import build_commander_commercial_signed_v2 as signer

APP=signer.APP
BASE=APP/"release-bundles/commercial-0.3.43-v2"
NEW=APP/"release-bundles/commercial-0.3.43-v3"
FILESET=signer.FILESET
EXTRA=("release/agent-manifest.json","release/agent-manifest.sig.json",
       "release/release-signing-public.jwk","release/SHA256SUMS")
OLD=b'  $tmp = $Agent + ".update"\n  $backup = $Agent + ".rollback"'
FIXED=(b"  # PowerShell -File requires an executable .ps1 suffix. The previous\n"
       b"  # '.ps1.update' name failed before self-test, even for a signed valid Agent.\n"
       b'  $tmp = $Agent + ".update.ps1"\n'
       b'  $backup = $Agent + ".rollback"')

def fail(code:str)->None:
    raise RuntimeError("COMMANDER_WINDOWS_UPDATER_V3_"+code)

def pin_source()->bytes:
    raw=(APP/"public/install/windows.ps1").read_bytes()
    pub,_=signer.public_key()
    for label,field in (("Kid","kid"),("N","n"),("E","e")):
        pattern=b'\\$ReleaseSigning'+label.encode()+b' = "[^"]+"'
        raw,count=re.subn(pattern,lambda m:b'$ReleaseSigning'+label.encode()+b' = "'+pub[field].encode()+b'"',raw)
        if count!=1:fail("CANONICAL_SIGNER_PIN_ANCHOR_MISSING")
    return raw

def check_old()->None:
    proc=subprocess.run([sys.executable,"-B",str(APP/"scripts/validate_signed_commercial_v2_bundle.py")],
                        capture_output=True,text=True,timeout=25)
    if proc.returncode:fail("HISTORICAL_V2_SIGNATURE_INVALID")
    if OLD not in (BASE/"install/windows.ps1").read_bytes():
        fail("OLD_INSTALLER_ORIGIN_CHANGED")

def prepare(stage:Path)->None:
    check_old()
    if stage.exists() or NEW.exists():fail("DESTINATION_EXISTS")
    old_bytes=(BASE/"install/windows.ps1").read_bytes()
    if old_bytes.count(OLD)!=1:fail("PATCH_ANCHOR_NONUNIQUE")
    fixed=old_bytes.replace(OLD,FIXED)
    if fixed!=pin_source():fail("CANONICAL_SOURCE_IS_NOT_ONLY_EXPECTED_HOTFIX")
    signer.populate(stage)
    public=stage/"apps/commander/public"
    for rel in FILESET:
        raw = fixed if rel=="install/windows.ps1" else (BASE/rel).read_bytes()
        dest=public/rel
        dest.write_bytes(raw)
    old_manifest=json.loads((BASE/"release/agent-manifest.json").read_text())
    manifest={**old_manifest,"files":[{
        "bytes":len((public/rel).read_bytes()),
        "path":rel,
        "sha256":signer.sha((public/rel).read_bytes()),
    } for rel in FILESET]}
    if manifest.get("agent_version")!="0.3.43":fail("UNEXPECTED_AGENT_VERSION")
    (public/"release/agent-manifest.json").write_bytes(signer.json_bytes(manifest))
    (public/"release/SHA256SUMS").write_text(
        "".join(f"{r['sha256']}  {r['path']}\n" for r in manifest["files"]),
        encoding="utf-8")
    if (public/"release/agent-manifest.sig.json").exists():fail("SIGNATURE_ALREADY_PRESENT")
    print("COMMANDER_WINDOWS_UPDATER_V3_STAGE=READY")

def publish_local(stage:Path)->None:
    signer.verify(stage)
    if NEW.exists():fail("IMMUTABLE_TARGET_EXISTS")
    NEW.mkdir(parents=True)
    public=stage/"apps/commander/public"
    for rel in (*FILESET,*EXTRA):
        source=public/rel
        dest=NEW/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        if signer.sha(dest.read_bytes())!=signer.sha(source.read_bytes()):
            fail("COPY_HASH_MISMATCH")
    (NEW/"README.md").write_text(
        "# Commercial 0.3.43-v3 — signed Windows updater hotfix\n\n"
        "Immutable v2 release retained. Same Linux and Windows Agent 0.3.43 bytes, "
        "same Linux installer. Only Windows bootstrap updater .ps1 suffix is fixed.\n"
        "RS256 v2 signature and all four file hashes are recomputed and verified.\n"
        "No automatic enrollment, restart or scheduled task boot changes.\n"
        "Do not deploy before Windows VM user-context acceptance and complete gate.\n")
    print("COMMERCIAL_0_3_43_V3_LOCAL_SIGNED_RELEASE=STAGED")

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["prepare","sign","freeze"])
    parser.add_argument("--stage",required=True)
    args=parser.parse_args()
    stage=signer.protect(args.stage)
    if args.action=="prepare":prepare(stage)
    elif args.action=="sign":
        check_old()
        signer.sign(stage)
    else:
        check_old()
        publish_local(stage)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
