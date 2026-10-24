#!/usr/bin/env python3
"""Provision an isolated DEV-only MCP token for Event V2 canary probes."""

from __future__ import annotations

import argparse
import ast
import os
import secrets
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CONFIG = APP / "wrangler.dev.jsonc"
TOKEN_FILE = APP / ".generated" / "mcp-product-dev-canary-token"
SECRET_NAME = "MCP_PRODUCT_CANARY_TOKEN"
WRANGLER_VERSION = "4.137.0"


def secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("DEV_CANARY_TOKEN_DIR_UNSAFE")
    if os.name != "nt":
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise RuntimeError("DEV_CANARY_TOKEN_DIR_OWNER")
        path.chmod(0o700)


def read_token(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise RuntimeError("DEV_CANARY_TOKEN_FILE_UNSAFE") from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("DEV_CANARY_TOKEN_FILE_UNSAFE")
        if os.name != "nt":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise RuntimeError("DEV_CANARY_TOKEN_FILE_OWNER")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError("DEV_CANARY_TOKEN_FILE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as handle:
            fd = -1
            return handle.read().strip()
    finally:
        if fd >= 0:
            os.close(fd)


def create_token(path: Path) -> str:
    token = secrets.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return read_token(path)
    except OSError as exc:
        raise RuntimeError("DEV_CANARY_TOKEN_FILE_CREATE_FAILED") from exc

    try:
        payload = token.encode("utf-8")
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise RuntimeError("DEV_CANARY_TOKEN_FILE_SHORT_WRITE")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    return token


def self_check() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "print":
            continue
        printed_names = {
            child.id
            for arg in node.args
            for child in ast.walk(arg)
            if isinstance(child, ast.Name)
        }
        if "token" in printed_names:
            raise RuntimeError("DEV_CANARY_TOKEN_SECRET_PRINT_SURFACE")
    assert SECRET_NAME == "MCP_PRODUCT_CANARY_TOKEN"
    assert CONFIG.name == "wrangler.dev.jsonc"
    assert "wrangler.jsonc" not in str(CONFIG)
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_PROVISION_SOURCE=PASS")
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_OUTPUT=ABSENT")
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_CONFIG=DEV_ONLY")


def execute() -> int:
    secure_dir(TOKEN_FILE.parent)
    token = read_token(TOKEN_FILE)
    if not token:
        token = create_token(TOKEN_FILE)
    if len(token) < 48:
        raise RuntimeError("DEV_CANARY_TOKEN_INVALID")

    proc = subprocess.run(
        [
            "npx", "--yes", f"wrangler@{WRANGLER_VERSION}",
            "secret", "put", SECRET_NAME,
            "--config", str(CONFIG),
        ],
        cwd=APP,
        text=True,
        input=token + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=90,
        env=os.environ.copy(),
    )
    token = ""
    if proc.returncode:
        print("COMMANDER_DEV_CANARY_MCP_TOKEN_WORKER=FAIL")
        print("COMMANDER_DEV_CANARY_MCP_TOKEN_DETAIL=REDACTED")
        return proc.returncode or 1

    print("COMMANDER_DEV_CANARY_MCP_TOKEN_FILE=PASS")
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_MODE=0600")
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_WORKER=PASS")
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_VALUE_EXPOSED=FALSE")
    print("COMMANDER_DEV_CANARY_MCP_TOKEN_PATH=" + str(TOKEN_FILE))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if args.execute:
        return execute()
    parser.error("use --check or --execute")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
