#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import ssl
import urllib.error
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[3]
MCP=ROOT/"apps/commander/mcp"
FREEZE=MCP/"certification-freeze.v1.json"
URL="https://commander.haralabs.com.br/api/mcp?profile=simple"
RESOURCE_META="https://commander.haralabs.com.br/.well-known/oauth-protected-resource/api/mcp"
RFC8414="https://auth.haralabs.com.br/.well-known/oauth-authorization-server"

ARTIFACT_PATHS={
    "client-compatibility-profile.v1.json":MCP/"client-compatibility-profile.v1.json",
    "client-adapter-expectations.v1.json":MCP/"client-adapter-expectations.v1.json",
    "client-certification-matrix.v1.json":MCP/"client-certification-matrix.v1.json",
    "certification-fixture-policy.v1.json":MCP/"certification-fixture-policy.v1.json",
    "certification-rollup-policy.v1.json":MCP/"certification-rollup-policy.v1.json",
    "client-certification-evidence.schema.json":MCP/"schemas/client-certification-evidence.schema.json",
    "client-certification-certificate.schema.json":MCP/"schemas/client-certification-certificate.schema.json",
}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def need(ok,code):
    if not ok:
        raise SystemExit("MCP_CERT_PREFLIGHT_"+code+"=FAIL")
    print("MCP_CERT_PREFLIGHT_"+code+"=PASS")

def fetch_json(url, *, method="GET", payload=None):
    headers={"accept":"application/json","user-agent":"HARA-MCP-Certification-Preflight/1"}
    body=None
    if payload is not None:
        headers["content-type"]="application/json"
        body=json.dumps(payload,separators=(",",":")).encode()
    req=urllib.request.Request(url,data=body,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=15,context=ssl.create_default_context()) as resp:
            return resp.status,dict(resp.headers.items()),json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        try:
            parsed=json.loads(raw) if raw else {}
        except Exception:
            parsed={}
        return exc.code,dict(exc.headers.items()),parsed

def main():
    ap=argparse.ArgumentParser(description="Certification readiness preflight. Does not launch an MCP client.")
    ap.add_argument("--live-readonly",action="store_true")
    args=ap.parse_args()

    freeze=load(FREEZE)
    need(freeze.get("schema")=="hara.commander.mcp-certification-freeze.v1","FREEZE_SCHEMA")
    need(freeze.get("client_execution") is False and freeze.get("local_client_execution") is False,"NO_EXECUTION_CLAIM")

    hashes=freeze.get("artifacts") or {}
    for name,path in ARTIFACT_PATHS.items():
        need(path.exists(),"ARTIFACT_EXISTS_"+re.sub(r"[^A-Z0-9]+","_",name.upper()).strip("_"))
        need(hashes.get(name)==sha(path),"ARTIFACT_HASH_"+re.sub(r"[^A-Z0-9]+","_",name.upper()).strip("_"))

    matrix=load(MCP/"client-certification-matrix.v1.json")
    ids=[case["id"] for case in matrix.get("cases",[])]
    need(len(ids)==22 and len(set(ids))==22,"MATRIX_22_UNIQUE_CASES")
    need(set(matrix.get("required_clients",[]))=={"vscode","cursor","claude-code","mcp-inspector"},"MATRIX_FOUR_CLIENTS")
    need(matrix.get("certification_policy",{}).get("static_bearer_primary_certification_forbidden") is True,"NO_STATIC_BEARER_PRIMARY")

    fixture=load(MCP/"certification-fixture-policy.v1.json")
    need(fixture.get("scratch",{}).get("root_template")=="/tmp/hara-mcp-cert/{run_id}","SCRATCH_ROOT")
    need(fixture.get("mutation_rules",{}).get("only_under_scratch_root") is True,"SCRATCH_ONLY")
    need(fixture.get("mutation_rules",{}).get("no_privilege_escalation") is True,"NO_PRIVILEGE_ESCALATION")
    need(fixture.get("mutation_rules",{}).get("no_reboot_or_power_action") is True,"NO_POWER_ACTION")

    templates=[
        MCP/"client-config-templates/vscode.portable.mcp.json",
        MCP/"client-config-templates/vscode.native.mcp.json",
        MCP/"client-config-templates/cursor.mcp.json",
    ]
    for path in templates:
        raw=path.read_text(encoding="utf-8")
        need(URL in raw,"TEMPLATE_CANONICAL_URL_"+path.name.upper().replace(".","_"))
        need(not re.search(r'(?i)(access[_-]?token|refresh[_-]?token|client[_-]?secret|bearer\s+[A-Za-z0-9])',raw),"TEMPLATE_NO_SECRET_"+path.name.upper().replace(".","_"))

    required_scripts=[
        ROOT/"apps/commander/scripts/commander_mcp_client_certification.py",
        ROOT/"apps/commander/scripts/commander_mcp_client_certificate.py",
        ROOT/"apps/commander/scripts/commander_mcp_certification_rollup.py",
        ROOT/"apps/identity-login/scripts/commander_mcp_dcr_lifecycle_canary.py",
        ROOT/"apps/identity-login/scripts/close_mcp_dcr_guarded.py",
    ]
    for path in required_scripts:
        need(path.exists(),"SCRIPT_"+path.name.upper().replace(".","_"))

    if args.live_readonly:
        status,headers,_=fetch_json(URL,method="POST",payload={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}})
        need(status==401,"LIVE_MCP_401")
        challenge=headers.get("WWW-Authenticate") or headers.get("Www-Authenticate") or ""
        need("resource_metadata=" in challenge,"LIVE_RESOURCE_METADATA_CHALLENGE")
        status,_,resource=fetch_json(RESOURCE_META)
        need(status==200 and "https://auth.haralabs.com.br" in list(resource.get("authorization_servers") or []),"LIVE_RESOURCE_METADATA")
        status,_,rfc=fetch_json(RFC8414)
        need(status==200,"LIVE_RFC8414")
        need(rfc.get("registration_endpoint")=="https://auth.haralabs.com.br/oauth/v2/register","LIVE_DCR_ADVERTISED")
        need(rfc.get("client_id_metadata_document_supported") is False,"LIVE_CIMD_DISABLED")
        need("S256" in list(rfc.get("code_challenge_methods_supported") or []),"LIVE_PKCE_S256")

    print("MCP_CERT_PREFLIGHT_CLIENT_LAUNCH=FALSE")
    print("MCP_CERT_PREFLIGHT=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
