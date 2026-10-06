#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import ssl
import subprocess
import time
import urllib.error
import urllib.request

ISSUER="https://auth.haralabs.com.br"
GET_SECURITY=ISSUER+"/v2/settings/security"
SET_SECURITY=ISSUER+"/v2/policies/security"
PUBLIC_REGISTER=ISSUER+"/oauth/v2/register"
DOCKER_NETWORK="hara-identity"
CANARY_IMAGE="hara-identity-dcr-gateway:v0.1.0"

def request_json(url: str, *, method="GET", token: str|None=None, payload=None):
    headers={"accept":"application/json","user-agent":"HARA-MCP-DCR-Internal-Canary/1"}
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
            return resp.status,json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        try: value=json.loads(raw) if raw else {}
        except Exception: value={}
        return exc.code,value

def settings_payload(settings: dict, *, enabled: bool, allow_unauthenticated: bool) -> dict:
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

def public_guard() -> None:
    status,_=request_json(
        PUBLIC_REGISTER,
        method="POST",
        payload={
            "client_name":"HARA Public Guard Probe",
            "application_type":"native",
            "redirect_uris":["http://127.0.0.1:33418"],
            "response_types":["code"],
            "grant_types":["authorization_code","refresh_token"],
            "token_endpoint_auth_method":"none",
        },
    )
    if status != 404:
        raise RuntimeError("PUBLIC_DCR_GUARD_NOT_CLOSED")

def read_dcr(token: str) -> tuple[dict,bool,bool]:
    status,current=request_json(GET_SECURITY,token=token)
    if status != 200:
        raise RuntimeError("DCR_SECURITY_READ_FAILED")
    settings=current.get("settings")
    if not isinstance(settings,dict):
        raise RuntimeError("DCR_SECURITY_PREIMAGE_INVALID")
    dcr=settings.get("dynamicClientRegistration") or {}
    return settings,bool(dcr.get("enabled")),bool(dcr.get("allowUnauthenticated"))

def write_dcr(token: str, settings: dict, *, enabled: bool, allow_unauthenticated: bool) -> None:
    status,_=request_json(
        SET_SECURITY,
        method="PUT",
        token=token,
        payload=settings_payload(
            settings,
            enabled=enabled,
            allow_unauthenticated=allow_unauthenticated,
        ),
    )
    if status != 200:
        raise RuntimeError("DCR_SECURITY_WRITE_FAILED")

