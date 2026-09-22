#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import secrets
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CONFIG = APP / ".generated" / "wrangler.remote.dev.json"
TOKEN_FILE = APP / ".generated" / "mcp-product-token"


def main() -> int:
    if not CONFIG.is_file():
        print("MCP_PRODUCT_CONFIG=FAIL")
        return 2

    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 48:
        print("MCP_PRODUCT_TOKEN_FILE=FAIL")
        return 3

    result = subprocess.run(
        ["npx", "wrangler", "secret", "put", "MCP_PRODUCT_TOKEN", "--config", str(CONFIG)],
        cwd=APP,
        text=True,
        input=token + "\n",
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        print("MCP_PRODUCT_WORKER_SECRET=FAIL")
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            print(detail)
        return result.returncode or 1

    print("MCP_PRODUCT_TOKEN_FILE=PASS")
    print("MCP_PRODUCT_TOKEN_MODE=0600")
    print("MCP_PRODUCT_WORKER_SECRET=PASS")
    print("MCP_PRODUCT_TOKEN_VALUE_EXPOSED=FALSE")
    print("MCP_PRODUCT_TOKEN_PATH=" + str(TOKEN_FILE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
