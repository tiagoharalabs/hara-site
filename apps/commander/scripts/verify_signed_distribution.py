#!/usr/bin/env python3
"""Verify a complete signed Commander release before it becomes public assets.

The manifest's SHA-256 values prove file consistency only after the manifest's
RS256 signature has been checked against the pinned release authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

APP = Path(__file__).resolve().parents[1]
PINNED_KEY = APP / "public/release/v2/release-signing-public.jwk"
PINNED_KEY_SHA256 = "93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
KID = "commander-release-v2"
FILES = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
METADATA = (
    "release/agent-manifest.json", "release/agent-manifest.sig.json",
    "release/release-signing-public.jwk", "release/SHA256SUMS",
)


class ReleaseValidationError(RuntimeError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ReleaseValidationError("SIGNED_DISTRIBUTION_" + code)


def b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_bytes(root: Path, relative: str) -> bytes:
    file = root / relative
    require(not root.is_symlink() and root.is_dir(), "UNSAFE_BUNDLE_ROOT")
    require(all(not parent.is_symlink() for parent in (file, *file.parents) if parent == root or root in parent.parents),
            "UNSAFE_BUNDLE_PATH")
    require(file.is_file(), "FILE_MISSING:" + relative)
    return file.read_bytes()


def version(data: bytes, expression: bytes, platform: str) -> str:
    found = re.findall(expression, data, re.M)
    require(len(found) == 1, "AGENT_VERSION_INVALID:" + platform)
    return found[0].decode("ascii")


def verify_bundle(bundle: Path) -> dict:
    """Return verified release metadata or fail closed with a stable code."""
    root = Path(bundle)
    manifest_raw = safe_bytes(root, METADATA[0])
    signature_raw = safe_bytes(root, METADATA[1])
    public_raw = safe_bytes(root, METADATA[2])
    sums_raw = safe_bytes(root, METADATA[3])
    try:
        manifest = json.loads(manifest_raw)
        signature = json.loads(signature_raw)
        public = json.loads(public_raw)
        pinned = json.loads(PINNED_KEY.read_bytes())
        require(sha(json.dumps(pinned, sort_keys=True, separators=(",", ":")).encode()) == PINNED_KEY_SHA256,
                "TRUST_ANCHOR_INVALID")
        require(public == pinned and public.get("kty") == "RSA" and
                public.get("alg") == "RS256" and public.get("kid") == KID and
                not any(field in public for field in ("d", "p", "q", "dp", "dq", "qi")),
                "TRUST_ANCHOR_MISMATCH")
        require(signature.get("schema") == "hara.commander-release-signature.v1" and
                signature.get("alg") == "RS256" and signature.get("kid") == KID and
                signature.get("manifest_sha256") == sha(manifest_raw), "SIGNATURE_METADATA_INVALID")
        key = rsa.RSAPublicNumbers(
            int.from_bytes(b64d(public["e"]), "big"),
            int.from_bytes(b64d(public["n"]), "big"),
        ).public_key()
        require(key.key_size == 3072, "KEY_SIZE_INVALID")
        try:
            key.verify(b64d(signature["signature"]), manifest_raw,
                       padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature as exc:
            raise ReleaseValidationError("SIGNED_DISTRIBUTION_SIGNATURE_INVALID") from exc
        require(manifest.get("schema") == "hara.commander-agent-release.v1" and
                manifest.get("channel") == "stable" and
                re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(manifest.get("agent_version", ""))) is not None,
                "MANIFEST_INVALID")
        rows = manifest.get("files")
        require(isinstance(rows, list) and len(rows) == len(FILES) and
                all(isinstance(row, dict) for row in rows) and
                tuple(row.get("path") for row in rows) == FILES, "FILESET_INVALID")
        blobs = {}
        for row in rows:
            relative = row["path"]
            data = safe_bytes(root, relative)
            require(type(row.get("bytes")) is int and row["bytes"] == len(data) and
                    row.get("sha256") == sha(data), "FILE_HASH_MISMATCH:" + relative)
            blobs[relative] = data
        expected_sums = "".join(f"{row['sha256']}  {row['path']}\n" for row in rows).encode()
        require(sums_raw == expected_sums, "SHA256SUMS_MISMATCH")
        linux_version = version(blobs["agent/linux.py"],
                                rb'^AGENT_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', "linux")
        windows_version = version(blobs["agent/windows.ps1"],
                                  rb'^\$AgentVersion = "([0-9]+\.[0-9]+\.[0-9]+)"$', "windows")
        require(linux_version == windows_version == manifest["agent_version"],
                "AGENT_VERSION_MISMATCH")
        linux = blobs["install/linux.sh"]
        windows = blobs["install/windows.ps1"]
        for label, value in ((b"KID", public["kid"].encode()),
                             (b"N", public["n"].encode()),
                             (b"E", public["e"].encode())):
            require(b'RELEASE_SIGNING_' + label + b'="' + value + b'"' in linux and
                    b'$ReleaseSigning' + label.title() + b' = "' + value + b'"' in windows,
                    "INSTALLER_TRUST_PIN_MISMATCH")
        return {"agent_version": manifest["agent_version"],
                "manifest_sha256": sha(manifest_raw),
                "files": {row["path"]: row["sha256"] for row in rows},
                "signature": "RS256_RSA3072_VALID"}
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError("SIGNED_DISTRIBUTION_MALFORMED") from exc
