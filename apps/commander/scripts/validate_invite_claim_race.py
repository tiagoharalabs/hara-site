#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "apps/commander/migrations"
AUTH = (ROOT / "apps/commander/src/auth.js").read_text(encoding="utf-8")

db = sqlite3.connect(":memory:")
for name in ("0001_product.sql","0002_oidc_sessions.sql","0004_identity_bindings.sql"):
    db.executescript((MIG / name).read_text(encoding="utf-8"))

db.execute("INSERT INTO tenants VALUES (?,?,?,?,?)",
           ("T1","Tenant","ACTIVE","PRODUCTION","2026-09-24T00:00:00.000Z"))
db.execute("""INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES (?,?,?,?,?,?,?,?,?)""",
           ("S1","T1","urn:hara:invite","pending-s1","u@example.com","Invited",
            "ACTIVE","MEMBER","2026-09-24T00:00:00.000Z"))
db.execute("""INSERT INTO identity_invites
(invite_id,normalized_email,target_subject_id,state,created_at_utc,expires_at_utc,
 claimed_at_utc,claimed_issuer,claimed_subject)
VALUES ('I1','u@example.com','S1','ACTIVE','2026-09-24T00:00:00.000Z',
        '2026-09-25T00:00:00.000Z',NULL,NULL,NULL)""")

def claim(issuer, subject, claimed_at):
    with db:
        invite = db.execute(
            """UPDATE identity_invites
               SET state='CLAIMED', claimed_at_utc=?, claimed_issuer=?, claimed_subject=?
               WHERE invite_id='I1' AND state='ACTIVE'""",
            (claimed_at,issuer,subject),
        )
        user = db.execute(
            """UPDATE users
               SET oidc_issuer=?, oidc_subject=?, email='u@example.com', display_name='User'
               WHERE subject_id='S1' AND state='ACTIVE'
                 AND EXISTS (
                   SELECT 1 FROM identity_invites i
                   WHERE i.invite_id='I1'
                     AND i.state='CLAIMED'
                     AND i.claimed_at_utc=?
                     AND i.claimed_issuer=?
                     AND i.claimed_subject=?
                 )""",
            (issuer,subject,claimed_at,issuer,subject),
        )
        binding = db.execute(
            """INSERT OR IGNORE INTO identity_bindings
               (identity_binding_id,subject_id,provider_code,issuer,external_subject,
                state,created_at_utc,revoked_at_utc)
               SELECT 'PRIMARY:S1','S1','PRIMARY_OIDC',?,?, 'ACTIVE',?,NULL
               WHERE EXISTS (
                 SELECT 1 FROM identity_invites i
                 WHERE i.invite_id='I1'
                   AND i.state='CLAIMED'
                   AND i.claimed_at_utc=?
                   AND i.claimed_issuer=?
                   AND i.claimed_subject=?
               )""",
            (issuer,subject,claimed_at,claimed_at,issuer,subject),
        )
    return invite.rowcount, user.rowcount, binding.rowcount

first = claim("https://issuer.example/","subject-A","2026-09-24T00:01:00.000Z")
assert first == (1,1,1), f"FIRST_CLAIM_FAILED:{first}"
second = claim("https://issuer.example/","subject-B","2026-09-24T00:01:01.000Z")
assert second == (0,0,0), f"LOSING_CLAIM_MUTATED_STATE:{second}"

user = db.execute(
    "SELECT oidc_issuer,oidc_subject FROM users WHERE subject_id='S1'"
).fetchone()
assert user == ("https://issuer.example/","subject-A"), f"USER_IDENTITY_OVERWRITTEN:{user}"

invite = db.execute(
    "SELECT state,claimed_issuer,claimed_subject FROM identity_invites WHERE invite_id='I1'"
).fetchone()
assert invite == ("CLAIMED","https://issuer.example/","subject-A"), f"INVITE_OWNER_CHANGED:{invite}"

bindings = db.execute(
    "SELECT issuer,external_subject FROM identity_bindings WHERE subject_id='S1' ORDER BY issuer"
).fetchall()
assert bindings == [("https://issuer.example/","subject-A")], f"LOSING_BINDING_CREATED:{bindings}"

claim_block = AUTH.split("const claimedAt = nowIso();",1)[1].split(
    "user = await env.PRODUCT_DB.prepare",1
)[0]
assert claim_block.index("UPDATE identity_invites") < claim_block.index("UPDATE users")
assert "i.claimed_issuer = ?" in claim_block
assert "i.claimed_subject = ?" in claim_block
assert "INSERT OR IGNORE INTO identity_bindings" in claim_block
assert claim_block.count("EXISTS (") >= 2

print("COMMANDER_INVITE_FIRST_CLAIM=PASS")
print("COMMANDER_INVITE_LOSING_CLAIM_MUTATION=ABSENT")
print("COMMANDER_INVITE_IDENTITY_OVERWRITE=BLOCKED")
print("COMMANDER_INVITE_BINDING_RACE=BLOCKED")
