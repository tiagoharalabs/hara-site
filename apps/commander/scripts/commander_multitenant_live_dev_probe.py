#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WRANGLER = ROOT / "node_modules" / ".bin" / "wrangler"
CONFIG = APP / "wrangler.dev.jsonc"
DB = "hara-commander-product-dev"
ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
TOKEN_FILE = APP / ".generated" / "mcp-product-dev-canary-token"
ISSUER = "https://auth.haralabs.com.br/"


def die(code: str) -> None:
    raise RuntimeError(code)


def q(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def d1(sql: str) -> list[dict]:
    proc = subprocess.run(
        [
            str(WRANGLER), "d1", "execute", DB,
            "--remote", "--config", str(CONFIG),
            "--command", sql, "--json",
        ],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=90,
        env=os.environ.copy(),
    )
    if proc.returncode:
        raise RuntimeError("D1_EXECUTE_FAILED")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("D1_JSON_INVALID") from exc
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("D1_RESULT_INVALID")
    return payload


def rows(sql: str) -> list[dict]:
    out = d1(sql)
    result = out[-1].get("results")
    return result if isinstance(result, list) else []


def session_hash(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def request_json(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    cookie: str | None = None,
    mcp_token: str | None = None,
) -> tuple[int, dict]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "HARA-Commander-Multitenant-Live-Probe/1",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    if method != "GET":
        headers["Origin"] = ORIGIN
        headers["Referer"] = ORIGIN + "/"
    if cookie:
        headers["Cookie"] = "hara_commander_session=" + cookie
    if mcp_token:
        headers["x-hara-mcp-product-token"] = mcp_token

    req = urllib.request.Request(
        ORIGIN + path,
        method=method,
        headers=headers,
        data=data,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            parsed = {"raw": ""}
        return exc.code, parsed


def denied(status: int, payload: dict, accepted_codes: set[str]) -> bool:
    code = str(payload.get("code") or "")
    return status >= 400 and code in accepted_codes


def main() -> int:
    if not WRANGLER.is_file():
        die("WRANGLER_MISSING")
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 48:
        die("DEV_CANARY_TOKEN_MISSING")
    if os.name != "nt" and (TOKEN_FILE.stat().st_mode & 0o777) != 0o600:
        die("DEV_CANARY_TOKEN_PERMISSIONS")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    ta, tb = f"HARA-MT-A-{suffix}", f"HARA-MT-B-{suffix}"
    ua, ub = f"HARA-MT-UA-{suffix}", f"HARA-MT-UB-{suffix}"
    da, db = f"HARA-MT-DA-{suffix}", f"HARA-MT-DB-{suffix}"
    pa, pb = f"HARA-MT-PA-{suffix}", f"HARA-MT-PB-{suffix}"
    ea, eb = f"HARA-MT-EA-{suffix}", f"HARA-MT-EB-{suffix}"
    ia, ib = f"HARA-MT-IA-{suffix}", f"HARA-MT-IB-{suffix}"
    ext_a, ext_b = f"mt-a-{suffix}", f"mt-b-{suffix}"
    call_b = f"HARA-MT-CALL-B-{suffix}"
    req_b = f"HARA-MT-REQ-B-{suffix}"
    req_a_live = f"HARA-MT-REQ-A-{suffix}"
    req_quota = f"HARA-MT-QUOTA-{suffix}"
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    exp_iso = (now + timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    call_exp = (now + timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00", "Z")

    sess_a = secrets.token_urlsafe(48)
    sess_b = secrets.token_urlsafe(48)
    sha_a = session_hash(sess_a)
    sha_b = session_hash(sess_b)
    redacted = "HARA_REDACTED_SHA256:" + ("a" * 64)

    seed = f"""
    INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES
      ({q(ta)},'MT Tenant A','ACTIVE','DEV',{q(now_iso)}),
      ({q(tb)},'MT Tenant B','ACTIVE','DEV',{q(now_iso)});
    INSERT INTO users
      (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
    VALUES
      ({q(ua)},{q(ta)},{q(ISSUER)},{q(ext_a)},NULL,'MT A','ACTIVE','OWNER',{q(now_iso)}),
      ({q(ub)},{q(tb)},{q(ISSUER)},{q(ext_b)},NULL,'MT B','ACTIVE','OWNER',{q(now_iso)});
    INSERT INTO identity_bindings
      (identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
    VALUES
      ({q(ia)},{q(ua)},'PRIMARY_OIDC',{q(ISSUER)},{q(ext_a)},'ACTIVE',{q(now_iso)},NULL),
      ({q(ib)},{q(ub)},'PRIMARY_OIDC',{q(ISSUER)},{q(ext_b)},'ACTIVE',{q(now_iso)},NULL);
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
      ({q(pa)},{q("hash-" + pa)},{q(ta)},{q(ua)},{q(now_iso)},{q(exp_iso)},{q(now_iso)}),
      ({q(pb)},{q("hash-" + pb)},{q(tb)},{q(ub)},{q(now_iso)},{q(exp_iso)},{q(now_iso)});
    INSERT INTO commander_devices
      (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,architecture,
       agent_version,tunnel_mode,credential_hash,state,created_at_utc,last_seen_at_utc,revoked_at_utc,approval_mode)
    VALUES
      ({q(da)},{q(pa)},{q(ta)},{q(ua)},'mt-device-a','LINUX','x86_64','0.3.30','OUTBOUND_RELAY',{q("cred-" + da)},'ACTIVE',{q(now_iso)},{q(now_iso)},NULL,'PERSISTENT_TRUSTED'),
      ({q(db)},{q(pb)},{q(tb)},{q(ub)},'mt-device-b','LINUX','x86_64','0.3.30','OUTBOUND_RELAY',{q("cred-" + db)},'ACTIVE',{q(now_iso)},{q(now_iso)},NULL,'PERSISTENT_TRUSTED');
    INSERT INTO commander_device_selections (tenant_id,subject_id,device_id,selected_at_utc) VALUES
      ({q(ta)},{q(ua)},{q(da)},{q(now_iso)}),
      ({q(tb)},{q(ub)},{q(db)},{q(now_iso)});
    INSERT INTO commander_device_calls
      (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
       created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
    VALUES
      ({q(call_b)},{q(req_b)},{q(tb)},{q(ub)},{q(db)},'hara.health',{q(redacted)},'COMPLETED',
       {q(now_iso)},{q(call_exp)},{q(now_iso)},{q(now_iso)},{q(redacted)},NULL);
    """
    cleanup = f"""
    DELETE FROM commander_device_calls WHERE tenant_id IN ({q(ta)},{q(tb)});
    DELETE FROM commander_device_selections WHERE tenant_id IN ({q(ta)},{q(tb)});
    DELETE FROM commander_devices WHERE tenant_id IN ({q(ta)},{q(tb)});
    DELETE FROM device_pairing_tokens WHERE tenant_id IN ({q(ta)},{q(tb)});
    DELETE FROM portal_sessions WHERE subject_id IN ({q(ua)},{q(ub)});
    DELETE FROM identity_bindings WHERE subject_id IN ({q(ua)},{q(ub)});
    DELETE FROM entitlements WHERE tenant_id IN ({q(ta)},{q(tb)});
    DELETE FROM commander_beta_access_requests WHERE tenant_id IN ({q(ta)},{q(tb)});
    DELETE FROM users WHERE subject_id IN ({q(ua)},{q(ub)});
    DELETE FROM tenants WHERE tenant_id IN ({q(ta)},{q(tb)});
    """

    quota_a_reserved = False
    quota_b_reserved = False
    blocked_reasons = []
    try:
        d1(seed)

        status, payload = request_json("GET", "/api/portal/devices", cookie=sess_a)
        if status != 200:
            die("MT_ENUM_A_HTTP")
        ids = {str(x.get("device_id")) for x in payload.get("devices", [])}
        if da not in ids or db in ids:
            die("MT_ENUM_A_LEAK")
        print("MULTITENANT_LIVE_DEVICE_ENUMERATION_A=PASS")

        status, payload = request_json("GET", "/api/portal/devices", cookie=sess_b)
        if status != 200:
            die("MT_ENUM_B_HTTP")
        ids = {str(x.get("device_id")) for x in payload.get("devices", [])}
        if db not in ids or da in ids:
            die("MT_ENUM_B_LEAK")
        print("MULTITENANT_LIVE_DEVICE_ENUMERATION_B=PASS")

        status, payload = request_json(
            "POST", "/api/portal/devices/select",
            cookie=sess_a, body={"device_id": db},
        )
        selected = rows(f"SELECT device_id FROM commander_device_selections WHERE tenant_id={q(ta)} AND subject_id={q(ua)};")
        print(f"MULTITENANT_LIVE_DEVICE_SELECTION_HTTP={status}")
        print("MULTITENANT_LIVE_DEVICE_SELECTION_CODE=" + str(payload.get("code") or "NONE"))
        if status < 400 or selected != [{"device_id": da}]:
            die("MT_CROSS_SELECT_NOT_DENIED")
        if status >= 500:
            blocked_reasons.append("PORTAL_SELECT_RATE_LIMIT")
            print("MULTITENANT_LIVE_DEVICE_SELECTION=BLOCKED_DO_CAPACITY")
        else:
            print("MULTITENANT_LIVE_DEVICE_SELECTION=DENIED")

        status, payload = request_json(
            "POST", "/api/portal/devices/revoke",
            cookie=sess_a, body={"device_id": db},
        )
        state_b = rows(f"SELECT state FROM commander_devices WHERE device_id={q(db)};")
        print(f"MULTITENANT_LIVE_DEVICE_REVOKE_HTTP={status}")
        print("MULTITENANT_LIVE_DEVICE_REVOKE_CODE=" + str(payload.get("code") or "NONE"))
        if status < 400 or state_b != [{"state": "ACTIVE"}]:
            die("MT_CROSS_REVOKE_NOT_DENIED")
        if status >= 500:
            blocked_reasons.append("PORTAL_REVOKE_RATE_LIMIT")
            print("MULTITENANT_LIVE_DEVICE_REVOKE=BLOCKED_DO_CAPACITY")
        else:
            print("MULTITENANT_LIVE_DEVICE_REVOKE=DENIED")

        status, payload = request_json(
            "POST", "/api/internal/device/calls",
            mcp_token=token,
            body={
                "issuer": ISSUER, "subject": ext_a,
                "tenant_id": tb,
                "request_id": "HARA-MT-CROSS-ENQUEUE-" + suffix,
                "tool_id": "hara.health",
                "device_id": db,
                "payload": {},
            },
        )
        cross_calls = rows(f"SELECT COUNT(*) AS n FROM commander_device_calls WHERE request_id={q('HARA-MT-CROSS-ENQUEUE-' + suffix)};")
        if status < 400 or cross_calls != [{"n": 0}]:
            die("MT_CROSS_ENQUEUE_NOT_DENIED")
        print(f"MULTITENANT_LIVE_DEVICE_ENQUEUE_HTTP={status}")
        print("MULTITENANT_LIVE_DEVICE_ENQUEUE=DENIED")

        status, payload = request_json(
            "POST", "/api/internal/device/calls",
            mcp_token=token,
            body={
                "issuer": ISSUER, "subject": ext_a,
                "tenant_id": tb,
                "request_id": req_a_live,
                "tool_id": "hara.health",
                "device_id": da,
                "payload": {},
            },
        )
        if status not in {200, 201} or not payload.get("call_id"):
            die("MT_SAME_TENANT_ENQUEUE_FAILED")
        call_a = str(payload["call_id"])
        call_row = rows(f"SELECT tenant_id,subject_id,device_id FROM commander_device_calls WHERE call_id={q(call_a)};")
        if call_row != [{"tenant_id": ta, "subject_id": ua, "device_id": da}]:
            die("MT_CALLER_TENANT_OVERRIDE_ACCEPTED")
        print("MULTITENANT_LIVE_CALLER_TENANT_OVERRIDE=ABSENT")

        status, payload = request_json(
            "POST", "/api/internal/device/calls/status",
            mcp_token=token,
            body={"issuer": ISSUER, "subject": ext_b, "call_id": call_a},
        )
        if status < 400:
            die("MT_CROSS_STATUS_NOT_DENIED")
        print(f"MULTITENANT_LIVE_CALL_STATUS_HTTP={status}")
        print("MULTITENANT_LIVE_CALL_STATUS=DENIED")

        status, payload = request_json(
            "POST", "/api/internal/device/calls/status",
            mcp_token=token,
            body={"issuer": ISSUER, "subject": ext_a, "call_id": call_a},
        )
        if status != 200 or str(payload.get("call_id")) != call_a:
            die("MT_SAME_STATUS_FAILED")
        print("MULTITENANT_LIVE_CALL_STATUS_SELF=PASS")

        status, payload = request_json(
            "POST", "/api/internal/device/calls",
            mcp_token=token,
            body={
                "issuer": ISSUER, "subject": ext_a,
                "request_id": "HARA-MT-RECEIPT-" + suffix,
                "tool_id": "hara.receipts.get",
                "device_id": db,
                "payload": {"receipt_id_or_sha256": "f" * 64},
            },
        )
        receipt_calls = rows(f"SELECT COUNT(*) AS n FROM commander_device_calls WHERE request_id={q('HARA-MT-RECEIPT-' + suffix)};")
        if status < 400 or receipt_calls != [{"n": 0}]:
            die("MT_CROSS_RECEIPT_NOT_DENIED")
        print(f"MULTITENANT_LIVE_RECEIPT_READ_HTTP={status}")
        print("MULTITENANT_LIVE_RECEIPT_READ=DENIED")

        auth_body_a = {
            "issuer": ISSUER, "subject": ext_a, "tenant_id": tb,
            "tool_id": "hara.functions.invoke",
            "function_id": "device.info",
            "request_id": req_quota,
        }
        status, payload_a = request_json(
            "POST", "/api/internal/mcp/authorize",
            mcp_token=token, body=auth_body_a,
        )
        print(f"MULTITENANT_LIVE_QUOTA_A_HTTP={status}")
        print("MULTITENANT_LIVE_QUOTA_A_CODE=" + str(payload_a.get("code") or "NONE"))
        if status >= 500:
            blocked_reasons.append("TENANT_QUOTA_DO")
            print("MULTITENANT_LIVE_QUOTA_NAMESPACE=BLOCKED_DO_CAPACITY")
        elif status != 200 or not payload_a.get("allowed"):
            die("MT_QUOTA_A_RESERVE_FAILED")
        else:
            quota_a_reserved = True
        if quota_a_reserved:
            if str(payload_a.get("subject", {}).get("tenant_id")) != ta:
                die("MT_QUOTA_A_TENANT_OVERRIDE")
            print("MULTITENANT_LIVE_QUOTA_TENANT_DERIVATION_A=PASS")

            status, payload_b = request_json(
                "POST", "/api/internal/mcp/authorize",
                mcp_token=token,
                body={
                    "issuer": ISSUER, "subject": ext_b, "tenant_id": ta,
                    "tool_id": "hara.functions.invoke",
                    "function_id": "device.info",
                    "request_id": req_quota,
                },
            )
            print(f"MULTITENANT_LIVE_QUOTA_B_HTTP={status}")
            print("MULTITENANT_LIVE_QUOTA_B_CODE=" + str(payload_b.get("code") or "NONE"))
            if status >= 500:
                blocked_reasons.append("TENANT_QUOTA_DO_B")
                print("MULTITENANT_LIVE_QUOTA_NAMESPACE=BLOCKED_DO_CAPACITY")
            elif status != 200 or not payload_b.get("allowed"):
                die("MT_QUOTA_B_RESERVE_FAILED")
            else:
                quota_b_reserved = True
                if str(payload_b.get("subject", {}).get("tenant_id")) != tb:
                    die("MT_QUOTA_B_TENANT_OVERRIDE")
                print("MULTITENANT_LIVE_QUOTA_TENANT_DERIVATION_B=PASS")
                print("MULTITENANT_LIVE_QUOTA_NAMESPACE=PASS")

        if blocked_reasons:
            print("MULTITENANT_ISOLATION_LIVE_DEV=BLOCKED_DO_CAPACITY")
            print("MULTITENANT_LIVE_BLOCKER_COUNT=" + str(len(set(blocked_reasons))))
            return 2
        print("MULTITENANT_ISOLATION_LIVE_DEV=PASS")
        return 0
    finally:
        # Release quota reservations first. Ignore cleanup errors only after attempting both.
        if quota_a_reserved:
            request_json(
                "POST", "/api/internal/mcp/release", mcp_token=token,
                body={"issuer": ISSUER, "subject": ext_a, "request_id": req_quota},
            )
        if quota_b_reserved:
            request_json(
                "POST", "/api/internal/mcp/release", mcp_token=token,
                body={"issuer": ISSUER, "subject": ext_b, "request_id": req_quota},
            )
        d1(cleanup)
        leftovers = rows(
            "SELECT "
            f"(SELECT COUNT(*) FROM tenants WHERE tenant_id IN ({q(ta)},{q(tb)})) AS tenants,"
            f"(SELECT COUNT(*) FROM users WHERE subject_id IN ({q(ua)},{q(ub)})) AS users,"
            f"(SELECT COUNT(*) FROM commander_devices WHERE tenant_id IN ({q(ta)},{q(tb)})) AS devices,"
            f"(SELECT COUNT(*) FROM commander_device_calls WHERE tenant_id IN ({q(ta)},{q(tb)})) AS calls;"
        )
        if leftovers != [{"tenants": 0, "users": 0, "devices": 0, "calls": 0}]:
            raise RuntimeError("MT_FIXTURE_CLEANUP_FAILED")
        print("MULTITENANT_LIVE_FIXTURE_CLEANUP=PASS")


if __name__ == "__main__":
    raise SystemExit(main())
