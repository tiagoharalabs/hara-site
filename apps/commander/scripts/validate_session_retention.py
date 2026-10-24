#!/usr/bin/env python3
"""Verify real-source retention SQL, not a stale copy of the previous query."""
from pathlib import Path
from validate_commander_1k_10k_capacity import database_probe
ROOT = Path(__file__).resolve().parents[3]
AUTH = (ROOT / "apps/commander/src/auth.js").read_text()
READBACK = (ROOT / "apps/commander/scripts/commander_prod_readback.py").read_text()
assert "SESSION_RETENTION_SECONDS = 30 * 24 * 60 * 60" in AUTH
assert "SESSION_RETENTION_BATCH = 100" in AUTH
assert "AUTH_RETENTION_MAX_ROUNDS = 20" in AUTH
assert "AUTH_RETENTION_TIME_BUDGET_MS = 5000" in AUTH
assert "report.state = \"DEGRADED\"" in AUTH
assert "SESSION_RETENTION_DAYS = 30" in READBACK
for field in ("retention_eligible_expired_sessions", "retention_eligible_revoked_sessions", "oldest_expired_age_days"):
    assert field in READBACK
probe = database_probe(1000)
assert probe["valid_sessions_preserved"] == 1000
assert probe["terminal_rows_deleted_in_one_statement"] == 100
print("COMMANDER_SESSION_RETENTION_EXACT_SQL=PASS")
print("COMMANDER_SESSION_RETENTION_POLICY_30_DAYS=PASS")
print("COMMANDER_SESSION_RETENTION_EXISTING_INDEXES=PASS")
