#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import runpy
import sqlite3
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
LEASE_MODULE = (APP / "src" / "product-lease.mjs").read_text(encoding="utf-8")
AGENT_PATH = APP / "public" / "agent" / "linux.py"
AGENT_SOURCE = AGENT_PATH.read_text(encoding="utf-8")

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SIGNED_LEASE_{code}=FAIL")
    print(f"COMMANDER_SIGNED_LEASE_{code}=PASS")

def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def b64ud(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))

def encoded(obj) -> str:
    return b64u(json.dumps(obj, separators=(",", ":"), sort_keys=False).encode())

need('PRODUCT_LEASE_KID = "commander-lease-v1"' in AGENT_SOURCE, "AGENT_KID_PIN")
need('PRODUCT_LEASE_RSA_N = "' in AGENT_SOURCE and 'PRODUCT_LEASE_RSA_E = "AQAB"' in AGENT_SOURCE, "AGENT_PUBLIC_KEY_PIN")
need("verify_product_lease_token" in AGENT_SOURCE and "_verify_rs256" in AGENT_SOURCE, "AGENT_RS256_VERIFY")
need("PRODUCT_LEASE_SIGNATURE_INVALID" in AGENT_SOURCE, "AGENT_SIGNATURE_FAIL_CLOSED")
need("PRODUCT_LEASE_PAYLOAD_MISMATCH" in AGENT_SOURCE, "AGENT_PAYLOAD_BINDING")
need("_active_verified_product_lease(conn,config)" in AGENT_SOURCE, "BUDGET_REVALIDATES_LEASE")
need("lease_token TEXT" in AGENT_SOURCE, "SIGNED_TOKEN_PERSISTED")
need('import { signProductLease } from "./product-lease.mjs";' in WORKER, "WORKER_SIGNER_IMPORT")
need("product_lease_token: productLeaseToken" in WORKER, "WORKER_SIGNED_TOKEN_RESPONSE")
need('alg: "RS256"' in WORKER and 'kid: "commander-lease-v1"' in WORKER, "WORKER_SIGNATURE_METADATA")
need("PRODUCT_LEASE_PRIVATE_JWK" in LEASE_MODULE, "PRIVATE_KEY_RUNTIME_ONLY")
need('"d":' not in LEASE_MODULE and '"p":' not in LEASE_MODULE and '"q":' not in LEASE_MODULE, "PRIVATE_KEY_NOT_COMMITTED")
need("RSASSA-PKCS1-v1_5" in LEASE_MODULE and 'hash: "SHA-256"' in LEASE_MODULE, "WORKER_RS256")

module_n = re.search(r'n: "([^"]+)"', LEASE_MODULE)
agent_n = re.search(r'PRODUCT_LEASE_RSA_N = "([^"]+)"', AGENT_SOURCE)
need(bool(module_n and agent_n and module_n.group(1) == agent_n.group(1)), "PUBLIC_KEY_MATCH")

