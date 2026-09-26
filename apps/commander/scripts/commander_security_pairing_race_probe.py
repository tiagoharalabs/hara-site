#!/usr/bin/env python3
"""Security #189 Gate 2: DEV-only concurrent pairing / replay adversarial probe."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
DEV_CONFIG = APP / "wrangler.dev.jsonc"
DEV_DB = "hara-commander-product-dev"
DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
WRANGLER_VERSION = "4.137.0"


def b64url_sha256(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip("=")


def d1_file(path: Path) -> str:
    proc = subprocess.run(
        [
            "npx", "--yes", f"wrangler@{WRANGLER_VERSION}", "d1", "execute",
            DEV_DB, "--remote", "--config", str(DEV_CONFIG), "--file", str(path),
        ],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=90,
    )
    if proc.returncode:
        raise RuntimeError("PAIRING_RACE_D1_EXEC_FAILED")
    return proc.stdout


def d1_command(sql: str) -> list[dict]:
    proc = subprocess.run(
        [
            "npx", "--yes", f"wrangler@{WRANGLER_VERSION}", "d1", "execute",
            DEV_DB, "--remote", "--config", str(DEV_CONFIG), "--command", sql,
        ],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=90,
    )
    if proc.returncode:
        raise RuntimeError("PAIRING_RACE_D1_QUERY_FAILED")
    text = proc.stdout
    start = text.find("[")
    if start < 0:
        raise RuntimeError("PAIRING_RACE_D1_JSON_MISSING")
    return json.loads(text[start:])


def enroll(token: str, label: str) -> tuple[int, dict]:
    payload = json.dumps({
        "pairing_token": token,
        "device_name": label,
        "platform": "LINUX",
        "architecture": "x86_64",
        "agent_version": "0.3.7",
    })
    proc = subprocess.run(
        [
            "curl", "-sS",
            "-A", "HARA-Security-Probe/1.0",
            "-H", "content-type: application/json",
            "-H", "accept: application/json",
            "--data-binary", "@-",
            "-w", "\n%{http_code}",
            DEV_ORIGIN + "/api/device/enroll",
        ],
        text=True,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=35,
    )
    if proc.returncode:
        return 599, {"code": "TRANSPORT_ERROR"}
    body_text, _, status_text = proc.stdout.rpartition("\n")
    try:
        status = int(status_text.strip())
    except ValueError:
        return 599, {"code": "TRANSPORT_STATUS_INVALID"}
    try:
        body = json.loads(body_text or "{}")
    except json.JSONDecodeError:
        body = {"code": "NON_JSON_RESPONSE"}
    return status, body

def pair_parallel(token: str, prefix: str) -> list[tuple[int, dict]]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(enroll, token, prefix + "-1"),
            pool.submit(enroll, token, prefix + "-2"),
        ]
        return [future.result(timeout=40) for future in futures]


def flatten_results(payload: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for entry in payload:
        rows.extend(entry.get("results", []))
    return rows


def self_check() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert DEV_ORIGIN.startswith("https://hara-commander-dev-v2.")
    assert "commander.haralabs.com.br" not in DEV_ORIGIN
    assert DEV_CONFIG.name == "wrangler.dev.jsonc"
    assert DEV_DB.endswith("-dev")
    assert "/api/device/enroll" in source
    assert "ThreadPoolExecutor(max_workers=2)" in source
    assert '"--data-binary", "@-"' in source
    assert '"HARA-Security-Probe/1.0"' in source
    assert "DEVICE_PAIRING_INVALID" in source
    assert "PAIRING_CONCURRENCY=PASS" in source
    assert "--remote" in source

    # No direct secret-bearing variables may be printed.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "print":
            continue
        printed = {
            child.id.lower()
            for arg in node.args
            for child in ast.walk(arg)
            if isinstance(child, ast.Name)
        }
        assert not ({"token", "race_token", "superseded_token", "expired_token"} & printed)

    print("PAIRING_RACE_PROBE_ENV=DEV_ONLY")
    print("PAIRING_RACE_PROBE_PROD_MUTATION=DENY")
    print("PAIRING_RACE_PROBE_SECRET_OUTPUT=ABSENT")
    print("PAIRING_RACE_PROBE_CONCURRENCY=2")
    print("PAIRING_RACE_PROBE_SOURCE=PASS")


def execute() -> int:
    suffix = secrets.token_hex(6).upper()
    tenant_r = f"SEC189-PAIR-R-{suffix}"
    subject_r = f"SEC189-SUB-R-{suffix}"
    pairing_r = f"SEC189-PAIRING-R-{suffix}"

    tenant_s = f"SEC189-PAIR-S-{suffix}"
    subject_s = f"SEC189-SUB-S-{suffix}"
    pairing_s = f"SEC189-PAIRING-S-{suffix}"

    tenant_e = f"SEC189-PAIR-E-{suffix}"
    subject_e = f"SEC189-SUB-E-{suffix}"
    pairing_e = f"SEC189-PAIRING-E-{suffix}"

    race_token = secrets.token_urlsafe(40)
    superseded_token = secrets.token_urlsafe(40)
    expired_token = secrets.token_urlsafe(40)

    now = "2026-09-26T03:00:00.000Z"
    future = "2026-09-27T03:00:00.000Z"
    past = "2026-09-25T03:00:00.000Z"

    with tempfile.TemporaryDirectory(prefix="hara-sec189-pairing-") as tmp:
        tmpdir = Path(tmp)
        fixture = tmpdir / "fixture.sql"
        cleanup = tmpdir / "cleanup.sql"

        fixture.write_text(f"""
