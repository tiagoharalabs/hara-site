#!/usr/bin/env python3
"""Materialize a pinned Commander Worker+toolchain for VERSION UPLOAD.

Git source is selected by the review ref; it is NEVER copied from an active
worktree. Dependencies are installed from the reviewed lockfile using offline
npm ci with lifecycle scripts disabled. Does not access Cloudflare/credentials.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[3]
FROZEN_WORKER_COMMIT = "c90907c6bd41d56411466542e01a3224538b76c1"
FROZEN_SOURCE_TREE = "f9afa5a4611cda6c6d87074bf8923574a9d0c6cd"
FROZEN_CONFIG_BLOB = "e68e5d64997a6a111502723297d7d83aa0928873"
FROZEN_LOCK_BLOB = "bb9fcc5c8001fe4e7b567df8f34b802191d938a6"
FROZEN_PUBLIC_TREE = "2138ef35e0f9bee92888e1bcf7bb5212956170bd"
LOCKED_WRANGLER_VERSION = "4.85.0"
ARCHIVE_PATHS = (
    "package.json",
    "package-lock.json",
    "apps/commander/package.json",
    "apps/commander/wrangler.jsonc",
    "apps/commander/src",
    "apps/commander/migrations",
)

class FrozenWorkerError(RuntimeError):
    pass

def run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        timeout=7, check=False,
    )
    if proc.returncode:
        raise FrozenWorkerError("WORKER_FROZEN_GIT_UNAVAILABLE")
    return proc.stdout.strip()

def require_frozen_git_objects() -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", FROZEN_WORKER_COMMIT):
        raise FrozenWorkerError("WORKER_FROZEN_COMMIT_INVALID")
    if run_git("rev-parse", FROZEN_WORKER_COMMIT+"^{commit}") != FROZEN_WORKER_COMMIT:
        raise FrozenWorkerError("WORKER_FROZEN_COMMIT_CHANGED")
    required = {
        "apps/commander/src": FROZEN_SOURCE_TREE,
        "apps/commander/wrangler.jsonc": FROZEN_CONFIG_BLOB,
        "package-lock.json": FROZEN_LOCK_BLOB,
        "apps/commander/public": FROZEN_PUBLIC_TREE,
    }
    for relative, expected in required.items():
        if run_git("rev-parse", FROZEN_WORKER_COMMIT+":"+relative) != expected:
            raise FrozenWorkerError("WORKER_FROZEN_GIT_OBJECT_MISMATCH:"+relative)

def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_digest(destination: Path) -> str:
    entries = []
    for relative in ARCHIVE_PATHS:
        p = destination / relative
        if p.is_file():
            entries.append([relative, file_sha(p)])
        elif p.is_dir():
            for leaf in sorted(p.rglob("*")):
                if leaf.is_file():
                    entries.append([leaf.relative_to(destination).as_posix(), file_sha(leaf)])
                elif leaf.is_symlink():
                    raise FrozenWorkerError("WORKER_ARCHIVE_SYMLINK_DENIED")
        else:
            raise FrozenWorkerError("WORKER_ARCHIVE_PATH_MISSING:"+relative)
    return hashlib.sha256(json.dumps(entries,separators=(",",":")).encode()).hexdigest()

def _extract_archive(destination: Path) -> None:
    cmd = ["git","archive","--format=tar",FROZEN_WORKER_COMMIT,*ARCHIVE_PATHS]
    proc = subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=12,check=False)
    if proc.returncode:
        raise FrozenWorkerError("WORKER_FROZEN_ARCHIVE_FAILED")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout),mode="r:") as bundle:
        members = bundle.getmembers()
        for item in members:
            pure = PurePosixPath(item.name)
            if pure.is_absolute() or ".." in pure.parts or not (item.isfile() or item.isdir()):
                raise FrozenWorkerError("WORKER_FROZEN_ARCHIVE_UNSAFE_ENTRY")
            target = destination.joinpath(*pure.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise FrozenWorkerError("WORKER_FROZEN_ARCHIVE_ESCAPE")
        bundle.extractall(destination,filter="data")

def build_frozen_worker(root: Path, *, install_dependencies: bool = True) -> dict:
    """Create a NEW private directory. Never accept or modify an existing one."""
    require_frozen_git_objects()
    if not root.is_absolute() or root.exists() or root.is_symlink():
        raise FrozenWorkerError("WORKER_SNAPSHOT_DESTINATION_UNSAFE")
    if not root.parent.is_dir() or root.parent.is_symlink():
        raise FrozenWorkerError("WORKER_SNAPSHOT_PARENT_UNSAFE")
    root.mkdir(mode=0o700)
    _extract_archive(root)
    digest = source_digest(root)
    config_path = root/"apps/commander/wrangler.jsonc"
    config = json.loads(config_path.read_text())
    if config.get("name") != "hara-commander" or config.get("main") != "src/worker.js":
        raise FrozenWorkerError("WORKER_CONFIG_ENTRYPOINT_DRIFT")
    assets = config.get("assets",{})
    if assets.get("directory") != "signed-assets-stage-required":
        raise FrozenWorkerError("WORKER_CONFIG_SIGNED_STAGE_REQUIRED")
    if config.get("vars",{}).get("ENVIRONMENT") != "PROD":
        raise FrozenWorkerError("WORKER_CONFIG_ENVIRONMENT_DRIFT")
    lock = json.loads((root/"package-lock.json").read_text())
    wrangler = lock.get("packages",{}).get("node_modules/wrangler",{}).get("version")
    if wrangler != LOCKED_WRANGLER_VERSION:
        raise FrozenWorkerError("WORKER_WRANGLER_LOCK_VERSION_DRIFT")
    if install_dependencies:
        npm = "/home/sartorius/.nvm/versions/node/v24.15.0/bin/npm"
        if not Path(npm).is_file():
            raise FrozenWorkerError("WORKER_NPM_NOT_AVAILABLE")
        env = os.environ.copy()
        env["PATH"] = str(Path(npm).parent)+":"+env.get("PATH","")
        cmd = [npm,"ci","--offline","--ignore-scripts","--no-audit","--no-fund"]
        result = subprocess.run(cmd,cwd=root,capture_output=True,text=True,
                                timeout=150,check=False,env=env)
        if result.returncode:
            raise FrozenWorkerError("WORKER_OFFLINE_LOCKED_NPM_INSTALL_FAILED")
        binary = root/"node_modules/.bin/wrangler"
        if not binary.exists():
            raise FrozenWorkerError("WORKER_WRANGLER_NOT_INSTALLED")
        result = subprocess.run([str(binary),"--version"],cwd=root,
                                capture_output=True,text=True,timeout=10,env=env)
        if result.returncode or LOCKED_WRANGLER_VERSION not in result.stdout:
            raise FrozenWorkerError("WORKER_WRANGLER_RUNTIME_VERSION_DRIFT")
    if source_digest(root)!=digest:
        raise FrozenWorkerError("WORKER_SNAPSHOT_SOURCE_CHANGED")
    return {"root":root,"app":root/"apps/commander",
            "config":config_path,"wrangler":root/"node_modules/.bin/wrangler",
            "source_sha256":digest,"frozen_commit":FROZEN_WORKER_COMMIT,
            "source_tree":FROZEN_SOURCE_TREE,"lock_blob":FROZEN_LOCK_BLOB,
            "dependencies_provisioned":bool(install_dependencies)}

def verify_frozen_worker(info: dict) -> None:
    if source_digest(info["root"]) != info["source_sha256"]:
        raise FrozenWorkerError("WORKER_SNAPSHOT_SOURCE_CHANGED")
    require_frozen_git_objects()
