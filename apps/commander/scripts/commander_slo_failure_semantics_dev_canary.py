#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import secrets
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
TOKEN_FILE = APP / ".generated" / "mcp-product-dev-canary-token"


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
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip("=")


def enroll(pairing_token: str, name: str) -> tuple[str, str]:
    body = json.dumps({
        "pairing_token": pairing_token,
        "device_name": name,
        "platform": "LINUX",
        "architecture": "x86_64",
        "agent_version": "0.3.40",
        "approval_mode": "PERSISTENT_TRUSTED",
    }, separators=(",", ":")).encode()
    req = urllib.request.Request(
        ORIGIN + "/api/device/enroll", data=body, method="POST",
        headers={"content-type": "application/json", "accept": "application/json",
                 "user-agent": "HARA-SLO-Semantics-DEV/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode())
    return str(payload["device_id"]), str(payload["device_token"])


def heartbeat(device_id: str, device_token: str, snapshot: dict) -> None:
    body = json.dumps({
        "device_id": device_id,
        "architecture": "x86_64",
        "agent_version": "0.3.40",
        "approval_mode": "PERSISTENT_TRUSTED",
        "activity_snapshots": snapshot,
    }, separators=(",", ":")).encode()
    req = urllib.request.Request(
        ORIGIN + "/api/device/heartbeat", data=body, method="POST",
        headers={"content-type": "application/json", "accept": "application/json",
                 "authorization": "Bearer " + device_token,
                 "user-agent": "HARA-SLO-Semantics-DEV/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode())
    if payload.get("ok") is not True:
        raise RuntimeError("HEARTBEAT_FAILED")


def maintenance(token: str) -> None:
    req = urllib.request.Request(
        ORIGIN + "/api/dev/slo-maintenance", data=b"{}", method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "x-hara-mcp-product-token": token,
            "user-agent": "HARA-SLO-Semantics-DEV/1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if payload.get("ok") is not True:
        raise RuntimeError("SLO_MAINTENANCE_FAILED")


def build_snapshot(service_failure: bool) -> dict:
    spec = importlib.util.spec_from_file_location("hara_slo_semantics_agent", AGENT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix="hara-slo-semantics-") as td:
        root = Path(td)
        g = mod.local_activity_snapshot.__globals__
        g["DATA_DIR"] = root
        g["OPERATIONS_DB_FILE"] = root / "operations.sqlite3"
        g["CONSOLE_EVENTS_FILE"] = root / "console-events.jsonl"
        g["STATUS_FILE"] = root / "runtime-status.json"
        g["SESSION_FILE"] = root / "operator-session.json"
        g["RECEIPT_DIR"] = root / "receipts"
        now = datetime.now(timezone.utc).isoformat()
        with mod._ops_connect() as db:
            idx = 0
            for _ in range(25):
                db.execute(
                    """INSERT INTO activity_events
                       (at_utc,event,state,tool_id,function_id,request_id,error_code,
                        receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (now, "PASS", "COMPLETED", "hara.ping", "device.ping", f"OK-{idx}",
                     None, hashlib.sha256(f"ok-{idx}".encode()).hexdigest(),
                     None, None, 500, "LOCAL_STDIO"),
                )
                idx += 1
            expected = [
                "HTTP_400",
                "FILENOTFOUNDERROR",
                "EDIT_MATCH_AMBIGUOUS",
                "PROCESS_SESSION_EXITED",
                "LOCAL_OPERATOR_APPROVAL_DENIED",
            ]
            for code in expected:
                db.execute(
                    """INSERT INTO activity_events
                       (at_utc,event,state,tool_id,function_id,request_id,error_code,
                        receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (now, "DENIED", "FAILED", "hara.ping", "device.ping", f"ERR-{idx}",
                     code, hashlib.sha256(f"err-{idx}".encode()).hexdigest(),
                     None, None, 100, "LOCAL_STDIO"),
                )
                idx += 1
            if service_failure:
                db.execute(
                    """INSERT INTO activity_events
                       (at_utc,event,state,tool_id,function_id,request_id,error_code,
                        receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (now, "DENIED", "FAILED", "hara.ping", "device.ping", "SERVICE-1",
                     "RUNTIME_ERROR", hashlib.sha256(b"service").hexdigest(),
                     None, None, 100, "LOCAL_STDIO"),
                )
            db.commit()
        return mod.local_activity_heartbeat_snapshot()


def state(tenant: str) -> dict:
    found = rows(
        "SELECT state,breach_streak,recovery_streak,current_incident_id,summary_json "
        f"FROM commander_slo_state WHERE tenant_id={q(tenant)} LIMIT 1;"
    )
    if len(found) != 1:
        raise RuntimeError("SLO_STATE_MISSING")
    return found[0]


def main() -> int:
    if not TOKEN_FILE.is_file():
        raise SystemExit("MCP_PRODUCT_CANARY_TOKEN_FILE_MISSING")
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("MCP_PRODUCT_CANARY_TOKEN_EMPTY")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    tenant = "HARA-SLO-SEM-T-" + suffix
    subject = "HARA-SLO-SEM-S-" + suffix
    binding = "HARA-SLO-SEM-I-" + suffix
    entitlement = "HARA-SLO-SEM-E-" + suffix
    pairing = "HARA-SLO-SEM-P-" + suffix
    pairing_token = "HARA-SLO-SEM-TOKEN-" + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    exp = (now + timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
    device_id = None
    device_token = ""

    seed = f"""
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc)
VALUES ({q(tenant)},'SLO Semantics Canary','ACTIVE','DEV',{q(now_iso)});
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(subject)},{q(tenant)},{q(ISSUER)},{q('slo-sem-'+suffix)},NULL,'SLO Semantics Canary','ACTIVE','OWNER',{q(now_iso)});
INSERT INTO identity_bindings
(identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
VALUES ({q(binding)},{q(subject)},'PRIMARY_OIDC',{q(ISSUER)},{q('slo-sem-'+suffix)},'ACTIVE',{q(now_iso)},NULL);
INSERT INTO entitlements
(entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc)
VALUES ({q(entitlement)},{q(tenant)},{q(subject)},'TRIAL','ACTIVE',{q(now_iso)},NULL);
INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc)
VALUES ({q(pairing)},{q(b64url_sha256(pairing_token))},{q(tenant)},{q(subject)},{q(now_iso)},{q(exp)},NULL,NULL);
"""
    cleanup = f"""
DELETE FROM commander_slo_incidents WHERE tenant_id={q(tenant)};
DELETE FROM commander_slo_state WHERE tenant_id={q(tenant)};
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
        device_id, device_token = enroll(pairing_token, "slo-semantics-" + suffix)

        expected = build_snapshot(False)
        e24 = expected["windows"]["24h"]
        assert e24["summary"]["success_rate_percent"] == 83.3
        assert e24["summary"]["availability_success_rate_percent"] == 100.0
        assert e24["summary"]["service_failed"] == 0
        assert e24["slo"]["status"] == "PASS"
        heartbeat(device_id, device_token, expected)
        maintenance(token)
        first = state(tenant)
        assert first["state"] == "PASS"
        assert int(first["breach_streak"]) == 0
        assert first["current_incident_id"] is None
        stored = rows(
            "SELECT activity_summary_json FROM commander_devices "
            f"WHERE device_id={q(device_id)} LIMIT 1;"
        )[0]
        stored24 = json.loads(stored["activity_summary_json"])["windows"]["24h"]
        assert stored24["summary"]["success_rate_percent"] == 83.3
        assert stored24["summary"]["availability_success_rate_percent"] == 100
        assert stored24["summary"]["service_failed"] == 0
        assert stored24["slo"]["success_metric"] == "availability_success_rate_percent"
        print("COMMANDER_SLO_SEMANTICS_DEV_EXPECTED_ERRORS_NO_INCIDENT=PASS")
        print("COMMANDER_SLO_SEMANTICS_DEV_OUTCOME_RATE=83.3")
        print("COMMANDER_SLO_SEMANTICS_DEV_AVAILABILITY_RATE=100.0")

        service = build_snapshot(True)
        s24 = service["windows"]["24h"]
        assert s24["summary"]["service_failed"] == 1
        assert s24["slo"]["status"] == "DEGRADED"
        heartbeat(device_id, device_token, service)
        maintenance(token)
        second = state(tenant)
        assert second["state"] == "DEGRADED"
        assert int(second["breach_streak"]) == 1
        assert second["current_incident_id"] is None
        maintenance(token)
        third = state(tenant)
        assert int(third["breach_streak"]) == 2
        assert third["current_incident_id"]
        print("COMMANDER_SLO_SEMANTICS_DEV_SERVICE_FAILURE_OPENS_AFTER_HYSTERESIS=PASS")
        print("COMMANDER_SLO_FAILURE_SEMANTICS_DEV=PASS")
        return 0
    finally:
        token = ""
        device_token = ""
        pairing_token = ""
        try:
            d1(cleanup)
            left = rows(f"SELECT COUNT(*) AS n FROM tenants WHERE tenant_id={q(tenant)};")
            print("COMMANDER_SLO_FAILURE_SEMANTICS_DEV_CLEANUP=" + ("PASS" if left == [{"n": 0}] else "FAIL"))
        except Exception:
            print("COMMANDER_SLO_FAILURE_SEMANTICS_DEV_CLEANUP=ERROR")


if __name__ == "__main__":
    raise SystemExit(main())
