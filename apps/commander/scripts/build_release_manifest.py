#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
PUBLIC = APP / "public"
RELEASE_DIR = PUBLIC / "release"
MANIFEST = RELEASE_DIR / "agent-manifest.json"
SUMS = RELEASE_DIR / "SHA256SUMS"
FILES = (
    "agent/linux.py",
    "agent/windows.ps1",
    "install/linux.sh",
    "install/windows.ps1",
)
SCHEMA = "hara.commander-agent-release.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def agent_version() -> str:
    linux = (PUBLIC / "agent/linux.py").read_text(encoding="utf-8")
    windows = (PUBLIC / "agent/windows.ps1").read_text(encoding="utf-8")
    l = re.search(r'^AGENT_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', linux, re.M)
    w = re.search(r'^\$AgentVersion = "([0-9]+\.[0-9]+\.[0-9]+)"$', windows, re.M)
    if not l or not w:
        raise SystemExit("AGENT_VERSION_NOT_FOUND")
    if l.group(1) != w.group(1):
        raise SystemExit("AGENT_VERSION_MISMATCH")
    return l.group(1)


def render() -> tuple[str, str]:
    version = agent_version()
    files = []
    for rel in FILES:
        path = PUBLIC / rel
        if not path.is_file():
            raise SystemExit(f"RELEASE_FILE_MISSING:{rel}")
        files.append({
            "bytes": path.stat().st_size,
            "path": rel,
            "sha256": sha256(path),
        })
    payload = {
        "agent_version": version,
        "channel": "stable",
        "files": files,
        "product": "H.A.R.A. Commander",
        "schema": SCHEMA,
    }
    manifest_text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    sums_text = "".join(f"{item['sha256']}  {item['path']}\n" for item in files)
    return manifest_text, sums_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest_text, sums_text = render()
    if args.check:
        if not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != manifest_text:
            print("COMMANDER_RELEASE_MANIFEST=STALE", file=sys.stderr)
            return 1
        if not SUMS.is_file() or SUMS.read_text(encoding="utf-8") != sums_text:
            print("COMMANDER_RELEASE_SHA256SUMS=STALE", file=sys.stderr)
            return 1
        print("COMMANDER_RELEASE_MANIFEST=PASS")
        print("COMMANDER_RELEASE_SHA256SUMS=PASS")
        return 0
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(manifest_text, encoding="utf-8")
    SUMS.write_text(sums_text, encoding="utf-8")
    print(f"COMMANDER_RELEASE_MANIFEST_WRITTEN={MANIFEST}")
    print(f"COMMANDER_RELEASE_SHA256SUMS_WRITTEN={SUMS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
