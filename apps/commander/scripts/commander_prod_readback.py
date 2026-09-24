#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
CONFIG = APP / "wrangler.jsonc"
DATABASE = "hara-commander-product-prod"
SESSION_RETENTION_DAYS = 30
PAIRING_RETENTION_DAYS = 30
TRANSIENT_MARKERS = (
    "code: 7403",
    "[code: 7403]",
    "code: 429",
    "[code: 429]",
    "internal server error",
    "service unavailable",
    "gateway timeout",
)

QUERIES = {
    "foreign_key_check": "PRAGMA foreign_key_check;",
    "counts": """SELECT
      (SELECT COUNT(*) FROM tenants) AS tenants,
      (SELECT COUNT(*) FROM users) AS users,
      (SELECT COUNT(*) FROM entitlements) AS entitlements,
      (SELECT COUNT(*) FROM identity_bindings) AS identity_bindings,
      (SELECT COUNT(*) FROM commander_devices) AS devices,
      (SELECT COUNT(*) FROM commander_device_selections) AS selections,
      (SELECT COUNT(*) FROM commander_device_calls) AS calls,
      (SELECT COUNT(*) FROM portal_sessions WHERE revoked_at_utc IS NULL AND julianday(expires_at_utc) > julianday('now')) AS active_sessions;""",
    "integrity": """SELECT
      (SELECT COUNT(*) FROM users u LEFT JOIN tenants t ON t.tenant_id=u.tenant_id WHERE t.tenant_id IS NULL) AS users_orphan_tenant,
      (SELECT COUNT(*) FROM entitlements e LEFT JOIN tenants t ON t.tenant_id=e.tenant_id WHERE t.tenant_id IS NULL) AS entitlements_orphan_tenant,
      (SELECT COUNT(*) FROM entitlements e LEFT JOIN plans p ON p.plan_code=e.plan_code WHERE p.plan_code IS NULL) AS entitlements_orphan_plan,
      (SELECT COUNT(*) FROM identity_bindings b LEFT JOIN users u ON u.subject_id=b.subject_id WHERE u.subject_id IS NULL) AS bindings_orphan_user,
      (SELECT COUNT(*) FROM commander_device_selections s LEFT JOIN commander_devices d ON d.device_id=s.device_id WHERE d.device_id IS NULL) AS selections_orphan_device,
      (SELECT COUNT(*) FROM device_pairing_tokens p
        LEFT JOIN commander_devices d ON d.pairing_id=p.pairing_id
        WHERE p.consumed_at_utc IS NOT NULL AND d.device_id IS NULL) AS consumed_pairing_without_device;""",
    "pairing_hygiene": f"""SELECT
      COUNT(*) AS total_pairing_tokens,
      COALESCE(SUM(CASE
        WHEN p.consumed_at_utc IS NULL
         AND p.superseded_at_utc IS NULL
         AND julianday(p.expires_at_utc) > julianday('now')
        THEN 1 ELSE 0 END), 0) AS current_valid_pairing_tokens,
      COALESCE(SUM(CASE
        WHEN p.consumed_at_utc IS NULL
         AND (
           p.superseded_at_utc IS NOT NULL
           OR julianday(p.expires_at_utc) <= julianday('now')
         )
        THEN 1 ELSE 0 END), 0) AS terminal_unconsumed_pairing_tokens,
      COALESCE(SUM(CASE
        WHEN p.consumed_at_utc IS NULL
         AND NOT EXISTS (
           SELECT 1 FROM commander_devices d WHERE d.pairing_id = p.pairing_id
         )
         AND (
           (
             p.superseded_at_utc IS NOT NULL
             AND julianday(p.superseded_at_utc) <= julianday('now', '-{PAIRING_RETENTION_DAYS} days')
           )
           OR (
             p.superseded_at_utc IS NULL
             AND julianday(p.expires_at_utc) <= julianday('now', '-{PAIRING_RETENTION_DAYS} days')
           )
         )
        THEN 1 ELSE 0 END), 0) AS retention_eligible_pairing_tokens,
      COALESCE(SUM(CASE
        WHEN p.consumed_at_utc IS NOT NULL
        THEN 1 ELSE 0 END), 0) AS consumed_pairing_tokens,
      COALESCE(SUM(CASE
        WHEN p.consumed_at_utc IS NOT NULL
         AND EXISTS (
           SELECT 1 FROM commander_devices d WHERE d.pairing_id = p.pairing_id
         )
        THEN 1 ELSE 0 END), 0) AS consumed_pairings_with_device
      FROM device_pairing_tokens p;""",
    "session_hygiene": f"""SELECT
      (SELECT COUNT(*) FROM portal_sessions
        WHERE revoked_at_utc IS NULL
          AND julianday(expires_at_utc) <= julianday('now')) AS expired_unrevoked_sessions,
      (SELECT COUNT(*) FROM portal_sessions
        WHERE revoked_at_utc IS NULL
          AND julianday(expires_at_utc) <= julianday('now', '-{SESSION_RETENTION_DAYS} days')) AS retention_eligible_expired_sessions,
      (SELECT COUNT(*) FROM portal_sessions
        WHERE revoked_at_utc IS NOT NULL
          AND julianday(revoked_at_utc) <= julianday('now', '-{SESSION_RETENTION_DAYS} days')) AS retention_eligible_revoked_sessions,
      (SELECT ROUND(MAX(julianday('now') - julianday(expires_at_utc)), 2)
         FROM portal_sessions
        WHERE revoked_at_utc IS NULL
          AND julianday(expires_at_utc) <= julianday('now')) AS oldest_expired_age_days;""",
    "migration_0009": """SELECT
      COUNT(*) AS superseded_at_utc_columns
      FROM pragma_table_info('device_pairing_tokens')
      WHERE name = 'superseded_at_utc';""",
}