private_path = os.environ.get("HARA_LEASE_PRIVATE_JWK_FILE")
if private_path:
    private = json.loads(Path(private_path).read_text(encoding="utf-8"))
    need(private.get("kid") == "commander-lease-v1" and private.get("alg") == "RS256", "DYNAMIC_PRIVATE_METADATA")
    need(private.get("n") == module_n.group(1) and private.get("e") == "AQAB", "DYNAMIC_KEYPAIR_MATCH")

    agent = runpy.run_path(str(AGENT_PATH))
    now = int(time.time())
    device_id = "HARA-LEASE-VALIDATOR"
    lease = {
        "schema": "hara.commander-device-product-lease.v1",
        "lease_id": "HARA-PRODUCT-LEASE-validator",
        "authority": "HARA_COMMANDER_CLOUD",
        "device_id": device_id,
        "tenant_id": "T-VALIDATOR",
        "entitlement_id": "E-VALIDATOR",
        "plan_code": "TRIAL",
        "plan_name": "Free",
        "grants": ["COMMANDER_READ_ONLY_INVOKE"],
        "meter_id": "HARA_COMMANDER_GOVERNED_INVOKE",
        "period_kind": "CALENDAR_MONTH",
        "unit_limit": 10000,
        "usage_mode": "LOCAL_BUDGET",
        "issued_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "valid_until_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600)),
    }
    header = {"alg": "RS256", "kid": "commander-lease-v1", "typ": "JWT"}
    claims = {
        "iss": "https://commander.haralabs.com.br",
        "aud": "hara-commander-agent",
        "sub": device_id,
        "jti": lease["lease_id"],
        "iat": now,
        "exp": now + 3600,
        "lease": lease,
    }
    signing_input = encoded(header) + "." + encoded(claims)
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input.encode()).digest()
    n = int.from_bytes(b64ud(private["n"]), "big")
    d = int.from_bytes(b64ud(private["d"]), "big")
    size = (n.bit_length() + 7) // 8
    em = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(size, "big")
    token = signing_input + "." + b64u(sig)

    cfg = {"HARA_COMMANDER_URL": "https://commander.haralabs.com.br", "HARA_DEVICE_ID": device_id}
    verified = agent["verify_product_lease_token"](cfg, token)
    need(verified["lease_id"] == lease["lease_id"], "DYNAMIC_VALID_TOKEN")

    bad_parts = token.split(".")
    bad_claims = dict(claims)
    bad_claims["lease"] = dict(lease)
    bad_claims["lease"]["plan_code"] = "STANDARD"
    tampered = bad_parts[0] + "." + encoded(bad_claims) + "." + bad_parts[2]
    try:
        agent["verify_product_lease_token"](cfg, tampered)
    except Exception:
        pass
    else:
        raise SystemExit("COMMANDER_SIGNED_LEASE_DYNAMIC_TAMPER_DENIED=FAIL")
    print("COMMANDER_SIGNED_LEASE_DYNAMIC_TAMPER_DENIED=PASS")

    expired_claims = dict(claims)
    expired_claims["iat"] = now - 7200
    expired_claims["exp"] = now - 3600
    expired_input = encoded(header) + "." + encoded(expired_claims)
    expired_di = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(expired_input.encode()).digest()
    expired_em = b"\x00\x01" + b"\xff" * (size - len(expired_di) - 3) + b"\x00" + expired_di
    expired_sig = pow(int.from_bytes(expired_em, "big"), d, n).to_bytes(size, "big")
    expired_token = expired_input + "." + b64u(expired_sig)
    try:
        agent["verify_product_lease_token"](cfg, expired_token)
    except Exception:
        pass
    else:
        raise SystemExit("COMMANDER_SIGNED_LEASE_DYNAMIC_EXPIRED_DENIED=FAIL")
    print("COMMANDER_SIGNED_LEASE_DYNAMIC_EXPIRED_DENIED=PASS")

    with tempfile.TemporaryDirectory(prefix="hara-signed-lease-") as td:
        root = Path(td)
        globals_map = agent["_store_product_lease_response"].__globals__
        globals_map["DATA_DIR"] = root
        globals_map["OPERATIONS_DB_FILE"] = root / "operations.sqlite3"
        globals_map["CONSOLE_EVENTS_FILE"] = root / "console-events.jsonl"
        payload = {
            "schema": "hara.commander-device-product-lease-response.v1",
            "ok": True,
            "product_lease": lease,
            "product_lease_token": token,
            "product_lease_signature": {"alg": "RS256", "kid": "commander-lease-v1"},
            "budget": None,
        }
        agent["_store_product_lease_response"](cfg, payload)
        with sqlite3.connect(globals_map["OPERATIONS_DB_FILE"]) as db:
            stored = db.execute("SELECT lease_json FROM product_lease WHERE singleton=1").fetchone()[0]
            altered = json.loads(stored)
            altered["plan_code"] = "STANDARD"
            db.execute("UPDATE product_lease SET lease_json=? WHERE singleton=1", (json.dumps(altered),))
            db.commit()
        with agent["_ops_connect"]() as conn:
            need(agent["_active_verified_product_lease"](conn, cfg) is None, "DYNAMIC_SQLITE_TAMPER_DENIED")

print("COMMANDER_SIGNED_PRODUCT_LEASE=PASS")
