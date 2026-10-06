#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import secrets
import sqlite3
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
AGENT = APP / "public" / "agent" / "linux.py"
WRANGLER = ROOT / "node_modules" / ".bin" / "wrangler"
CONFIG = APP / "wrangler.dev.jsonc"
DB = "hara-commander-product-dev"
ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
ISSUER = "https://auth.haralabs.com.br/"


def q(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def d1(sql: str) -> list[dict]:
    proc = subprocess.run(
        [str(WRANGLER), "d1", "execute", DB, "--remote", "--config", str(CONFIG),
         "--command", sql, "--json"],
        cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=90, check=False,
    )
    if proc.returncode:
        raise RuntimeError("D1_EXECUTE_FAILED")
    return json.loads(proc.stdout)


def rows(sql: str) -> list[dict]:
    out = d1(sql)
    result = out[-1].get("results")
    return result if isinstance(result, list) else []


def b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def enroll(pairing_token: str, name: str) -> tuple[str, str]:
    body = json.dumps({
        "pairing_token": pairing_token,
        "device_name": name,
        "platform": "LINUX",
        "architecture": "x86_64",
        "agent_version": "0.3.38",
        "approval_mode": "PERSISTENT_TRUSTED",
    }, separators=(",", ":")).encode()
    req = urllib.request.Request(
        ORIGIN + "/api/device/enroll", data=body, method="POST",
        headers={"content-type": "application/json", "accept": "application/json",
                 "user-agent": "HARA-SLO-DEV-Canary/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode())
    return str(payload["device_id"]), str(payload["device_token"])


def heartbeat(device_id: str, token: str, snapshot: dict) -> None:
    body = json.dumps({
        "device_id": device_id,
        "architecture": "x86_64",
        "agent_version": "0.3.38",
        "approval_mode": "PERSISTENT_TRUSTED",
        "activity_snapshots": snapshot,
    }, separators=(",", ":")).encode()
    req = urllib.request.Request(
        ORIGIN + "/api/device/heartbeat", data=body, method="POST",
        headers={"content-type": "application/json", "accept": "application/json",
                 "authorization": "Bearer " + token,
                 "user-agent": "HARA-SLO-DEV-Canary/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode())
    if payload.get("ok") is not True:
        raise RuntimeError("HEARTBEAT_FAILED")


def synthetic_snapshot() -> dict:
    spec = importlib.util.spec_from_file_location("hara_slo_canary_agent", AGENT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix="hara-slo-agent-") as td:
        root = Path(td)
        globals_map = mod.local_activity_snapshot.__globals__
        globals_map["DATA_DIR"] = root
        globals_map["OPERATIONS_DB_FILE"] = root / "operations.sqlite3"
        globals_map["CONSOLE_EVENTS_FILE"] = root / "console-events.jsonl"
        globals_map["STATUS_FILE"] = root / "runtime-status.json"
        globals_map["SESSION_FILE"] = root / "operator-session.json"
        globals_map["RECEIPT_DIR"] = root / "receipts"
        now = datetime.now(timezone.utc).isoformat()
        durations = [500] * 13 + [900] * 5 + [2500] * 5 + [5000] * 2
        with mod._ops_connect() as db:
            for idx, duration in enumerate(durations, start=1):
                db.execute(
                    """INSERT INTO activity_events
                       (at_utc,event,state,tool_id,function_id,request_id,error_code,
                        receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (now, "PASS", "COMPLETED", "hara.ping", "device.ping",
                     f"SLO-{idx}", None, hashlib.sha256(f"r{idx}".encode()).hexdigest(),
                     None, None, duration, "LOCAL_STDIO"),
                )
            db.commit()
        snap = mod.local_activity_heartbeat_snapshot()
        s24 = snap["windows"]["24h"]
        assert s24["summary"]["latency_sample_size"] == 25
        assert s24["summary"]["latency_p50_ms"] == 500
        assert s24["summary"]["latency_p95_ms"] == 5000
        assert s24["summary"]["latency_p99_ms"] == 5000
        assert s24["slo"]["status"] == "PASS"
        return snap


def main() -> int:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    tenant = "HARA-SLO-T-" + suffix
    subject = "HARA-SLO-S-" + suffix
    binding = "HARA-SLO-I-" + suffix
    entitlement = "HARA-SLO-E-" + suffix
    pairing = "HARA-SLO-P-" + suffix
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    exp = (now + timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
    device_id = None
    device_token = ""
    seed = f"""
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc)
VALUES ({q(tenant)},'SLO Canary','ACTIVE','DEV',{q(now_iso)});
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(subject)},{q(tenant)},{q(ISSUER)},{q('slo-'+suffix)},NULL,'SLO Canary','ACTIVE','OWNER',{q(now_iso)});
INSERT INTO identity_bindings
(identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
VALUES ({q(binding)},{q(subject)},'PRIMARY_OIDC',{q(ISSUER)},{q('slo-'+suffix)},'ACTIVE',{q(now_iso)},NULL);
INSERT INTO entitlements
(entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc)
VALUES ({q(entitlement)},{q(tenant)},{q(subject)},'TRIAL','ACTIVE',{q(now_iso)},NULL);
INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc)
VALUES ({q(pairing)},{q(b64url_sha256(token))},{q(tenant)},{q(subject)},{q(now_iso)},{q(exp)},NULL,NULL);
"""
    cleanup = f"""
DELETE FROM commander_device_calls WHERE tenant_id={q(tenant)};
DELETE FROM commander_device_selections WHERE tenant_id={q(tenant)};
DELETE FROM commander_devices WHERE tenant_id={q(tenant)};
DELETE FROM device_pairing_tokens WHERE tenant_id={q(tenant)};
DELETE FROM identity_bindings WHERE subject_id={q(subject)};
DELETE FROM entitlements WHERE tenant_id={q(tenant)};
DELETE FROM users WHERE subject_id={q(subject)};
DELETE FROM tenants WHERE tenant_id={q(tenant)};
"""
    try:
        d1(seed)
        device_id, device_token = enroll(token, "slo-canary-" + suffix)
        snap = synthetic_snapshot()
        heartbeat(device_id, device_token, snap)
        result = rows(
            "SELECT agent_version,activity_summary_json FROM commander_devices "
            f"WHERE device_id={q(device_id)} LIMIT 1;"
        )
        if len(result) != 1:
            raise RuntimeError("DEVICE_READBACK_MISSING")
        stored = json.loads(result[0]["activity_summary_json"])
        win = stored["windows"]["24h"]
        summary = win["summary"]
        slo = win["slo"]
        def collect_keys(node, out):
            if isinstance(node, dict):
                for key, value in node.items():
                    out.add(str(key).lower())
                    collect_keys(value, out)
            elif isinstance(node, list):
                for item in node:
                    collect_keys(item, out)
        observed_keys=set()
        collect_keys(stored,observed_keys)
        assert result[0]["agent_version"] == "0.3.38"
        assert summary["latency_p50_ms"] == 500
        assert summary["latency_p95_ms"] == 5000
        assert summary["latency_p99_ms"] == 5000
        assert summary["latency_sample_size"] == 25
        assert slo["status"] == "PASS"
        assert slo["profile"] == "INTERNAL_BETA_V1"
        forbidden={"events","action_summary","payload","payload_json","result","result_json","command","stdout","stderr"}
        assert not (observed_keys & forbidden), sorted(observed_keys & forbidden)
        print("COMMANDER_SLO_DEV_AGENT_038=PASS")
        print("COMMANDER_SLO_DEV_P50_MS=500")
        print("COMMANDER_SLO_DEV_P95_MS=5000")
        print("COMMANDER_SLO_DEV_P99_MS=5000")
        print("COMMANDER_SLO_DEV_STATUS=PASS")
        print("COMMANDER_SLO_DEV_RAW_CONTENT_SYNCED=FALSE")
        return 0
    finally:
        device_token = ""
        token = ""
        try:
            d1(cleanup)
            left = rows(f"SELECT COUNT(*) AS n FROM tenants WHERE tenant_id={q(tenant)};")
            print("COMMANDER_SLO_DEV_CLEANUP=" + ("PASS" if left == [{"n": 0}] else "FAIL"))
        except Exception:
            print("COMMANDER_SLO_DEV_CLEANUP=ERROR")


if __name__ == "__main__":
    raise SystemExit(main())
