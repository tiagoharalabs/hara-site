#!/usr/bin/env python3
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
compose=(ROOT/"apps/identity-login/compose.fragment.yml").read_text()
dockerfile=(ROOT/"apps/identity-login/dcr-gateway/Dockerfile").read_text()
server=(ROOT/"apps/identity-login/dcr-gateway/server.mjs").read_text()
policy=(ROOT/"apps/identity-login/dcr-gateway/dcr-policy.mjs").read_text()

def need(ok: bool, code: str):
    if not ok:
        raise SystemExit(f"HARA_IDENTITY_DCR_GATEWAY_{code}=FAIL")
    print(f"HARA_IDENTITY_DCR_GATEWAY_{code}=PASS")

need("zitadel-dcr-gateway:" in compose,"SERVICE")
need("hara-identity-dcr-gateway:v0.1.0" in compose,"IMAGE")
need("HARA_DCR_GATEWAY_MODE: closed" in compose,"CLOSED_DEFAULT")
need("PathPrefix(`/oauth/v2/register`)" in compose,"ROUTE")
need("priority=800" in compose,"ROUTE_PRIORITY")
need("COPY server.mjs /app/server.mjs" in dockerfile,"SERVER_PACKAGED")
need("COPY dcr-policy.mjs /app/dcr-policy.mjs" in dockerfile,"POLICY_PACKAGED")
need('VALID_MODES=new Set(["closed","guarded"])' in server,"MODE_ALLOWLIST")
need('mode !== "guarded"' in server,"FAIL_CLOSED")
need("registrationLimit=20" in server,"RATE_LIMIT")
need("DCR_PUBLIC_CLIENT_REQUIRED" in policy,"PUBLIC_CLIENT_ONLY")
need("DCR_REDIRECT_URI_SCHEME_FORBIDDEN" in policy,"REDIRECT_SCHEME_GUARD")
need("DCR_NATIVE_REDIRECT_REQUIRES_NATIVE_APP" in policy,"NATIVE_APP_GUARD")
need("client_secret" not in policy,"NO_CLIENT_SECRET_ISSUANCE")

proc=subprocess.run(
    ["node","apps/identity-login/scripts/test_mcp_dcr_gateway.mjs"],
    cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT
)
if proc.returncode != 0:
    print(proc.stdout,end="")
    raise SystemExit(proc.returncode)
print(proc.stdout,end="")
print("HARA_IDENTITY_DCR_GATEWAY_SOURCE=PASS")
