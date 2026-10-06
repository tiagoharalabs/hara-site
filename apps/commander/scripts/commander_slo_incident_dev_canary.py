#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
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
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def enroll(pairing_token: str, name: str) -> str:
    body = json.dumps({
        "pairing_token": pairing_token,
        "device_name": name,
        "platform": "LINUX",
        "architecture": "x86_64",
        "agent_version": "0.3.39",
        "approval_mode": "PERSISTENT_TRUSTED",
    }, separators=(",", ":")).encode()
    req = urllib.request.Request(
        ORIGIN + "/api/device/enroll", data=body, method="POST",
        headers={"content-type": "application/json", "accept": "application/json",
                 "user-agent": "HARA-SLO-Incident-DEV-Canary/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode())
    return str(payload["device_id"])


def maintenance(token: str) -> None:
    req = urllib.request.Request(
        ORIGIN + "/api/dev/slo-maintenance", data=b"{}", method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "x-hara-mcp-product-token": token,
            "user-agent": "HARA-SLO-Incident-DEV-Canary/1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if payload.get("ok") is not True:
        raise RuntimeError("SLO_MAINTENANCE_FAILED")


def snapshot(status: str) -> str:
    if status == "DEGRADED":
        completed, failed, p50, p95, p99 = 90, 10, 900, 9000, 15000
    else:
        completed, failed, p50, p95, p99 = 100, 0, 700, 4000, 8000
    obj = {
        "schema": "hara.commander-device-activity-snapshots.v1",
        "windows": {
            "24h": {
                "schema": "hara.commander-device-activity-window.v1",
                "window_key": "24h",
                "summary": {
                    "total_calls": completed + failed,
                    "completed": completed,
                    "failed": failed,
                    "pending": 0,
                    "executing": 0,
                    "expired": 0,
                    "cancelled": 0,
                    "success_rate_percent": round(completed * 100 / (completed + failed), 1),
                    "under_3s_percent": 90.0,
                    "avg_queue_ms": 0,
                    "avg_execution_ms": p50,
                    "avg_total_ms": p50,
                    "latency_p50_ms": p50,
                    "latency_p95_ms": p95,
                    "latency_p99_ms": p99,
                    "latency_sample_size": completed,
                    "latency_population_size": completed,
                    "latency_sample_capped": False,
                    "transport_modes": ["OUTBOUND_RELAY"],
                },
                "slo": {
                    "profile": "INTERNAL_BETA_V1",
                    "status": status,
                    "evaluable": True,
                    "targets": {
                        "min_success_rate_percent": 99,
                        "p50_max_ms": 1000,
                        "p95_max_ms": 6000,
                        "p99_max_ms": 12000,
                        "min_latency_samples": 20,
                    },
                    "checks": {
                        "success_rate": status == "PASS",
                        "p50": True,
                        "p95": status == "PASS",
                        "p99": status == "PASS",
                    },
                },
                "diagnostics": {"top_tools": [], "top_errors": []},
            }
        },
        "detail_location": "LOCAL_DEVICE",
        "customer_content_synced": False,
    }
    return json.dumps(obj, separators=(",", ":"))


def set_snapshot(device_id: str, status: str) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    d1(
        "UPDATE commander_devices SET "
        f"last_seen_at_utc={q(now)},activity_summary_at_utc={q(now)},"
        f"activity_summary_json={q(snapshot(status))} "
        f"WHERE device_id={q(device_id)};"
    )


def state(tenant: str) -> dict:
    found = rows(
        "SELECT state,breach_streak,recovery_streak,current_incident_id,summary_json "
        f"FROM commander_slo_state WHERE tenant_id={q(tenant)} LIMIT 1;"
    )
    if len(found) != 1:
        raise RuntimeError("SLO_STATE_MISSING")
    return found[0]


def incident(tenant: str) -> list[dict]:
    return rows(
        "SELECT incident_id,state,opened_at_utc,resolved_at_utc,acknowledged_at_utc,acknowledged_by_subject_id,escalation_level,escalated_at_utc "
        f"FROM commander_slo_incidents WHERE tenant_id={q(tenant)} ORDER BY opened_at_utc;"
    )


def main() -> int:
    if not TOKEN_FILE.is_file():
        raise SystemExit("MCP_PRODUCT_CANARY_TOKEN_FILE_MISSING")
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("MCP_PRODUCT_CANARY_TOKEN_EMPTY")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    tenant = "HARA-SLO-INC-T-" + suffix
    subject = "HARA-SLO-INC-S-" + suffix
    binding = "HARA-SLO-INC-I-" + suffix
    entitlement = "HARA-SLO-INC-E-" + suffix
    pairing = "HARA-SLO-INC-P-" + suffix
    pairing_token = "HARA-SLO-INC-TOKEN-" + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    exp = (now + timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
    device_id = None

    seed = f"""
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc)
VALUES ({q(tenant)},'SLO Incident Canary','ACTIVE','DEV',{q(now_iso)});
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(subject)},{q(tenant)},{q(ISSUER)},{q('slo-inc-'+suffix)},NULL,'SLO Incident Canary','ACTIVE','OWNER',{q(now_iso)});
INSERT INTO identity_bindings
(identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
VALUES ({q(binding)},{q(subject)},'PRIMARY_OIDC',{q(ISSUER)},{q('slo-inc-'+suffix)},'ACTIVE',{q(now_iso)},NULL);
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
        device_id = enroll(pairing_token, "slo-incident-" + suffix)

        set_snapshot(device_id, "DEGRADED")
        maintenance(token)
        first = state(tenant)
        assert first["state"] == "DEGRADED"
        assert int(first["breach_streak"]) == 1
        assert first["current_incident_id"] is None
        print("COMMANDER_SLO_INCIDENT_DEV_FIRST_BREACH=PASS")

        set_snapshot(device_id, "DEGRADED")
        maintenance(token)
        second = state(tenant)
        opened = incident(tenant)
        assert second["state"] == "DEGRADED"
        assert int(second["breach_streak"]) == 2
        assert second["current_incident_id"]
        assert len(opened) == 1 and opened[0]["state"] == "OPEN"
        print("COMMANDER_SLO_INCIDENT_DEV_OPEN=PASS")

        incident_id = str(opened[0]["incident_id"])
        for hours, expected_level in ((2, 1), (5, 2), (13, 3)):
            aged = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds").replace("+00:00", "Z")
            d1(
                "UPDATE commander_slo_incidents SET opened_at_utc="
                f"{q(aged)} WHERE incident_id={q(incident_id)};"
            )
            set_snapshot(device_id, "DEGRADED")
            maintenance(token)
            escalated = incident(tenant)
            assert int(escalated[0]["escalation_level"]) == expected_level
            assert escalated[0]["escalated_at_utc"]
            print(f"COMMANDER_SLO_INCIDENT_DEV_AUTO_ESCALATION_L{expected_level}=PASS")

        set_snapshot(device_id, "PASS")
        maintenance(token)
        third = state(tenant)
        still_open = incident(tenant)
        assert third["state"] == "PASS"
        assert int(third["recovery_streak"]) == 1
        assert third["current_incident_id"]
        assert still_open[0]["state"] == "OPEN"
        print("COMMANDER_SLO_INCIDENT_DEV_FIRST_RECOVERY=PASS")

        set_snapshot(device_id, "PASS")
        maintenance(token)
        fourth = state(tenant)
        resolved = incident(tenant)
        assert fourth["state"] == "PASS"
        assert int(fourth["recovery_streak"]) == 0
        assert fourth["current_incident_id"] is None
        assert resolved[0]["state"] == "RESOLVED"
        assert resolved[0]["resolved_at_utc"]
        print("COMMANDER_SLO_INCIDENT_DEV_RESOLVED=PASS")
        print("COMMANDER_SLO_INCIDENT_DEV=PASS")
        return 0
    finally:
        token = ""
        pairing_token = ""
        try:
            d1(cleanup)
            left = rows(f"SELECT COUNT(*) AS n FROM tenants WHERE tenant_id={q(tenant)};")
            print("COMMANDER_SLO_INCIDENT_DEV_CLEANUP=" + ("PASS" if left == [{"n": 0}] else "FAIL"))
        except Exception:
            print("COMMANDER_SLO_INCIDENT_DEV_CLEANUP=ERROR")


if __name__ == "__main__":
    raise SystemExit(main())
