#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request

DEFAULT_REGISTER="https://auth.haralabs.com.br/oauth/v2/register"
USER_AGENT="HARA-MCP-DCR-Lifecycle-Canary/1"

def request(url: str, *, method: str="GET", payload=None, token: str|None=None):
    headers={"accept":"application/json","user-agent":USER_AGENT}
    body=None
    if payload is not None:
        headers["content-type"]="application/json"
        body=json.dumps(payload,separators=(",",":")).encode()
    if token:
        headers["authorization"]="Bearer "+token
    req=urllib.request.Request(url,data=body,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as resp:
            raw=resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        try:
            parsed=json.loads(raw) if raw else {}
        except Exception:
            parsed={}
        return exc.code,parsed

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--register-url",default=DEFAULT_REGISTER)
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args()
    if not args.execute:
        print("DCR_LIFECYCLE_CANARY_EXECUTE=FALSE")
        return 0

    payload={
        "client_name":"HARA MCP disposable lifecycle canary",
        "application_type":"native",
        "redirect_uris":["http://127.0.0.1:6276/oauth/callback"],
        "response_types":["code"],
        "grant_types":["authorization_code","refresh_token"],
        "token_endpoint_auth_method":"none",
    }

    status,registration=request(args.register_url,method="POST",payload=payload)
    if status != 201:
        raise SystemExit(f"DCR_LIFECYCLE_REGISTER_FAIL:{status}:{registration.get('error')}")
    client_id=registration.get("client_id")
    token=registration.get("registration_access_token")
    registration_uri=registration.get("registration_client_uri")
    if not client_id or not token or not registration_uri:
        raise SystemExit("DCR_LIFECYCLE_REGISTRATION_RESPONSE_INCOMPLETE")
    if registration.get("client_secret"):
        raise SystemExit("DCR_LIFECYCLE_PUBLIC_CLIENT_SECRET_UNEXPECTED")
    print("DCR_LIFECYCLE_REGISTER=PASS")
    print("DCR_LIFECYCLE_PUBLIC_CLIENT=PASS")
    print("DCR_LIFECYCLE_REGISTRATION_ACCESS_TOKEN=RECEIVED_NOT_PRINTED")

    status,readback=request(registration_uri,token=token)
    if status != 200 or readback.get("client_id") != client_id:
        raise SystemExit(f"DCR_LIFECYCLE_READ_FAIL:{status}")
    print("DCR_LIFECYCLE_MANAGEMENT_READ=PASS")

    status,_=request(registration_uri,method="DELETE",token=token)
    if status != 204:
        raise SystemExit(f"DCR_LIFECYCLE_DELETE_FAIL:{status}")
    print("DCR_LIFECYCLE_DELETE=PASS")

    status,_=request(registration_uri,token=token)
    if status not in (401,404):
        raise SystemExit(f"DCR_LIFECYCLE_POST_DELETE_FAIL:{status}")
    print("DCR_LIFECYCLE_POST_DELETE_DENY=PASS")
    print("DCR_LIFECYCLE_SECRET_MATERIAL_STDOUT=false")
    print("DCR_LIFECYCLE_CANARY=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
