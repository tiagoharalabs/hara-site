#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMMANDER = ROOT / "apps" / "commander"
WRANGLER = COMMANDER / "wrangler.jsonc"
WRANGLER_BIN = ROOT / "node_modules/.bin/wrangler"

REQUIRED_SECRET_NAMES = {
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
}
REQUIRED_PRICE_NAMES = {
    "STRIPE_PRICE_STANDARD",
}

TRIAL_PREVIOUS_PROD_UNITS = 100
TRIAL_TARGET_MONTHLY_UNITS = 10_000
STANDARD_APPROVED_BRL_MONTHLY_CENTS = 8_000


def run_json(args: list[str]) -> object:
    """Only allow read-only PROD inspection using the installed Wrangler.

    A bounded second attempt tolerates transient Cloudflare API failures while
    never printing CLI stderr, account credentials or customer content.
    """
    if args[:2] != ["npx", "wrangler"]:
        raise RuntimeError("BILLING_PREFLIGHT_WRANGLER_COMMAND_DENIED")
    tail = args[2:]
    if tail[:2] == ["secret", "list"]:
        pass
    elif tail[:2] == ["d1", "execute"]:
        if "--remote" not in tail or "--command" not in tail:
            raise RuntimeError("BILLING_PREFLIGHT_D1_REMOTE_READ_REQUIRED")
        sql = tail[tail.index("--command") + 1].strip()
        if not sql.upper().startswith("SELECT ") or ";" in sql.rstrip(";"):
            raise RuntimeError("BILLING_PREFLIGHT_READ_ONLY_SQL_REQUIRED")
    else:
        raise RuntimeError("BILLING_PREFLIGHT_COMMAND_NOT_READONLY")
    if not WRANGLER_BIN.is_file():
        raise RuntimeError("BILLING_PREFLIGHT_WRANGLER_NOT_INSTALLED")
    command = [str(WRANGLER_BIN), *tail]
    for attempt in range(2):
        try:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=35,
            )
        except subprocess.TimeoutExpired:
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise RuntimeError("BILLING_PREFLIGHT_READ_TIMEOUT") from None
        if proc.returncode != 0:
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise RuntimeError("BILLING_PREFLIGHT_READ_UNAVAILABLE")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise RuntimeError("BILLING_PREFLIGHT_NON_JSON_RESPONSE") from None
    raise RuntimeError("BILLING_PREFLIGHT_RETRY_EXHAUSTED")


def secret_names() -> set[str]:
    data = run_json([
        "npx", "wrangler", "secret", "list",
        "-c", str(WRANGLER),
    ])
    if not isinstance(data, list):
        raise RuntimeError("SECRET_LIST_INVALID")
    return {
        str(item.get("name") or "")
        for item in data
        if isinstance(item, dict) and item.get("name")
    }


def d1_rows(sql: str) -> list[dict]:
    data = run_json([
        "npx", "wrangler", "d1", "execute",
        "hara-commander-product-prod",
        "--remote",
        "--json",
        "-c", str(WRANGLER),
        "--command", sql,
    ])
    if not isinstance(data, list) or not data:
        raise RuntimeError("D1_RESULT_INVALID")
    results = data[0].get("results") if isinstance(data[0], dict) else None
    if not isinstance(results, list):
        raise RuntimeError("D1_ROWS_INVALID")
    return [row for row in results if isinstance(row, dict)]


