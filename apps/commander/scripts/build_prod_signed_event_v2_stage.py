#!/usr/bin/env python3
"""Build a signed-asset-only staging directory for a guarded PROD Worker deploy.

The canonical source Agent may be newer/unsigned. PROD must serve the exact
four published 0.3.41 files whose hashes appear in the signed release manifest.
No private signing key, secret, device token or customer data is accessed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
SIGNED_RELEASE_COMMIT = "08500d5"
EXPECTED_AGENT_VERSION = "0.3.41"
EXPECTED_WORKER_NAME = "hara-commander"
EXPECTED_CANARY_DEVICE = "HARA-DEVICE-e032ffff-f2d2-43ad-b2a8-f5385a900f62"

def require(condition: bool, code: str) -> None:
    if not condition:
        raise SystemExit("EVENT_V2_PROD_STAGE_" + code + "=FAIL")

def run_git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True
    ).stdout

def build(target: Path) -> None:
    require(not target.exists(), "TARGET_MUST_BE_NEW")
    require(target.is_absolute() and str(target).startswith("/tmp_hara/"),
            "TARGET_MUST_BE_PRIVATE_TMP_HARA")
    cfg = json.loads((APP/"wrangler.jsonc").read_text(encoding="utf-8"))
    require(cfg.get("name") == EXPECTED_WORKER_NAME, "WORKER_NAME")
    require(cfg.get("vars", {}).get("ENVIRONMENT") == "PROD", "ENVIRONMENT")
    require(cfg["vars"].get("DEVICE_EVENT_V2_ENABLED") == "true", "FEATURE_FLAG")
    require(cfg["vars"].get("DEVICE_EVENT_V2_CANARY_DEVICE_ID") == EXPECTED_CANARY_DEVICE,
            "CANARY_ALLOWLIST")
    require(cfg["vars"].get("DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED") is None,
            "TRANSIENT_PROD_MUST_BE_DISABLED")
    require(any(row.get("name") == "DEVICE_CHANNEL"
                and row.get("class_name") == "DeviceChannel"
                for row in cfg["durable_objects"]["bindings"]), "DEVICE_CHANNEL_BINDING")
    require(any(row.get("tag") == "v3"
                and row.get("new_sqlite_classes") == ["DeviceChannel"]
                for row in cfg["migrations"]), "MIGRATION_V3")

    manifest_bytes = (APP/"public/release/agent-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    signature = json.loads((APP/"public/release/agent-manifest.sig.json").read_text())
    public = json.loads((APP/"public/release/release-signing-public.jwk").read_text())
    require(signature.get("schema") == "hara.commander-release-signature.v1"
            and signature.get("alg") == "RS256"
            and signature.get("kid") == public.get("kid") == "commander-release-v1"
            and signature.get("manifest_sha256") == hashlib.sha256(manifest_bytes).hexdigest()
            and public.get("kty") == "RSA"
            and not any(field in public for field in ("d","p","q","dp","dq","qi")),
            "SIGNED_MANIFEST_METADATA")
    def b64ud(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * ((-len(value)) % 4))
    signature_bytes = b64ud(str(signature.get("signature") or ""))
    n = int.from_bytes(b64ud(public["n"]), "big")
    exponent = int.from_bytes(b64ud(public["e"]), "big")
    size = (n.bit_length() + 7) // 8
    require(len(signature_bytes) == size, "SIGNATURE_SIZE")
    digest_info = (bytes.fromhex("3031300d060960864801650304020105000420")
                   + hashlib.sha256(manifest_bytes).digest())
    require(size - len(digest_info) - 3 >= 8, "RSA_PADDING_SIZE")
    padded = (b"\x00\x01" + b"\xff" * (size-len(digest_info)-3)
              + b"\x00" + digest_info)
    verified = pow(int.from_bytes(signature_bytes,"big"),exponent,n).to_bytes(size,"big")
    require(verified == padded, "SIGNATURE_VERIFY")
    require(manifest.get("agent_version") == EXPECTED_AGENT_VERSION, "SIGNED_VERSION")
    expected_files = {
        "agent/linux.py", "agent/windows.ps1",
        "install/linux.sh", "install/windows.ps1"
    }
    require({x["path"] for x in manifest.get("files", [])} == expected_files,
            "SIGNED_MANIFEST_FILE_SET")

    target.mkdir(mode=0o700, parents=True)
    os.chmod(target, 0o700)
    dest = target/"apps/commander"
    dest.mkdir(mode=0o700, parents=True)
    shutil.copytree(APP/"src", dest/"src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    shutil.copytree(APP/"public", dest/"public",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    shutil.copytree(APP/"migrations", dest/"migrations")
    shutil.copy2(APP/"wrangler.jsonc", dest/"wrangler.jsonc")
    original_modules = ROOT/"node_modules"
    require(original_modules.is_dir(), "ORIGINAL_NODE_MODULES_MISSING")
    (target/"node_modules").symlink_to(original_modules, target_is_directory=True)

    for item in manifest["files"]:
        rel = item["path"]
        data = run_git("show",
                       SIGNED_RELEASE_COMMIT + ":apps/commander/public/" + rel)
        require(len(data) == item["bytes"], "SIGNED_FILE_SIZE_" + rel.replace("/", "_"))
        require(hashlib.sha256(data).hexdigest() == item["sha256"],
                "SIGNED_FILE_SHA_" + rel.replace("/", "_"))
        (dest/"public"/rel).write_bytes(data)

    for item in manifest["files"]:
        actual = (dest/"public"/item["path"]).read_bytes()
        require(len(actual) == item["bytes"]
                and hashlib.sha256(actual).hexdigest() == item["sha256"],
                "STAGE_ASSET_DRIFT_" + item["path"].replace("/", "_"))

    require((dest/"public/release/agent-manifest.json").read_bytes() == manifest_bytes,
            "MANIFEST_IN_STAGE_CHANGED")
    expected_cfg = json.loads((dest/"wrangler.jsonc").read_text(encoding="utf-8"))
    require(expected_cfg == cfg, "STAGE_CONFIG_CHANGED")

    # Fail-forward emergency kill switch. Preserve the v3 class migration and
    # public signed assets; only disable the Event V2 route and notifications.
    from copy import deepcopy
    disabled_cfg = deepcopy(cfg)
    disabled_cfg["vars"]["DEVICE_EVENT_V2_ENABLED"] = "false"
    rollback_path = dest/"wrangler.event-v2-disabled.jsonc"
    rollback_path.write_text(json.dumps(disabled_cfg, indent=2)+"\n", encoding="utf-8")
    require(json.loads(rollback_path.read_text())["migrations"] == cfg["migrations"],
            "ROLLBACK_MIGRATION_MUST_NOT_REVERSE")
    guard = (dest/"src/worker.js").read_text(encoding="utf-8")
    require('DEVICE_EVENT_V2_CANARY_DENIED' in guard
            and 'env.ENVIRONMENT === "PROD"' in guard, "CANARY_SOURCE_GUARD")

    print("EVENT_V2_PROD_STAGE=PASS")
    print("EVENT_V2_PROD_STAGE_PATH=" + str(dest))
    print("EVENT_V2_SIGNED_ASSETS=EXACT_0.3.41")
    print("EVENT_V2_SIGNED_RSA_RELEASE_MANIFEST=VERIFIED")
    print("EVENT_V2_CUSTOMER_SECRETS_STAGED=FALSE")
    print("EVENT_V2_AGENT_UNSIGNED_0.3.43_EXCLUDED=TRUE")
    print("EVENT_V2_EMERGENCY_DISABLE_CONFIG="+str(rollback_path))
    print("EVENT_V2_CANARY_ONLY=" + EXPECTED_CANARY_DEVICE)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    build(args.target)

if __name__ == "__main__":
    main()