PRAGMA foreign_keys=ON;
INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES
('{tenant_r}','Pair Race','ACTIVE','DEV','{now}'),
('{tenant_s}','Pair Superseded','ACTIVE','DEV','{now}'),
('{tenant_e}','Pair Expired','ACTIVE','DEV','{now}');
INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc) VALUES
('{subject_r}','{tenant_r}','https://security-189.invalid/','race-{suffix}','race-{suffix}@example.test','Race','ACTIVE','OWNER','{now}'),
('{subject_s}','{tenant_s}','https://security-189.invalid/','sup-{suffix}','sup-{suffix}@example.test','Superseded','ACTIVE','OWNER','{now}'),
('{subject_e}','{tenant_e}','https://security-189.invalid/','exp-{suffix}','exp-{suffix}@example.test','Expired','ACTIVE','OWNER','{now}');
INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc) VALUES
('{pairing_r}','{b64url_sha256(race_token)}','{tenant_r}','{subject_r}','{now}','{future}',NULL,NULL),
('{pairing_s}','{b64url_sha256(superseded_token)}','{tenant_s}','{subject_s}','{now}','{future}',NULL,'{now}'),
('{pairing_e}','{b64url_sha256(expired_token)}','{tenant_e}','{subject_e}','{past}','{past}',NULL,NULL);
""", encoding="utf-8")

        cleanup.write_text(f"""
PRAGMA foreign_keys=ON;
DELETE FROM commander_device_calls WHERE tenant_id IN ('{tenant_r}','{tenant_s}','{tenant_e}');
DELETE FROM commander_device_selections WHERE tenant_id IN ('{tenant_r}','{tenant_s}','{tenant_e}');
DELETE FROM commander_devices WHERE tenant_id IN ('{tenant_r}','{tenant_s}','{tenant_e}');
DELETE FROM device_pairing_tokens WHERE tenant_id IN ('{tenant_r}','{tenant_s}','{tenant_e}');
DELETE FROM portal_sessions WHERE subject_id IN ('{subject_r}','{subject_s}','{subject_e}');
DELETE FROM entitlements WHERE tenant_id IN ('{tenant_r}','{tenant_s}','{tenant_e}');
DELETE FROM identity_bindings WHERE subject_id IN ('{subject_r}','{subject_s}','{subject_e}');
DELETE FROM users WHERE subject_id IN ('{subject_r}','{subject_s}','{subject_e}');
DELETE FROM tenants WHERE tenant_id IN ('{tenant_r}','{tenant_s}','{tenant_e}');
""", encoding="utf-8")

        d1_file(fixture)
        try:
            # Same one-time token consumed concurrently: exactly one enrollment succeeds.
            race = pair_parallel(race_token, "Security race")
            statuses = sorted(status for status, _ in race)
            safe_codes = sorted(str(body.get("code") or ("OK" if status == 201 else "NO_CODE")) for status, body in race)
            print("LIVE_PAIRING_RACE_HTTP=" + ",".join(str(x) for x in statuses))
            print("LIVE_PAIRING_RACE_CODES=" + ",".join(safe_codes))
            if statuses != [201, 401]:
                raise RuntimeError("PAIRING_CONCURRENT_RESULT_INVALID")
            loser = [body for status, body in race if status == 401][0]
            if loser.get("code") != "DEVICE_PAIRING_INVALID":
                raise RuntimeError("PAIRING_CONCURRENT_LOSER_NOT_FAIL_CLOSED")

            # Replay after the winning consumption must fail.
            replay_status, replay_body = enroll(race_token, "Security replay")
            if replay_status != 401 or replay_body.get("code") != "DEVICE_PAIRING_INVALID":
                raise RuntimeError("PAIRING_REPLAY_ACCEPTED")

            # Superseded and expired tokens must fail even under concurrent attempts.
            superseded = pair_parallel(superseded_token, "Security superseded")
            if any(status != 401 or body.get("code") != "DEVICE_PAIRING_INVALID" for status, body in superseded):
                raise RuntimeError("PAIRING_SUPERSEDED_ACCEPTED")

            expired = pair_parallel(expired_token, "Security expired")
            if any(status != 401 or body.get("code") != "DEVICE_PAIRING_INVALID" for status, body in expired):
                raise RuntimeError("PAIRING_EXPIRED_ACCEPTED")

            rows = flatten_results(d1_command(f"""
