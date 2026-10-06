#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import secrets

ROOT=pathlib.Path(__file__).resolve().parents[3]
MATRIX_PATH=ROOT/"apps/commander/mcp/client-certification-matrix.v1.json"
CANONICAL_URL="https://commander.haralabs.com.br/api/mcp?profile=simple"
FORBIDDEN_KEYS={
    "access_token","refresh_token","registration_access_token","client_secret",
    "authorization","cookie","set_cookie","raw_command","raw_result","payload",
}
SHA256_RE=re.compile(r"^[0-9a-f]{64}$")

def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path: pathlib.Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=False)+"\n",encoding="utf-8")

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")

def scrub(value, where="root"):
    if isinstance(value,dict):
        for key,item in value.items():
            normalized=str(key).lower().replace("-","_")
            if normalized in FORBIDDEN_KEYS or "token" in normalized or "secret" in normalized:
                raise SystemExit(f"CERT_EVIDENCE_FORBIDDEN_SECRET_FIELD:{where}.{key}")
            scrub(item,where+"."+str(key))
    elif isinstance(value,list):
        for idx,item in enumerate(value):
            scrub(item,f"{where}[{idx}]")

def new_plan(client: str, version: str, surface: str, platform: str|None):
    matrix=load(MATRIX_PATH)
    run_id="HARA-MCP-CERT-"+secrets.token_hex(8)
    cases=[]
    for item in matrix["cases"]:
        cases.append({
            "case_id":item["id"],
            "requirement":item["level"],
            "state":"PENDING",
            "http_status":None,
            "mcp_error_code":None,
            "tool_name":None,
            "transport_request_id":None,
            "bridge_receipt_sha256":None,
            "latency_ms":None,
            "note":None,
        })
    value={
        "schema":"hara.commander.mcp-client-certification-evidence.v1",
        "run_id":run_id,
        "client":{"id":client,"version":version,"surface":surface,"platform":platform or ""},
        "server":{"url":CANONICAL_URL,"simple_profile_version":"1.1.0","protocol_version":None},
        "started_at_utc":now(),
        "finished_at_utc":None,
        "state":"PLANNED",
        "cases":cases,
        "summary":{},
        "privacy":{
            "access_token_recorded":False,
            "refresh_token_recorded":False,
            "registration_access_token_recorded":False,
            "client_secret_recorded":False,
            "raw_command_content_recorded":False,
            "raw_result_content_recorded":False,
        },
    }
    return value

def recalc(value):
    req=[x for x in value["cases"] if x["requirement"]=="REQUIRED"]
    opt=[x for x in value["cases"] if x["requirement"]=="OPTIONAL"]
    summary={
        "required_pass":sum(x["state"]=="PASS" for x in req),
        "required_fail":sum(x["state"]=="FAIL" for x in req),
        "required_pending":sum(x["state"] in {"PENDING","BLOCKED"} for x in req),
        "optional_pass":sum(x["state"]=="PASS" for x in opt),
        "optional_not_applicable":sum(x["state"]=="NOT_APPLICABLE" for x in opt),
    }
    value["summary"]=summary
    if summary["required_fail"]:
        value["state"]="FAIL"
    elif summary["required_pending"]:
        value["state"]="RUNNING"
    else:
        value["state"]="PASS"
        value["finished_at_utc"]=value.get("finished_at_utc") or now()
    return value

def main():
    ap=argparse.ArgumentParser(description="Prepare and reconcile MCP client certification evidence. This tool does not launch clients.")
    sub=ap.add_subparsers(dest="cmd",required=True)

    p=sub.add_parser("plan")
    p.add_argument("--client",required=True,choices=["vscode","cursor","claude-code","mcp-inspector"])
    p.add_argument("--version",required=True)
    p.add_argument("--surface",required=True)
    p.add_argument("--platform")
    p.add_argument("--out",type=pathlib.Path,required=True)

    r=sub.add_parser("record")
    r.add_argument("--evidence",type=pathlib.Path,required=True)
    r.add_argument("--case",required=True)
    r.add_argument("--state",required=True,choices=["PASS","FAIL","NOT_APPLICABLE","BLOCKED"])
    r.add_argument("--http-status",type=int)
    r.add_argument("--mcp-error-code")
    r.add_argument("--tool-name")
    r.add_argument("--transport-request-id")
    r.add_argument("--bridge-receipt-sha256")
    r.add_argument("--latency-ms",type=float)
    r.add_argument("--note")
    r.add_argument("--protocol-version")

    s=sub.add_parser("summary")
    s.add_argument("--evidence",type=pathlib.Path,required=True)

    args=ap.parse_args()
    if args.cmd=="plan":
        value=new_plan(args.client,args.version,args.surface,args.platform)
        scrub(value)
        save(args.out,value)
        print("MCP_CLIENT_CERTIFICATION_PLAN="+str(args.out))
        print("MCP_CLIENT_CERTIFICATION_RUN_ID="+value["run_id"])
        return 0

    value=load(args.evidence)
    scrub(value)
    if args.cmd=="record":
        match=next((x for x in value["cases"] if x["case_id"]==args.case),None)
        if match is None:
            raise SystemExit("CERT_CASE_UNKNOWN:"+args.case)
        if args.bridge_receipt_sha256 and not SHA256_RE.fullmatch(args.bridge_receipt_sha256):
            raise SystemExit("CERT_RECEIPT_SHA256_INVALID")
        match.update({
            "state":args.state,
            "http_status":args.http_status,
            "mcp_error_code":args.mcp_error_code,
            "tool_name":args.tool_name,
            "transport_request_id":args.transport_request_id,
            "bridge_receipt_sha256":args.bridge_receipt_sha256,
            "latency_ms":args.latency_ms,
            "note":args.note,
        })
        if args.protocol_version:
            value["server"]["protocol_version"]=args.protocol_version
        recalc(value)
        scrub(value)
        save(args.evidence,value)
        print("MCP_CLIENT_CERTIFICATION_RECORDED="+args.case+":"+args.state)
        return 0

    recalc(value)
    scrub(value)
    print(json.dumps({"run_id":value["run_id"],"client":value["client"],"state":value["state"],"summary":value["summary"]},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
