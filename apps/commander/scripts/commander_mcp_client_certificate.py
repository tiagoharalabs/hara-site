#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import secrets

ROOT=pathlib.Path(__file__).resolve().parents[3]
MATRIX=ROOT/"apps/commander/mcp/client-certification-matrix.v1.json"
SOURCE_RE=re.compile(r"^[0-9a-f]{40}$")

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")

def main():
    ap=argparse.ArgumentParser(description="Issue an offline MCP client certificate from completed evidence. Does not contact MCP clients or servers.")
    ap.add_argument("--evidence",type=pathlib.Path,required=True)
    ap.add_argument("--source-commit",required=True)
    ap.add_argument("--out",type=pathlib.Path,required=True)
    args=ap.parse_args()

    if not SOURCE_RE.fullmatch(args.source_commit):
        raise SystemExit("CERT_SOURCE_COMMIT_INVALID")
    evidence=load(args.evidence)
    if evidence.get("schema")!="hara.commander.mcp-client-certification-evidence.v1":
        raise SystemExit("CERT_EVIDENCE_SCHEMA_INVALID")
    if evidence.get("state")!="PASS":
        raise SystemExit("CERT_EVIDENCE_NOT_PASS")
    cases=evidence.get("cases") or []
    required=[case for case in cases if case.get("requirement")=="REQUIRED"]
    if not required or any(case.get("state")!="PASS" for case in required):
        raise SystemExit("CERT_REQUIRED_CASE_NOT_PASS")
    privacy=evidence.get("privacy") or {}
    if any(bool(value) for value in privacy.values()):
        raise SystemExit("CERT_PRIVACY_GUARD_FAILED")
    protocol=evidence.get("server",{}).get("protocol_version")
    if not protocol:
        raise SystemExit("CERT_PROTOCOL_VERSION_MISSING")

    certificate={
        "schema":"hara.commander.mcp-client-certification-certificate.v1",
        "certificate_id":"HARA-MCP-CERTIFICATE-"+secrets.token_hex(8),
        "issued_at_utc":now(),
        "client":evidence["client"],
        "server":{
            "url":evidence["server"]["url"],
            "simple_profile_version":evidence["server"]["simple_profile_version"],
            "protocol_version":protocol,
        },
        "evidence_sha256":sha(args.evidence),
        "matrix_sha256":sha(MATRIX),
        "source_commit":args.source_commit,
        "state":"CERTIFIED",
        "notes":[],
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(certificate,indent=2)+"\n",encoding="utf-8")
    print("MCP_CLIENT_CERTIFICATE="+str(args.out))
    print("MCP_CLIENT_CERTIFICATE_STATE=CERTIFIED")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
