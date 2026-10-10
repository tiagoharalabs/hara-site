#!/usr/bin/env python3
"""Read-only verification of immutable, publicly SIGNED Commander 0.3.41.

Compare official Cloudflare PROD static assets with the exact historic Git
commit which contains the signed v1 distribution. NEVER use the latest
unreleased source tree as a production recovery package.

--check: git/history and signature, no network.
--live: optional GET of the six public Cloudflare URLs, no deployment/mutation.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "apps/commander/public"
SIGNED_COMMIT = "08500d5"
DOMAIN = "https://commander.haralabs.com.br"
FILES = (
    "agent/linux.py",
    "agent/windows.ps1",
    "install/linux.sh",
    "install/windows.ps1",
)
MANIFEST = "release/agent-manifest.json"
SIGNATURE = "release/agent-manifest.sig.json"


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{SIGNED_COMMIT}:apps/commander/public/{path}"],
        cwd=ROOT,
        timeout=15,
    )


def urlsafe_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def pub_int(text: str) -> int:
    return int.from_bytes(urlsafe_decode(text), "big")


def verify_release() -> dict[str, str]:
    manifest_raw = git_bytes(MANIFEST)
    sig_raw = git_bytes(SIGNATURE)
    manifest = json.loads(manifest_raw)
    signature = json.loads(sig_raw)
    assert manifest.get("agent_version") == "0.3.41", "SIGNED_VERSION_NOT_V1"
    assert signature.get("alg") == "RS256", "SIGNATURE_ALGORITHM_DENIED"
    assert signature.get("kid") == "commander-release-v1", "SIGNED_KID_CHANGED"
    assert signature.get("manifest_sha256") == hashlib.sha256(manifest_raw).hexdigest(), "MANIFEST_HASH_INVALID"

    # Recover ONLY the public verification key pinned in the signed installer.
    installer = git_bytes("install/linux.sh").decode("utf-8")
    m = re.search(r'^RELEASE_SIGNING_N="([^"]+)"', installer, re.M)
    e = re.search(r'^RELEASE_SIGNING_E="([^"]+)"', installer, re.M)
    assert m and e, "SIGNER_PUBLIC_KEY_NOT_FOUND"
    key = rsa.RSAPublicNumbers(pub_int(e.group(1)), pub_int(m.group(1))).public_key()
    try:
        key.verify(urlsafe_decode(signature["signature"]), manifest_raw,
                   padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise AssertionError("SIGNATURE_CRYPTOGRAPHIC_VERIFY_FAILED") from None

    indexes = {obj["path"]:obj for obj in manifest["files"]}
    expected: dict[str,str] = {}
    for name in FILES:
        raw = git_bytes(name)
        entry = indexes[name]
        digest = hashlib.sha256(raw).hexdigest()
        assert entry["sha256"] == digest and entry["bytes"] == len(raw), "MANIFEST_FILE_INTEGRITY_MISMATCH:" + name
        expected[name] = digest
    expected[MANIFEST] = hashlib.sha256(manifest_raw).hexdigest()
    expected[SIGNATURE] = hashlib.sha256(sig_raw).hexdigest()
    return expected


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("PUBLIC_RELEASE_REDIRECT_REJECTED")


def check_live(expected: dict[str,str]) -> dict[str,str]:
    opener = urllib.request.build_opener(NoRedirect)
    actual = {}
    for path,digest in expected.items():
        req=urllib.request.Request(
            DOMAIN + "/" + path,
            headers={"User-Agent":"HARA-Commander-Verified-Distribution-Audit/1",
                     "Cache-Control":"no-cache"},
            method="GET",
        )
        with opener.open(req, timeout=16) as response:
            assert response.status == 200, "PUBLIC_ASSET_HTTP_FAILURE:" + path
            raw = response.read(2 * 1024 * 1024)
            observed = hashlib.sha256(raw).hexdigest()
            assert observed == digest, "CLOUDFLARE_GIT_SIGNED_ARTIFACT_DRIFT:" + path
            actual[path] = observed
    return actual


def main() -> int:
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--check",action="store_true")
    group.add_argument("--live",action="store_true")
    args=parser.parse_args()
    try:
        expected=verify_release()
        print("COMMANDER_SIGNED_V1_GIT_COMMIT="+subprocess.check_output(
            ["git","rev-parse",SIGNED_COMMIT],cwd=ROOT,text=True).strip())
        print("COMMANDER_SIGNED_V1_MANIFEST_CRYPTOGRAPHIC_SIGNATURE=PASS")
        print("COMMANDER_SIGNED_V1_GIT_FOUR_FILE_HASHES=PASS")
        if args.live:
            check_live(expected)
            print("COMMANDER_PUBLIC_CLOUDFLARE_SIX_ARTIFACTS_EXACT_GIT_READBACK=PASS")
        print("COMMANDER_LATEST_CANDIDATE_IS_NOT_SIGNED_RECOVERY_ASSET=TRUE")
        print("COMMANDER_PRODUCTION_MUTATION=FALSE")
        return 0
    except (AssertionError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError,
            urllib.error.URLError, TimeoutError):
        print("COMMANDER_SIGNED_DISTRIBUTION_VERIFICATION=FAILED")
        return 1


if __name__=="__main__":
    raise SystemExit(main())
