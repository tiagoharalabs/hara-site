#!/usr/bin/env python3
"""HARA Commander public launch distribution gate, READ ONLY.

Validates the live manifest signature against the immutable trusted v1 signing
key in the historical signed Git commit and hashes ALL live declared assets.
It cannot sign, upload, install, revoke, or modify production.
"""
from __future__ import annotations
import base64
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT=Path(__file__).resolve().parents[3]
URL="https://commander.haralabs.com.br"
SIGNED_REFERENCE_COMMIT="08500d5"
FILES={"agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1"}
EXPECTED_MANIFEST_SCHEMA="hara.commander-agent-release.v1"
SIGNATURE_SCHEMA="hara.commander-release-signature.v1"
MAX_BYTES=2*1024*1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise RuntimeError("UNEXPECTED_REDIRECT")

def download(path):
    if path.startswith("/") or ".." in path or "://" in path:
        raise ValueError("INVALID_ASSET_PATH")
    req=urllib.request.Request(
        URL+"/"+path,
        headers={"Cache-Control":"no-cache","User-Agent":"HARA-R16-Launch-Gate-Readonly"},
        method="GET")
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=18) as res:
        if res.status!=200:raise RuntimeError("HTTP_NOT_200")
        blob=res.read(MAX_BYTES+1)
        if len(blob)>MAX_BYTES:raise RuntimeError("ASSET_TOO_LARGE")
        return blob

def b64url(text):
    if not isinstance(text,str):raise ValueError("BASE64_REQUIRED")
    return base64.urlsafe_b64decode(text+"="*((-len(text))%4))

def trusted_signing_key():
    source=subprocess.check_output(
        ["git","show",SIGNED_REFERENCE_COMMIT+":apps/commander/public/install/linux.sh"],
        cwd=ROOT,timeout=15,text=True)
    n=re.search(r'^RELEASE_SIGNING_N="([^"]+)"',source,re.M)
    e=re.search(r'^RELEASE_SIGNING_E="([^"]+)"',source,re.M)
    if not (n and e):raise ValueError("TRUSTED_PUBLIC_KEY_NOT_FOUND")
    return rsa.RSAPublicNumbers(
        int.from_bytes(b64url(e.group(1)),"big"),
        int.from_bytes(b64url(n.group(1)),"big")).public_key()

def inspect_asset(entry):
    name=entry.get("path")
    if name not in FILES:
        return {"path":str(name),"state":"UNEXPECTED_ARTIFACT"}
    try:
        data=download(name)
        digest=hashlib.sha256(data).hexdigest()
        expected=entry.get("sha256")
        size=entry.get("bytes")
        same=digest==expected and len(data)==size
        return {"path":name,"state":"PASS" if same else "HASH_OR_SIZE_MISMATCH",
                "declared_bytes":size,"actual_bytes":len(data),
                "digest_equal":digest==expected}
    except Exception as exc:
        return {"path":str(name),"state":"FETCH_FAILED",
                "error_class":type(exc).__name__}

def main():
    report={"schema":"hara.commander.launch-public-artifact-gate.v1",
            "site":URL,"read_only":True,
            "historical_trusted_signature_commit":SIGNED_REFERENCE_COMMIT,
            "checks":[]}
    try:
        manifest_raw=download("release/agent-manifest.json")
        sig_raw=download("release/agent-manifest.sig.json")
        manifest=json.loads(manifest_raw)
        sig=json.loads(sig_raw)
        report["manifest_version"]=manifest.get("agent_version")
        if manifest.get("schema")!=EXPECTED_MANIFEST_SCHEMA:
            raise ValueError("MANIFEST_SCHEMA_INVALID")
        if sig.get("schema")!=SIGNATURE_SCHEMA or sig.get("alg")!="RS256":
            raise ValueError("SIGNATURE_SCHEMA_INVALID")
        if sig.get("kid")!="commander-release-v1":
            raise ValueError("SIGNING_KID_NOT_APPROVED")
        if sig.get("manifest_sha256")!=hashlib.sha256(manifest_raw).hexdigest():
            raise ValueError("SIGNATURE_MANIFEST_HASH_MISMATCH")
        trusted_signing_key().verify(b64url(sig.get("signature")),manifest_raw,
            padding.PKCS1v15(),hashes.SHA256())
        report["manifest_signature"]="PASS_PINNED_KEY"
        entries=manifest.get("files")
        if not isinstance(entries,list) or {x.get("path") for x in entries}!=FILES:
            raise ValueError("MANIFEST_FILE_LIST_INVALID")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            report["checks"]=list(pool.map(inspect_asset,entries))
        report["state"]="PASS" if all(c["state"]=="PASS" for c in report["checks"]) else "BLOCKED"
    except Exception as exc:
        report["state"]="BLOCKED"
        report["error_class"]=type(exc).__name__
        report["gate_error"]=str(exc)[:100] if isinstance(exc,ValueError) else "TRUST_OR_FETCH_FAILED"
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
    return 0 if report["state"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
