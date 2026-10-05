#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"

fresh = __import__("runpy").run_path(
    str(APP / "scripts" / "commander_fresh_customer_dev_acceptance.py")
)
d1 = fresh["d1"]
rows = fresh["rows"]
q = fresh["q"]
enroll = fresh["enroll"]
ISSUER = fresh["ISSUER"]


def fail(code: str):
    raise RuntimeError(code)


def wait_until(predicate, *, timeout=20.0, interval=0.5):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    return last


def download_agent(target: Path) -> None:
    req = urllib.request.Request(
        DEV_ORIGIN + "/agent/linux.py",
        headers={"user-agent": "HARA-LocalBudget-Canary/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        target.write_bytes(response.read())
    req = urllib.request.Request(
        DEV_ORIGIN + "/release/agent-manifest.json",
        headers={"user-agent": "HARA-LocalBudget-Canary/1"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        manifest = json.loads(response.read().decode())
    entry = next(
        item for item in manifest.get("files", [])
        if item.get("path") == "agent/linux.py"
    )
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    if manifest.get("agent_version") != "0.3.35" or sha != entry.get("sha256"):
        fail("SERVED_AGENT_INTEGRITY_INVALID")
    target.chmod(0o700)


def main() -> int:
    suffix = secrets.token_hex(5)
    tenant = "HARA-BUDGET-CANARY-T-" + suffix
    subject = "HARA-BUDGET-CANARY-S-" + suffix
    binding = "HARA-BUDGET-CANARY-I-" + suffix
    entitlement = "HARA-BUDGET-CANARY-E-" + suffix
    pairing = "HARA-BUDGET-CANARY-P-" + suffix
    ext_subject = "budget-canary-" + suffix
    device_name = "budget-canary-" + suffix
    pairing_token = secrets.token_urlsafe(32)
    token_hash = base64.urlsafe_b64encode(
        hashlib.sha256(pairing_token.encode()).digest()
    ).decode().rstrip("=")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    pairing_exp = (now + timedelta(minutes=10)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    period_key = now.strftime("%Y-%m")

    seed = f"""
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc)
VALUES ({q(tenant)},'Local Budget Canary','ACTIVE','DEV',{q(now_iso)});
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(subject)},{q(tenant)},{q(ISSUER)},{q(ext_subject)},NULL,
        'Local Budget Canary','ACTIVE','OWNER',{q(now_iso)});
INSERT INTO identity_bindings
(identity_binding_id,subject_id,provider_code,issuer,external_subject,state,created_at_utc,revoked_at_utc)
VALUES ({q(binding)},{q(subject)},'PRIMARY_OIDC',{q(ISSUER)},{q(ext_subject)},
        'ACTIVE',{q(now_iso)},NULL);
INSERT INTO entitlements
(entitlement_id,tenant_id,subject_id,plan_code,state,valid_from_utc,valid_until_utc)
VALUES ({q(entitlement)},{q(tenant)},{q(subject)},'TRIAL','ACTIVE',{q(now_iso)},NULL);
INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,
 consumed_at_utc,superseded_at_utc)
VALUES ({q(pairing)},{q(token_hash)},{q(tenant)},{q(subject)},{q(now_iso)},
        {q(pairing_exp)},NULL,NULL);
"""

    cleanup = f"""
DELETE FROM commander_device_calls WHERE tenant_id={q(tenant)};
DELETE FROM commander_device_selections WHERE tenant_id={q(tenant)};
DELETE FROM commander_device_budget_blocks WHERE tenant_id={q(tenant)};
DELETE FROM commander_devices WHERE tenant_id={q(tenant)};
DELETE FROM device_pairing_tokens WHERE tenant_id={q(tenant)};
DELETE FROM portal_sessions WHERE subject_id={q(subject)};
DELETE FROM identity_bindings WHERE subject_id={q(subject)};
DELETE FROM entitlements WHERE tenant_id={q(tenant)};
DELETE FROM commander_beta_access_requests WHERE tenant_id={q(tenant)};
DELETE FROM users WHERE subject_id={q(subject)};
DELETE FROM tenants WHERE tenant_id={q(tenant)};
"""

    agent_proc = None
    agent_proc2 = None
    device_token = ""
    try:
        d1(seed)
        device_id, device_token = enroll(pairing_token, device_name)
        pairing_token = ""

        with tempfile.TemporaryDirectory(
            prefix="hara-local-budget-canary-"
        ) as tmp:
            root = Path(tmp)
            xdg_config = root / "config"
            xdg_data = root / "data"
            cfg_dir = xdg_config / "hara-commander"
            cfg_dir.mkdir(parents=True)
            xdg_data.mkdir()
            cfg = cfg_dir / "device.env"
            cfg.write_text(
                f"HARA_COMMANDER_URL={DEV_ORIGIN}\n"
                f"HARA_DEVICE_ID={device_id}\n"
                f"HARA_DEVICE_TOKEN={device_token}\n"
                "HARA_DEVICE_ARCH=x86_64\n"
                "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n",
                encoding="utf-8",
            )
            os.chmod(cfg, 0o600)
            device_token = ""

            served_agent = root / "agent.py"
            download_agent(served_agent)
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = str(xdg_config)
            env["XDG_DATA_HOME"] = str(xdg_data)
            env["HARA_COMMANDER_LOCAL_PORT"] = "0"

            agent_proc = subprocess.Popen(
                ["python3", str(served_agent)],
                env=env,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            def budget_rows():
                return rows(
                    "SELECT budget_id,units_allocated,units_issued,units_reported,state "
                    "FROM commander_device_budget_blocks "
                    f"WHERE tenant_id={q(tenant)} ORDER BY issued_at_utc;"
                )

            block_rows = wait_until(budget_rows, timeout=15)
            if not block_rows:
                ops = xdg_data / "hara-commander" / "operations.sqlite3"
                code = "UNKNOWN"
                recent = []
                if ops.is_file():
                    with sqlite3.connect(ops) as local:
                        local.row_factory = sqlite3.Row
                        row = local.execute(
                            "SELECT error_code FROM activity_events "
                            "WHERE event='PRODUCT_LEASE_DEGRADED' "
                            "ORDER BY event_id DESC LIMIT 1"
                        ).fetchone()
                        if row and row["error_code"]:
                            code = str(row["error_code"])
                        recent = [
                            (str(x["event"]), str(x["state"] or ""), str(x["error_code"] or ""))
                            for x in local.execute(
                                "SELECT event,state,error_code FROM activity_events "
                                "ORDER BY event_id DESC LIMIT 8"
                            ).fetchall()
                        ]
                runtime = xdg_data / "hara-commander" / "runtime-status.json"
                runtime_error = "NONE"
                if runtime.is_file():
                    try:
                        status = json.loads(runtime.read_text())
                        runtime_error = str(status.get("last_runtime_error_code") or "NONE")
                    except Exception:
                        runtime_error = "RUNTIME_STATUS_INVALID"
                print("LOCAL_BUDGET_DEV_BLOCK_ISSUE=BLOCKED")
                print("LOCAL_BUDGET_DEV_BLOCK_ERROR=" + code)
                print("LOCAL_BUDGET_DEV_AGENT_ALIVE=" + str(agent_proc.poll() is None).upper())
                print("LOCAL_BUDGET_DEV_AGENT_EXIT=" + str(agent_proc.poll()))
                print("LOCAL_BUDGET_DEV_RUNTIME_ERROR=" + runtime_error)
                print("LOCAL_BUDGET_DEV_RECENT_EVENTS=" + json.dumps(recent, separators=(",",":")))
                return 3

            if len(block_rows) != 1:
                fail("UNEXPECTED_BLOCK_COUNT")
            first = block_rows[0]
            if int(first["units_allocated"]) != 100 or int(first["units_issued"]) != 0 or first["state"] != "ACTIVE":
                fail("BLOCK_SHAPE_INVALID")
            print("LOCAL_BUDGET_DEV_BLOCK_ISSUE=PASS")
            print("LOCAL_BUDGET_DEV_BLOCK_UNITS=100")
            baseline = rows(
                "SELECT legacy_consumed_units,source,state "
                "FROM commander_tenant_budget_baselines "
                f"WHERE tenant_id={q(tenant)} AND period_key={q(period_key)};"
            )
            if (
                len(baseline) != 1
                or int(baseline[0]["legacy_consumed_units"]) != 0
                or baseline[0]["source"] != "FRESH_TENANT_ZERO"
                or baseline[0]["state"] != "ACTIVE"
            ):
                fail("FRESH_BASELINE_INVALID")
            print("LOCAL_BUDGET_DEV_BASELINE=FRESH_TENANT_ZERO")
            print("LOCAL_BUDGET_DEV_LEGACY_DO_READS_FOR_BASELINE=0")

            device = wait_until(
                lambda: rows(
                    "SELECT agent_version,tunnel_mode,last_seen_at_utc "
                    "FROM commander_devices "
                    f"WHERE device_id={q(device_id)} AND state='ACTIVE';"
                ),
                timeout=10,
            )
            if not device or device[0]["agent_version"] != "0.3.35":
                fail("AGENT_HEARTBEAT_INVALID")

            requests = []
            for idx in range(1, 4):
                call_id = "HARA-BUDGET-CALL-" + secrets.token_hex(8)
                request_id = "HARA-BUDGET-REQ-" + secrets.token_hex(8)
                created = datetime.now(timezone.utc)
                created_iso = created.isoformat(timespec="milliseconds").replace(
                    "+00:00", "Z"
                )
                expires = (created + timedelta(seconds=45)).isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z")
                sql = f"""
INSERT INTO commander_device_calls
(call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,
 state,created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,
 result_json,error_code,usage_mode,usage_units,usage_period_key,usage_budget_id)
VALUES
({q(call_id)},{q(request_id)},{q(tenant)},{q(subject)},{q(device_id)},
 'hara.health','{{}}','PENDING',{q(created_iso)},{q(expires)},NULL,NULL,
 NULL,NULL,'LOCAL_BUDGET',1,{q(period_key)},{q(first["budget_id"])});
"""
                d1(sql)
                requests.append(request_id)

                def completed():
                    got = rows(
                        "SELECT state,error_code FROM commander_device_calls "
                        f"WHERE call_id={q(call_id)};"
                    )
                    return got if got and got[0]["state"] in {
                        "COMPLETED", "FAILED"
                    } else None

                final = wait_until(completed, timeout=15)
                if not final or final[0]["state"] != "COMPLETED":
                    fail("REMOTE_CALL_NOT_COMPLETED")

            ops = xdg_data / "hara-commander" / "operations.sqlite3"
            if not ops.is_file():
                fail("LOCAL_DB_MISSING")
            with sqlite3.connect(ops) as local:
                local.row_factory = sqlite3.Row
                debits = local.execute(
                    "SELECT request_id,state,units FROM local_budget_debits "
                    "ORDER BY created_at_utc"
                ).fetchall()
                blocks = local.execute(
                    "SELECT budget_id,allocated_units,state "
                    "FROM local_budget_blocks"
                ).fetchall()
            observed = {
                row["request_id"]: (row["state"], int(row["units"]))
                for row in debits
                if row["request_id"] in requests
            }
            if len(observed) != 3 or any(
                state != "COMMITTED" or units != 1
                for state, units in observed.values()
            ):
                fail("LOCAL_DEBITS_INVALID")
            if len(blocks) != 1 or int(blocks[0]["allocated_units"]) != 100:
                fail("LOCAL_BLOCK_INVALID")
            print("LOCAL_BUDGET_DEV_THREE_CALLS_ONE_BLOCK=PASS")
            print("LOCAL_BUDGET_DEV_LOCAL_DEBITS=3")
            issued = budget_rows()
            if not issued or int(issued[0]["units_issued"]) != 3:
                fail("CLOUD_ISSUED_COUNT_INVALID")
            print("LOCAL_BUDGET_DEV_CLOUD_ISSUED=3")

            agent_proc.terminate()
            agent_proc.wait(timeout=5)
            agent_proc = None

            agent_proc2 = subprocess.Popen(
                ["python3", str(served_agent)],
                env=env,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            def reported():
                got = budget_rows()
                return got if got and int(got[0]["units_reported"]) >= 3 else None

            report_rows = wait_until(reported, timeout=15)
            if not report_rows:
                fail("CLOUD_REPORT_NOT_RECONCILED")
            if int(report_rows[0]["units_reported"]) != 3:
                fail("CLOUD_REPORT_COUNT_INVALID")
            if len(report_rows) != 1:
                fail("UNEXPECTED_BLOCK_ROLLOVER")
            print("LOCAL_BUDGET_DEV_CLOUD_REPORTED=3")
            print("LOCAL_BUDGET_DEV_BLOCK_COUNT=1")
            print("LOCAL_BUDGET_DEV_CANARY=PASS")
        return 0
    finally:
        for proc in (agent_proc, agent_proc2):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        device_token = ""
        try:
            d1(cleanup)
            print("LOCAL_BUDGET_DEV_CLEANUP=PASS")
        except Exception:
            print("LOCAL_BUDGET_DEV_CLEANUP=FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