NODE_CANARY=r"""
const upstream="http://zitadel-api:8080/oauth/v2/register";
const common={
  "content-type":"application/json",
  "accept":"application/json",
  "host":"auth.haralabs.com.br",
  "x-forwarded-proto":"https",
};
const payload={
  client_name:"HARA MCP DCR Internal Canary",
  application_type:"native",
  redirect_uris:[
    "http://127.0.0.1:33418",
    "https://vscode.dev/redirect"
  ],
  response_types:["code"],
  grant_types:["authorization_code","refresh_token"],
  token_endpoint_auth_method:"none",
};
let created=null;
function fail(code){ throw new Error(code); }
async function jsonOrNull(res){
  const text=await res.text();
  if(!text) return null;
  try{return JSON.parse(text);}catch{return null;}
}
for(let attempt=0;attempt<10;attempt++){
  const res=await fetch(upstream,{method:"POST",headers:common,body:JSON.stringify(payload)});
  const data=await jsonOrNull(res);
  if(res.status===201){
    created=data;
    break;
  }
  if(attempt===9) fail("DCR_CREATE_HTTP_"+res.status);
  await new Promise(r=>setTimeout(r,300));
}
if(!created?.client_id) fail("DCR_CLIENT_ID_MISSING");
if(!created?.registration_access_token) fail("DCR_REGISTRATION_TOKEN_MISSING");

const id=String(created.client_id);
const token=String(created.registration_access_token);
const management=upstream+"/"+encodeURIComponent(id);
const authHeaders={
  "accept":"application/json",
  "authorization":"Bearer "+token,
  "host":"auth.haralabs.com.br",
  "x-forwarded-proto":"https",
};

const getRes=await fetch(management,{headers:authHeaders});
const getData=await jsonOrNull(getRes);
if(getRes.status!==200) fail("DCR_GET_HTTP_"+getRes.status);
if(String(getData?.client_id||"")!==id) fail("DCR_GET_CLIENT_MISMATCH");

let activeToken=token;
const updatePayload={
  ...payload,
  client_id:id,
  client_name:"HARA MCP DCR Internal Canary Updated",
};
const putRes=await fetch(management,{
  method:"PUT",
  headers:{...authHeaders,"content-type":"application/json"},
  body:JSON.stringify(updatePayload),
});
const putData=await jsonOrNull(putRes);
if(![200,201].includes(putRes.status)) fail("DCR_PUT_HTTP_"+putRes.status);
if(putData?.registration_access_token) activeToken=String(putData.registration_access_token);

const get2=await fetch(management,{
  headers:{...authHeaders,authorization:"Bearer "+activeToken},
});
const get2Data=await jsonOrNull(get2);
if(get2.status!==200) fail("DCR_GET2_HTTP_"+get2.status);
if(!String(get2Data?.client_name||"").includes("Updated")) fail("DCR_UPDATE_NOT_VISIBLE");

const del=await fetch(management,{
  method:"DELETE",
  headers:{...authHeaders,authorization:"Bearer "+activeToken},
});
if(del.status!==204) fail("DCR_DELETE_HTTP_"+del.status);

const after=await fetch(management,{
  headers:{...authHeaders,authorization:"Bearer "+activeToken},
});
if(![401,403,404].includes(after.status)) fail("DCR_DELETE_NOT_TERMINAL_"+after.status);

console.log("INTERNAL_DCR_CREATE=PASS");
console.log("INTERNAL_DCR_READ=PASS");
console.log("INTERNAL_DCR_UPDATE=PASS");
console.log("INTERNAL_DCR_DELETE=PASS");
console.log("SECRET_MATERIAL_STDOUT=false");
"""

def internal_canary() -> str:
    proc=subprocess.run(
        [
            "docker","run","--rm","-i",
            "--network",DOCKER_NETWORK,
            CANARY_IMAGE,
            "node","--input-type=module","-",
        ],
        input=NODE_CANARY,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError("INTERNAL_DCR_CANARY_FAILED:"+proc.stdout[-1200:])
    return proc.stdout

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--pat-file",type=pathlib.Path,required=True)
    args=ap.parse_args()
    token=args.pat_file.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("PAT_EMPTY")

    public_guard()
    settings,pre_enabled,pre_open=read_dcr(token)
    if pre_enabled or pre_open:
        raise SystemExit("DCR_PREIMAGE_NOT_CLOSED")

    canary_output=""
    restored=False
    try:
        write_dcr(token,settings,enabled=True,allow_unauthenticated=True)
        for _ in range(20):
            _,enabled,opened=read_dcr(token)
            if enabled and opened:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("DCR_BACKEND_ENABLE_READBACK_FAILED")

        public_guard()
        canary_output=internal_canary()
        public_guard()
    finally:
        try:
            write_dcr(
                token,
                settings,
                enabled=pre_enabled,
                allow_unauthenticated=pre_open,
            )
            _,post_enabled,post_open=read_dcr(token)
            restored=(post_enabled==pre_enabled and post_open==pre_open)
        finally:
            if not restored:
                raise RuntimeError("DCR_PREIMAGE_RESTORE_FAILED")

    public_guard()
    print(canary_output,end="")
    print("PUBLIC_DCR_GUARD_DURING_BACKEND_OPEN=PASS")
    print("DCR_BACKEND_PREIMAGE_ENABLED=false")
    print("DCR_BACKEND_PREIMAGE_ALLOW_UNAUTHENTICATED=false")
    print("DCR_BACKEND_RESTORED=PASS")
    print("HARA_MCP_DCR_INTERNAL_CANARY=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
