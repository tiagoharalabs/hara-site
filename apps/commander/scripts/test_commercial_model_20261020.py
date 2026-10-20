#!/usr/bin/env python3
"""Final catalog contract over historical, already-applied migrations."""
from __future__ import annotations

import sqlite3
from pathlib import Path
import unittest

APP = Path(__file__).resolve().parents[1]
MIGRATIONS = APP / "migrations"


class CommercialCatalogTests(unittest.TestCase):
    def test_additive_migration_preserves_founder_and_sets_customer_limits(self):
        db = sqlite3.connect(":memory:")
        db.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE plans (
              plan_code TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              meter_id TEXT NOT NULL,
              period_kind TEXT NOT NULL CHECK (period_kind IN ('CALENDAR_MONTH','LIFETIME','NONE')),
              unit_limit INTEGER,
              state TEXT NOT NULL,
              CHECK ((period_kind='NONE' AND unit_limit IS NULL) OR
                     (period_kind<>'NONE' AND unit_limit>0))
            );
            CREATE TABLE plan_grants (
              plan_code TEXT NOT NULL REFERENCES plans(plan_code),
              grant_code TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              PRIMARY KEY(plan_code,grant_code)
            );
        """)
        for name in (
            "0008_trial_onboarding.sql", "0014_founder_internal_entitlement.sql",
            "0019_standard_beta_plan.sql", "0021_commercial_terms_20261005.sql",
            "0031_free_15000_20261010.sql", "0032_free_10000_revert_20261010.sql",
            "0036_commander_prelaunch_commercial_terms.sql",
        ):
            db.executescript((MIGRATIONS / name).read_text())
        rows = {
            row[0]: row[1:] for row in db.execute(
                "SELECT plan_code,period_kind,unit_limit,active_device_limit,state FROM plans"
            )
        }
        self.assertEqual(rows["TRIAL"], ("LIFETIME", 5000, 5, "ACTIVE"))
        self.assertEqual(rows["STANDARD"], ("CALENDAR_MONTH", 1_000_000, 5, "ACTIVE"))
        self.assertEqual(rows["FOUNDER_INTERNAL"], ("NONE", None, None, "ACTIVE"))
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
