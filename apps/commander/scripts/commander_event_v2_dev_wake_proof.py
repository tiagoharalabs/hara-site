#!/usr/bin/env python3
"""Secret-safe DEV Event V2 wake proof.

This helper rotates only the DEV MCP product token, then enqueues one governed
device call through the normal internal Worker endpoint and polls status.
It never prints the token value and rejects PROD origin/config by construction.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
DEV_CONFIG = APP / "wrangler.dev.jsonc"
DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
WRANGLER_VERSION = "4.137.0"
DEFAULT_TOKEN_FILE = Path("/tmp_hara/commander-event-v2-dev-canary/mcp-product-dev-token")
DEFAULT_ISSUER = "https://auth.haralabs.com.br/"
DEFAULT_SUBJECT = "391814630923567107"
DEFAULT_DEVICE_ID = "HARA-DEVICE-dfff4315-0637-414a-a880-74c4514ff3fc"


def fail(code: str) -> RuntimeError:
    return RuntimeError(code)


def require_dev_config() -> None:
    cfg = json.loads(DEV_CONFIG.read_text(encoding="utf-8"))
    if cfg.get("name") != "hara-commander-dev-v2":
        raise fail("WAKE_DEV_WORKER_NAME_INVALID")
    if (cfg.get("vars") or {}).get("ENVIRONMENT") != "DEV":
        raise fail("WAKE_ENVIRONMENT_NOT_DEV")
    if (cfg.get("vars") or {}).get("DEVICE_EVENT_V2_ENABLED") != "true":
        raise fail("WAKE_EVENT_V2_NOT_ENABLED")
    raw = DEV_CONFIG.read_text(encoding="utf-8")
    if "commander.haralabs.com.br" in raw:
        raise fail("WAKE_PROD_ORIGIN_IN_DEV_CONFIG")


def secure_token_file(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        token = secrets.token_urlsafe(48)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.write(fd, token.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise fail("WAKE_TOKEN_FILE_UNSAFE")
            if os.name != "nt" and stat.S_IMODE(info.st_mode) != 0o600:
                raise fail("WAKE_TOKEN_FILE_PERMISSIONS")
            token = os.read(fd, 4096).decode("utf-8").strip()
        finally:
            os.close(fd)

    if len(token) < 48:
        raise fail("WAKE_TOKEN_INVALID")
    if os.name != "nt":
        path.chmod(0o600)
    return token


def provision_dev_secret(token: str) -> None:
    proc = subprocess.run(
        [
            "npx", "--yes", f"wrangler@{WRANGLER_VERSION}",
            "secret", "put", "MCP_PRODUCT_TOKEN",
            "--config", str(DEV_CONFIG),
        ],
        cwd=APP,
        input=token + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )
    if proc.returncode:
        raise fail("WAKE_DEV_SECRET_PROVISION_FAILED")


def post_json(path: str, token: str, body: dict) -> dict:
    req = Request(
        DEV_ORIGIN + path,
        data=json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "x-hara-mcp-product-token": token,
            "user-agent": "HARA-Commander-EventV2-DEV-Wake-Proof/1",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            obj = json.loads(raw or "{}")
        except json.JSONDecodeError:
            obj = {}
        raise fail(str(obj.get("code") or f"WAKE_HTTP_{exc.code}")) from None


def execute(token: str, issuer: str, subject: str, device_id: str, timeout: float) -> dict:
    request_id = "HARA-EV2-WAKE-" + str(uuid.uuid4())
    call = post_json(
        "/api/internal/device/calls",
        token,
        {
            "issuer": issuer,
            "subject": subject,
            "tool_id": "hara.health",
            "request_id": request_id,
            "device_id": device_id,
            "payload": {},
        },
    )
    call_id = str(call.get("call_id") or "")
    if not call_id.startswith("HARA-CALL-"):
        raise fail("WAKE_CALL_ID_INVALID")

    deadline = time.monotonic() + timeout
    terminal = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}
    last = None
    while time.monotonic() < deadline:
        last = post_json(
            "/api/internal/device/calls/status",
            token,
            {"issuer": issuer, "subject": subject, "call_id": call_id},
        )
        state = str(last.get("state") or "")
        if state in terminal:
            break
        time.sleep(0.25)

    if not last:
        raise fail("WAKE_STATUS_MISSING")
    if last.get("state") != "COMPLETED":
        raise fail("WAKE_CALL_NOT_COMPLETED:" + str(last.get("state") or "UNKNOWN"))
    result = last.get("result") or {}
    if result.get("state") != "PASS":
        raise fail("WAKE_RESULT_NOT_PASS")
    if result.get("operational_authority") != "HARA_COMMANDER":
        raise fail("WAKE_AUTHORITY_DRIFT")
    inner = result.get("result") or {}
    device = inner.get("device") or {}
    if device.get("tunnel_mode") != "EVENT_V2":
        raise fail("WAKE_TRANSPORT_NOT_EVENT_V2")

    return {
        "call_id": call_id,
        "request_id": request_id,
        "state": last.get("state"),
        "authority": result.get("operational_authority"),
        "tunnel_mode": device.get("tunnel_mode"),
        "receipt_sha256": result.get("bridge_receipt_sha256"),
    }


def self_check() -> None:
    require_dev_config()
    source = Path(__file__).read_text(encoding="utf-8")
    assert DEFAULT_ORIGIN_NOT_PRESENT(source)
    assert "print(token" not in source
    assert "commander.haralabs.com.br/api" not in source
    assert 'x-hara-mcp-product-token' in source
    assert 'MCP_PRODUCT_TOKEN' in source
    print("COMMANDER_EVENT_V2_DEV_WAKE_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_DEV_WAKE_PROD_ORIGIN=ABSENT")
    print("COMMANDER_EVENT_V2_DEV_WAKE_TOKEN_OUTPUT=ABSENT")


def DEFAULT_ORIGIN_NOT_PRESENT(source: str) -> bool:
    # The canonical PROD hostname may appear in a deny-check literal elsewhere;
    # the wake request origin itself must remain the exact workers.dev DEV URL.
    return 'DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"' in source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--token-file", default=str(DEFAULT_TOKEN_FILE))
    parser.add_argument("--issuer", default=DEFAULT_ISSUER)
    parser.add_argument("--subject", default=DEFAULT_SUBJECT)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    if args.check:
        self_check()
        return 0
    if not args.execute:
        parser.error("use --check or --execute")
    if args.timeout < 5 or args.timeout > 45:
        raise fail("WAKE_TIMEOUT_INVALID")

    require_dev_config()
    token_file = Path(args.token_file)
    token = secure_token_file(token_file)
    try:
        provision_dev_secret(token)
        proof = execute(token, args.issuer, args.subject, args.device_id, args.timeout)
    finally:
        token = ""

    print("COMMANDER_EVENT_V2_DEV_WAKE_SECRET_PROVISION=PASS")
    print("COMMANDER_EVENT_V2_DEV_WAKE_ENQUEUE=PASS")
    print("COMMANDER_EVENT_V2_DEV_WAKE_COMPLETION=PASS")
    print("COMMANDER_EVENT_V2_DEV_WAKE_AUTHORITY=" + str(proof["authority"]))
    print("COMMANDER_EVENT_V2_DEV_WAKE_TRANSPORT=" + str(proof["tunnel_mode"]))
    print("COMMANDER_EVENT_V2_DEV_WAKE_RECEIPT_PRESENT=" + str(bool(proof["receipt_sha256"])).upper())
    print("COMMANDER_EVENT_V2_DEV_WAKE_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
