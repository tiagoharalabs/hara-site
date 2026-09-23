#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
CFG = json.loads((APP / "wrangler.jsonc").read_text())
WORKER = (APP / "src/worker.js").read_text()
HTML = (APP / "public/index.html").read_text()
JS = (APP / "public/app.js").read_text()
CSS = (APP / "public/styles.css").read_text()
LINUX = (APP / "public/install/linux.sh").read_text()
WINDOWS = (APP / "public/install/windows.ps1").read_text()
HEADERS = (APP / "public/_headers").read_text()
READBACK = (APP / "scripts/commander_prod_readback.py").read_text()

def need(ok, code):
    if not ok:
        raise AssertionError(code)

need(CFG["name"] == "hara-commander", "WORKER_NAME")
need(CFG["vars"]["ENVIRONMENT"] == "PROD", "ENVIRONMENT")
need(CFG["vars"]["STORAGE_MODE"] == "REMOTE_PROD", "STORAGE_MODE")
need(CFG["vars"]["AUTH_CLIENT_AUTH"] == "BASIC", "AUTH_CLIENT_AUTH")
need(CFG["d1_databases"][0]["database_name"] == "hara-commander-product-prod", "PROD_D1_NAME")
need(CFG["d1_databases"][0]["database_id"] == "2c6473ff-9f65-4ee3-b9aa-a68996d47c46", "PROD_D1_ID")
need(CFG["routes"][0] == {"pattern": "commander.haralabs.com.br", "custom_domain": True}, "PROD_ROUTE")
need('"DEV", "PROD"' in WORKER, "RUNTIME_ENV_GATE")
need('url.pathname.startsWith("/api/dev/")' in WORKER, "DEV_PREFIX_GATE")
need('requireDev(env)' in WORKER, "DEV_REQUIRE_GATE")
need('url.pathname === "/api/health"' in WORKER, "PROD_HEALTH")
need('DEV_ENDPOINT_DISABLED: 404' in WORKER, "DEV_DISABLED_STATUS")
need("auth-bootstrap-pending" in HTML, "AUTH_FIRST_PAINT")
need("styles.css?v=20260922-dualline1" in HTML, "STYLE_CACHE_KEY")

prod = "https://commander.haralabs.com.br"
dev = "hara-commander-dev-v2.tiago-sartori.workers.dev"
for label, content in (("HTML", HTML), ("JS", JS), ("LINUX", LINUX), ("WINDOWS", WINDOWS)):
    need(prod in content, f"{label}_PROD_DOMAIN")
    need(dev not in content, f"{label}_DEV_URL_LEAK")

need("border-top:2px solid rgba(233,177,40,.92)" in CSS, "LIGHT_TOP_GOLD")
need("border-bottom:2px solid rgba(233,177,40,.82)" in CSS, "LIGHT_BOTTOM_GOLD")
need('html[data-theme="dark"] .topbar' in CSS, "DARK_TOPBAR")
need("border-top:2px solid rgba(72,109,134,.56)" in CSS, "DARK_TOP_BLUE")
need("border-bottom:2px solid rgba(27,64,84,.96)" in CSS, "DARK_BOTTOM_BLUE")
need(not (ROOT / "public/dev/commander").exists(), "DEV_SNAPSHOT_ARCHIVE")
need(not (APP / "seed/dev.sql").exists(), "DEV_SEED_RESIDUE")
need("Strict-Transport-Security: max-age=31536000; includeSubDomains" in HEADERS, "STATIC_HSTS")
need("Content-Security-Policy:" in HEADERS and "frame-ancestors 'none'" in HEADERS, "STATIC_CSP")
need("X-Content-Type-Options: nosniff" in HEADERS, "STATIC_NOSNIFF")
need("SECURITY_HEADERS" in WORKER and '"strict-transport-security"' in WORKER, "WORKER_SECURITY_HEADERS")
need("7403" in READBACK and "TRANSIENT_MARKERS" in READBACK, "D1_TRANSIENT_RETRY")
need("function sanitizeErrorCode" in WORKER and "INVALID_JSON: 400" in WORKER, "ERROR_SANITIZATION")

print("COMMANDER_PROD_CONFIG=PASS")
print("COMMANDER_PROD_D1_ISOLATION=PASS")
print("COMMANDER_PROD_DEV_ENDPOINT_GATE=PASS")
print("COMMANDER_PROD_DOMAIN_REFERENCES=PASS")
print("COMMANDER_PROD_AUTH_FIRST_PAINT=PASS")
print("COMMANDER_PROD_LIGHT_HEADER_SIGNATURE=PASS")
print("COMMANDER_PROD_DARK_HEADER_SIGNATURE=PASS")
print("COMMANDER_PROD_DEV_SNAPSHOT_ARCHIVE=ABSENT")
print("COMMANDER_PROD_DEV_SEED=ABSENT")
print("COMMANDER_PROD_STATIC_SECURITY_HEADERS=PASS")
print("COMMANDER_PROD_WORKER_SECURITY_HEADERS=PASS")
print("COMMANDER_PROD_D1_TRANSIENT_RETRY=READY")
print("COMMANDER_PROD_ERROR_SANITIZATION=PASS")
