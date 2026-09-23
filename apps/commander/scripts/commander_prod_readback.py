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
      (SELECT COUNT(*) FROM portal_sessions WHERE revoked_at_utc IS NULL) AS active_sessions;""",
    "integrity": """SELECT
      (SELECT COUNT(*) FROM users u LEFT JOIN tenants t ON t.tenant_id=u.tenant_id WHERE t.tenant_id IS NULL) AS users_orphan_tenant,
      (SELECT COUNT(*) FROM entitlements e LEFT JOIN tenants t ON t.tenant_id=e.tenant_id WHERE t.tenant_id IS NULL) AS entitlements_orphan_tenant,
      (SELECT COUNT(*) FROM entitlements e LEFT JOIN plans p ON p.plan_code=e.plan_code WHERE p.plan_code IS NULL) AS entitlements_orphan_plan,
      (SELECT COUNT(*) FROM identity_bindings b LEFT JOIN users u ON u.subject_id=b.subject_id WHERE u.subject_id IS NULL) AS bindings_orphan_user,
      (SELECT COUNT(*) FROM commander_device_selections s LEFT JOIN commander_devices d ON d.device_id=s.device_id WHERE d.device_id IS NULL) AS selections_orphan_device,
      (SELECT COUNT(*) FROM portal_sessions WHERE revoked_at_utc IS NULL AND expires_at_utc <= datetime('now')) AS expired_unrevoked_sessions;""",
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
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 5:
        raise SystemExit("--attempts must be between 1 and 5")

    report = {"state": "PASS", "database": DATABASE, "queries": {}}
    for name, sql in QUERIES.items():
        payload, attempt = execute(sql, wrangler_version=args.wrangler_version, attempts=args.attempts)
        report["queries"][name] = {"attempt": attempt, "row": first_row(payload)}

    fk_payload = report["queries"]["foreign_key_check"]["row"]
    if fk_payload:
        raise RuntimeError("D1_FOREIGN_KEY_CHECK_FAILED")
    integrity = report["queries"]["integrity"]["row"]
    if any(int(value or 0) != 0 for value in integrity.values()):
        raise RuntimeError("D1_INTEGRITY_ANOMALY")

    print(json.dumps(report, indent=2, sort_keys=True))
    print("COMMANDER_PROD_D1_READBACK=PASS")
    print("COMMANDER_PROD_D1_TRANSIENT_RETRY=READY")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMMANDER_PROD_D1_READBACK=FAIL:{exc}", file=sys.stderr)
        raise
