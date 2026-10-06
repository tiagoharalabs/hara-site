#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys

ROOT=Path(__file__).resolve().parents[3]
script=(ROOT/"apps/identity-login/scripts/promote_mcp_dcr_guarded.py").read_text()

def need(ok,code):
    if not ok:
        raise SystemExit(f"HARA_MCP_DCR_PROMOTION_{code}=FAIL")
    print(f"HARA_MCP_DCR_PROMOTION_{code}=PASS")

for token,code in [
    ("DCR_PROMOTION_REQUIRES_CLOSED_COMPOSE","CLOSED_PRECONDITION"),
    ("DCR_PROMOTION_REQUIRES_BACKEND_DISABLED","BACKEND_DISABLED_PRECONDITION"),
    ("DCR_PROMOTION_REQUIRES_METADATA_HIDDEN","METADATA_HIDDEN_PRECONDITION"),
    ("DCR_BACKEND_ENABLE_FAILED","BACKEND_ENABLE_CHECK"),
    ("docker_recreate(compose_path)","SCOPED_RECREATE"),
    ("verify_public_guarded()","PUBLIC_GUARDED_READBACK"),
    ("verify_public_closed()","ROLLBACK_PUBLIC_CLOSED_READBACK"),
    ("security_restore","SECURITY_PREIMAGE_RESTORE"),
    (".pre-mcp-dcr-guarded-","COMPOSE_PREIMAGE"),
    ("DCR_PROMOTION_SECRET_MATERIAL_STDOUT=false","SECRET_OUTPUT_GUARD"),
]:
    need(token in script,code)

proc=subprocess.run(
    [sys.executable,"apps/identity-login/scripts/promote_mcp_dcr_guarded.py","--self-test"],
    cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
)
if proc.returncode!=0:
    print(proc.stdout,end="")
    raise SystemExit(proc.returncode)
print(proc.stdout,end="")
print("HARA_MCP_DCR_PROMOTION_SOURCE=PASS")
