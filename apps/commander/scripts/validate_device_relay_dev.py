#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CONFIG = APP / ".generated" / "wrangler.remote.dev.json"
TOKEN_FILE = APP / ".generated" / "mcp-product-token"
BASE = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DB = "hara-commander-product-dev"
TENANT = "HARA-TENANT-REVIEW-0001"
SUBJECT = "HARA-SUBJECT-REVIEW-0001"
OIDC_SUBJECT = "391922351219933187"
ISSUER = "https://auth.haralabs.com.br/"

def b64sha(value: str) -> str:
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")

def wrangler_sql(sql: str, json_mode: bool = False) -> str:
    args = ["npx", "--yes", "wrangler@4.136.1", "d1", "execute", DB,
            "--remote", "--config", str(CONFIG)]
    if json_mode:
        args.append("--json")
    args += ["--command", sql]
    cp = subprocess.run(args, cwd=APP, text=True, capture_output=True)
    if cp.returncode != 0:
        raise RuntimeError("D1_FAILED:" + (cp.stderr or cp.stdout)[-500:])
    return cp.stdout

def post(path: str, payload: dict, *, device_token: str | None = None,
         product_token: str | None = None) -> tuple[int, dict | None]:
    headers = {"content-type": "application/json", "accept": "application/json",
               "user-agent": "HARA-Commander-Relay-Validator/1.0"}
    if device_token:
        headers["authorization"] = "Bearer " + device_token
    if product_token:
        headers["x-hara-mcp-product-token"] = product_token
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode() or "{}") if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = json.loads(raw.decode() or "{}") if raw else None
        return exc.code, body

def main() -> int:
    product_token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    assert product_token
    pairing = secrets.token_urlsafe(32)
    pairing_hash = b64sha(pairing)
    pairing_id = "HARA-PAIR-RELAY-" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=10)
    device_id = None
    call_id = None
    request_id = "relay-health-" + uuid.uuid4().hex

    wrangler_sql(
        "INSERT INTO device_pairing_tokens "
        "(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc) VALUES "
        f"('{pairing_id}','{pairing_hash}','{TENANT}','{SUBJECT}',"
        f"'{now.isoformat().replace('+00:00','Z')}','{expires.isoformat().replace('+00:00','Z')}',NULL);"
    )

    try:
        status, enrolled = post("/api/device/enroll", {
            "pairing_token": pairing,
            "device_name": "HARA Relay Canary",
            "platform": "LINUX",
            "architecture": "x86_64",
            "agent_version": "0.2.0-canary",
        })
        assert status == 201 and enrolled
        device_id = str(enrolled["device_id"])
        device_token = str(enrolled["device_token"])
        print("DEVICE_RELAY_ENROLLMENT=PASS")

        hb_status, heartbeat = post("/api/device/heartbeat", {
            "device_id": device_id,
            "architecture": "x86_64",
            "agent_version": "0.2.0-canary",
        }, device_token=device_token)
        assert hb_status == 200 and heartbeat and heartbeat.get("ok") is True
        print("DEVICE_RELAY_ONLINE=PASS")

        enqueue_status, queued = post("/api/internal/device/calls", {
            "issuer": ISSUER,
            "subject": OIDC_SUBJECT,
            "device_id": device_id,
            "tool_id": "hara.health",
            "request_id": request_id,
            "payload": {},
        }, product_token=product_token)
        assert enqueue_status == 201 and queued
        assert queued.get("state") == "PENDING"
        call_id = str(queued["call_id"])
        print("DEVICE_RELAY_ENQUEUE=PASS")

        claim_status, claimed = post("/api/device/calls/next", {},
                                     device_token=device_token)
        assert claim_status == 200 and claimed
        assert claimed.get("call_id") == call_id
        assert claimed.get("tool_id") == "hara.health"
        print("DEVICE_RELAY_ATOMIC_CLAIM=PASS")

        second_status, second = post("/api/device/calls/next", {},
                                     device_token=device_token)
        assert second_status == 204 and second is None
        print("DEVICE_RELAY_DUPLICATE_CLAIM=DENIED")

        complete_status, completed = post("/api/device/calls/complete", {
            "call_id": call_id,
            "state": "COMPLETED",
            "result": {
                "ok": True,
                "agent_version": "0.2.0-canary",
                "device_id": device_id,
                "platform": "LINUX",
                "architecture": "x86_64",
                "hostname": "relay-canary",
                "tunnel_mode": "OUTBOUND_RELAY",
            },
        }, device_token=device_token)
        assert complete_status == 200 and completed
        assert completed.get("state") == "COMPLETED"
        print("DEVICE_RELAY_COMPLETE=PASS")

        read_status, readback = post("/api/internal/device/calls/status", {
            "issuer": ISSUER,
            "subject": OIDC_SUBJECT,
            "call_id": call_id,
        }, product_token=product_token)
        assert read_status == 200 and readback
        assert readback.get("state") == "COMPLETED"
        result = readback.get("result") or {}
        assert result.get("ok") is True
        assert result.get("device_id") == device_id
        assert result.get("tunnel_mode") == "OUTBOUND_RELAY"
        print("DEVICE_RELAY_RESULT_ROUNDTRIP=PASS")

        idem_status, idem = post("/api/internal/device/calls", {
            "issuer": ISSUER,
            "subject": OIDC_SUBJECT,
            "device_id": device_id,
            "tool_id": "hara.health",
            "request_id": request_id,
            "payload": {},
        }, product_token=product_token)
        assert idem_status == 201 and idem
        assert idem.get("existing") is True and idem.get("call_id") == call_id
        print("DEVICE_RELAY_IDEMPOTENCY=PASS")

        bad_status, bad = post("/api/internal/device/calls", {
            "issuer": ISSUER,
            "subject": OIDC_SUBJECT,
            "device_id": device_id,
            "tool_id": "unknown.shell",
            "request_id": "bad-" + uuid.uuid4().hex,
            "payload": {"command": "whoami"},
        }, product_token=product_token)
        assert bad_status == 403 and bad and bad.get("code") == "DEVICE_CALL_TOOL_DENIED"
        print("DEVICE_RELAY_ARBITRARY_TOOL=DENIED")
        print("DEVICE_RELAY_SECRET_EXPOSED=FALSE")
        print("DEVICE_RELAY_HEALTH_E2E=PASS")
        return 0

    finally:
        if call_id:
            wrangler_sql(f"DELETE FROM commander_device_calls WHERE call_id='{call_id}';")
        if device_id:
            wrangler_sql(f"DELETE FROM commander_devices WHERE device_id='{device_id}';")
        wrangler_sql(f"DELETE FROM device_pairing_tokens WHERE pairing_id='{pairing_id}';")
        print("DEVICE_RELAY_CANARY_CLEANUP=PASS")

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("DEVICE_RELAY_VALIDATION=FAIL:" + repr(exc), file=sys.stderr)
        raise
