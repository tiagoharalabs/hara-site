#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import secrets

REQUIRED={"vscode","cursor","claude-code","mcp-inspector"}
URL="https://commander.haralabs.com.br/api/mcp?profile=simple"
PROFILE="1.1.0"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description="Build the offline H.A.R.A. multi-client MCP certification rollup.")
    ap.add_argument("certificates",type=pathlib.Path,nargs="+")
    ap.add_argument("--out",type=pathlib.Path,required=True)
    args=ap.parse_args()

    rows=[]
    seen=set()
    source_commits=set()
    for path in args.certificates:
        cert=load(path)
        if cert.get("schema")!="hara.commander.mcp-client-certification-certificate.v1" or cert.get("state")!="CERTIFIED":
            raise SystemExit("ROLLUP_CERTIFICATE_INVALID:"+str(path))
        client=cert.get("client",{}).get("id")
        if client not in REQUIRED or client in seen:
            raise SystemExit("ROLLUP_CLIENT_SET_INVALID:"+str(client))
        server=cert.get("server") or {}
        if server.get("url")!=URL or server.get("simple_profile_version")!=PROFILE:
            raise SystemExit("ROLLUP_SERVER_CONTRACT_MISMATCH:"+str(client))
        seen.add(client)
        source_commits.add(cert.get("source_commit"))
        rows.append({
            "client":client,
            "version":cert["client"].get("version"),
            "surface":cert["client"].get("surface"),
            "protocol_version":server.get("protocol_version"),
            "certificate_sha256":sha(path),
            "source_commit":cert.get("source_commit"),
        })
    if seen != REQUIRED:
        raise SystemExit("ROLLUP_MISSING_CLIENTS:"+",".join(sorted(REQUIRED-seen)))
    if len(source_commits)!=1:
        raise SystemExit("ROLLUP_SOURCE_COMMIT_MISMATCH")

    out={
        "schema":"hara.commander.mcp-multiclient-certificate.v1",
        "rollup_id":"HARA-MCP-MULTICLIENT-"+secrets.token_hex(8),
        "issued_at_utc":now(),
        "state":"MULTI_CLIENT_CERTIFIED",
        "server":{"url":URL,"simple_profile_version":PROFILE},
        "source_commit":next(iter(source_commits)),
        "clients":sorted(rows,key=lambda row:row["client"]),
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print("MCP_MULTICLIENT_CERTIFICATE="+str(args.out))
    print("MCP_MULTICLIENT_CERTIFICATE_STATE=MULTI_CLIENT_CERTIFIED")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
