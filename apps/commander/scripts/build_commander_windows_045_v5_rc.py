#!/usr/bin/env python3
"""Prepare a separately signed Windows 0.3.45 RC without altering PROD 0.3.44.

Release adds per-action local consent, bounded managed processes and CAS-safe
writes. Signed Linux Agent/installer are byte-identical to v3.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import build_commander_commercial_signed_v2 as signer

APP=signer.APP
# v4 signs a 0.3.45 Windows Agent but retains the unchanged signed 0.3.44
# Linux component. This version is a manifest/release label, not a Linux bump.
signer.VERSION="0.3.45"
BASE=APP/"release-bundles/commercial-0.3.44-v4-rc"
NEW=APP/"release-bundles/commercial-0.3.45-v5-rc"
FILESET=signer.FILESET
EXTRA=("release/agent-manifest.json","release/agent-manifest.sig.json",
       "release/release-signing-public.jwk","release/SHA256SUMS")
OLD=b'agent_version="0.3.44"'
UPDATED=b'agent_version="0.3.45"'

def fail(code):raise RuntimeError("COMMANDER_WINDOWS_045_V5_"+code)

def old_verification():
    proc=subprocess.run([sys.executable,"-B",str(APP/"scripts/validate_signed_windows_044_v4_rc.py")],
                        capture_output=True,text=True,timeout=30)
    if proc.returncode:fail("PREVIOUS_SIGNED_RELEASE_INVALID")
    if not BASE.is_dir():fail("PREVIOUS_RELEASE_MISSING")

def expected_installer():
    source=(BASE/"install/windows.ps1").read_bytes()
    if source.count(OLD)!=3:fail("INSTALLER_VERSION_ANCHOR_INVALID")
    return source.replace(OLD,UPDATED)

def pin_canonical_installer():
    raw=(APP/"public/install/windows.ps1").read_bytes()
    pub,_=signer.public_key()
    for label,key in (("Kid","kid"),("N","n"),("E","e")):
        pattern=rb'\$ReleaseSigning'+label.encode()+rb' = "[^"]+"'
        raw,n=re.subn(pattern,lambda m:b'$ReleaseSigning'+label.encode()+b' = "'+pub[key].encode()+b'"',raw)
        if n!=1:fail("CANONICAL_SIGNER_PIN_MISSING")
    return raw

def expected_agent():
    source=(APP/"public/agent/windows.ps1").read_bytes()
    if source.count(b'$AgentVersion = "0.3.45"')!=1:fail("AGENT_VERSION_INVALID")
    if b'WINDOWS_PER_ACTION_APPROVAL_UNSUPPORTED' in source:fail("UNSUPPORTED_APPROVAL_CODE_REMAINS")
    if b'action_summary=$null' not in source:fail('METADATA_ONLY_CONSOLE_LOG_MISSING')
    if b'SELF_TEST_LOCAL_CONSOLE_PRIVATE_COMMAND_PERSISTED' not in source:fail('PRIVACY_SELFTEST_MISSING')
    if b'$ApprovalTimeoutSeconds = 30' not in source:fail('APPROVAL_WINDOW_NOT_PINNED')
    for anchor in (b'Invoke-LocalActionApproval',b'Respond-ToLocalApprovalRequest',
                   b'HaraWindowsProcessSession',b'FILE_PRECONDITION_FAILED',
                   b'PROCESS_SESSION_CAPACITY'):
        if anchor not in source:fail("REQUIRED_FEATURE_MISSING")
    return source

def prepare(stage):
    old_verification()
    if stage.exists() or NEW.exists():fail("IMMUTABLE_RELEASE_TARGET_EXISTS")
    if pin_canonical_installer()!=expected_installer():
        fail("CANONICAL_INSTALLER_NOT_PINNED")
    agent=expected_agent()
    installer=expected_installer()
    stage.mkdir(mode=0o700,parents=True)
    target=stage/"apps/commander"
    for folder in ("src","migrations","public"):
        shutil.copytree(APP/folder,target/folder,
                        ignore=shutil.ignore_patterns("__pycache__","*.pyc","*.pyo"))
    shutil.copy2(APP/"wrangler.jsonc",target/"wrangler.jsonc")
    node=signer.ROOT/"node_modules"
    if not node.is_dir():fail("NPM_DEPENDENCIES_MISSING")
    (stage/"node_modules").symlink_to(node,target_is_directory=True)
    public=target/"public"
    (public/"release/release-signing-public.jwk").write_bytes(
        (BASE/"release/release-signing-public.jwk").read_bytes())
    for rel in FILESET:
        new=agent if rel=="agent/windows.ps1" else installer if rel=="install/windows.ps1" else (BASE/rel).read_bytes()
        (public/rel).write_bytes(new)
    previous=json.loads((BASE/"release/agent-manifest.json").read_text())
    manifest={**previous,"agent_version":"0.3.45",
      "files":[{"bytes":len((public/rel).read_bytes()),"path":rel,
                "sha256":signer.sha((public/rel).read_bytes())} for rel in FILESET]}
    (public/"release/agent-manifest.json").write_bytes(signer.json_bytes(manifest))
    (public/"release/SHA256SUMS").write_text(
       "".join(f"{row['sha256']}  {row['path']}\n" for row in manifest["files"]),encoding="utf-8")
    # Only the copied staging source has its old v1 signature discarded.
    stale=public/"release/agent-manifest.sig.json"
    if stale.exists():stale.unlink()
    if stale.exists():fail("STAGE_SIGNATURE_UNEXPECTED")
    print("WINDOWS_0_3_45_RC_STAGE_PREPARED")

def freeze(stage):
    old_verification()
    signer.verify(stage)
    if NEW.exists():fail("RELEASE_ALREADY_EXISTS")
    NEW.mkdir(parents=True)
    public=stage/"apps/commander/public"
    for rel in (*FILESET,*EXTRA):
        source=public/rel
        dest=NEW/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        if signer.sha(source.read_bytes())!=signer.sha(dest.read_bytes()):
            fail("FROZEN_FILE_HASH_MISMATCH")
    (NEW/"README.md").write_text(
      "# Windows 0.3.45-v4 RC - Founder lab candidate\n\n"
      "RS256 signed release for Windows 11 lab approval. Adds local per-action\n"
      "consent, bounded managed process sessions, atomic CAS-safe file writes.\n"
      "Original v3 commercial release and Linux source remain unchanged.\n"
      "NOT PUBLIC: do not update Cloudflare or enrolled users until a local\n"
      "operator explicitly verifies an approved and denied action on the VM,\n"
      "and the full gate passes. Windows Event V2 RC transport is separate.\n",
      encoding="utf-8")
    print("WINDOWS_0_3_45_V5_RC_SIGNED_AND_FROZEN")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("prepare","sign","freeze"))
    ap.add_argument("--stage",required=True)
    args=ap.parse_args()
    stage=signer.protect(args.stage)
    if args.action=="prepare":prepare(stage)
    elif args.action=="sign":
      old_verification();signer.sign(stage)
    else:freeze(stage)
if __name__=="__main__":main()
