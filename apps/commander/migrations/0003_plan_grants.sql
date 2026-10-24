PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS plan_grants (
  plan_code TEXT NOT NULL REFERENCES plans(plan_code) ON DELETE CASCADE,
  grant_code TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  PRIMARY KEY (plan_code, grant_code)
);

CREATE INDEX IF NOT EXISTS idx_plan_grants_plan
  ON plan_grants(plan_code);

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
SELECT plan_code, 'COMMANDER_DISCOVERY', '2026-09-22T14:20:00Z'
FROM plans
WHERE plan_code IN ('TRIAL','STANDARD','SCALE','DEV_ONE_UNIT');

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
SELECT plan_code, 'COMMANDER_READ_ONLY_INVOKE', '2026-09-22T14:20:00Z'
FROM plans
WHERE plan_code IN ('TRIAL','STANDARD','SCALE','DEV_ONE_UNIT');

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
SELECT plan_code, 'COMMANDER_RECEIPT_READ', '2026-09-22T14:20:00Z'
FROM plans
WHERE plan_code IN ('TRIAL','STANDARD','SCALE','DEV_ONE_UNIT');
