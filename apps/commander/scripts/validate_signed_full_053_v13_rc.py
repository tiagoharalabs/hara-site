#!/usr/bin/env python3
"""Independently verify the full .53 private RC without loading a signer/key."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
BUNDLE = APP / "release-bundles/commercial-0.3.53-v13-rc-r3"
VERSION = "0.3.53"
KID = "commander-release-v2"
PUBLIC_KEY_BYTES_SHA256 = "4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b"
PUBLIC_KEY_CANONICAL_SHA256 = "93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
FILESET = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
EXTRA = ("release/agent-manifest.json", "release/agent-manifest.sig.json",
         "release/release-signing-public.jwk", "release/SHA256SUMS")
REVIEWED_PUBLIC = {
    "agent/linux.py": "db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e",
    "agent/windows.ps1": "f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299",
    "install/linux.sh": "7600f844c24696c7d2e0113328fb39425fa3182ae4e93ab8573d7ce4b74926a2",
    "install/windows.ps1": "114b7dd430641010a95de325a17069cf023f1de95d567718bb50bc3df92ff1b4",
}

class ValidationError(RuntimeError):
    pass

def need(ok, code):
    if not ok:
        raise ValidationError("FULL053_" + code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()

def unb64(value):
    need(isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+", value)),
         "BASE64URL_INVALID")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)

def regular(root, rel):
    need(root.is_dir() and not root.is_symlink(), "BUNDLE_INVALID")
    path = root / rel
    need(path.is_file() and not path.is_symlink(), "FILE_MISSING_OR_SYMLINK")
    parent = path.parent
    while parent != root:
        need(not parent.is_symlink(), "PARENT_SYMLINK")
        parent = parent.parent
    return path.read_bytes()

def repinned_installer(raw, rel, jwk):
    names = (("KID", "kid"), ("N", "n"), ("E", "e")) if rel.endswith(".sh") else (("Kid", "kid"), ("N", "n"), ("E", "e"))
    for label, key in names:
        if rel.endswith(".sh"):
            pattern = rb'RELEASE_SIGNING_' + label.encode() + rb'="[^"]+"'
            replacement = b'RELEASE_SIGNING_' + label.encode() + b'="' + jwk[key].encode() + b'"'
        else:
            pattern = rb'\$ReleaseSigning' + label.encode() + rb' = "[^"]+"'
            replacement = b'$ReleaseSigning' + label.encode() + b' = "' + jwk[key].encode() + b'"'
        raw, count = re.subn(pattern, lambda _: replacement, raw)
        need(count == 1, "INSTALLER_SIGNER_PIN_SCOPE")
    return raw

def verify_bundle(bundle, *, compare_active=True):
    blobs = {rel: regular(bundle, rel) for rel in (*FILESET, *EXTRA)}
    public_raw = blobs["release/release-signing-public.jwk"]
    need(sha(public_raw) == PUBLIC_KEY_BYTES_SHA256, "PINNED_PUBLIC_KEY_BYTES")
    jwk = json.loads(public_raw)
    need(sha(json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode()) ==
         PUBLIC_KEY_CANONICAL_SHA256, "PINNED_PUBLIC_KEY_AUTHORITY")
    need(jwk.get("kty") == "RSA" and jwk.get("alg") == "RS256" and
         jwk.get("kid") == KID, "PUBLIC_KEY_CONTRACT")
    need(not set(jwk).intersection(("d", "p", "q", "dp", "dq", "qi")),
         "PRIVATE_KEY_MATERIAL_FORBIDDEN")
    key = rsa.RSAPublicNumbers(int.from_bytes(unb64(jwk["e"]), "big"),
                              int.from_bytes(unb64(jwk["n"]), "big")).public_key()
    need(key.key_size == 3072, "RSA3072_REQUIRED")
    raw = blobs["release/agent-manifest.json"]
    manifest = json.loads(raw)
    need(raw == canonical(manifest), "MANIFEST_NOT_CANONICAL")
    need(set(manifest) == {"agent_version", "channel", "files", "product", "schema"},
         "MANIFEST_SCOPE")
    need(manifest.get("schema") == "hara.commander-agent-release.v1" and
         manifest.get("agent_version") == VERSION and
         manifest.get("channel") == "stable" and
         manifest.get("product") == "H.A.R.A. Commander", "MANIFEST_VERSION")
    envelope = json.loads(blobs["release/agent-manifest.sig.json"])
    need(set(envelope) == {"alg", "kid", "manifest_sha256", "schema", "signature"},
         "SIGNATURE_ENVELOPE_SCOPE")
    need(envelope.get("schema") == "hara.commander-release-signature.v1" and
         envelope.get("alg") == "RS256" and envelope.get("kid") == KID and
         envelope.get("manifest_sha256") == sha(raw), "SIGNATURE_ENVELOPE")
    try:
        key.verify(unb64(envelope["signature"]), raw, padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise ValidationError("FULL053_SIGNATURE_INVALID") from exc
    rows = manifest["files"]
    need(isinstance(rows, list) and len(rows) == 4 and
         all(isinstance(row, dict) for row in rows) and
         tuple(row.get("path") for row in rows) == FILESET, "EXACT_FILESET")
    for row in rows:
        need(set(row) == {"bytes", "path", "sha256"} and
             type(row["bytes"]) is int and row["bytes"] >= 1 and
             isinstance(row["sha256"], str) and
             bool(re.fullmatch(r"[0-9a-f]{64}", row["sha256"])), "FILE_ROW_CONTRACT")
        data = blobs[row["path"]]
        need(len(data) == row["bytes"] and sha(data) == row["sha256"],
             "FILE_DIGEST:" + row["path"])
    need(blobs["release/SHA256SUMS"] ==
         "".join(f"{row['sha256']}  {row['path']}\n" for row in rows).encode(),
         "CHECKSUM_INDEX")
    linux = blobs["agent/linux.py"].decode("utf-8-sig")
    windows = blobs["agent/windows.ps1"].decode("utf-8-sig")
    need(re.findall(r'(?m)^AGENT_VERSION = "([^"]+)"$', linux) == [VERSION],
         "LINUX_AGENT_MANIFEST_VERSION")
    need(re.findall(r'(?m)^\$AgentVersion = "([^"]+)"$', windows) == [VERSION],
         "WINDOWS_AGENT_MANIFEST_VERSION")
    need(blobs["install/windows.ps1"].count(b'agent_version="0.3.53"') == 3,
         "WINDOWS_INSTALLER_VERSION_SCOPE")
    need(len(re.findall(rb'agent_version"\s*:\s*"0[.]3[.]53"', blobs["install/linux.sh"])) == 3,
         "LINUX_INSTALLER_VERSION_SCOPE")
    if compare_active:
        for rel in FILESET:
            public = regular(APP / "public", rel)
            need(sha(public) == REVIEWED_PUBLIC[rel], "REVIEWED_ACTIVE_SOURCE:" + rel)
            expected = repinned_installer(public, rel, jwk) if rel.startswith("install/") else public
            need(blobs[rel] == expected, "ACTIVE_SOURCE_DRIFT:" + rel)
    return {
        "schema": "hara.commander-full053-signature-validation.v1", "state": "PASS",
        "version": VERSION, "authority": KID, "signature": "RS256_RSA3072",
        "manifest_sha256": sha(raw), "signature_sha256": sha(blobs["release/agent-manifest.sig.json"]),
        "four_files_authenticated": True, "both_agent_versions_match_manifest": True,
        "active_source_checked": compare_active, "signer_loaded": False,
        "private_key_accessed": False, "signing_performed": False,
        "production_deployed": False,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    args = parser.parse_args()
    print(json.dumps(verify_bundle(args.bundle), sort_keys=True))

if __name__ == "__main__":
    main()
