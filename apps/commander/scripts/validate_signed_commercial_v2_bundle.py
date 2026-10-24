#!/usr/bin/env python3
"""Verify the immutable commercial v0.3.43 v2-signed Git release bundle.

--live confirms the public Cloudflare URL serves the exact signed Git assets.
No private signing keys, Cloudflare credentials, local customer data or writes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from validate_prod_runtime_drift import normalize_asset

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
BUNDLE = APP / "release-bundles/commercial-0.3.43-v2"
PUBLIC = APP / "public"
ORIGIN = "https://commander.haralabs.com.br"
FILESET = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
LIVE_FILES = FILESET + (
    "release/agent-manifest.json", "release/agent-manifest.sig.json",
    "release/release-signing-public.jwk", "release/SHA256SUMS",
    "index.html", "app.js",
)


def b64d(value: str):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def check_local():
    doc = json.loads((BUNDLE/"release/agent-manifest.json").read_text())
    sig = json.loads((BUNDLE/"release/agent-manifest.sig.json").read_text())
    pub = json.loads((BUNDLE/"release/release-signing-public.jwk").read_text())
    if doc.get("agent_version") != "0.3.43" or doc.get("schema") != "hara.commander-agent-release.v1":
        raise RuntimeError("COMMERCIAL_BUNDLE_SCHEMA_INVALID")
    if sig.get("kid") != "commander-release-v2" or pub.get("kid") != "commander-release-v2":
        raise RuntimeError("COMMERCIAL_BUNDLE_KID_INVALID")
    if sig.get("alg") != "RS256" or pub.get("alg") != "RS256":
        raise RuntimeError("COMMERCIAL_BUNDLE_ALGORITHM_INVALID")
    raw = (BUNDLE/"release/agent-manifest.json").read_bytes()
    if sha(raw) != sig.get("manifest_sha256"):
        raise RuntimeError("COMMERCIAL_BUNDLE_MANIFEST_HASH_INVALID")
    key = rsa.RSAPublicNumbers(
        int.from_bytes(b64d(pub["e"]), "big"),
        int.from_bytes(b64d(pub["n"]), "big"),
    ).public_key()
    if key.key_size != 3072:
        raise RuntimeError("COMMERCIAL_BUNDLE_RSA_SIZE_INVALID")
    key.verify(b64d(sig["signature"]), raw, padding.PKCS1v15(), hashes.SHA256())
    if {r["path"] for r in doc["files"]} != set(FILESET):
        raise RuntimeError("COMMERCIAL_BUNDLE_FILESET_INVALID")
    for row in doc["files"]:
        data = (BUNDLE/row["path"]).read_bytes()
        if len(data) != row["bytes"] or sha(data) != row["sha256"]:
            raise RuntimeError("COMMERCIAL_BUNDLE_HASH_INVALID:"+row["path"])
    linux=(BUNDLE/"install/linux.sh").read_text()
    windows=(BUNDLE/"install/windows.ps1").read_text()
    if 'RELEASE_SIGNING_KID="commander-release-v2"' not in linux or '$ReleaseSigningKid = "commander-release-v2"' not in windows:
        raise RuntimeError("COMMERCIAL_BUNDLE_INSTALL_TRUST_MISMATCH")
    if "systemctl --user enable --now hara-commander-agent.service" in linux or "New-ScheduledTaskTrigger -AtLogon" in windows:
        raise RuntimeError("COMMERCIAL_BUNDLE_AUTOSTART_REINTRODUCED")
    print("COMMANDER_COMMERCIAL_V2_BUNDLE_SIGNATURE=PASS")
    print("COMMANDER_COMMERCIAL_V2_BUNDLE_SHA256=4_OF_4")
    print("COMMANDER_COMMERCIAL_V2_BUNDLE_MANUAL_START=PASS")


def check_live():
    for rel in LIVE_FILES:
        source=(BUNDLE/rel) if (BUNDLE/rel).is_file() else (PUBLIC/rel)
        expected=source.read_bytes()
        # The canonical public page is '/' (as verified by the PROD drift
        # checker). Cloudflare may cache '/index.html' separately during rollout.
        # Verify the actual customer landing route, never a stale HTML alias.
        public_path="/" if rel=="index.html" else "/"+rel
        request=Request(ORIGIN+public_path,headers={
            "User-Agent":"HARA-Signed-Commercial-V2-Readback/1",
            "Cache-Control":"no-cache",
        })
        with urlopen(request,timeout=16) as response:
            actual=response.read(4*1024*1024)
            if response.status!=200:
                raise RuntimeError("COMMERCIAL_V2_PUBLIC_STATUS:"+rel)
        if rel=="index.html":
            # Cloudflare PROD injects its own analytics beacon in HTML only.
            # Remove precisely that known script with the existing validated
            # production normalizer, never ignore any other HTML difference.
            actual,removed=normalize_asset("/",actual)
            print("COMMANDER_COMMERCIAL_V2_CF_BEACON_NORMALIZED="+str(removed).upper())
        if sha(actual)!=sha(expected):
            raise RuntimeError("COMMERCIAL_V2_PUBLIC_ASSET_MISMATCH:"+rel)
        print("COMMANDER_COMMERCIAL_V2_PUBLIC_ASSET=PASS:"+rel)
    print("COMMANDER_COMMERCIAL_V2_PUBLIC_SHA_READBACK=10_OF_10")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true")
    args=parser.parse_args()
    check_local()
    if args.live:check_live()
    print("COMMANDER_COMMERCIAL_V2_CUSTOMER_SECRET_READ=FALSE")
    print("COMMANDER_COMMERCIAL_V2_MUTATION=FALSE")


if __name__=="__main__":
    main()
