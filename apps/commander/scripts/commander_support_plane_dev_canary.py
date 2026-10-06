#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import urllib.error
import urllib.parse
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


def q(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def d1(sql: str) -> list[dict]:
    proc = subprocess.run(
        [str(WRANGLER), "d1", "execute", DB, "--remote", "--config", str(CONFIG),
         "--command", sql, "--json"],
        cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=90, check=False, env=os.environ.copy(),
    )
    if proc.returncode:
        raise RuntimeError("D1_EXECUTE_FAILED")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("D1_RESULT_INVALID")
    return payload


def rows(sql: str) -> list[dict]:
    payload = d1(sql)
    result = payload[-1].get("results")
    return result if isinstance(result, list) else []


def session_hash(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def request_json(method: str, path: str, *, cookie: str, body: dict | None = None) -> tuple[int, dict]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "HARA-Support-Plane-DEV-Canary/1",
        "Cookie": "hara_commander_session=" + cookie,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode()
    if method != "GET":
        headers["Origin"] = ORIGIN
        headers["Referer"] = ORIGIN + "/"
    req = urllib.request.Request(ORIGIN + path, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def support_body(device_id: str, *, privacy_ok: bool = True) -> dict:
    return {
        "schema": "hara.commander-support-report.v2",
        "platform": "LINUX",
        "computer": "support-canary",
        "device_id": device_id,
        "agent_version": "0.3.40",
        "approval_mode": "PERSISTENT_TRUSTED",
        "operator_session_active": False,
        "last_successful_heartbeat_at_utc": datetime.now(timezone.utc).isoformat(),
        "last_runtime_error_code": "CANARY_SAFE_ERROR",
        "last_runtime_error_at_utc": datetime.now(timezone.utc).isoformat(),
        "activity_24h": {
            "summary": {
                "total_calls": 100,
                "completed": 99,
                "failed": 1,
                "success_rate_percent": 99.0,
                "avg_total_ms": 1234.5,
                "latency_p50_ms": 700,
                "latency_p95_ms": 5000,
                "latency_p99_ms": 9000,
                "latency_sample_size": 100,
                "latency_population_size": 100,
                "latency_sample_capped": False,
            },
            "slo": {
                "profile": "INTERNAL_BETA_V1",
                "status": "PASS",
                "evaluable": True,
            },
            "top_errors": [{"error_code": "SAFE_CANARY", "calls": 1}],
        },
        "product_lease": {
            "plan_code": "TRIAL",
            "usage_mode": "LOCAL_BUDGET",
            "period_kind": "CALENDAR_MONTH",
            "valid_until_utc": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
            "signed_token_present": True,
        },
        "local_budget": {
            "budget_id": "HARA-BUDGET-CANARY",
            "state": "ACTIVE",
            "allocated_units": 100,
            "committed_units": 3,
            "reserved_units": 0,
            "remaining_units": 97,
            "expires_at_utc": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        },
        "operations_db": {"present": True, "bytes": 4096, "mode": "600"},
        "recent_receipt_sha256": [
            hashlib.sha256(b"canary-receipt").hexdigest(),
            "not-a-valid-hash",
        ],
        "privacy": {
            "secret_material_exposed": not privacy_ok,
            "customer_content_included": False,
            "command_content_included": False,
            "payload_content_included": False,
            "result_content_included": False,
        },
        "raw_command": "SHOULD_NOT_SURVIVE",
        "payload_json": {"secret": "SHOULD_NOT_SURVIVE"},
        "stdout": "SHOULD_NOT_SURVIVE",
    }


def main() -> int:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    ta, tb = "HARA-SUP-A-" + suffix, "HARA-SUP-B-" + suffix
    ua, ub = "HARA-SUP-UA-" + suffix, "HARA-SUP-UB-" + suffix
    ia, ib = "HARA-SUP-IA-" + suffix, "HARA-SUP-IB-" + suffix
    ea, eb = "HARA-SUP-EA-" + suffix, "HARA-SUP-EB-" + suffix
    pa, pb = "HARA-SUP-PA-" + suffix, "HARA-SUP-PB-" + suffix
    da, db = "HARA-SUP-DA-" + suffix, "HARA-SUP-DB-" + suffix
    sess_a, sess_b = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    sha_a, sha_b = session_hash(sess_a), session_hash(sess_b)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    exp_iso = (now + timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")

    seed = f"""
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES
({q(ta)},'Support A','ACTIVE','DEV',{q(now_iso)}),
({q(tb)},'Support B','ACTIVE','DEV',{q(now_iso)});
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES
({q(ua)},{q(ta)},{q(ISSUER)},{q('sup-a-'+suffix)},NULL,'Support A','ACTIVE','OWNER',{q(now_iso)}),
({q(ub)},{q(tb)},{q(ISSUER)},{q('sup-b-'+suffix)},NULL,'Support B','ACTIVE','OWNER',{q(now_iso)});
INSERT INTO identity_bindings
(identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
VALUES
({q(ia)},{q(ua)},'PRIMARY_OIDC',{q(ISSUER)},{q('sup-a-'+suffix)},'ACTIVE',{q(now_iso)},NULL),
({q(ib)},{q(ub)},'PRIMARY_OIDC',{q(ISSUER)},{q('sup-b-'+suffix)},'ACTIVE',{q(now_iso)},NULL);
INSERT INTO entitlements
(entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc)
VALUES
({q(ea)},{q(ta)},{q(ua)},'TRIAL','ACTIVE',{q(now_iso)},NULL),
({q(eb)},{q(tb)},{q(ub)},'TRIAL','ACTIVE',{q(now_iso)},NULL);
INSERT INTO portal_sessions
(session_hash,subject_id,created_at_utc,expires_at_utc,last_seen_at_utc,revoked_at_utc)
VALUES
({q(sha_a)},{q(ua)},{q(now_iso)},{q(exp_iso)},{q(now_iso)},NULL),
({q(sha_b)},{q(ub)},{q(now_iso)},{q(exp_iso)},{q(now_iso)},NULL);
INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc)
VALUES
({q(pa)},{q('hash-'+pa)},{q(ta)},{q(ua)},{q(now_iso)},{q(exp_iso)},{q(now_iso)}),
({q(pb)},{q('hash-'+pb)},{q(tb)},{q(ub)},{q(now_iso)},{q(exp_iso)},{q(now_iso)});
INSERT INTO commander_devices
(device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,architecture,
 agent_version,tunnel_mode,credential_hash,state,created_at_utc,last_seen_at_utc,revoked_at_utc,approval_mode)
VALUES
({q(da)},{q(pa)},{q(ta)},{q(ua)},'support-a','LINUX','x86_64','0.3.40','OUTBOUND_RELAY',{q('cred-'+da)},'ACTIVE',{q(now_iso)},{q(now_iso)},NULL,'PERSISTENT_TRUSTED'),
({q(db)},{q(pb)},{q(tb)},{q(ub)},'support-b','LINUX','x86_64','0.3.40','OUTBOUND_RELAY',{q('cred-'+db)},'ACTIVE',{q(now_iso)},{q(now_iso)},NULL,'PERSISTENT_TRUSTED');
"""
    cleanup = f"""
DELETE FROM commander_support_reports WHERE tenant_id IN ({q(ta)},{q(tb)});
DELETE FROM commander_device_calls WHERE tenant_id IN ({q(ta)},{q(tb)});
DELETE FROM commander_device_selections WHERE tenant_id IN ({q(ta)},{q(tb)});
DELETE FROM commander_devices WHERE tenant_id IN ({q(ta)},{q(tb)});
DELETE FROM device_pairing_tokens WHERE tenant_id IN ({q(ta)},{q(tb)});
DELETE FROM portal_sessions WHERE subject_id IN ({q(ua)},{q(ub)});
DELETE FROM identity_bindings WHERE subject_id IN ({q(ua)},{q(ub)});
DELETE FROM entitlements WHERE tenant_id IN ({q(ta)},{q(tb)});
DELETE FROM users WHERE subject_id IN ({q(ua)},{q(ub)});
DELETE FROM tenants WHERE tenant_id IN ({q(ta)},{q(tb)});
"""
    try:
        d1(seed)

        bad_status, bad = request_json("POST", "/api/portal/support-reports", cookie=sess_a,
                                       body=support_body(da, privacy_ok=False))
        assert bad_status == 400 and bad.get("code") == "SUPPORT_REPORT_PRIVACY_INVALID", (bad_status, bad)
        print("COMMANDER_SUPPORT_DEV_PRIVACY_FAIL_CLOSED=PASS")

        status, created = request_json("POST", "/api/portal/support-reports", cookie=sess_a,
                                       body=support_body(da, privacy_ok=True))
        assert status == 201, (status, created)
        report_id = str(created["support_report_id"])
        stored_report = created["report"]
        rendered = json.dumps(stored_report).lower()
        for forbidden in ("should_not_survive", "raw_command", "payload_json", "stdout", "device_token", "lease_token"):
            assert forbidden not in rendered, forbidden
        assert len(stored_report.get("recent_receipt_sha256") or []) == 1
        print("COMMANDER_SUPPORT_DEV_SANITIZER=PASS")

        status_a, listed_a = request_json("GET", "/api/portal/support-reports?limit=10", cookie=sess_a)
        assert status_a == 200
        assert [x["support_report_id"] for x in listed_a.get("reports", [])] == [report_id]
        print("COMMANDER_SUPPORT_DEV_OWNER_LIST=PASS")

        status_b, listed_b = request_json("GET", "/api/portal/support-reports?limit=10", cookie=sess_b)
        assert status_b == 200 and listed_b.get("reports") == []
        print("COMMANDER_SUPPORT_DEV_CROSS_TENANT_LIST=DENIED")

        status_del_b, del_b = request_json("POST", "/api/portal/support-reports/delete", cookie=sess_b,
                                           body={"support_report_id": report_id})
        assert status_del_b == 404 and del_b.get("code") == "SUPPORT_REPORT_NOT_FOUND"
        print("COMMANDER_SUPPORT_DEV_CROSS_TENANT_DELETE=DENIED")

        dbrow = rows(f"SELECT tenant_id,subject_id,device_id,length(report_json) AS bytes,report_json FROM commander_support_reports WHERE support_report_id={q(report_id)} LIMIT 1;")
        assert len(dbrow) == 1
        assert dbrow[0]["tenant_id"] == ta and dbrow[0]["subject_id"] == ua and dbrow[0]["device_id"] == da
        assert int(dbrow[0]["bytes"]) < 16 * 1024
        db_rendered = str(dbrow[0]["report_json"]).lower()
        for forbidden in ("should_not_survive", "payload_json", "raw_command", "stdout"):
            assert forbidden not in db_rendered
        print("COMMANDER_SUPPORT_DEV_D1_SANITIZED=PASS")

        status_del_a, del_a = request_json("POST", "/api/portal/support-reports/delete", cookie=sess_a,
                                           body={"support_report_id": report_id})
        assert status_del_a == 200 and del_a.get("deleted") is True
        assert rows(f"SELECT COUNT(*) AS n FROM commander_support_reports WHERE support_report_id={q(report_id)};") == [{"n": 0}]
        print("COMMANDER_SUPPORT_DEV_DELETE=PASS")
        print("COMMANDER_SUPPORT_PLANE_DEV=PASS")
        return 0
    finally:
        try:
            d1(cleanup)
            left = rows(f"SELECT COUNT(*) AS n FROM tenants WHERE tenant_id IN ({q(ta)},{q(tb)});")
            print("COMMANDER_SUPPORT_DEV_CLEANUP=" + ("PASS" if left == [{"n": 0}] else "FAIL"))
        except Exception:
            print("COMMANDER_SUPPORT_DEV_CLEANUP=ERROR")


if __name__ == "__main__":
    raise SystemExit(main())
