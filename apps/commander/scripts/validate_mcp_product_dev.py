#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

BASE = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
ISSUER = "https://auth.haralabs.com.br/"
SUBJECT = "391814630923567107"
TOKEN_FILE = pathlib.Path(__file__).resolve().parents[1] / ".generated" / "mcp-product-token"

def post(path: str, body: dict) -> dict:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "HARA-Commander-Product-Validator/1.0",
            "x-hara-mcp-product-token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode() or "{}")
            if resp.status != 200:
                raise RuntimeError(f"HTTP_{resp.status}")
            return payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP_{exc.code}:{detail[:240]}") from exc

def need(cond: bool, code: str) -> None:
    if not cond:
        raise AssertionError(code)

def main() -> int:
    need(TOKEN_FILE.is_file(), "TOKEN_FILE_MISSING")
    need(TOKEN_FILE.stat().st_mode & 0o777 == 0o600, "TOKEN_MODE")
    run_id = str(time.time_ns())

    discovery = post("/api/internal/mcp/authorize", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "tool_id": "hara.health",
        "request_id": "mcp-product-discovery-" + run_id,
    })
    need(discovery.get("allowed") is True, "DISCOVERY_DENIED")
    need(discovery.get("subject", {}).get("oidc_subject") == SUBJECT, "DISCOVERY_SUBJECT")
    print("MCP_PRODUCT_DISCOVERY=PASS")

    release_id = "mcp-product-release-" + run_id
    reserve_release = post("/api/internal/mcp/authorize", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "tool_id": "hara.functions.invoke",
        "function_id": "fleet.list",
        "request_id": release_id,
    })
    need(reserve_release.get("allowed") is True, "RELEASE_RESERVE_DENIED")
    released = post("/api/internal/mcp/release", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "request_id": release_id,
    })
    need(released.get("usage", {}).get("state") == "RELEASED", "RELEASE_STATE")
    print("MCP_PRODUCT_RELEASE=PASS")

    terminal_retry = post("/api/internal/mcp/authorize", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "tool_id": "hara.functions.invoke",
        "function_id": "fleet.list",
        "request_id": release_id,
    })
    need(terminal_retry.get("allowed") is False, "RELEASE_RETRY_ALLOWED")
    need(terminal_retry.get("code") == "REQUEST_USAGE_TERMINAL", "RELEASE_RETRY_CODE")
    print("MCP_PRODUCT_RELEASE_TERMINAL=PASS")

    commit_id = "mcp-product-commit-" + run_id
    reserve_commit = post("/api/internal/mcp/authorize", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "tool_id": "hara.functions.invoke",
        "function_id": "fleet.list",
        "request_id": commit_id,
    })
    need(reserve_commit.get("allowed") is True, "COMMIT_RESERVE_DENIED")
    receipt = hashlib.sha256(b"hara-commander-mcp-product-e2e-20260922").hexdigest()
    committed = post("/api/internal/mcp/commit", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(committed.get("usage", {}).get("state") == "COMMITTED", "COMMIT_STATE")
    print("MCP_PRODUCT_COMMIT=PASS")

    commit_repeat = post("/api/internal/mcp/commit", {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(commit_repeat.get("usage", {}).get("state") == "COMMITTED", "COMMIT_REPEAT_STATE")
    need(commit_repeat.get("usage", {}).get("existing") is True, "COMMIT_REPEAT_IDEMPOTENCY")
    print("MCP_PRODUCT_COMMIT_IDEMPOTENCY=PASS")

    print("MCP_PRODUCT_TOKEN_EXPOSED=FALSE")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MCP_PRODUCT_VALIDATION=FAIL:{exc}", file=sys.stderr)
        raise
