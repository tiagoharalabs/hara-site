#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
RELEASE = APP / "public" / "release"
MANIFEST = RELEASE / "agent-manifest.json"
SIGNATURE = RELEASE / "agent-manifest.sig.json"
PUBLIC = RELEASE / "release-signing-public.jwk"
LINUX = (APP / "public" / "install" / "linux.sh").read_text(encoding="utf-8")
WINDOWS = (APP / "public" / "install" / "windows.ps1").read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_RELEASE_TRUST_{code}=FAIL")
    print(f"COMMANDER_RELEASE_TRUST_{code}=PASS")


def b64ud(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def verify(data: bytes, signature: str, public: dict) -> bool:
    try:
        sig = b64ud(signature)
        n = int.from_bytes(b64ud(public["n"]), "big")
        e = int.from_bytes(b64ud(public["e"]), "big")
        size = (n.bit_length() + 7) // 8
        if len(sig) != size:
            return False
        em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(size, "big")
        digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(data).digest()
        padding = size - len(digest_info) - 3
        if padding < 8:
            return False
        expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
        return em == expected
    except Exception:
        return False


manifest = MANIFEST.read_bytes()
sig = json.loads(SIGNATURE.read_text(encoding="utf-8"))
public = json.loads(PUBLIC.read_text(encoding="utf-8"))

need(sig.get("schema") == "hara.commander-release-signature.v1", "SCHEMA")
need(sig.get("alg") == "RS256", "ALG")
need(sig.get("kid") == "commander-release-v1", "KID")
need(public.get("kty") == "RSA" and public.get("alg") == "RS256", "PUBLIC_KEY")
need(public.get("kid") == sig.get("kid"), "PUBLIC_KID")
need(not any(key in public for key in ("d", "p", "q", "dp", "dq", "qi")), "PUBLIC_NO_PRIVATE_FIELDS")
need(sig.get("manifest_sha256") == hashlib.sha256(manifest).hexdigest(), "MANIFEST_HASH")
need(verify(manifest, str(sig.get("signature") or ""), public), "SIGNATURE_VERIFY")
need(not verify(manifest + b"\n", str(sig.get("signature") or ""), public), "TAMPER_DENIED")

n = str(public["n"])
e = str(public["e"])
need('RELEASE_SIGNING_KID="commander-release-v1"' in LINUX, "LINUX_KID_PIN")
need(n in LINUX and e in LINUX, "LINUX_KEY_PIN")
need("agent-manifest.sig.json" in LINUX, "LINUX_SIGNATURE_FETCH")
need("verify_release_manifest_signature" in LINUX, "LINUX_SIGNATURE_VERIFY")
need("AGENT_RELEASE_SIGNATURE_INVALID" in LINUX, "LINUX_FAIL_CLOSED")
need('"release_signature":True' in LINUX, "LINUX_PREFLIGHT_ATTESTS_SIGNATURE")

need('$ReleaseSigningKid = "commander-release-v1"' in WINDOWS, "WINDOWS_KID_PIN")
need(n in WINDOWS and e in WINDOWS, "WINDOWS_KEY_PIN")
need("agent-manifest.sig.json" in WINDOWS, "WINDOWS_SIGNATURE_FETCH")
need("Assert-ReleaseManifestSignature" in WINDOWS, "WINDOWS_SIGNATURE_VERIFY")
need("AGENT_RELEASE_SIGNATURE_INVALID" in WINDOWS, "WINDOWS_FAIL_CLOSED")
need("release_signature = $true" in WINDOWS, "WINDOWS_PREFLIGHT_ATTESTS_SIGNATURE")
need("[IO.File]::ReadAllBytes($manifestPath)" in WINDOWS, "WINDOWS_EXACT_BYTES")

tracked = subprocess.run(
    ["git", "ls-files"],
    cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    check=True,
).stdout.splitlines()
private_candidates = [name for name in tracked if "release-signing-private" in name.lower()]
need(not private_candidates, "PRIVATE_KEY_NOT_TRACKED")

for rel in tracked:
    if not rel.startswith("apps/commander/"):
        continue
    if rel == "apps/commander/scripts/validate_release_signature.py":
        continue
    path = ROOT / rel
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        continue
    if '"kid": "commander-release-v1"' in text and '"d":' in text:
        raise SystemExit("COMMANDER_RELEASE_TRUST_PRIVATE_JWK_SOURCE_LEAK=FAIL")
print("COMMANDER_RELEASE_TRUST_PRIVATE_JWK_SOURCE_LEAK=PASS")

print("COMMANDER_RELEASE_TRUST=PASS")
