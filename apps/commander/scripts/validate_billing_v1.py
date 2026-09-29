#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

COMMANDER = Path(__file__).resolve().parent.parent
ROOT = COMMANDER.parent.parent
MIGRATION = COMMANDER / "migrations" / "0013_billing_v1.sql"
BILLING = COMMANDER / "src" / "billing.mjs"
WORKER = COMMANDER / "src" / "worker.js"
WRANGLER = COMMANDER / "wrangler.jsonc"
SELFTEST = COMMANDER / "scripts" / "billing_v1_selftest.mjs"
PREFLIGHT = COMMANDER / "scripts" / "billing_prod_activation_preflight.py"
RUNBOOK = ROOT / "docs" / "operations" / "HARA_COMMANDER_BILLING_PROD_ACTIVATION_RUNBOOK.md"

BASE_SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE tenants (
  tenant_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  state TEXT NOT NULL,
  environment TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);

CREATE TABLE plans (
  plan_code TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  period_kind TEXT NOT NULL,
  unit_limit INTEGER,
  state TEXT NOT NULL
);

CREATE TABLE entitlements (
  entitlement_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  subject_id TEXT,
  plan_code TEXT NOT NULL REFERENCES plans(plan_code),
  state TEXT NOT NULL,
  valid_from_utc TEXT NOT NULL,
  valid_until_utc TEXT
);

CREATE TABLE billing_connections (
  billing_connection_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  provider TEXT NOT NULL,
  external_customer_id TEXT,
  external_subscription_id TEXT,
  state TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

INSERT INTO tenants VALUES
  ('T1','Tenant','ACTIVE','PRODUCTION','2026-09-29T00:00:00Z');
INSERT INTO plans VALUES
  ('TRIAL','Trial','HARA_COMMANDER_GOVERNED_INVOKE','CALENDAR_MONTH',100,'ACTIVE');
INSERT INTO billing_connections VALUES
  ('LEGACY:T1','T1','LEGACY',NULL,NULL,'ACTIVE','2026-09-29T00:00:00Z','2026-09-29T00:00:00Z');
"""


def main() -> int:
    migration = MIGRATION.read_text(encoding="utf-8")
    source = BILLING.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    wrangler = WRANGLER.read_text(encoding="utf-8")
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "ALTER TABLE billing_connections ADD COLUMN plan_code" in migration
    assert "billing_webhook_events" in migration
    assert "idx_billing_provider_customer" in migration
    assert "idx_billing_provider_subscription" in migration

    db = sqlite3.connect(":memory:")
    db.executescript(BASE_SCHEMA)
    db.executescript(migration)

    columns = {
        row[1] for row in db.execute("PRAGMA table_info(billing_connections)")
    }
    assert {
        "plan_code",
        "subscription_status",
        "current_period_end_utc",
        "cancel_at_period_end",
    }.issubset(columns)

    assert db.execute(
        "SELECT count(*) FROM billing_connections WHERE billing_connection_id='LEGACY:T1'"
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='billing_webhook_events'"
    ).fetchone()[0] == "billing_webhook_events"
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    required_source = (
        "verifyStripeWebhookSignature",
        "stripe-signature",
        "WEBHOOK_TOLERANCE_SECONDS = 300",
        "WEBHOOK_MAX_BYTES = 512 * 1024",
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
        "BILLING_PLAN_UNAVAILABLE",
        "BILLING_PRICE_MISMATCH",
        "tax_id_collection[enabled]",
        "subscription_data[metadata][tenant_id]",
        "secret_material_exposed: false",
    )
    for token in required_source:
        assert token in source, token

    required_routes = (
        '"/api/billing/stripe/webhook"',
        '"/api/portal/billing"',
        '"/api/portal/billing/checkout"',
        '"/api/portal/billing/portal"',
        "requirePortalMutationOrigin(request)",
        "enforcePortalMutationRateLimit(env, session)",
    )
    for token in required_routes:
        assert token in worker, token

    # Billing secrets and price IDs are runtime configuration only.
    for forbidden in ("sk_live_", "sk_test_", "whsec_", "price_"):
        assert forbidden not in wrangler, forbidden

    # Commercial price/capacity is deliberately not invented in source.
    assert "STRIPE_PRICE_STANDARD" in source
    assert "STRIPE_PRICE_SCALE" in source
    assert "INSERT INTO plans" not in migration

    # Activation tooling is read-only by default and records the approved Trial direction.
    assert "TRIAL_CURRENT_PROD_UNITS = 100" in preflight
    assert "TRIAL_TARGET_MONTHLY_UNITS = 10_000" in preflight
    assert "TRIAL_PROD_CHANGE_NOW=FALSE" in runbook
    assert "STRIPE_SECRET_KEY=PENDING" in runbook
    assert "COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE" in runbook
    for forbidden in ("wrangler secret put", "INSERT INTO plans", "UPDATE plans", "DELETE FROM plans"):
        assert forbidden not in preflight, forbidden

    subprocess.run(
        ["node", str(SELFTEST)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        ["python3", str(PREFLIGHT)],
        cwd=ROOT,
        check=True,
    )

    print("COMMANDER_BILLING_V1_SCHEMA=PASS")
    print("COMMANDER_BILLING_V1_WEBHOOK_SIGNATURE=PASS")
    print("COMMANDER_BILLING_V1_IDEMPOTENCY=SOURCE_BOUND")
    print("COMMANDER_BILLING_V1_ENTITLEMENT_BRIDGE=PASS")
    print("COMMANDER_BILLING_V1_CHECKOUT_PORTAL=PASS")
    print("COMMANDER_BILLING_V1_SECRETS_IN_GIT=FALSE")
    print("COMMANDER_BILLING_V1_COMMERCIAL_PRICE_INVENTED=FALSE")
    print("COMMANDER_BILLING_PROD_ACTIVATION_PREFLIGHT=PASS")
    print("TRIAL_CURRENT_PROD_UNITS=100")
    print("TRIAL_TARGET_MONTHLY_UNITS=10000")
    print("TRIAL_PROD_CHANGE_NOW=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
