#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import ssl
import urllib.error
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[3]
MCP=ROOT/"apps/commander/mcp"
FREEZE=MCP/"certification-freeze.v1.json"
RFC8414="https://auth.haralabs.com.br/.well-known/oauth-authorization-server"
RESOURCE_META="https://commander.haralabs.com.br/.well-known/oauth-protected-resource/api/mcp"

TRACKED=[
    MCP/"certification-freeze.v1.json",
    MCP/"client-compatibility-profile.v1.json",
    MCP/"client-adapter-expectations.v1.json",
    MCP/"client-certification-matrix.v1.json",
    MCP/"certification-fixture-policy.v1.json",
    MCP/"certification-rollup-policy.v1.json",
    MCP/"schemas/client-certification-evidence.schema.json",
    MCP/"schemas/client-certification-certificate.schema.json",
]

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True).strip()

def fetch_json(url):
    req=urllib.request.Request(url,headers={"accept":"application/json","user-agent":"HARA-MCP-Certification-Snapshot/1"})
    try:
        with urllib.request.urlopen(req,timeout=15,context=ssl.create_default_context()) as resp:
            return resp.status,json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        try:
            payload=json.loads(raw) if raw else {}
        except Exception:
            payload={}
        return exc.code,payload

def storage_snapshot(host):
    cmd=[
        "ssh","-n","-T",host,
        """sudo -n sh -lc '
set -eu
printf "CONTAINERS_BEGIN\\n"
docker ps --format "{{.Names}}|{{.Image}}|{{.Status}}" | grep -E "hara-identity-zitadel-(api|dcr-gateway|oauth-metadata)-1|hara-identity-proxy-1" || true
printf "CONTAINERS_END\\n"
printf "COMPOSE_BEGIN\\n"
grep -E "HARA_DCR_GATEWAY_MODE|HARA_DCR_REGISTRATION_ADVERTISED|HARA_CIMD_ADVERTISED" /srv/hara/identity/compose/compose.yml || true
printf "COMPOSE_END\\n"
'"""
    ]
    proc=subprocess.run(cmd,capture_output=True,text=True,check=False,timeout=20)
    if proc.returncode!=0:
        return {"state":"UNAVAILABLE","returncode":proc.returncode,"stderr_code":"SSH_OR_READBACK_FAILED"}
    lines=proc.stdout.splitlines()
    containers=[]
    compose={}
    mode=None
    for line in lines:
        if line=="CONTAINERS_BEGIN":
            mode="containers"; continue
        if line=="CONTAINERS_END":
            mode=None; continue
        if line=="COMPOSE_BEGIN":
            mode="compose"; continue
        if line=="COMPOSE_END":
            mode=None; continue
        if mode=="containers" and "|" in line:
            name,image,status=line.split("|",2)
            containers.append({"name":name,"image":image,"status":status})
        elif mode=="compose" and ":" in line:
            key,value=line.strip().split(":",1)
            compose[key.strip()]=value.strip().strip('"')
    return {"state":"READBACK","containers":containers,"compose":compose}

def main():
    ap=argparse.ArgumentParser(description="Capture a secret-free MCP certification environment snapshot. Does not launch clients.")
    ap.add_argument("--out",type=pathlib.Path,required=True)
    ap.add_argument("--live-readonly",action="store_true")
    ap.add_argument("--storage-host",default="sartorius@storage")
    ap.add_argument("--prod-worker-version")
    args=ap.parse_args()

    freeze=json.loads(FREEZE.read_text(encoding="utf-8"))
    value={
        "schema":"hara.commander.mcp-certification-environment-snapshot.v1",
        "captured_at_utc":now(),
        "client_execution":False,
        "local_client_execution":False,
        "git":{
            "head":git("rev-parse","HEAD"),
            "branch":git("branch","--show-current"),
            "status_clean":not bool(git("status","--porcelain")),
            "server_contract_commit":freeze.get("server_contract_commit"),
            "certification_bundle_commit":freeze.get("certification_bundle_commit"),
        },
        "artifacts":{
            str(path.relative_to(ROOT)):sha(path)
            for path in TRACKED
        },
        "prod_worker_version":args.prod_worker_version,
        "live":None,
        "privacy":{
            "access_token_recorded":False,
            "refresh_token_recorded":False,
            "registration_access_token_recorded":False,
            "client_secret_recorded":False,
            "pat_recorded":False,
            "cookie_recorded":False,
        },
    }

    if args.live_readonly:
        rfc_status,rfc=fetch_json(RFC8414)
        resource_status,resource=fetch_json(RESOURCE_META)
        value["live"]={
            "rfc8414":{
                "http_status":rfc_status,
                "issuer":rfc.get("issuer"),
                "authorization_endpoint":rfc.get("authorization_endpoint"),
                "token_endpoint":rfc.get("token_endpoint"),
                "registration_endpoint":rfc.get("registration_endpoint"),
                "client_id_metadata_document_supported":rfc.get("client_id_metadata_document_supported"),
                "code_challenge_methods_supported":rfc.get("code_challenge_methods_supported"),
            },
            "protected_resource":{
                "http_status":resource_status,
                "resource":resource.get("resource"),
                "authorization_servers":resource.get("authorization_servers"),
            },
            "identity_runtime":storage_snapshot(args.storage_host),
        }

    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
    print("MCP_CERT_SNAPSHOT="+str(args.out))
    print("MCP_CERT_SNAPSHOT_CLIENT_LAUNCH=FALSE")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
