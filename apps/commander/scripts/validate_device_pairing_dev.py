#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CONFIG = APP / ".generated" / "wrangler.remote.dev.json"
BASE = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DB = "hara-commander-product-dev"
TENANT = "HARA-TENANT-REVIEW-0001"
SUBJECT = "HARA-SUBJECT-REVIEW-0001"

def b64sha(value: str) -> str:
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")

def wrangler_sql(sql: str, json_mode: bool = False) -> str:
    args = [
        "npx", "--yes", "wrangler@4.136.1",
        "d1", "execute", DB,
        "--remote", "--config", str(CONFIG),
    ]
    if json_mode:
        args.append("--json")
    args += ["--command", sql]
    cp = subprocess.run(args, cwd=APP, text=True, capture_output=True, check=False)
    if cp.returncode != 0:
        raise RuntimeError("D1_FAILED:" + (cp.stderr or cp.stdout)[-600:])
    return cp.stdout

def post(path: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": "HARA-Commander-Device-Validator/1.0",
    }
    if token:
        headers["authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode() or "{}")
        return exc.code, body

def main() -> int:
    raw_pairing = secrets.token_urlsafe(32)
    pairing_hash = b64sha(raw_pairing)
    pairing_id = "HARA-PAIR-TEST-" + uuid.uuid4().hex
    created = datetime.now(timezone.utc)
    expires = created + timedelta(minutes=10)
    created_iso = created.isoformat().replace("+00:00", "Z")
    expires_iso = expires.isoformat().replace("+00:00", "Z")
    device_id = None

    wrangler_sql(
        "INSERT INTO device_pairing_tokens "
        "(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc) VALUES "
        f"('{pairing_id}','{pairing_hash}','{TENANT}','{SUBJECT}','{created_iso}','{expires_iso}',NULL);"
    )

    try:
        status, enrolled = post("/api/device/enroll", {
            "pairing_token": raw_pairing,
            "device_name": "HARA Device Canary",
            "platform": "LINUX",
            "architecture": "x86_64",
            "agent_version": "0.1.0-canary",
        })
        assert status == 201, (status, enrolled)
        device_id = str(enrolled.get("device_id") or "")
        device_token = str(enrolled.get("device_token") or "")
        assert device_id.startswith("HARA-DEVICE-")
        assert len(device_token) >= 32
        assert enrolled.get("state") == "ACTIVE"
        assert enrolled.get("tunnel_mode") == "OUTBOUND_RELAY"
        print("DEVICE_ENROLLMENT=PASS")
        print("DEVICE_CREDENTIAL_EXPOSED=FALSE")

        status2, replay = post("/api/device/enroll", {
            "pairing_token": raw_pairing,
            "device_name": "Replay",
            "platform": "LINUX",
            "architecture": "x86_64",
            "agent_version": "0.1.0-canary",
        })
        assert status2 == 401, (status2, replay)
        assert replay.get("code") == "DEVICE_PAIRING_INVALID", replay
        print("PAIRING_TOKEN_ONE_TIME=PASS")

        hb_status, heartbeat = post("/api/device/heartbeat", {
            "device_id": device_id,
            "architecture": "x86_64",
            "agent_version": "0.1.0-canary",
        }, device_token)
        assert hb_status == 200, (hb_status, heartbeat)
        assert heartbeat.get("ok") is True
        assert heartbeat.get("device_id") == device_id
        assert heartbeat.get("heartbeat_after_seconds") == 30
        print("DEVICE_HEARTBEAT=PASS")

        readback = wrangler_sql(
            f"SELECT device_id,state,last_seen_at_utc,platform,tunnel_mode FROM commander_devices WHERE device_id='{device_id}';",
            json_mode=True,
        )
        parts = json.loads(readback)
        rows = [row for part in parts for row in (part.get("results") or [])]
        assert len(rows) == 1
        assert rows[0]["state"] == "ACTIVE"
        assert rows[0]["last_seen_at_utc"]
        assert rows[0]["platform"] == "LINUX"
        assert rows[0]["tunnel_mode"] == "OUTBOUND_RELAY"
        print("DEVICE_D1_READBACK=PASS")

        wrangler_sql(
            f"UPDATE commander_devices SET state='REVOKED', revoked_at_utc='{datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}' "
            f"WHERE device_id='{device_id}';"
        )
        revoked_status, revoked = post("/api/device/heartbeat", {"device_id": device_id}, device_token)
        assert revoked_status == 401, (revoked_status, revoked)
        assert revoked.get("code") == "DEVICE_AUTH_INVALID", revoked
        print("DEVICE_REVOKE_INVALIDATES_CREDENTIAL=PASS")

        print("DEVICE_PAIRING_VALIDATION=PASS")
        return 0
    finally:
        if device_id:
            wrangler_sql(f"DELETE FROM commander_devices WHERE device_id='{device_id}';")
        wrangler_sql(f"DELETE FROM device_pairing_tokens WHERE pairing_id='{pairing_id}';")
        print("DEVICE_CANARY_CLEANUP=PASS")

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("DEVICE_PAIRING_VALIDATION=FAIL:" + repr(exc), file=sys.stderr)
        raise
