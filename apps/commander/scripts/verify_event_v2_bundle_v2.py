#!/usr/bin/env python3
"""Standalone verifier for the isolated H.A.R.A. Commander Linux v2 bundle.

Pins the independently acknowledged v2 public key fingerprint, validates the
RS256 signature and each manifest-pinned file without requiring secret access.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

TRUSTED_FINGERPRINT = "93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
TRUSTED_KID = "commander-release-v2"
CANARY_ID = "HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62"
EXPECTED_FILES = frozenset({
    "public/agent/linux.py",
    "experimental/event_v2_websocket.py",
    "experimental/event_v2_agent_loop.py",
    "experimental/event_v2_customer_agent.py",
    "candidate/event_v2_full_agent.py",
    "candidate/linux_founder_event_v2.py",
})


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * ((-len(text)) % 4))


def check(stage: Path) -> None:
    stage = stage.expanduser().resolve(strict=True)
    key_path = stage / "release-v2/release-signing-public.jwk"
    manifest_path = stage / "release-v2/agent-manifest.json"
    signature_path = stage / "release-v2/agent-manifest.sig.json"
    for p in (key_path, manifest_path, signature_path):
        assert p.is_file() and not p.is_symlink(), "RELEASE_METADATA_FILE_INVALID"

    key = json.loads(key_path.read_text(encoding="utf-8"))
    raw_key = json.dumps(key, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(raw_key).hexdigest()
    assert fingerprint == TRUSTED_FINGERPRINT, "PUBLIC_TRUST_ANCHOR_MISMATCH"
    assert key["kid"] == TRUSTED_KID and key["alg"] == "RS256" and key["kty"] == "RSA"
    assert not any(k in key for k in ("d","p","q","dp","dq","qi")), "PRIVATE_KEY_EMBEDDED"
    n = int.from_bytes(b64d(key["n"]), "big")
    e = int.from_bytes(b64d(key["e"]), "big")
    public = rsa.RSAPublicNumbers(e, n).public_key()
    assert public.key_size == 3072, "PUBLIC_KEY_STRENGTH"

    data = manifest_path.read_bytes()
    obj = json.loads(data)
    assert (obj.get("schema") == "hara.commander-agent-release.v2"
        and obj.get("agent_version") == "0.3.44"
        and obj.get("kid") == TRUSTED_KID
        and obj.get("channel") == "FOUNDER_CANARY"
        and obj.get("platform") == "linux"
        and obj.get("device_id") == CANARY_ID
        and obj.get("entrypoint") == "candidate/linux_founder_event_v2.py"), "MANIFEST_TARGET_INVALID"
    files = obj.get("files")
    assert isinstance(files, list), "MANIFEST_FILES_INVALID"
    assert {item.get("path") for item in files} == EXPECTED_FILES, "MANIFEST_FILE_SET_INVALID"
    assert len(files) == len(EXPECTED_FILES), "MANIFEST_DUPLICATE_PATH"
    for item in files:
        path = stage / item["path"]
        assert path.is_file() and not path.is_symlink(), "MANIFEST_FILE_MISSING"
        raw = path.read_bytes()
        assert len(raw) == item["bytes"], "MANIFEST_SIZE_MISMATCH"
        assert hashlib.sha256(raw).hexdigest() == item["sha256"], "MANIFEST_HASH_MISMATCH"

    sig = json.loads(signature_path.read_text(encoding="utf-8"))
    assert sig.get("schema") == "hara.commander-agent-signature.v2"
    assert sig.get("kid") == TRUSTED_KID and sig.get("alg") == "RS256"
    assert sig.get("manifest_sha256") == hashlib.sha256(data).hexdigest()
    public.verify(b64d(sig["signature"]), data, padding.PKCS1v15(), hashes.SHA256())
    assert b'AGENT_VERSION = "0.3.44"' in (stage/"public/agent/linux.py").read_bytes()
    print("HARA_EVENT_V2_V2_TRUST_ANCHOR=PASS")
    print("HARA_EVENT_V2_V2_SIGNATURE=PASS")
    print("HARA_EVENT_V2_V2_SIX_ARTIFACTS=PASS")
    print("HARA_EVENT_V2_V2_FOUNDER_CANARY=PASS")
    print("HARA_EVENT_V2_V2_SECRET_KEYS_PRESENT=FALSE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    check(Path(args.stage))
