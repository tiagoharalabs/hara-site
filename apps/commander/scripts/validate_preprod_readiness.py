#!/usr/bin/env python3
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]

def run(label, command):
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        print(f"{label}=FAIL")
        print(proc.stdout, end="")
        raise SystemExit(proc.returncode)
    print(f"{label}=PASS")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-readonly",
        action="store_true",
        help="also run public Identity and PROD D1 read-only checks",
    )
    args = parser.parse_args()

    run("COMMANDER_PREPROD_APP_JS", [
        "node", "--check", "apps/commander/public/app.js",
    ])
    run("COMMANDER_PREPROD_WORKER_JS", [
        "node", "--check", "apps/commander/src/worker.js",
    ])
    run("COMMANDER_PREPROD_AUTH_JS", [
        "node", "--check", "apps/commander/src/auth.js",
    ])
    checks = (
        ("COMMANDER_PREPROD_UI", "validate_prod_static.py"),
        ("COMMANDER_PREPROD_AGENT", "validate_device_installers.py"),
        ("COMMANDER_PREPROD_CONTRACT", "validate_prod_contracts.py"),
        ("COMMANDER_PREPROD_LIFECYCLE", "validate_device_lifecycle_races.py"),
        ("COMMANDER_PREPROD_PAIRING", "validate_pairing_supersession.py"),
        ("COMMANDER_PREPROD_RETENTION", "validate_session_retention.py"),
        ("COMMANDER_PREPROD_ORIGIN", "validate_portal_origin_guard.py"),
        ("COMMANDER_PREPROD_CLAIM_REVOKE_RACE", "validate_claim_revoke_race.py"),
        ("COMMANDER_PREPROD_INVITE_CLAIM_RACE", "validate_invite_claim_race.py"),
    )
    for label, script in checks:
        run(label, [
            sys.executable,
            f"apps/commander/scripts/{script}",
        ])

    migration = ROOT / "apps/commander/migrations/0009_pairing_supersession.sql"
    worker = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
    wrangler = (ROOT / "apps/commander/wrangler.jsonc").read_text(encoding="utf-8")
    assert migration.is_file(), "PAIRING_MIGRATION_0009_MISSING"
    assert "superseded_at_utc" in worker, "WORKER_PAIRING_COLUMN_MISSING"
    assert '"workers_dev": false' in wrangler, "WORKERS_DEV_NOT_DISABLED"
    assert '"preview_urls": false' in wrangler, "PREVIEW_URLS_NOT_DISABLED"
    print("COMMANDER_PREPROD_DEPLOY_ORDER_CONTRACT=PASS")
    print("COMMANDER_SOURCE_PREPROD_READY=PASS")

    if args.live_readonly:
        run("COMMANDER_IDENTITY_LIVE_READONLY", [
            sys.executable,
            "apps/identity-login/scripts/validate_live_white_label.py",
        ])
        run("COMMANDER_PROD_D1_LIVE_READONLY", [
            sys.executable,
            "apps/commander/scripts/commander_prod_readback.py",
            "--attempts", "3",
        ])

    print("COMMANDER_PROD_D1_MIGRATION_0009=PENDING_PROMOTION_GATE")
    print("COMMANDER_PROD_WORKER_DEPLOYMENT=PENDING_PROMOTION_GATE")
    print("COMMANDER_HUMAN_HOMOLOGATION=PENDING_OPERATOR_GATE")
    print("COMMANDER_FIRST_DEVICE_E2E=PENDING_HOMOLOGATION")

if __name__ == "__main__":
    main()
