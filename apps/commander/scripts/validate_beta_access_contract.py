#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")
HTML=(APP/"public/index.html").read_text(encoding="utf-8")
JS=(APP/"public/app.js").read_text(encoding="utf-8")
MIG=(APP/"migrations/0020_beta_access_requests.sql").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise AssertionError("COMMANDER_BETA_ACCESS_"+code+"=FAIL")
    print("COMMANDER_BETA_ACCESS_"+code+"=PASS")

need("async function portalBetaAccessStatus" in WORKER and "async function requestPortalBetaAccess" in WORKER,"HELPERS")
need('url.pathname === "/api/portal/beta-access"' in WORKER,"ROUTE")
need("requirePortalMutationOrigin(request)" in WORKER and "enforcePortalMutationRateLimit(env,session)" in WORKER,"MUTATION_GUARDS")
need("BETA_ACCESS_ADMIN_REQUIRED" in WORKER and '["OWNER","ADMIN"]' in WORKER,"ROLE_GUARD")
need("BETA_ACCESS_PLAN_UNAVAILABLE" in WORKER and "plan_code = 'STANDARD'" in WORKER,"STANDARD_ONLY")
need("message" not in MIG.lower() and "payload" not in MIG.lower() and "email" not in MIG.lower(),"NO_FREE_TEXT_OR_DUPLICATE_EMAIL")
need("UNIQUE (tenant_id, subject_id, plan_code)" in MIG,"IDEMPOTENT_IDENTITY")
need('data-beta-access type="button"' in HTML,"BUTTON")
need('function requestBetaAccess(button)' in JS and 'fetch("/api/portal/beta-access"' in JS,"PORTAL_FLOW")
need('"Solicitação enviada"' in JS and '"Acesso beta aprovado"' in JS,"STATE_UX")

db=sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys=OFF")
db.executescript("CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);\nCREATE TABLE users(subject_id TEXT PRIMARY KEY,tenant_id TEXT);\nINSERT INTO tenants VALUES('T1');\nINSERT INTO users VALUES('U1','T1');")
db.executescript(MIG)
db.execute("INSERT INTO commander_beta_access_requests VALUES(?,?,?,?,?,?,?)",(
    "R1","T1","U1","STANDARD","REQUESTED","2026-10-05T00:00:00Z","2026-10-05T00:00:00Z"))
try:
    db.execute("INSERT INTO commander_beta_access_requests VALUES(?,?,?,?,?,?,?)",(
        "R2","T1","U1","STANDARD","REQUESTED","2026-10-05T00:01:00Z","2026-10-05T00:01:00Z"))
    raise AssertionError("COMMANDER_BETA_ACCESS_DUPLICATE_GUARD=FAIL")
except sqlite3.IntegrityError:
    print("COMMANDER_BETA_ACCESS_DUPLICATE_GUARD=PASS")
print("COMMANDER_BETA_ACCESS_CONTRACT=PASS")
