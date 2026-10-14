#!/usr/bin/env python3
"""Prepare, sign, verify a commercial signed release in a PRIVATE STAGING DIRECTORY.

The v1 release signing key is unavailable for this distribution. Reuse the
already-custodied v2 3072-bit release signing authority with its public pin,
while keeping the public v1 Git tag immutable. A new v2-trusted bootstrap
installer is signed together with both agents. No Cloudflare/Git mutations.
Never prints signing material, machine credentials, or entire manifests.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
PUB = APP / "public/release/v2/release-signing-public.jwk"
SECRET = Path.home() / ".config/hara-commander-release/v2/release-signing-private.jwk"
FP = "93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
KID = "commander-release-v2"
VERSION = "0.3.43"
FILESET = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
RELEASE_CONFIG = "apps/commander/wrangler.jsonc"


class ReleaseError(RuntimeError):
    pass


def die(code: str):
    raise ReleaseError("COMMERCIAL_SIGNED_V2_" + code)


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def integer(text: str) -> int:
    return int.from_bytes(unb64(text), "big")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def public_key():
    payload = json.loads(PUB.read_text(encoding="utf-8"))
    digest = sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    if digest != FP or payload.get("kid") != KID or payload.get("alg") != "RS256" or payload.get("kty") != "RSA":
        die("PUBLIC_TRUST_ANCHOR_MISMATCH")
    if any(k in payload for k in ("d", "p", "q", "dp", "dq", "qi")):
        die("UNSAFE_PUBLIC_JWK")
    key = rsa.RSAPublicNumbers(integer(payload["e"]), integer(payload["n"])).public_key()
    if key.key_size != 3072:
        die("KEY_SIZE_INVALID")
    return payload, key


def protect(stage_text: str) -> Path:
    stage = Path(stage_text).resolve()
    if str(stage) == "/tmp_hara" or not str(stage).startswith("/tmp_hara/"):
        die("STAGING_LOCATION_DENIED")
    if stage.is_symlink():
        die("STAGING_SYMLINK_DENIED")
    return stage


def replace_once(source: bytes, expression: bytes, replacement: bytes) -> bytes:
    updated, count = re.subn(expression, lambda _: replacement, source)
    if count != 1:
        die("INSTALLER_PIN_REPLACEMENT_MISMATCH")
    return updated


def populate(stage: Path):
    if stage.exists():
        die("STAGE_ALREADY_EXISTS")
    stage.mkdir(mode=0o700, parents=True)
    target = stage / "apps/commander"
    for folder in ("src", "migrations", "public"):
        shutil.copytree(APP/folder, target/folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    shutil.copy2(APP/"wrangler.jsonc", target/"wrangler.jsonc")
    # Freeze production-proven commercial 0.3.43 agents/Windows installer.
    # Only the Linux bootstrap policy changes in this release candidate.
    frozen = APP/"release-bundles/commercial-0.3.43-v3"
    pinned = {
        "agent/linux.py": "3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7",
        "agent/windows.ps1": "d507a6f91a635b025ef4f06cbd758a03c7da6f3410aadec9a3d76c28f904c6fb",
        "install/windows.ps1": "d0f6d7e3a79a87e439a6275ebf60b2918ad5ccdbc28666ce18288644f3d595b9",
    }
    for relative, expected in pinned.items():
        data=(frozen/relative).read_bytes()
        if sha(data)!=expected:
            die("FROZEN_COMMERCIAL_INPUT_DRIFT")
        (target/"public"/relative).write_bytes(data)
    node = ROOT/"node_modules"
    if not node.is_dir():
        die("NPM_DEPENDENCIES_MISSING")
    (stage/"node_modules").symlink_to(node, target_is_directory=True)
    public, _ = public_key()
    for rel in ("install/linux.sh", "install/windows.ps1"):
        file = target/"public"/rel
        data = file.read_bytes()
        if rel.endswith("linux.sh"):
            data = replace_once(data, b'RELEASE_SIGNING_KID="[^"]+"',
                                b'RELEASE_SIGNING_KID="'+KID.encode()+b'"')
            data = replace_once(data, b'RELEASE_SIGNING_N="[^"]+"',
                                b'RELEASE_SIGNING_N="'+public["n"].encode()+b'"')
            data = replace_once(data, b'RELEASE_SIGNING_E="[^"]+"',
                                b'RELEASE_SIGNING_E="'+public["e"].encode()+b'"')
        else:
            data = replace_once(data, rb'\$ReleaseSigningKid = "[^"]+"',
                                b'$ReleaseSigningKid = "'+KID.encode()+b'"')
            data = replace_once(data, rb'\$ReleaseSigningN = "[^"]+"',
                                b'$ReleaseSigningN = "'+public["n"].encode()+b'"')
            data = replace_once(data, rb'\$ReleaseSigningE = "[^"]+"',
                                b'$ReleaseSigningE = "'+public["e"].encode()+b'"')
        file.write_bytes(data)
    (target/"public/release/release-signing-public.jwk").write_bytes(PUB.read_bytes())
    manifest = {
        "agent_version": VERSION,
        "channel": "stable",
        "files": [{
            "bytes": len((target/"public"/rel).read_bytes()),
            "path": rel,
            "sha256": sha((target/"public"/rel).read_bytes()),
        } for rel in FILESET],
        "product": "H.A.R.A. Commander",
        "schema": "hara.commander-agent-release.v1",
    }
    (target/"public/release/agent-manifest.json").write_bytes(json_bytes(manifest))
    # Discard the copied v1 signature in the PRIVATE staging tree only;
    # the v2 signer must produce a fresh signature for the new manifest.
    (target/"public/release/agent-manifest.sig.json").unlink()
    (target/"public/release/SHA256SUMS").write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in manifest["files"]),
        encoding="utf-8")
    for keypath in ("agent/linux.py","agent/windows.ps1"):
        source = (target/"public"/keypath).read_text()
        if VERSION not in source:
            die("AGENT_VERSION_INVALID")
    print("COMMERCIAL_SIGNED_V2_STAGE_PREPARED=PASS")
    print("COMMERCIAL_SIGNED_V2_STAGE_PATH="+str(target))
    print("COMMERCIAL_SIGNED_V2_SOURCE_V1_UNCHANGED=TRUE")


def verify(stage: Path):
    target = stage/"apps/commander/public"
    public, key = public_key()
    manifest_data=(target/"release/agent-manifest.json").read_bytes()
    obj=json.loads(manifest_data)
    if obj.get("agent_version") != VERSION or obj.get("schema") != "hara.commander-agent-release.v1":
        die("MANIFEST_SCHEMA_INVALID")
    if {r["path"] for r in obj["files"]} != set(FILESET):
        die("MANIFEST_FILESET_INVALID")
    for row in obj["files"]:
        f=target/row["path"]
        data=f.read_bytes()
        if len(data)!=row["bytes"] or sha(data)!=row["sha256"]:
            die("FILE_HASH_MISMATCH")
    digest_sha=sha(manifest_data)
    signature=json.loads((target/"release/agent-manifest.sig.json").read_text())
    if signature.get("alg")!="RS256" or signature.get("kid")!=KID or signature.get("schema")!="hara.commander-release-signature.v1" or signature.get("manifest_sha256")!=digest_sha:
        die("SIGNATURE_METADATA_INVALID")
    try:
        key.verify(unb64(signature["signature"]),manifest_data,padding.PKCS1v15(),hashes.SHA256())
    except Exception:
        die("SIGNATURE_INVALID")
    linux=(target/"install/linux.sh").read_bytes()
    windows=(target/"install/windows.ps1").read_bytes()
    if (b'AGENT_AUTOSTART="${HARA_COMMANDER_AGENT_AUTOSTART:-ON}"' not in linux
        or b'systemctl --user enable --now "$SERVICE"' not in linux
        or b'systemctl --user disable "$SERVICE"' not in linux
        or b'loginctl enable-linger' not in linux):
        die("AUTO_RECONNECT_POLICY_MISSING")
    if b"New-ScheduledTaskTrigger -AtLogOn" in windows or b"New-ScheduledTaskTrigger -AtStartup" in windows:
        die("WINDOWS_MANUAL_ONLY_POLICY_BROKEN")
    if b'HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION' not in (target/"index.html").read_bytes():
        die("PORTAL_APPROVAL_POLICY_DRIFT")
    if b"10.000 chamadas" not in (target/"index.html").read_bytes():
        die("PORTAL_FREE_QUOTA_DRIFT")
    if b'RELEASE_SIGNING_KID="'+KID.encode()+b'"' not in linux:
        die("LINUX_BOOTSTRAP_KEY_MISMATCH")
    if b'$ReleaseSigningKid = "'+KID.encode()+b'"' not in windows:
        die("WINDOWS_BOOTSTRAP_KEY_MISMATCH")
    print("COMMERCIAL_SIGNED_V2_SIGNATURE_RSA3072=PASS")
    print("COMMERCIAL_SIGNED_V2_FOUR_FILE_SHA=PASS")
    print("COMMERCIAL_SIGNED_V2_LINUX_AUTO_RECONNECT=PASS")
    print("COMMERCIAL_SIGNED_V2_WINDOWS_MANUAL_BETA_PRESERVED=PASS")
    print("COMMERCIAL_SIGNED_V2_APP_ORIGIN_RELEASE_VERSION="+VERSION)
    print("COMMERCIAL_SIGNED_V2_PRODUCTION_MUTATION=FALSE")


def sign(stage: Path):
    if not SECRET.is_file() or SECRET.is_symlink():
        die("KEY_NOT_CUSTODIED")
    if stat.S_IMODE(SECRET.stat().st_mode)!=0o600 or SECRET.stat().st_uid!=os.getuid():
        die("KEY_PERMISSION_DENIED")
    public,_=public_key()
    private=json.loads(SECRET.read_text(encoding="utf-8"))
    if any(private.get(field)!=public.get(field) for field in ("n","e","kid")):
        die("PRIVATE_PUBLIC_MISMATCH")
    if any(name not in private for name in ("d","p","q","dp","dq","qi")):
        die("INCOMPLETE_KEY")
    priv=rsa.RSAPrivateNumbers(
        p=integer(private["p"]),q=integer(private["q"]),d=integer(private["d"]),
        dmp1=integer(private["dp"]),dmq1=integer(private["dq"]),iqmp=integer(private["qi"]),
        public_numbers=rsa.RSAPublicNumbers(integer(public["e"]),integer(public["n"]))).private_key()
    data=(stage/"apps/commander/public/release/agent-manifest.json").read_bytes()
    signature=priv.sign(data,padding.PKCS1v15(),hashes.SHA256())
    dest=stage/"apps/commander/public/release/agent-manifest.sig.json"
    if dest.exists():
        die("SIGNATURE_ALREADY_EXISTS")
    dest.write_bytes(json_bytes({
       "alg":"RS256","kid":KID,"manifest_sha256":sha(data),
       "schema":"hara.commander-release-signature.v1","signature":b64(signature)
    }))
    del private,priv
    print("COMMERCIAL_SIGNED_V2_CRYPTOGRAPHIC_SIGNING=PASS")
    print("COMMERCIAL_SIGNED_V2_PRIVATE_KEY_EXPORTED=FALSE")
    verify(stage)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare","sign","verify"))
    parser.add_argument("--stage",required=True)
    args=parser.parse_args()
    stage=protect(args.stage)
    if args.action=="prepare":populate(stage)
    elif args.action=="sign":sign(stage)
    else:verify(stage)


if __name__=="__main__":
    main()
