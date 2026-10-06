#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, ssl, urllib.error, urllib.request

ISSUER="https://auth.haralabs.com.br"
RFC8414=ISSUER+"/.well-known/oauth-authorization-server"
OIDC=ISSUER+"/.well-known/openid-configuration"

def get_json(url):
    req=urllib.request.Request(url,headers={"accept":"application/json","user-agent":"HARA-Identity-MCP-Metadata-Live/1"})
    try:
        with urllib.request.urlopen(req,timeout=15,context=ssl.create_default_context()) as resp:
            return resp.status,json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code,{}

def need(ok,code):
    if not ok: raise SystemExit(f"HARA_IDENTITY_MCP_METADATA_LIVE_{code}=FAIL")
    print(f"HARA_IDENTITY_MCP_METADATA_LIVE_{code}=PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--expect-cimd",choices=("disabled","enabled"),default="disabled")
    args=ap.parse_args()
    rfc_status,rfc=get_json(RFC8414)
    oidc_status,oidc=get_json(OIDC)
    need(rfc_status==200,"RFC8414_HTTP")
    need(oidc_status==200,"OIDC_HTTP")
    need(rfc.get("issuer")==ISSUER==oidc.get("issuer"),"ISSUER")
    for key in ("authorization_endpoint","token_endpoint","introspection_endpoint","revocation_endpoint","jwks_uri"):
        need(rfc.get(key)==oidc.get(key),key.upper())
    need("code" in list(rfc.get("response_types_supported") or []),"AUTHORIZATION_CODE_RESPONSE")
    need("authorization_code" in list(rfc.get("grant_types_supported") or []),"AUTHORIZATION_CODE_GRANT")
    need("S256" in list(rfc.get("code_challenge_methods_supported") or []),"PKCE_S256")
    if args.expect_cimd=="enabled":
        need(rfc.get("client_id_metadata_document_supported") is True,"CIMD_ENABLED")
    else:
        need(rfc.get("client_id_metadata_document_supported") is False,"CIMD_DISABLED")
        need("registration_endpoint" not in rfc,"DCR_NOT_ADVERTISED")
    print("HARA_IDENTITY_MCP_METADATA_LIVE=PASS")
    return 0

if __name__=="__main__": raise SystemExit(main())
