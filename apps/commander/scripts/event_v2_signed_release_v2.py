#!/usr/bin/env python3
"""Build, sign, and independently verify a separate Event V2 Linux v2 release.

Does not touch the signed v1 public install paths. Private JWK stays in local
custody; only v2 public JWK, manifest and signature are distributable.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
PUBLIC = APP / "public/release/v2/release-signing-public.jwk"
PRIVATE = Path.home() / ".config/hara-commander-release/v2/release-signing-private.jwk"
FINGERPRINT = "93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
VERSION = "0.3.44"
KID = "commander-release-v2"
CANARY_ID = "HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62"
FILES = (
    "public/agent/linux.py",
    "experimental/event_v2_websocket.py",
    "experimental/event_v2_agent_loop.py",
    "experimental/event_v2_customer_agent.py",
    "candidate/event_v2_full_agent.py",
    "candidate/linux_founder_event_v2.py",
)
MANIFEST = "release-v2/agent-manifest.json"
SIGNATURE = "release-v2/agent-manifest.sig.json"
PUBLIC_TARGET = "release-v2/release-signing-public.jwk"


def die(code):
    raise RuntimeError("HARA_EVENT_V2_RELEASE_" + code)


def b64u(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64d(value):
    value = str(value)
    return base64.urlsafe_b64decode(value + "=" * ((-len(value)) % 4))


def integer(value):
    return int.from_bytes(b64d(value), "big")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pure_json(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def load_public():
    obj = json.loads(PUBLIC.read_text(encoding="utf-8"))
    fp = sha(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())
    if fp != FINGERPRINT or obj.get("kid") != KID or obj.get("alg") != "RS256":
        die("PUBLIC_TRUST_ANCHOR_MISMATCH")
    if obj.get("kty") != "RSA" or "d" in obj:
        die("PUBLIC_KEY_INVALID")
    pub = rsa.RSAPublicNumbers(integer(obj["e"]), integer(obj["n"])).public_key()
    if pub.key_size != 3072:
        die("PUBLIC_KEY_STRENGTH_INVALID")
    return obj, pub


def safe_stage(value):
    dest = Path(value).expanduser().resolve()
    if not dest.is_absolute() or not str(dest).startswith("/tmp_hara/"):
        die("STAGE_ROOT_DENIED")
    if dest == Path("/tmp_hara") or dest.is_symlink():
        die("STAGE_ROOT_DENIED")
    return dest


def validate_v1_untouched():
    expected = "e1f44e4695266717c6585f8d0de1e664d99123e36e75b152e136a4428f7b2730"
    manifest = json.loads((APP / "public/release/agent-manifest.json").read_text())
    if manifest["agent_version"] != "0.3.41":
        die("V1_RELEASE_VERSION_DRIFT")
    found = next((v for v in manifest["files"] if v["path"] == "agent/linux.py"), None)
    if not found or found["sha256"] != expected:
        die("V1_SIGNED_MANIFEST_DRIFT")


def prepare(stage):
    load_public()
    validate_v1_untouched()
    if stage.exists():
        die("STAGE_ALREADY_EXISTS")
    stage.mkdir(mode=0o700, parents=True)
    stage.chmod(0o700)
    for rel in FILES:
        source = APP / rel
        if not source.is_file() or source.is_symlink():
            die("SOURCE_MISSING")
        dest = stage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        if rel == "public/agent/linux.py":
            old = b'AGENT_VERSION = "0.3.43"'
            if raw.count(old) != 1:
                die("SOURCE_VERSION_EXPECTATION_FAILED")
            raw = raw.replace(old, b'AGENT_VERSION = "0.3.44"')
        dest.write_bytes(raw)
        dest.chmod(0o700 if rel in (
            "public/agent/linux.py", "candidate/linux_founder_event_v2.py"
        ) else 0o600)
    (stage/"release-v2").mkdir(mode=0o700)
    (stage/PUBLIC_TARGET).write_bytes(PUBLIC.read_bytes())
    rows = []
    for rel in FILES:
        p = stage / rel
        raw = p.read_bytes()
        rows.append({"path": rel, "bytes": len(raw), "sha256": sha(raw)})
    manifest = {
        "schema": "hara.commander-agent-release.v2",
        "agent_version": VERSION,
        "platform": "linux",
        "channel": "FOUNDER_CANARY",
        "device_id": CANARY_ID,
        "kid": KID,
        "entrypoint": "candidate/linux_founder_event_v2.py",
        "files": rows,
    }
    (stage/MANIFEST).write_bytes(pure_json(manifest))
    print("EVENT_V2_V2_STAGE_PREPARED=PASS")
    print("EVENT_V2_V2_STAGE="+str(stage))
    print("EVENT_V2_V2_MANIFEST_SHA256="+sha((stage/MANIFEST).read_bytes()))
    print("EVENT_V2_V1_RELEASE_PRESERVED=TRUE")


def sign(stage):
    public, pub = load_public()
    verify_content(stage)
    if (stage/SIGNATURE).exists():
        die("SIGNATURE_ALREADY_EXISTS")
    if not PRIVATE.is_file() or PRIVATE.is_symlink():
        die("PRIVATE_KEY_CUSTODY_MISSING")
    info = PRIVATE.stat()
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        die("PRIVATE_KEY_PERMISSIONS_INVALID")
    key = json.loads(PRIVATE.read_text(encoding="utf-8"))
    if key.get("kid") != KID or key.get("n") != public["n"] or key.get("e") != public["e"]:
        die("PRIVATE_KEY_PUBLIC_MISMATCH")
    if any(k not in key for k in ("d","p","q","dp","dq","qi")):
        die("PRIVATE_KEY_INCOMPLETE")
    priv = rsa.RSAPrivateNumbers(
        p=integer(key["p"]), q=integer(key["q"]), d=integer(key["d"]),
        dmp1=integer(key["dp"]), dmq1=integer(key["dq"]), iqmp=integer(key["qi"]),
        public_numbers=rsa.RSAPublicNumbers(integer(key["e"]), integer(key["n"]))
    ).private_key()
    data = (stage/MANIFEST).read_bytes()
    sig = priv.sign(data, padding.PKCS1v15(), hashes.SHA256())
    payload = {
        "schema": "hara.commander-agent-signature.v2",
        "alg": "RS256",
        "kid": KID,
        "manifest_sha256": sha(data),
        "signature": b64u(sig),
    }
    (stage/SIGNATURE).write_bytes(pure_json(payload))
    (stage/SIGNATURE).chmod(0o600)
    del priv, key
    print("EVENT_V2_V2_RELEASE_SIGNED=PASS")
    print("EVENT_V2_V2_PRIVATE_JWK_EXPORTED=FALSE")
    verify(stage)


def verify_content(stage):
    pub, _ = load_public()
    data = (stage/MANIFEST).read_bytes()
    obj = json.loads(data)
    if (obj.get("schema") != "hara.commander-agent-release.v2"
        or obj.get("agent_version") != VERSION or obj.get("kid") != KID
        or obj.get("platform") != "linux" or obj.get("device_id") != CANARY_ID
        or obj.get("channel") != "FOUNDER_CANARY"
        or obj.get("entrypoint") != "candidate/linux_founder_event_v2.py"):
        die("MANIFEST_SCHEMA_OR_TARGET_INVALID")
    rows = obj.get("files")
    if not isinstance(rows, list) or {row.get("path") for row in rows} != set(FILES):
        die("MANIFEST_FILE_SET_INVALID")
    for row in rows:
        p = stage / row["path"]
        if not p.is_file() or p.is_symlink():
            die("MANIFEST_FILE_MISSING")
        raw = p.read_bytes()
        if len(raw) != row["bytes"] or sha(raw) != row["sha256"]:
            die("MANIFEST_FILE_TAMPERED")
    if (stage/PUBLIC_TARGET).read_bytes() != PUBLIC.read_bytes():
        die("PUBLIC_KEY_BUNDLE_MISMATCH")
    if b'AGENT_VERSION = "0.3.44"' not in (stage/"public/agent/linux.py").read_bytes():
        die("STAGED_VERSION_INVALID")
    return data


def verify(stage):
    data = verify_content(stage)
    _, pub = load_public()
    signed = json.loads((stage/SIGNATURE).read_text())
    if (signed.get("schema") != "hara.commander-agent-signature.v2"
        or signed.get("kid") != KID or signed.get("alg") != "RS256"
        or signed.get("manifest_sha256") != sha(data)):
        die("SIGNATURE_METADATA_INVALID")
    try:
        pub.verify(b64d(signed["signature"]), data,
                   padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise RuntimeError("HARA_EVENT_V2_RELEASE_SIGNATURE_INVALID") from exc
    print("EVENT_V2_V2_SIGNATURE_VERIFIED=PASS")
    print("EVENT_V2_V2_RELEASE_CONTENT_VERIFIED=PASS")
    print("EVENT_V2_V2_PUBLIC_FINGERPRINT="+FINGERPRINT)
    print("EVENT_V2_V1_RELEASE_PRESERVED=TRUE")


def test(stage):
    verify(stage)
    script = stage / "candidate/linux_founder_event_v2.py"
    p = subprocess.run(["python3",str(script),"--self-test"],
                       capture_output=True, text=True, timeout=35)
    if p.returncode != 0:
        print(p.stdout[-800:])
        die("FOUNDER_SELFTEST_FAILED")
    print(p.stdout[-1200:])
    print("EVENT_V2_V2_LINUX_CANARY_SELFTEST=PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "sign", "verify", "test"))
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    stage = safe_stage(args.stage)
    if args.action == "prepare":
        prepare(stage)
    elif args.action == "sign":
        sign(stage)
    elif args.action == "verify":
        verify(stage)
    else:
        test(stage)


if __name__ == "__main__":
    main()