def execute(sql: str, *, wrangler_version: str, attempts: int) -> tuple[list[dict], int]:
    command = [
        "npx", "--yes", f"wrangler@{wrangler_version}", "d1", "execute", DATABASE,
        "--remote", "--config", str(CONFIG), "--command", sql, "--json",
    ]
    last = ""
    for attempt in range(1, attempts + 1):
        proc = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("D1_READBACK_JSON_INVALID") from exc
            return payload, attempt
        last = combined
        lower = combined.lower()
        if attempt >= attempts or not any(marker in lower for marker in TRANSIENT_MARKERS):
            raise RuntimeError(combined.strip() or "D1_READBACK_FAILED")
        time.sleep(attempt)
    raise RuntimeError(last or "D1_READBACK_FAILED")


def first_row(payload: list[dict]) -> dict:
    for block in payload:
        rows = block.get("results") or []
        if rows:
            return rows[0]
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrangler-version", default="4.137.0")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument(
        "--expect-migration-0009",
        choices=("pending", "applied", "any"),
        default="any",
    )
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 5:
        raise SystemExit("--attempts must be between 1 and 5")

    report = {
        "state": "PASS",
        "database": DATABASE,
        "session_retention_days": SESSION_RETENTION_DAYS,
        "pairing_retention_days": PAIRING_RETENTION_DAYS,
        "queries": {},
    }
    for name, sql in QUERIES.items():
        payload, attempt = execute(sql, wrangler_version=args.wrangler_version, attempts=args.attempts)
        report["queries"][name] = {"attempt": attempt, "row": first_row(payload)}

    fk_payload = report["queries"]["foreign_key_check"]["row"]
    if fk_payload:
        raise RuntimeError("D1_FOREIGN_KEY_CHECK_FAILED")
    integrity = report["queries"]["integrity"]["row"]
    if any(int(value or 0) != 0 for value in integrity.values()):
        raise RuntimeError("D1_INTEGRITY_ANOMALY")

    migration_row = report["queries"]["migration_0009"]["row"]
    migration_count = int(migration_row.get("superseded_at_utc_columns", 0) or 0)
    if migration_count not in (0, 1):
        raise RuntimeError("D1_MIGRATION_0009_SCHEMA_ANOMALY")
    migration_state = "APPLIED" if migration_count == 1 else "PENDING"
    expected = args.expect_migration_0009.upper()
    if expected != "ANY" and migration_state != expected:
        raise RuntimeError(
            f"D1_MIGRATION_0009_EXPECTED_{expected}_GOT_{migration_state}"
        )
    report["migration_0009_state"] = migration_state

    pairing_hygiene = report["queries"]["pairing_hygiene"]["row"]
    pairing_retention_eligible = int(
        pairing_hygiene.get("retention_eligible_pairing_tokens", 0) or 0
    )

    session_hygiene = report["queries"]["session_hygiene"]["row"]
    retention_eligible = (
        int(session_hygiene.get("retention_eligible_expired_sessions", 0) or 0)
        + int(session_hygiene.get("retention_eligible_revoked_sessions", 0) or 0)
    )
    oldest_expired_age = session_hygiene.get("oldest_expired_age_days")

    print(json.dumps(report, indent=2, sort_keys=True))
    print("COMMANDER_PROD_D1_READBACK=PASS")
    print("COMMANDER_PROD_D1_TRANSIENT_RETRY=READY")
    print(f"COMMANDER_PROD_D1_MIGRATION_0009={migration_state}")
    print(f"COMMANDER_PROD_PAIRING_RETENTION_WINDOW_DAYS={PAIRING_RETENTION_DAYS}")
    print(f"COMMANDER_PROD_PAIRING_RETENTION_ELIGIBLE={pairing_retention_eligible}")
    print(
        "COMMANDER_PROD_PAIRING_CURRENT_VALID="
        + str(int(pairing_hygiene.get("current_valid_pairing_tokens", 0) or 0))
    )
    print(
        "COMMANDER_PROD_PAIRING_TERMINAL_UNCONSUMED="
        + str(int(pairing_hygiene.get("terminal_unconsumed_pairing_tokens", 0) or 0))
    )
    print(
        "COMMANDER_PROD_PAIRING_CONSUMED_PROVENANCE="
        + str(int(pairing_hygiene.get("consumed_pairings_with_device", 0) or 0))
    )
    print(f"COMMANDER_PROD_SESSION_RETENTION_WINDOW_DAYS={SESSION_RETENTION_DAYS}")
    print(f"COMMANDER_PROD_SESSION_RETENTION_ELIGIBLE={retention_eligible}")
    print(
        "COMMANDER_PROD_SESSION_OLDEST_EXPIRED_AGE_DAYS="
        + ("NONE" if oldest_expired_age is None else str(oldest_expired_age))
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMMANDER_PROD_D1_READBACK=FAIL:{exc}", file=sys.stderr)
        raise
