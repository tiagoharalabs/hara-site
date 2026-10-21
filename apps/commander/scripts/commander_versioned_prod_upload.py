#!/usr/bin/env python3
"""Recheck an exact signed asset tree immediately before version upload.

Default mode is offline and read-only. --execute uploads one version without
deploying it; the returned version still needs independent Cloudflare readback.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from stage_signed_commercial_assets import require_signed_stage
from commander_frozen_worker_source import (
    build_frozen_worker, verify_frozen_worker,
    FROZEN_WORKER_COMMIT, FROZEN_PUBLIC_TREE,
)

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
CONFIG = APP / "wrangler.jsonc"
WRANGLER = ROOT / "node_modules/.bin/wrangler"


def checked_stage(stage: Path, tree_sha256: str, source_public_tree: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", tree_sha256):
        raise RuntimeError("SIGNED_UPLOAD_TREE_SHA256_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40,64}", source_public_tree):
        raise RuntimeError("SIGNED_UPLOAD_SOURCE_TREE_INVALID")
    config = json.loads(CONFIG.read_text())
    if config["assets"]["directory"] != "signed-assets-stage-required":
        raise RuntimeError("SIGNED_UPLOAD_RAW_PUBLIC_CONFIG_DENIED")
    report = require_signed_stage(stage, expected_tree_sha256=tree_sha256)
    if report["source_public_tree"] != source_public_tree:
        raise RuntimeError("SIGNED_UPLOAD_SOURCE_TREE_MISMATCH")
    return report


def run_wrangler_upload(stage: Path, message: str, worker: dict) -> subprocess.CompletedProcess[str]:
    # The reviewed Worker and locked, offline-installed npm dependencies are in
    # the same private snapshot as the signed assets. Never execute from APP.
    path = "/home/sartorius/.nvm/versions/node/v24.15.0/bin:"
    env = os.environ.copy()
    env["PATH"] = path + env.get("PATH", "")
    return subprocess.run(
        [str(worker["wrangler"]), "versions", "upload", "--config",
         str(worker["config"]), "--assets", str(stage), "--message", message],
        cwd=worker["app"], env=env, capture_output=True,
        text=True, timeout=300, check=False,
    )


def copy_snapshot(stage: Path, snapshot: Path) -> None:
    shutil.copytree(stage, snapshot, symlinks=True)


def upload_version(stage: Path, tree_sha256: str, source_public_tree: str,
                   message: str, *, execute: bool = False) -> dict:
    if not message.strip() or len(message) > 140:
        raise RuntimeError("SIGNED_UPLOAD_MESSAGE_INVALID")
    before = checked_stage(stage, tree_sha256, source_public_tree)
    if source_public_tree != FROZEN_PUBLIC_TREE:
        raise RuntimeError("SIGNED_UPLOAD_WORKER_PUBLIC_REF_MISMATCH")
    result = {
        "state": "VERIFIED_NOT_UPLOADED",
        "stage_tree_sha256": before["stage_tree_sha256"],
        "source_public_tree": before["source_public_tree"],
        "signed_manifest_sha256": before["manifest_sha256"],
        "cloud_operations": False,
        "version_content_verified": False,
        "worker_frozen_commit": FROZEN_WORKER_COMMIT,
        "worker_source_verified": False,
    }
    if not execute:
        return result

    # Wrangler reads a private, verified copy. A writer touching the original
    # stage during upload cannot change the bytes Wrangler sees. Preserve the
    # copy until the command exits, then verify both trees again.
    with tempfile.TemporaryDirectory(prefix="hara-commander-upload-") as temporary:
        snapshot = Path(temporary) / "assets"
        copy_snapshot(stage, snapshot)
        checked_stage(snapshot, tree_sha256, source_public_tree)
        worker = build_frozen_worker(Path(temporary) / "worker",
                                     install_dependencies=True)
        verify_frozen_worker(worker)
        # On timeout or error the upload may have succeeded: inspect versions,
        # never retry the mutation without reconciling remote state.
        try:
            proc = run_wrangler_upload(snapshot, message, worker)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise RuntimeError("SIGNED_UPLOAD_OUTCOME_UNKNOWN") from exc
        if proc.returncode:
            raise RuntimeError("SIGNED_UPLOAD_OUTCOME_UNKNOWN:WRANGLER_EXIT_" + str(proc.returncode))
        try:
            checked_stage(snapshot, tree_sha256, source_public_tree)
            checked_stage(stage, tree_sha256, source_public_tree)
            verify_frozen_worker(worker)
        except Exception as exc:
            raise RuntimeError("SIGNED_UPLOAD_OUTCOME_UNKNOWN:STAGE_CHANGED") from exc
    result["state"] = "UPLOAD_SUBMITTED_VERSION_READBACK_REQUIRED"
    result["cloud_operations"] = True
    result["worker_source_verified"] = True
    result["worker_source_sha256"] = worker["source_sha256"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--stage-tree-sha256", required=True)
    parser.add_argument("--source-public-tree", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = upload_version(
        args.stage, args.stage_tree_sha256, args.source_public_tree,
        args.message, execute=args.execute,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
