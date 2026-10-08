#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ISSUER="https://auth.haralabs.com.br"
SECURITY_GET=ISSUER+"/v2/settings/security"
SECURITY_SET=ISSUER+"/v2/policies/security"
RFC8414=ISSUER+"/.well-known/oauth-authorization-server"
REGISTER=ISSUER+"/oauth/v2/register"
USER_AGENT="HARA-MCP-DCR-Promoter/1"

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

def security_payload(settings: dict, *, enabled: bool, allow_unauthenticated: bool) -> dict:
    payload={}
    if isinstance(settings.get("embeddedIframe"),dict):
        payload["embeddedIframe"]=settings["embeddedIframe"]
    if isinstance(settings.get("enableImpersonation"),bool):
        payload["enableImpersonation"]=settings["enableImpersonation"]
    payload["dynamicClientRegistration"]={
        "enabled":bool(enabled),
        "allowUnauthenticated":bool(allow_unauthenticated),
    }
    return payload

def dcr_state(settings: dict) -> tuple[bool,bool]:
    dcr=settings.get("dynamicClientRegistration")
    if not isinstance(dcr,dict):
        return False,False
    return bool(dcr.get("enabled")),bool(dcr.get("allowUnauthenticated"))

def transition_compose(text: str, *, guarded: bool) -> str:
    required=[
        "hara-identity-dcr-gateway:v0.2.0",
        "hara-identity-oauth-metadata:v1.1.0",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError("DCR_HARDENED_IMAGE_MISSING:"+marker)
    pairs=[
        (
            "HARA_DCR_GATEWAY_MODE: closed" if guarded else "HARA_DCR_GATEWAY_MODE: guarded",
            "HARA_DCR_GATEWAY_MODE: guarded" if guarded else "HARA_DCR_GATEWAY_MODE: closed",
        ),
        (
            'HARA_DCR_REGISTRATION_ADVERTISED: "false"' if guarded else 'HARA_DCR_REGISTRATION_ADVERTISED: "true"',
            'HARA_DCR_REGISTRATION_ADVERTISED: "true"' if guarded else 'HARA_DCR_REGISTRATION_ADVERTISED: "false"',
        ),
    ]
    updated=text
    for old,new in pairs:
        if updated.count(old) != 1:
            raise RuntimeError("DCR_COMPOSE_STATE_AMBIGUOUS:"+old)
        updated=updated.replace(old,new,1)
    return updated

def compose_state(text: str) -> str:
    guarded="HARA_DCR_GATEWAY_MODE: guarded" in text
    closed="HARA_DCR_GATEWAY_MODE: closed" in text
    advertised='HARA_DCR_REGISTRATION_ADVERTISED: "true"' in text
    hidden='HARA_DCR_REGISTRATION_ADVERTISED: "false"' in text
    if closed and hidden and not guarded and not advertised:
        return "closed"
    if guarded and advertised and not closed and not hidden:
        return "guarded"
    return "mixed"

def docker_recreate(compose_path: pathlib.Path) -> None:
    subprocess.run(
        [
            "sudo","-n","docker","compose",
            "--env-file",str(compose_path.parent.parent/"secrets/identity.env"),
            "-f",str(compose_path),
            "up","-d","--no-deps",
            "zitadel-dcr-gateway","zitadel-oauth-metadata",
        ],
        check=True,
    )

def public_metadata() -> tuple[int,dict]:
    cache_bust=str(time.time_ns())
    status,_,payload=request_json(RFC8414+"?proof="+cache_bust)
    return status,payload

def wait_for(predicate, *, attempts=20, delay=1.0):
    last=None
    for _ in range(attempts):
        try:
            last=predicate()
            if last:
                return last
        except Exception as exc:
            last=exc
        time.sleep(delay)
    raise RuntimeError("DCR_PROMOTION_READBACK_TIMEOUT:"+repr(last))

def verify_public_guarded() -> None:
    def metadata_ready():
        status,metadata=public_metadata()
        return (
            status==200
            and metadata.get("registration_endpoint")==REGISTER
            and metadata.get("client_id_metadata_document_supported") is False
        )
    wait_for(metadata_ready)
    status,_,payload=request_json(
        REGISTER,
        method="POST",
        payload={
            "client_name":"HARA invalid promotion probe",
            "application_type":"web",
            "redirect_uris":["http://example.invalid/callback"],
            "response_types":["code"],
            "grant_types":["authorization_code","refresh_token"],
            "token_endpoint_auth_method":"none",
        },
    )
    if status != 400 or payload.get("error") != "invalid_client_metadata":
        raise RuntimeError("DCR_PUBLIC_GUARD_INVALID_REJECTION_FAILED")

def verify_public_closed() -> None:
    def metadata_closed():
        status,metadata=public_metadata()
        return status==200 and "registration_endpoint" not in metadata
    wait_for(metadata_closed)
    status,_,_=request_json(
        REGISTER,
        method="POST",
        payload={
            "client_name":"HARA closed probe",
            "application_type":"native",
            "redirect_uris":["http://127.0.0.1:6276/oauth/callback"],
            "response_types":["code"],
            "grant_types":["authorization_code","refresh_token"],
            "token_endpoint_auth_method":"none",
        },
    )
    if status != 404:
        raise RuntimeError("DCR_PUBLIC_CLOSED_ROUTE_NOT_404")

def self_test() -> int:
    sample="""services:
  zitadel-dcr-gateway:
    image: hara-identity-dcr-gateway:v0.2.0
    environment:
      HARA_DCR_GATEWAY_MODE: closed
  zitadel-oauth-metadata:
    image: hara-identity-oauth-metadata:v1.1.0
    environment:
      HARA_DCR_REGISTRATION_ADVERTISED: "false"
"""
    assert compose_state(sample)=="closed"
    guarded=transition_compose(sample,guarded=True)
    assert compose_state(guarded)=="guarded"
    restored=transition_compose(guarded,guarded=False)
    assert restored==sample
    settings={
        "embeddedIframe":{"enabled":False},
        "enableImpersonation":False,
        "dynamicClientRegistration":{},
    }
    assert dcr_state(settings)==(False,False)
    opened=security_payload(settings,enabled=True,allow_unauthenticated=True)
    assert opened["dynamicClientRegistration"]=={"enabled":True,"allowUnauthenticated":True}
    restored_security=security_payload(settings,enabled=False,allow_unauthenticated=False)
    assert restored_security["dynamicClientRegistration"]=={"enabled":False,"allowUnauthenticated":False}
    print("HARA_MCP_DCR_PROMOTION_SELFTEST=PASS")
    print("HARA_MCP_DCR_PROMOTION_COMPOSE_TRANSITION=PASS")
    print("HARA_MCP_DCR_PROMOTION_EXACT_ROLLBACK=PASS")
    return 0

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--pat-file",type=pathlib.Path)
    ap.add_argument("--compose-file",type=pathlib.Path)
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.pat_file or not args.compose_file:
        ap.error("--pat-file and --compose-file are required")

    token=args.pat_file.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("DCR_PAT_EMPTY")
    compose_path=args.compose_file.resolve()
    original=compose_path.read_text(encoding="utf-8")
    if compose_state(original)!="closed":
        raise SystemExit("DCR_PROMOTION_REQUIRES_CLOSED_COMPOSE")

    status,_,current=request_json(SECURITY_GET,token=token)
    if status!=200 or not isinstance(current.get("settings"),dict):
        raise SystemExit("DCR_SECURITY_PREIMAGE_READ_FAILED")
    settings=current["settings"]
    pre_enabled,pre_open=dcr_state(settings)
    if pre_enabled or pre_open:
        raise SystemExit("DCR_PROMOTION_REQUIRES_BACKEND_DISABLED")

    rfc_status,rfc=public_metadata()
    if rfc_status!=200 or "registration_endpoint" in rfc:
        raise SystemExit("DCR_PROMOTION_REQUIRES_METADATA_HIDDEN")

    candidate=transition_compose(original,guarded=True)
    print("DCR_PROMOTION_PREFLIGHT=CLOSED_PASS")
    print("DCR_PROMOTION_BACKEND_PRE_ENABLED=false")
    print("DCR_PROMOTION_BACKEND_PRE_ALLOW_UNAUTHENTICATED=false")
    print("DCR_PROMOTION_CANDIDATE_STATE="+compose_state(candidate))
    print("DCR_PROMOTION_SECRET_MATERIAL_STDOUT=false")
    if not args.execute:
        print("DCR_PROMOTION_EXECUTE=FALSE")
        return 0

    stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    backup=compose_path.with_name(compose_path.name+".pre-mcp-dcr-guarded-"+stamp)
    shutil.copy2(compose_path,backup)
    os.chmod(backup,0o600)

    security_open=security_payload(settings,enabled=True,allow_unauthenticated=True)
    security_restore=security_payload(
        settings,
        enabled=pre_enabled,
        allow_unauthenticated=pre_open,
    )

    promoted=False
    try:
        set_status,_,_=request_json(
            SECURITY_SET,method="PUT",token=token,payload=security_open,
        )
        if set_status!=200:
            raise RuntimeError("DCR_BACKEND_ENABLE_FAILED")

        compose_path.write_text(candidate,encoding="utf-8")
        docker_recreate(compose_path)
        verify_public_guarded()
        promoted=True
    finally:
        if not promoted:
            compose_path.write_text(original,encoding="utf-8")
            try:
                docker_recreate(compose_path)
            finally:
                request_json(
                    SECURITY_SET,method="PUT",token=token,payload=security_restore,
                )
            verify_public_closed()

    status,_,current_after=request_json(SECURITY_GET,token=token)
    after_settings=current_after.get("settings") if status==200 else {}
    enabled,opened=dcr_state(after_settings if isinstance(after_settings,dict) else {})
    if not (enabled and opened):
        raise SystemExit("DCR_BACKEND_POST_STATE_FAILED")

    print("DCR_PROMOTION_EXECUTE=TRUE")
    print("DCR_PROMOTION_BACKUP="+str(backup))
    print("DCR_BACKEND_ENABLED=true")
    print("DCR_BACKEND_ALLOW_UNAUTHENTICATED=true")
    print("DCR_GATEWAY_MODE=guarded")
    print("DCR_REGISTRATION_ADVERTISED=true")
    print("DCR_PROMOTION_PUBLIC_INVALID_GUARD=PASS")
    print("DCR_PROMOTION=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
