#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request

ISSUER="https://auth.haralabs.com.br"
SECURITY_GET=ISSUER+"/v2/settings/security"
SECURITY_SET=ISSUER+"/v2/policies/security"
RFC8414=ISSUER+"/.well-known/oauth-authorization-server"
REGISTER=ISSUER+"/oauth/v2/register"
USER_AGENT="HARA-MCP-DCR-Emergency-Close/1"

def request_json(url: str, *, method="GET", token: str|None=None, payload=None):
    headers={"accept":"application/json","user-agent":USER_AGENT}
    body=None
    if token:
        headers["authorization"]="Bearer "+token
    if payload is not None:
        headers["content-type"]="application/json"
        body=json.dumps(payload,separators=(",",":")).encode()
    req=urllib.request.Request(url,data=body,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as resp:
            raw=resp.read()
            return resp.status,dict(resp.headers.items()),json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        try:
            parsed=json.loads(raw) if raw else {}
        except Exception:
            parsed={}
        return exc.code,dict(exc.headers.items()),parsed

def dcr_state(settings: dict) -> tuple[bool,bool]:
    dcr=settings.get("dynamicClientRegistration")
    if not isinstance(dcr,dict):
        return False,False
    return bool(dcr.get("enabled")),bool(dcr.get("allowUnauthenticated"))

def security_payload(settings: dict) -> dict:
    payload={}
    if isinstance(settings.get("embeddedIframe"),dict):
        payload["embeddedIframe"]=settings["embeddedIframe"]
    if isinstance(settings.get("enableImpersonation"),bool):
        payload["enableImpersonation"]=settings["enableImpersonation"]
    payload["dynamicClientRegistration"]={"enabled":False,"allowUnauthenticated":False}
    return payload

def compose_state(text: str) -> str:
    guarded="HARA_DCR_GATEWAY_MODE: guarded" in text
    closed="HARA_DCR_GATEWAY_MODE: closed" in text
    advertised='HARA_DCR_REGISTRATION_ADVERTISED: "true"' in text
    hidden='HARA_DCR_REGISTRATION_ADVERTISED: "false"' in text
    if guarded and advertised and not closed and not hidden:
        return "guarded"
    if closed and hidden and not guarded and not advertised:
        return "closed"
    return "mixed"

def close_compose(text: str) -> str:
    required=[
        "hara-identity-dcr-gateway:v0.2.0",
        "hara-identity-oauth-metadata:v1.1.0",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError("DCR_CLOSE_REQUIRED_IMAGE_MISSING:"+marker)
    state=compose_state(text)
    if state=="closed":
        return text
    if state!="guarded":
        raise RuntimeError("DCR_CLOSE_COMPOSE_STATE_MIXED")
    text=text.replace("HARA_DCR_GATEWAY_MODE: guarded","HARA_DCR_GATEWAY_MODE: closed",1)
    text=text.replace('HARA_DCR_REGISTRATION_ADVERTISED: "true"','HARA_DCR_REGISTRATION_ADVERTISED: "false"',1)
    if compose_state(text)!="closed":
        raise RuntimeError("DCR_CLOSE_TRANSITION_FAILED")
    return text

def docker_recreate(compose_path: pathlib.Path) -> None:
    subprocess.run([
        "sudo","-n","docker","compose",
        "--env-file",str(compose_path.parent.parent/"secrets/identity.env"),
        "-f",str(compose_path),
        "up","-d","--no-deps",
        "zitadel-dcr-gateway","zitadel-oauth-metadata",
    ],check=True)

def public_closed() -> bool:
    status,_,metadata=request_json(RFC8414+"?close="+str(time.time_ns()))
    if status!=200 or "registration_endpoint" in metadata:
        return False
    status,_,_=request_json(
        REGISTER,
        method="POST",
        payload={
            "client_name":"HARA emergency close probe",
            "application_type":"native",
            "redirect_uris":["http://127.0.0.1:6276/oauth/callback"],
            "response_types":["code"],
            "grant_types":["authorization_code"],
            "token_endpoint_auth_method":"none",
        },
    )
    return status==404

def wait_public_closed(attempts=30,delay=1.0) -> None:
    last=False
    for _ in range(attempts):
        try:
            last=public_closed()
            if last:
                return
        except Exception:
            last=False
        time.sleep(delay)
    raise RuntimeError("DCR_CLOSE_PUBLIC_READBACK_TIMEOUT:"+str(last))

def main() -> int:
    ap=argparse.ArgumentParser(description="Fail-closed emergency closure for guarded HARA MCP DCR. Dry-run by default.")
    ap.add_argument("--pat-file",type=pathlib.Path,required=True)
    ap.add_argument("--compose-file",type=pathlib.Path,required=True)
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args()

    token=args.pat_file.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("DCR_CLOSE_PAT_EMPTY")
    compose_path=args.compose_file.resolve()
    original=compose_path.read_text(encoding="utf-8")
    state=compose_state(original)
    if state not in {"guarded","closed"}:
        raise SystemExit("DCR_CLOSE_REQUIRES_GUARDED_OR_CLOSED_COMPOSE")

    status,_,current=request_json(SECURITY_GET,token=token)
    if status!=200 or not isinstance(current.get("settings"),dict):
        raise SystemExit("DCR_CLOSE_SECURITY_PREIMAGE_READ_FAILED")
    settings=current["settings"]
    enabled,opened=dcr_state(settings)
    candidate=close_compose(original)

    print("DCR_CLOSE_PREFLIGHT=PASS")
    print("DCR_CLOSE_COMPOSE_PRE_STATE="+state)
    print("DCR_CLOSE_BACKEND_PRE_ENABLED="+str(enabled).lower())
    print("DCR_CLOSE_BACKEND_PRE_ALLOW_UNAUTHENTICATED="+str(opened).lower())
    print("DCR_CLOSE_CANDIDATE_STATE="+compose_state(candidate))
    print("DCR_CLOSE_FAIL_CLOSED_ORDER=PUBLIC_FIRST_BACKEND_SECOND")
    print("DCR_CLOSE_SECRET_MATERIAL_STDOUT=false")

    if not args.execute:
        print("DCR_CLOSE_EXECUTE=FALSE")
        return 0

    stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    backup=compose_path.with_name(compose_path.name+".pre-mcp-dcr-emergency-close-"+stamp)
    shutil.copy2(compose_path,backup)
    os.chmod(backup,0o600)

    # Fail-closed order: hide/close the public route first.
    if candidate != original:
        compose_path.write_text(candidate,encoding="utf-8")
        docker_recreate(compose_path)
    wait_public_closed()

    # Then disable the backend. If this step fails, the public guard remains closed.
    status,_,_=request_json(
        SECURITY_SET,
        method="PUT",
        token=token,
        payload=security_payload(settings),
    )
    if status!=200:
        raise SystemExit("DCR_CLOSE_BACKEND_DISABLE_FAILED_PUBLIC_REMAINS_CLOSED")

    status,_,after=request_json(SECURITY_GET,token=token)
    after_settings=after.get("settings") if status==200 else {}
    post_enabled,post_open=dcr_state(after_settings if isinstance(after_settings,dict) else {})
    if post_enabled or post_open:
        raise SystemExit("DCR_CLOSE_BACKEND_POST_STATE_FAILED_PUBLIC_REMAINS_CLOSED")
    wait_public_closed()

    print("DCR_CLOSE_EXECUTE=TRUE")
    print("DCR_CLOSE_BACKUP="+str(backup))
    print("DCR_GATEWAY_MODE=closed")
    print("DCR_REGISTRATION_ADVERTISED=false")
    print("DCR_BACKEND_ENABLED=false")
    print("DCR_BACKEND_ALLOW_UNAUTHENTICATED=false")
    print("DCR_CLOSE_PUBLIC_READBACK=PASS")
    print("DCR_CLOSE=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
