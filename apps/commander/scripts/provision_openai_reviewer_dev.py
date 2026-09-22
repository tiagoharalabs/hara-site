#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CONFIG = APP / ".generated" / "wrangler.remote.dev.json"
DB_NAME = "hara-commander-product-dev"

TENANT_ID = "HARA-TENANT-REVIEW-0001"
SUBJECT_ID = "HARA-SUBJECT-REVIEW-0001"
ENTITLEMENT_ID = "HARA-ENTITLEMENT-REVIEW-0001"
BILLING_ID = "HARA-BILLING-REVIEW-0001"
INVITE_ID = "HARA-INVITE-OPENAI-REVIEW-0001"
EMAIL = "openai-reviewer@haralabs.com.br"
PLAN = "REVIEW"

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def run_wrangler(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npx", "--yes", "wrangler@4.136.1", *args],
        cwd=APP,
        text=True,
        capture_output=True,
        check=False,
    )

def main() -> int:
    if not CONFIG.is_file():
        print("REVIEWER_REMOTE_CONFIG=FAIL")
        return 2

    now = datetime.now(timezone.utc)
    created = iso(now)
    expires = iso(now + timedelta(days=90))

    sql = f"""
PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO tenants
  (tenant_id, display_name, state, environment, created_at_utc)
VALUES
  ('{TENANT_ID}', 'HARA Review', 'ACTIVE', 'REVIEW', '{created}');

INSERT OR IGNORE INTO plans
  (plan_code, display_name, meter_id, period_kind, unit_limit, state)
VALUES
  ('{PLAN}', 'OpenAI Review', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 100, 'ACTIVE');

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc) VALUES
  ('{PLAN}', 'COMMANDER_DISCOVERY', '{created}'),
  ('{PLAN}', 'COMMANDER_READ_ONLY_INVOKE', '{created}'),
  ('{PLAN}', 'COMMANDER_RECEIPT_READ', '{created}');

INSERT OR IGNORE INTO users
  (subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name, state, role, created_at_utc)
VALUES
  ('{SUBJECT_ID}', '{TENANT_ID}', 'https://review.pending.haralabs.invalid/', 'openai-reviewer-pending',
   '{EMAIL}', 'OpenAI Reviewer', 'ACTIVE', 'REVIEWER', '{created}');

INSERT OR IGNORE INTO entitlements
  (entitlement_id, tenant_id, subject_id, plan_code, state, valid_from_utc, valid_until_utc)
VALUES
  ('{ENTITLEMENT_ID}', '{TENANT_ID}', '{SUBJECT_ID}', '{PLAN}', 'ACTIVE', '{created}', NULL);

INSERT OR IGNORE INTO billing_connections
  (billing_connection_id, tenant_id, provider, external_customer_id, external_subscription_id, state, created_at_utc, updated_at_utc)
VALUES
  ('{BILLING_ID}', '{TENANT_ID}', 'REVIEW_NO_BILLING', NULL, NULL, 'NOT_CONNECTED', '{created}', '{created}');

INSERT OR IGNORE INTO identity_invites
  (invite_id, normalized_email, target_subject_id, state, created_at_utc, expires_at_utc,
   claimed_at_utc, claimed_issuer, claimed_subject)
VALUES
  ('{INVITE_ID}', '{EMAIL}', '{SUBJECT_ID}', 'ACTIVE', '{created}', '{expires}', NULL, NULL, NULL);
"""

    applied = run_wrangler(
        "d1", "execute", DB_NAME,
        "--remote", "--config", str(CONFIG),
        "--command", sql,
    )
    if applied.returncode != 0:
        print("REVIEWER_D1_PROVISION=FAIL")
        print((applied.stderr or applied.stdout or "")[:1200])
        return applied.returncode or 1

    verify_sql = f"""
SELECT t.tenant_id,t.display_name,t.state,t.environment,
       u.subject_id,u.email,u.display_name,u.state AS user_state,u.role,
       e.entitlement_id,e.plan_code,e.state AS entitlement_state,
       p.unit_limit,
       i.invite_id,i.state AS invite_state,i.expires_at_utc
FROM tenants t
JOIN users u ON u.tenant_id=t.tenant_id
JOIN entitlements e ON e.tenant_id=t.tenant_id AND e.subject_id=u.subject_id
JOIN plans p ON p.plan_code=e.plan_code
JOIN identity_invites i ON i.target_subject_id=u.subject_id
WHERE t.tenant_id='{TENANT_ID}';
"""
    verified = run_wrangler(
        "d1", "execute", DB_NAME,
        "--remote", "--config", str(CONFIG),
        "--json", "--command", verify_sql,
    )
    if verified.returncode != 0:
        print("REVIEWER_D1_VERIFY=FAIL")
        return verified.returncode or 1
    data = json.loads(verified.stdout or "[]")
    rows = []
    for part in data:
        rows.extend(part.get("results") or [])
    if len(rows) != 1:
        print("REVIEWER_D1_VERIFY=FAIL_ROW_COUNT")
        return 3
    row = rows[0]
    if (
        row.get("tenant_id") != TENANT_ID
        or row.get("environment") != "REVIEW"
        or row.get("role") != "REVIEWER"
        or row.get("plan_code") != PLAN
        or row.get("entitlement_state") != "ACTIVE"
        or row.get("invite_state") not in {"ACTIVE", "CLAIMED"}
        or int(row.get("unit_limit") or 0) != 100
    ):
        print("REVIEWER_D1_VERIFY=FAIL_STATE")
        return 4

    print("REVIEWER_D1_PROVISION=PASS")
    print("REVIEWER_TENANT=HARA Review")
    print("REVIEWER_ROLE=REVIEWER")
    print("REVIEWER_PLAN=REVIEW")
    print("REVIEWER_QUOTA=100")
    print("REVIEWER_INVITE_STATE=" + str(row.get("invite_state")))
    print("REVIEWER_CREDENTIAL_IN_GIT=FALSE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
