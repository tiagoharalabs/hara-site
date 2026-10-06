#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
SCRIPT=(APP/"scripts/commander_versioned_prod_promote.py").read_text(encoding="utf-8")
WRANGLER=(APP/"wrangler.jsonc").read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit("COMMANDER_VERSIONED_PROMOTE_"+code+"=FAIL")
    print("COMMANDER_VERSIONED_PROMOTE_"+code+"=PASS")

need('"17 * * * *"' in WRANGLER,"CRON_DECLARED")
need('"workers_dev": false' in WRANGLER,"PROD_ONLY")
need('"preview_urls": false' in WRANGLER,"NO_PREVIEW")
need('"versions", "deploy"' in SCRIPT,"VERSION_DEPLOY")
need('"triggers", "deploy"' in SCRIPT,"TRIGGER_DEPLOY")
need("commander_prod_deployment_readback.py" in SCRIPT,"POST_DEPLOY_READBACK")
need("PRODUCT_LEASE_PRIVATE_JWK" in SCRIPT,"SIGNED_LEASE_SECRET")
need("MCP_PRODUCT_TOKEN" in SCRIPT,"MCP_SECRET")
need("ROLLBACK_VERSION_NOT_CURRENT_100_PERCENT" in SCRIPT,"ROLLBACK_GUARD")
need("TARGET_VERSION_SECRET_MISSING" in SCRIPT,"SECRET_GUARD")
need("--execute" in SCRIPT,"EXPLICIT_EXECUTE_GATE")
need(SCRIPT.index('"versions", "deploy"') < SCRIPT.index('"triggers", "deploy"') < SCRIPT.index("COMMANDER_VERSIONED_PROMOTE_READBACK"),"ORDER")
print("COMMANDER_VERSIONED_PROD_PROMOTE_CONTRACT=PASS")