def live_preflight() -> int:
    names = secret_names()
    missing_secrets = sorted(REQUIRED_SECRET_NAMES - names)

    plan_rows = d1_rows(
        "SELECT plan_code, display_name, period_kind, unit_limit, state "
        "FROM plans ORDER BY plan_code;"
    )
    plans = {str(row.get("plan_code") or ""): row for row in plan_rows}
    trial = plans.get("TRIAL") or {}
    standard = plans.get("STANDARD")
    scale = plans.get("SCALE")

    schema_rows = d1_rows(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name IN "
        "('billing_connections','billing_webhook_events','entitlements','plans') "
        "ORDER BY name;"
    )
    schema_names = {str(row.get("name") or "") for row in schema_rows}
    schema_ok = schema_names == {
        "billing_connections",
        "billing_webhook_events",
        "entitlements",
        "plans",
    }

    counts = d1_rows(
        "SELECT "
        "(SELECT COUNT(*) FROM billing_connections) AS billing_connections_count, "
        "(SELECT COUNT(*) FROM billing_webhook_events) AS billing_webhook_events_count;"
    )
    count_row = counts[0] if counts else {}

    print("COMMANDER_BILLING_PROD_SCHEMA=" + ("PASS" if schema_ok else "FAIL"))
    print("TRIAL_CURRENT_PROD_UNITS=" + str(trial.get("unit_limit")))
    print("TRIAL_LIVE_ALIGNED=" + ("TRUE" if int(trial.get("unit_limit") or 0) == TRIAL_TARGET_MONTHLY_UNITS and trial.get("period_kind") == "CALENDAR_MONTH" else "FALSE"))
    print("TRIAL_TARGET_MONTHLY_UNITS=" + str(TRIAL_TARGET_MONTHLY_UNITS))
    print("COMMERCIAL_TERMS_AUTHORIZED=TRUE")
    print("STANDARD_APPROVED_BRL_MONTHLY_CENTS=" + str(STANDARD_APPROVED_BRL_MONTHLY_CENTS))
    print("STANDARD_APPROVED_USAGE=UNLIMITED")
    print(
        "STANDARD_LIVE_UNLIMITED="
        + ("TRUE" if standard and standard.get("period_kind") == "NONE" and standard.get("unit_limit") is None else "FALSE")
    )
    print("STANDARD_CATALOG_ACTIVE=" + ("TRUE" if standard and standard.get("state") == "ACTIVE" else "FALSE"))
    print("SCALE_CATALOG_ACTIVE=" + ("TRUE" if scale and scale.get("state") == "ACTIVE" else "FALSE"))
    print("STRIPE_SECRET_KEY=" + ("READY" if "STRIPE_SECRET_KEY" in names else "PENDING"))
    print("STRIPE_WEBHOOK_SECRET=" + ("READY" if "STRIPE_WEBHOOK_SECRET" in names else "PENDING"))
    # Price IDs are intentionally runtime config, but may be kept as Worker secrets.
    print("STRIPE_PRICE_STANDARD=" + ("READY" if "STRIPE_PRICE_STANDARD" in names else "PENDING"))
    print("STRIPE_PRICE_SCALE=" + ("READY" if "STRIPE_PRICE_SCALE" in names else "PENDING"))
    print("BILLING_CONNECTIONS=" + str(count_row.get("billing_connections_count", 0)))
    print("BILLING_WEBHOOK_EVENTS=" + str(count_row.get("billing_webhook_events_count", 0)))

    ready = (
        schema_ok
        and not missing_secrets
        and REQUIRED_PRICE_NAMES.issubset(names)
        and int(trial.get("unit_limit") or 0) == TRIAL_TARGET_MONTHLY_UNITS
        and trial.get("period_kind") == "CALENDAR_MONTH"
        and standard is not None
        and standard.get("state") == "ACTIVE"
        and standard.get("period_kind") == "NONE"
        and standard.get("unit_limit") is None
    )
    print("COMMANDER_BILLING_FIRST_CHECKOUT_READY=" + ("TRUE" if ready else "FALSE"))
    print("PROD_MUTATION=FALSE")
    return 0 if schema_ok else 1


def source_preflight() -> int:
    billing = (COMMANDER / "src" / "billing.mjs").read_text(encoding="utf-8")
    worker = (COMMANDER / "src" / "worker.js").read_text(encoding="utf-8")
    migration = (COMMANDER / "migrations" / "0013_billing_v1.sql").read_text(encoding="utf-8")

    checks = {
        "checkout": 'mode: "subscription"' in billing,
        "portal": "/billing_portal/sessions" in billing,
        "webhook_signature": "verifyStripeWebhookSignature" in billing,
        "idempotency": "billing_webhook_events" in billing and "billing_webhook_events" in migration,
        "entitlement_bridge": "syncPaidEntitlement" in billing,
        "webhook_route": '/api/billing/stripe/webhook' in worker,
        "checkout_route": '/api/portal/billing/checkout' in worker,
        "portal_route": '/api/portal/billing/portal' in worker,
    }
    for key, ok in checks.items():
        print("BILLING_SOURCE_" + key.upper() + "=" + ("PASS" if ok else "FAIL"))
    print("TRIAL_PREVIOUS_PROD_UNITS=" + str(TRIAL_PREVIOUS_PROD_UNITS))
    print("TRIAL_TARGET_MONTHLY_UNITS=" + str(TRIAL_TARGET_MONTHLY_UNITS))
    print("TRIAL_PROD_CHANGE_NOW=TRUE")
    print("STANDARD_APPROVED_BRL_MONTHLY_CENTS=" + str(STANDARD_APPROVED_BRL_MONTHLY_CENTS))
    print("STANDARD_APPROVED_USAGE=UNLIMITED")
    print("COMMERCIAL_TERMS_AUTHORIZED=TRUE")
    return 0 if all(checks.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="read PROD secret names and D1 catalog without mutating anything",
    )
    args = parser.parse_args()
    return live_preflight() if args.live else source_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
