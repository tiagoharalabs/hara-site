#!/usr/bin/env python3
"""Isolated DEV fixtures for acceptance; secrets stay in owner-only files."""
from __future__ import annotations
import argparse, base64, hashlib, importlib.util, json, os, re, secrets, stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
PRIVATE = APP / ".generated" / "full-acceptance-20261012"
CANARY = Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/apps/commander/.generated/mcp-product-dev-canary-token")
spec = importlib.util.spec_from_file_location("fresh", APP / "scripts/commander_fresh_customer_dev_acceptance.py")
fresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fresh)

def guard():
    cfg = json.loads((APP / "wrangler.dev.jsonc").read_text())
    assert cfg["name"] == "hara-commander-dev-v2"
    assert cfg["vars"]["ENVIRONMENT"] == "DEV"
    assert cfg["d1_databases"][0]["database_id"] == "698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
    assert fresh.DEV_ORIGIN == "https://hara-commander-dev-v2.tiago-sartori.workers.dev"

def secure_dir():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    s = PRIVATE.lstat()
    assert stat.S_ISDIR(s.st_mode) and not stat.S_ISLNK(s.st_mode) and s.st_uid == os.getuid()
    PRIVATE.chmod(0o700)

def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s = os.fstat(f.fileno())
        assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o600
        return json.load(f)

def create(purpose, external_subject=None):
    guard()
    assert re.fullmatch(r"[a-z0-9-]{1,40}", purpose)
    secure_dir()
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(4)
    tenant, subject = "HARA-ACCEPT-T-" + suffix, "HARA-ACCEPT-S-" + suffix
    identity, entitlement, pairing = ("HARA-ACCEPT-I-" + suffix, "HARA-ACCEPT-E-" + suffix, "HARA-ACCEPT-P-" + suffix)
    external = external_subject or ("accept-" + purpose + "-" + suffix)
    assert re.fullmatch(r"[A-Za-z0-9:@._-]{1,255}", external)
    assert not fresh.rows("SELECT identity_binding_id FROM identity_bindings WHERE issuer="+fresh.q(fresh.ISSUER)+" AND external_subject="+fresh.q(external)+";")
    now = datetime.now(timezone.utc)
    stamp = lambda d: d.isoformat(timespec="seconds").replace("+00:00", "Z")
    token, cookie = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    q = fresh.q
    h = fresh.b64url_sha256
    sql = f"""
INSERT INTO tenants VALUES ({q(tenant)},'Acceptance DEV','ACTIVE','DEV',{q(stamp(now))});
INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(subject)},{q(tenant)},{q(fresh.ISSUER)},{q(external)},NULL,'Acceptance DEV','ACTIVE','OWNER',{q(stamp(now))});
INSERT INTO identity_bindings VALUES ({q(identity)},{q(subject)},'PRIMARY_OIDC',{q(fresh.ISSUER)},{q(external)},'ACTIVE',{q(stamp(now))},NULL);
INSERT INTO entitlements VALUES ({q(entitlement)},{q(tenant)},{q(subject)},'TRIAL','ACTIVE',{q(stamp(now))},NULL);
INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc)
VALUES ({q(pairing)},{q(h(token))},{q(tenant)},{q(subject)},{q(stamp(now))},{q(stamp(now+timedelta(minutes=10)))},NULL,NULL);
INSERT INTO portal_sessions VALUES ({q(h(cookie))},{q(subject)},{q(stamp(now))},{q(stamp(now+timedelta(hours=2)))},{q(stamp(now))},NULL);
"""
    data = dict(schema="hara.dev-private-fixture.v1", purpose=purpose, environment="DEV", tenant_id=tenant,
                subject_id=subject, external_subject=external, issuer=fresh.ISSUER, entitlement_id=entitlement,
                pairing_id=pairing, pairing_token=token, session_cookie=cookie, dev_origin=fresh.DEV_ORIGIN,
                created_at=stamp(now), pairing_expires_at=stamp(now+timedelta(minutes=10)), canary_token_file=str(CANARY))
    path = PRIVATE / (purpose + "-" + suffix + ".json")
    write_private(path, data)
    try:
        fresh.d1(sql)
    except Exception:
        cleanup(path)
        raise
    return path

def refresh_pairing(path):
    guard()
    data = read_private(path)
    assert data["environment"] == "DEV" and data["tenant_id"].startswith("HARA-ACCEPT-T-")
    token = secrets.token_urlsafe(32)
    pairing = "HARA-ACCEPT-P-" + secrets.token_hex(12)
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=10)
    stamp = lambda d: d.isoformat(timespec="seconds").replace("+00:00", "Z")
    q = fresh.q
    fresh.d1(f"INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc) VALUES ({q(pairing)},{q(fresh.b64url_sha256(token))},{q(data['tenant_id'])},{q(data['subject_id'])},{q(stamp(now))},{q(stamp(expiry))},NULL,NULL);")
    updated = dict(data, pairing_id=pairing, pairing_token=token, pairing_expires_at=stamp(expiry))
    new_path = path.with_name(path.stem + "-pair-" + secrets.token_hex(3) + ".json")
    write_private(new_path, updated)
    return new_path

def cleanup(path):
    guard()
    data = read_private(path)
    assert data["environment"] == "DEV" and data["tenant_id"].startswith("HARA-ACCEPT-T-")
    tenant, subject = fresh.q(data["tenant_id"]), fresh.q(data["subject_id"])
    tables = {r["name"] for r in fresh.rows("SELECT name FROM sqlite_master WHERE type='table';")}
    order = ["commander_device_calls","commander_device_selections","commander_device_budget_blocks",
             "commander_tenant_budget_baselines","commander_devices","device_pairing_tokens","entitlements","commander_beta_access_requests"]
    statements = []
    for table in order:
        if table in tables:
            cols = {r["name"] for r in fresh.rows("SELECT name FROM pragma_table_info(" + fresh.q(table) + ");")}
            if "tenant_id" in cols:
                statements.append(f"DELETE FROM {table} WHERE tenant_id={tenant};")
    statements += [f"DELETE FROM portal_sessions WHERE subject_id={subject};",
                   f"DELETE FROM identity_bindings WHERE subject_id={subject};",
                   f"DELETE FROM users WHERE subject_id={subject};", f"DELETE FROM tenants WHERE tenant_id={tenant};"]
    fresh.d1("\n".join(statements))
    remaining = fresh.rows(f"SELECT COUNT(*) AS n FROM tenants WHERE tenant_id={tenant};")
    assert remaining == [{"n":0}]
    return {"fixture_cleanup":"PASS","remaining_tenants":0}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create","refresh-pairing","cleanup"])
    parser.add_argument("--purpose")
    parser.add_argument("--file", type=Path)
    a = parser.parse_args()
    if a.action == "create":
        path = create(a.purpose)
        print(json.dumps({"fixture_created":"PASS","private_path":str(path),"secrets_printed":False}))
    elif a.action == "refresh-pairing":
        path = refresh_pairing(a.file)
        print(json.dumps({"pairing_refreshed":"PASS","private_path":str(path),"secrets_printed":False}))
    else:
        print(json.dumps(cleanup(a.file)))

if __name__ == "__main__":
    main()
