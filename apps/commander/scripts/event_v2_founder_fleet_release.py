#!/usr/bin/env python3
"""Build per-device signed Founder-fleet Event V2 Linux 0.3.44 bundles.

A bound signed manifest and bound launcher are generated for each enrolled device.
Only the v2 public key and signed assets leave Services; v1 artifacts are untouched.
This is not a generic public customer installer.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import event_v2_signed_release_v2 as trusted

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path("/tmp_hara/commander-event-v2-0.3.44-founder-signed-v2")
OLD_ID = trusted.CANARY_ID
DEVICE_PATTERN = re.compile(r"^HARA-DEVICE-[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$")
VERIFY_TEMPLATE = ROOT / "apps/commander/scripts/verify_event_v2_bundle_v2.py"


def require(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeError("EVENT_V2_FLEET_" + code)


def make_bundle(destination: Path, device_id: str) -> None:
    require(DEVICE_PATTERN.fullmatch(device_id) is not None, "INVALID_DEVICE_ID")
    require(device_id != OLD_ID, "FOUNDER_CANNOT_BE_REPACKED")
    require(destination.is_absolute() and str(destination).startswith("/tmp_hara/"), "BAD_STAGE")
    require(not destination.exists() and not destination.is_symlink(), "STAGE_EXISTS")
    trusted.verify(SOURCE)
    trusted.validate_v1_untouched()
    public, _ = trusted.load_public()
    require(VERIFY_TEMPLATE.is_file() and not VERIFY_TEMPLATE.is_symlink(), "VERIFIER_SOURCE")

    original = json.loads((SOURCE / trusted.MANIFEST).read_text(encoding="utf-8"))
    require(original.get("channel") == "FOUNDER_CANARY"
            and original.get("device_id") == OLD_ID
            and original.get("agent_version") == "0.3.44", "SOURCE_MANIFEST")
    require({x["path"] for x in original["files"]} == set(trusted.FILES), "SOURCE_FILE_SET")
    destination.mkdir(mode=0o700, parents=True)
    destination.chmod(0o700)
    rows = []
    for src_row in original["files"]:
        rel = src_row["path"]
        require(rel in trusted.FILES and ".." not in Path(rel).parts, "FILE_PATH")
        src = SOURCE / rel
        require(src.is_file() and not src.is_symlink(), "SOURCE_FILE_UNSAFE")
        raw = src.read_bytes()
        require(trusted.sha(raw) == src_row["sha256"]
                and len(raw) == src_row["bytes"], "SOURCE_FILE_HASH")
        if rel == "candidate/linux_founder_event_v2.py":
            before = ('CANARY_DEVICE = "' + OLD_ID + '"').encode()
            after = ('CANARY_DEVICE = "' + device_id + '"').encode()
            require(raw.count(before) == 1, "LAUNCHER_BINDING")
            raw = raw.replace(before, after)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o700 if rel in ("public/agent/linux.py",
                                     "candidate/linux_founder_event_v2.py") else 0o600)
        rows.append({"path": rel, "bytes": len(raw), "sha256": trusted.sha(raw)})

    (destination / "release-v2").mkdir(mode=0o700)
    (destination / trusted.PUBLIC_TARGET).write_bytes(
        (SOURCE / trusted.PUBLIC_TARGET).read_bytes()
    )
    manifest = {**original, "device_id": device_id, "files": rows}
    data = trusted.pure_json(manifest)
    (destination / trusted.MANIFEST).write_bytes(data)
    (destination / trusted.MANIFEST).chmod(0o600)

    # The signing key must remain on Services, owned by the signing user (0600).
    keyfile = trusted.PRIVATE
    require(keyfile.is_file() and not keyfile.is_symlink(), "PRIVATE_KEY_CUSTODY")
    key_stat = keyfile.stat()
    require(key_stat.st_uid == os.getuid()
            and stat.S_IMODE(key_stat.st_mode) == 0o600, "PRIVATE_KEY_PERMISSIONS")
    key = json.loads(keyfile.read_text(encoding="utf-8"))
    require(key.get("kid") == trusted.KID
            and key.get("n") == public["n"]
            and key.get("e") == public["e"], "PRIVATE_PUBLIC_MISMATCH")
    numbers = rsa.RSAPrivateNumbers(
        p=trusted.integer(key["p"]), q=trusted.integer(key["q"]),
        d=trusted.integer(key["d"]), dmp1=trusted.integer(key["dp"]),
        dmq1=trusted.integer(key["dq"]), iqmp=trusted.integer(key["qi"]),
        public_numbers=rsa.RSAPublicNumbers(trusted.integer(key["e"]),
                                             trusted.integer(key["n"])),
    )
    sig = numbers.private_key().sign(data, padding.PKCS1v15(), hashes.SHA256())
    del key, numbers
    signed = {
        "schema": "hara.commander-agent-signature.v2",
        "alg": "RS256",
        "kid": trusted.KID,
        "manifest_sha256": trusted.sha(data),
        "signature": trusted.b64u(sig),
    }
    (destination / trusted.SIGNATURE).write_bytes(trusted.pure_json(signed))
    (destination / trusted.SIGNATURE).chmod(0o600)

    source_verifier = VERIFY_TEMPLATE.read_text(encoding="utf-8")
    anchor = 'CANARY_ID = "' + OLD_ID + '"'
    require(source_verifier.count(anchor) == 1, "VERIFIER_BINDING")
    source_verifier = source_verifier.replace(
        anchor, 'CANARY_ID = "' + device_id + '"'
    )
    metadata_anchor = '    key_path = stage / "release-v2/release-signing-public.jwk"'
    require(source_verifier.count(metadata_anchor) == 1, "VERIFIER_CACHE_ANCHOR")
    source_verifier = source_verifier.replace(
        metadata_anchor,
        '    assert not any(p.name == "__pycache__" or p.suffix == ".pyc" '
        'for p in stage.rglob("*")), "UNSIGNED_BYTECODE_DENIED"\n'
        + metadata_anchor,
    )
    verifier = destination / "verify_release_v2.py"
    verifier.write_text(source_verifier, encoding="utf-8")
    verifier.chmod(0o700)
    subprocess.run([sys.executable, "-B", str(verifier), "--stage", str(destination)],
                   check=True, timeout=30,
                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    subprocess.run([sys.executable, "-B",
                    str(destination / "candidate/linux_founder_event_v2.py"),
                    "--self-test"], check=True, timeout=35,
                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    require(not any(p.name == "__pycache__" or p.suffix == ".pyc"
                    for p in destination.rglob("*")), "UNSIGNED_BYTECODE_GENERATED")
    print("EVENT_V2_FLEET_SIGNED=PASS")
    print("EVENT_V2_FLEET_TARGET=" + device_id)
    print("EVENT_V2_FLEET_STAGE=" + str(destination))
    print("EVENT_V2_FLEET_MANIFEST_SHA256=" + trusted.sha(data))
    print("EVENT_V2_FLEET_PRIVATE_KEY_EXPORTED=FALSE")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--stage", required=True, type=Path)
    args = parser.parse_args()
    make_bundle(args.stage, args.device_id)


if __name__ == "__main__":
    main()
