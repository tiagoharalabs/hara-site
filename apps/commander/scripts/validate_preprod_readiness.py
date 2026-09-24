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
    return proc.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-readonly",
        action="store_true",
        help="also run public Identity, PROD D1/runtime, fail-closed and deployment checks",
    )
    parser.add_argument(
        "--expect-prod-migration",
        choices=("pending", "applied", "any"),
        default="pending",
        help="expected PROD D1 migration 0009 state during live read-only validation",
    )
    parser.add_argument(
        "--expect-prod-assets",
        choices=("stale", "current", "any"),
        default="stale",
        help="expected public Commander asset state during live read-only validation",
    )
    parser.add_argument(
        "--expect-prod-worker-version",
        default="",
        help="optional exact Cloudflare Worker version expected at 100 percent",
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
    run("COMMANDER_PREPROD_DEVICE_TOOL_CONTRACT", [
        "node", "apps/commander/scripts/validate_device_tool_contract.mjs",
    ])
    checks = (
        ("COMMANDER_PREPROD_UI", "validate_prod_static.py"),
        ("COMMANDER_PREPROD_AGENT", "validate_device_installers.py"),
        ("COMMANDER_PREPROD_SUPPLY_CHAIN", "validate_bootstrap_supply_chain.py"),
        ("COMMANDER_PREPROD_CONTRACT", "validate_prod_contracts.py"),
        ("COMMANDER_PREPROD_LIFECYCLE", "validate_device_lifecycle_races.py"),
        ("COMMANDER_PREPROD_PAIRING", "validate_pairing_supersession.py"),
        ("COMMANDER_PREPROD_PAIRING_RETENTION", "validate_pairing_retention.py"),
        ("COMMANDER_PREPROD_RETENTION", "validate_session_retention.py"),
        ("COMMANDER_PREPROD_ORIGIN", "validate_portal_origin_guard.py"),
        ("COMMANDER_PREPROD_CLAIM_REVOKE_RACE", "validate_claim_revoke_race.py"),
        ("COMMANDER_PREPROD_INVITE_CLAIM_RACE", "validate_invite_claim_race.py"),
        ("COMMANDER_PREPROD_OIDC_TX_HYGIENE", "validate_oidc_transaction_hygiene.py"),
        ("COMMANDER_PREPROD_E2E_HARNESS", "validate_e2e_harness.py"),
        ("COMMANDER_PREPROD_FIRST_DEVICE_PREFLIGHT", "validate_first_device_preflight.py"),
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

    migration_state_line = None
    oidc_window_line = None
    oidc_active_line = None
    oidc_expired_line = None
    oidc_active_consumed_line = None
    pairing_retention_window_line = None
    pairing_retention_eligible_line = None
    pairing_current_valid_line = None
    pairing_terminal_unconsumed_line = None
    pairing_consumed_provenance_line = None
    retention_window_line = None
    retention_eligible_line = None
    retention_oldest_age_line = None
    runtime_asset_state_line = None
    worker_deployment_state_line = None
    worker_version_line = None
    if args.live_readonly:
        run("COMMANDER_IDENTITY_LIVE_READONLY", [
            sys.executable,
            "apps/identity-login/scripts/validate_live_white_label.py",
        ])
        d1_output = run("COMMANDER_PROD_D1_LIVE_READONLY", [
            sys.executable,
            "apps/commander/scripts/commander_prod_readback.py",
            "--attempts", "3",
            "--expect-migration-0009", args.expect_prod_migration,
        ])
        for line in d1_output.splitlines():
            if line.startswith("COMMANDER_PROD_D1_MIGRATION_0009="):
                migration_state_line = line
            elif line.startswith("COMMANDER_PROD_OIDC_TX_WINDOW_MINUTES="):
                oidc_window_line = line
            elif line.startswith("COMMANDER_PROD_OIDC_TX_ACTIVE="):
                oidc_active_line = line
            elif line.startswith("COMMANDER_PROD_OIDC_TX_EXPIRED="):
                oidc_expired_line = line
            elif line.startswith("COMMANDER_PROD_OIDC_TX_ACTIVE_CONSUMED="):
                oidc_active_consumed_line = line
            elif line.startswith("COMMANDER_PROD_PAIRING_RETENTION_WINDOW_DAYS="):
                pairing_retention_window_line = line
            elif line.startswith("COMMANDER_PROD_PAIRING_RETENTION_ELIGIBLE="):
                pairing_retention_eligible_line = line
            elif line.startswith("COMMANDER_PROD_PAIRING_CURRENT_VALID="):
                pairing_current_valid_line = line
            elif line.startswith("COMMANDER_PROD_PAIRING_TERMINAL_UNCONSUMED="):
                pairing_terminal_unconsumed_line = line
            elif line.startswith("COMMANDER_PROD_PAIRING_CONSUMED_PROVENANCE="):
                pairing_consumed_provenance_line = line
            elif line.startswith("COMMANDER_PROD_SESSION_RETENTION_WINDOW_DAYS="):
                retention_window_line = line
            elif line.startswith("COMMANDER_PROD_SESSION_RETENTION_ELIGIBLE="):
                retention_eligible_line = line
            elif line.startswith("COMMANDER_PROD_SESSION_OLDEST_EXPIRED_AGE_DAYS="):
                retention_oldest_age_line = line
        if migration_state_line is None:
            raise SystemExit("COMMANDER_PROD_D1_MIGRATION_STATE_MISSING")
        if (
            oidc_window_line is None
            or oidc_active_line is None
            or oidc_expired_line is None
            or oidc_active_consumed_line is None
        ):
            raise SystemExit("COMMANDER_PROD_OIDC_TX_STATE_MISSING")
        if (
            pairing_retention_window_line is None
            or pairing_retention_eligible_line is None
            or pairing_current_valid_line is None
            or pairing_terminal_unconsumed_line is None
            or pairing_consumed_provenance_line is None
        ):
            raise SystemExit("COMMANDER_PROD_PAIRING_RETENTION_STATE_MISSING")
        if (
            retention_window_line is None
            or retention_eligible_line is None
            or retention_oldest_age_line is None
        ):
            raise SystemExit("COMMANDER_PROD_SESSION_RETENTION_STATE_MISSING")
        runtime_output = run("COMMANDER_PROD_RUNTIME_LIVE_READONLY", [
            sys.executable,
            "apps/commander/scripts/validate_prod_runtime_drift.py",
            "--expect-assets", args.expect_prod_assets,
        ])
        for line in runtime_output.splitlines():
            if line.startswith("COMMANDER_PROD_RUNTIME_ASSETS="):
                runtime_asset_state_line = line
                break
        if runtime_asset_state_line is None:
            raise SystemExit("COMMANDER_PROD_RUNTIME_ASSET_STATE_MISSING")

        run("COMMANDER_PROD_FAIL_CLOSED_LIVE_READONLY", [
            sys.executable,
            "apps/commander/scripts/validate_prod_fail_closed.py",
        ])

        deployment_command = [
            sys.executable,
            "apps/commander/scripts/commander_prod_deployment_readback.py",
        ]
        if args.expect_prod_worker_version:
            deployment_command += [
                "--expect-version", args.expect_prod_worker_version,
            ]
        deployment_output = run(
            "COMMANDER_PROD_WORKER_LIVE_READONLY",
            deployment_command,
        )
        for line in deployment_output.splitlines():
            if line.startswith("COMMANDER_PROD_WORKER_DEPLOYMENT="):
                worker_deployment_state_line = line
            elif line.startswith("COMMANDER_PROD_WORKER_VERSION="):
                worker_version_line = line
        if worker_deployment_state_line is None or worker_version_line is None:
            raise SystemExit("COMMANDER_PROD_WORKER_STATE_MISSING")

    if migration_state_line:
        print(migration_state_line)
    else:
        print("COMMANDER_PROD_D1_MIGRATION_0009=LIVE_READBACK_REQUIRED")
    if oidc_window_line:
        print(oidc_window_line)
        print(oidc_active_line)
        print(oidc_expired_line)
        print(oidc_active_consumed_line)
    else:
        print("COMMANDER_PROD_OIDC_TX_STATE=LIVE_READBACK_REQUIRED")
    if pairing_retention_window_line:
        print(pairing_retention_window_line)
        print(pairing_retention_eligible_line)
        print(pairing_current_valid_line)
        print(pairing_terminal_unconsumed_line)
        print(pairing_consumed_provenance_line)
    else:
        print("COMMANDER_PROD_PAIRING_RETENTION_STATE=LIVE_READBACK_REQUIRED")
    if retention_window_line:
        print(retention_window_line)
        print(retention_eligible_line)
        print(retention_oldest_age_line)
    else:
        print("COMMANDER_PROD_SESSION_RETENTION_STATE=LIVE_READBACK_REQUIRED")
    if runtime_asset_state_line:
        print(runtime_asset_state_line)
    else:
        print("COMMANDER_PROD_RUNTIME_ASSETS=LIVE_READBACK_REQUIRED")
    if worker_deployment_state_line:
        print(worker_deployment_state_line)
        print(worker_version_line)
    else:
        print("COMMANDER_PROD_WORKER_DEPLOYMENT=LIVE_READBACK_REQUIRED")
    print("COMMANDER_HUMAN_HOMOLOGATION=PENDING_OPERATOR_GATE")
    print("COMMANDER_FIRST_DEVICE_E2E=PENDING_HOMOLOGATION")

if __name__ == "__main__":
    main()
