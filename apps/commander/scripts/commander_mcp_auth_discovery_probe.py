#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import ssl
import urllib.error
import urllib.request

RESOURCE="https://commander.haralabs.com.br/api/mcp?profile=simple"
RESOURCE_METADATA="https://commander.haralabs.com.br/.well-known/oauth-protected-resource/api/mcp"
ISSUER="https://auth.haralabs.com.br"
AS_METADATA=ISSUER+"/.well-known/oauth-authorization-server"
OIDC_METADATA=ISSUER+"/.well-known/openid-configuration"

def request(url: str, *, method: str="GET", payload: bytes|None=None, headers: dict[str,str]|None=None):
    request_headers={"user-agent":"HARA-Commander-MCP-Conformance/1"}
    request_headers.update(headers or {})
    req=urllib.request.Request(url,data=payload,method=method,headers=request_headers)
    try:
        with urllib.request.urlopen(req,timeout=15,context=ssl.create_default_context()) as resp:
            return resp.status,dict(resp.headers.items()),resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code,dict(exc.headers.items()),exc.read()

def json_body(raw: bytes):
    return json.loads(raw.decode("utf-8"))

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--require-generic-auto",action="store_true")
    args=ap.parse_args()

    body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}).encode()
    status,headers,raw=request(
        RESOURCE,
        method="POST",
        payload=body,
        headers={
            "content-type":"application/json",
            "accept":"application/json, text/event-stream",
        },
    )
    if status != 401:
        raise SystemExit("COMMANDER_MCP_AUTH_UNAUTHENTICATED_401=FAIL")
    print("COMMANDER_MCP_AUTH_UNAUTHENTICATED_401=PASS")

    challenge=headers.get("WWW-Authenticate") or headers.get("Www-Authenticate") or ""
    match=re.search(r'resource_metadata="([^"]+)"',challenge)
    if not match or match.group(1) != RESOURCE_METADATA:
        raise SystemExit("COMMANDER_MCP_AUTH_WWW_AUTHENTICATE_RESOURCE_METADATA=FAIL")
    print("COMMANDER_MCP_AUTH_WWW_AUTHENTICATE_RESOURCE_METADATA=PASS")

    prm_status,_,prm_raw=request(RESOURCE_METADATA)
    if prm_status != 200:
        raise SystemExit("COMMANDER_MCP_AUTH_PROTECTED_RESOURCE_METADATA=FAIL")
    prm=json_body(prm_raw)
    if prm.get("resource") != "https://commander.haralabs.com.br/api/mcp":
        raise SystemExit("COMMANDER_MCP_AUTH_RESOURCE_IDENTIFIER=FAIL")
    if ISSUER not in list(prm.get("authorization_servers") or []):
        raise SystemExit("COMMANDER_MCP_AUTH_AUTHORIZATION_SERVER_BINDING=FAIL")
    print("COMMANDER_MCP_AUTH_PROTECTED_RESOURCE_METADATA=PASS")
    print("COMMANDER_MCP_AUTH_AUTHORIZATION_SERVER_BINDING=PASS")

    as_status,_,as_raw=request(AS_METADATA)
    as_meta=json_body(as_raw) if as_status == 200 else {}
    rfc8414_ready=(
        as_status == 200
        and as_meta.get("issuer") == ISSUER
        and str(as_meta.get("authorization_endpoint") or "").startswith("https://")
        and str(as_meta.get("token_endpoint") or "").startswith("https://")
    )
    print("COMMANDER_MCP_AUTH_RFC8414_METADATA="+("PASS" if rfc8414_ready else "PENDING_IDENTITY"))

    oidc_status,_,oidc_raw=request(OIDC_METADATA)
    if oidc_status != 200:
        raise SystemExit("COMMANDER_MCP_AUTH_OIDC_DISCOVERY_FALLBACK=FAIL")
    oidc=json_body(oidc_raw)
    if oidc.get("issuer") != ISSUER:
        raise SystemExit("COMMANDER_MCP_AUTH_OIDC_ISSUER=FAIL")
    if "S256" not in list(oidc.get("code_challenge_methods_supported") or []):
        raise SystemExit("COMMANDER_MCP_AUTH_PKCE_S256=FAIL")
    if not str(oidc.get("authorization_endpoint") or "").startswith("https://"):
        raise SystemExit("COMMANDER_MCP_AUTH_OIDC_AUTHORIZATION_ENDPOINT=FAIL")
    if not str(oidc.get("token_endpoint") or "").startswith("https://"):
        raise SystemExit("COMMANDER_MCP_AUTH_OIDC_TOKEN_ENDPOINT=FAIL")
    print("COMMANDER_MCP_AUTH_OIDC_DISCOVERY_FALLBACK=PASS")
    print("COMMANDER_MCP_AUTH_PKCE_S256=PASS")

    metadata=as_meta if rfc8414_ready else oidc
    cimd=metadata.get("client_id_metadata_document_supported") is True
    dcr=bool(metadata.get("registration_endpoint"))
    print("COMMANDER_MCP_AUTH_CIMD_ADVERTISED="+("PASS" if cimd else "PENDING_IDENTITY"))
    print("COMMANDER_MCP_AUTH_DCR_ADVERTISED="+("PASS" if dcr else "PENDING_IDENTITY"))

    automatic=rfc8414_ready and (cimd or dcr)
    state="PASS" if automatic else "PENDING_IDENTITY_METADATA"
    print("COMMANDER_MCP_GENERIC_AUTO_OAUTH_ONBOARDING="+state)
    print("COMMANDER_MCP_AUTH_DISCOVERY_PROBE=PASS")

    if args.require_generic_auto and not automatic:
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
