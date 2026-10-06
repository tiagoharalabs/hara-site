#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
compose=(ROOT/"apps/identity-login/compose.fragment.yml").read_text()
dockerfile=(ROOT/"apps/identity-login/oauth-metadata/Dockerfile").read_text()
metadata=(ROOT/"apps/identity-login/oauth-metadata/server.mjs").read_text()
cimd=(ROOT/"apps/identity-login/oauth-metadata/cimd-policy.mjs").read_text()
fetcher=(ROOT/"apps/identity-login/oauth-metadata/cimd-fetch.mjs").read_text()

def need(ok: bool, code: str):
    if not ok:
        raise SystemExit(f"HARA_IDENTITY_MCP_METADATA_{code}=FAIL")
    print(f"HARA_IDENTITY_MCP_METADATA_{code}=PASS")

need("zitadel-oauth-metadata:" in compose,"SERVICE")
need("Path(`/.well-known/oauth-authorization-server`)" in compose,"RFC8414_ROUTE")
need("priority=700" in compose,"ROUTE_PRIORITY")
need("COPY server.mjs /app/server.mjs" in dockerfile,"METADATA_SERVER_PACKAGED")
need("COPY cimd-policy.mjs /app/cimd-policy.mjs" in dockerfile,"CIMD_POLICY_PACKAGED")
need("COPY cimd-fetch.mjs /app/cimd-fetch.mjs" in dockerfile,"CIMD_FETCH_PACKAGED")
need("hara-identity-oauth-metadata:v1.1.0" in compose,"DEDICATED_IMAGE")
need("networks: [identity]" in compose,"IDENTITY_NETWORK")
need('HARA_CIMD_ADVERTISED: "false"' in compose,"CIMD_FAIL_CLOSED_DEFAULT")
need('HARA_DCR_REGISTRATION_ADVERTISED: "false"' in compose,"DCR_FAIL_CLOSED_DEFAULT")
need("client_id_metadata_document_supported: Boolean(cimdSupported)" in metadata,"CIMD_CONDITIONAL_ADVERTISEMENT")
need("if (dcrRegistrationEnabled)" in metadata and 'metadata.registration_endpoint=issuer + "/oauth/v2/register"' in metadata,"DCR_CONDITIONAL_ADVERTISEMENT")
need('code_challenge_methods_supported: ["S256"]' in metadata,"PKCE_S256")
need("CIMD_CLIENT_ID_HOST_FORBIDDEN" in cimd,"CIMD_HOST_GUARD")
need("CIMD_PUBLIC_CLIENT_REQUIRED" in cimd,"CIMD_PUBLIC_CLIENT")
need("CIMD_REDIRECT_URI_HTTPS_OR_LOOPBACK_REQUIRED" in cimd,"CIMD_REDIRECT_GUARD")
need("CIMD_DNS_PRIVATE_ADDRESS_FORBIDDEN" in fetcher,"CIMD_DNS_SSRF_GUARD")
need('lookup(_hostname,_options,callback)' in fetcher,"CIMD_DNS_PINNING")
need('response.statusCode' in fetcher and "CIMD_REDIRECT_FORBIDDEN" in fetcher,"CIMD_REDIRECT_FAIL_CLOSED")
need("max_document_bytes" in fetcher,"CIMD_SIZE_CAP")

proc=subprocess.run(
    ["node","apps/identity-login/scripts/test_mcp_oauth_metadata.mjs"],
    cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT
)
if proc.returncode != 0:
    print(proc.stdout,end="")
    raise SystemExit(proc.returncode)
print(proc.stdout,end="")
print("HARA_IDENTITY_MCP_METADATA_SOURCE=PASS")
