#!/usr/bin/env python3
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[3]
TARGET=ROOT/"apps/commander/scripts/commander_fresh_customer_dev_acceptance.py"
SOURCE=TARGET.read_text(encoding="utf-8")
ast.parse(SOURCE)

def need(ok,code):
    if not ok:
        raise SystemExit("COMMANDER_FRESH_CUSTOMER_"+code+"=FAIL")
    print("COMMANDER_FRESH_CUSTOMER_"+code+"=PASS")

need('DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"' in SOURCE,"DEV_ONLY_ORIGIN")
need('DEV_DB = "hara-commander-product-dev"' in SOURCE,"DEV_ONLY_DATABASE")
need('"PERSISTENT_TRUSTED"' in SOURCE,"PERSISTENT_TRUST")
need('TemporaryDirectory(prefix="hara-fresh-customer-")' in SOURCE,"TEMP_XDG_ISOLATION")
need('"python3",str(AGENT),"mcp"' in SOURCE,"LOCAL_MCP_STDIO")
need('len(names)!=24' in SOURCE and 'name.startswith("hara.")' in SOURCE,"SIMPLE_24_NO_HARA_PREFIX")
need('"relay_calls_per_local_tool_call"' in SOURCE and '"cloud_quota_consumed_by_local_tool_call"' in SOURCE,"ZERO_RELAY_ASSERTION")
need('"write_file"' in SOURCE and '"read_file"' in SOURCE and '"edit_block"' in SOURCE and '"start_process"' in SOURCE,"CORE_TOOL_ACCEPTANCE")
need('"payload_json"' in SOURCE and '"command"' in SOURCE,"RECEIPT_PRIVACY_ASSERTION")
need('d1(cleanup)' in SOURCE and 'FRESH_CUSTOMER_DEV_FIXTURE_CLEANUP' in SOURCE,"FIXTURE_CLEANUP")

tree=ast.parse(SOURCE)
for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="print":
        rendered=" ".join(ast.dump(arg) for arg in node.args)
        need("pairing_token" not in rendered and "device_token" not in rendered,"TOKEN_PRINT_ABSENT")

for forbidden in ("commander.haralabs.com.br","wrangler.jsonc --env production","hara-commander-agent.service"):
    need(forbidden not in SOURCE,"PROD_MUTATION_SURFACE_ABSENT_"+forbidden.replace(".","_").replace("-","_").replace(" ","_").upper()[:24])

print("COMMANDER_FRESH_CUSTOMER_ACCEPTANCE_SOURCE=PASS")