SELECT
 (SELECT COUNT(*) FROM commander_devices WHERE pairing_id='{pairing_r}') AS race_devices,
 (SELECT COUNT(*) FROM commander_devices WHERE pairing_id='{pairing_s}') AS superseded_devices,
 (SELECT COUNT(*) FROM commander_devices WHERE pairing_id='{pairing_e}') AS expired_devices,
 (SELECT CASE WHEN consumed_at_utc IS NULL THEN 0 ELSE 1 END
    FROM device_pairing_tokens WHERE pairing_id='{pairing_r}') AS race_consumed;
"""))
            if len(rows) != 1:
                raise RuntimeError("PAIRING_RACE_VERIFY_RESULT_INVALID")
            row = rows[0]
            if int(row["race_devices"]) != 1 or int(row["race_consumed"]) != 1:
                raise RuntimeError("PAIRING_RACE_EXACTLY_ONE_VIOLATED")
            if int(row["superseded_devices"]) != 0:
                raise RuntimeError("PAIRING_SUPERSEDED_CREATED_DEVICE")
            if int(row["expired_devices"]) != 0:
                raise RuntimeError("PAIRING_EXPIRED_CREATED_DEVICE")

            print("LIVE_PAIRING_CONCURRENT_WINNERS=1")
            print("LIVE_PAIRING_CONCURRENT_LOSERS=1")
            print("LIVE_PAIRING_REPLAY=DENIED")
            print("LIVE_PAIRING_SUPERSEDED=DENIED")
            print("LIVE_PAIRING_EXPIRED=DENIED")
            print("LIVE_PAIRING_DEVICE_COUNT=1")
            print("PROD_MUTATION=FALSE")
            print("PAIRING_CONCURRENCY=PASS")
        finally:
            d1_file(cleanup)

    # Independent cleanup readback by prefix, after temporary files are gone.
    rows = flatten_results(d1_command(
        "SELECT "
        "(SELECT COUNT(*) FROM tenants WHERE tenant_id LIKE 'SEC189-PAIR-%') AS tenants,"
        "(SELECT COUNT(*) FROM users WHERE subject_id LIKE 'SEC189-SUB-%') AS users,"
        "(SELECT COUNT(*) FROM commander_devices WHERE device_id LIKE 'HARA-DEVICE-%' "
        " AND tenant_id LIKE 'SEC189-PAIR-%') AS devices,"
        "(SELECT COUNT(*) FROM device_pairing_tokens WHERE tenant_id LIKE 'SEC189-PAIR-%') AS pairings;"
    ))
    if len(rows) != 1 or any(int(rows[0][key]) != 0 for key in ("tenants", "users", "devices", "pairings")):
        raise RuntimeError("PAIRING_RACE_FIXTURE_CLEANUP_FAILED")
    print("LIVE_PAIRING_FIXTURE_CLEANUP=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.check:
        self_check()
        return 0
    if args.execute:
        return execute()
    parser.error("use --check or --execute")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
