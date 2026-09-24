#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import secrets
import stat
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CONFIG = APP / "wrangler.jsonc"
TOKEN_FILE = APP / ".generated" / "mcp-product-prod-token"
WRANGLER_VERSION = "4.137.0"


def _secure_secret_dir(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("MCP_PRODUCT_TOKEN_DIR_UNSAFE")
    if os.name != "nt":
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise RuntimeError("MCP_PRODUCT_TOKEN_DIR_OWNER")
        path.chmod(0o700)


def _read_existing_token(path: pathlib.Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise RuntimeError("MCP_PRODUCT_TOKEN_FILE_UNSAFE") from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("MCP_PRODUCT_TOKEN_FILE_UNSAFE")
        if os.name != "nt":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise RuntimeError("MCP_PRODUCT_TOKEN_FILE_OWNER")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError("MCP_PRODUCT_TOKEN_FILE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as handle:
            fd = -1
            return handle.read().strip()
    finally:
        if fd >= 0:
            os.close(fd)


def _create_token(path: pathlib.Path) -> str:
    token = secrets.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return _read_existing_token(path)
    except OSError as exc:
        raise RuntimeError("MCP_PRODUCT_TOKEN_FILE_CREATE_FAILED") from exc

    try:
        payload = token.encode("utf-8")
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise RuntimeError("MCP_PRODUCT_TOKEN_FILE_SHORT_WRITE")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    return token


def main() -> int:
    if not CONFIG.is_file():
        print("MCP_PRODUCT_CONFIG=FAIL")
        return 2

    try:
        _secure_secret_dir(TOKEN_FILE.parent)
        token = _read_existing_token(TOKEN_FILE)
        if not token:
            token = _create_token(TOKEN_FILE)
    except RuntimeError as exc:
        print(f"MCP_PRODUCT_TOKEN_FILE=FAIL:{exc}")
        return 3

    if len(token) < 48:
        print("MCP_PRODUCT_TOKEN_FILE=FAIL:MCP_PRODUCT_TOKEN_INVALID")
        return 3

    result = subprocess.run(
        [
            "npx", "--yes", f"wrangler@{WRANGLER_VERSION}",
            "secret", "put", "MCP_PRODUCT_TOKEN",
            "--config", str(CONFIG),
        ],
        cwd=APP,
        text=True,
        input=token + "\n",
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        print("MCP_PRODUCT_WORKER_SECRET=FAIL")
        print(f"MCP_PRODUCT_WORKER_SECRET_EXIT_CODE={result.returncode}")
        print("MCP_PRODUCT_WORKER_SECRET_DETAIL=REDACTED")
        return result.returncode or 1

    print("MCP_PRODUCT_TOKEN_FILE=PASS")
    print("MCP_PRODUCT_TOKEN_MODE=0600")
    print("MCP_PRODUCT_TOKEN_PARENT_MODE=0700")
    print("MCP_PRODUCT_TOKEN_SYMLINK=DENIED")
    print(f"MCP_PRODUCT_WRANGLER_VERSION={WRANGLER_VERSION}")
    print("MCP_PRODUCT_WORKER_SECRET=PASS")
    print("MCP_PRODUCT_TOKEN_VALUE_EXPOSED=FALSE")
    print("MCP_PRODUCT_TOKEN_PATH=" + str(TOKEN_FILE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
