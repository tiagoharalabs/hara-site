#!/usr/bin/env python3
"""Read-only, fail-closed PROD signed Linux 0.3.54 verification.

No device token, no Cloudflare mutation, no secrets, no sudo.
"""
import base64,hashlib,json,pathlib,sys,urllib.request
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa

SITE="https://commander.haralabs.com.br"
KEY=pathlib.Path("/home/sartorius/.local/share/hara-commander/releases/0.3.54-event-v2-fleet-20261013-1639-r2/release-v2/release-signing-public.jwk")
PIN="93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
FILES={"agent/linux.py","install/linux.sh"}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError("REDIRECT_DENIED")
def get(path,limit=300000):
    opener=urllib.request.build_opener(NoRedirect())
    req=urllib.request.Request(SITE+"/"+path,headers={"Accept":"application/json" if path.endswith("json") else "application/octet-stream","User-Agent":"HARA-Commander-ReadOnly-Signed-Release-Acceptance/1"})
    with opener.open(req,timeout=8) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise RuntimeError("ASSET_TOO_LARGE")
        if response.geturl()!=SITE+"/"+path:raise RuntimeError("URL_MISMATCH")
        return data
def sha(raw):return hashlib.sha256(raw).hexdigest()
def b64i(v):
    return int.from_bytes(base64.urlsafe_b64decode(v+"="*((-len(v))%4)),"big")
def verify():
    pub=json.loads(KEY.read_bytes())
    raw=json.dumps(pub,sort_keys=True,separators=(",",":")).encode()
    assert sha(raw)==PIN and pub.get("kid")=="commander-release-v2","PUBKEY_PIN_INVALID"
    manifest_data=get("release/linux-agent-manifest.json",20000)
    signature_data=get("release/linux-agent-manifest.sig.json",15000)
    manifest=json.loads(manifest_data);signature=json.loads(signature_data)
    assert manifest.get("schema")=="hara.commander-agent-release.v1","SCHEMA"
    assert manifest.get("platform")=="linux" and manifest.get("channel")=="stable","CHANNEL_PLATFORM"
    assert manifest.get("agent_version")=="0.3.54","NOT_LATEST_VERSION"
    assert signature.get("kid")=="commander-release-v2" and signature.get("alg")=="RS256","SIGNATURE_ID"
    assert signature.get("manifest_sha256")==sha(manifest_data),"MANIFEST_DIGEST"
    public=rsa.RSAPublicNumbers(b64i(pub["e"]),b64i(pub["n"])).public_key()
    signature_bytes=base64.urlsafe_b64decode(signature["signature"]+"="*((-len(signature["signature"]))%4))
    public.verify(signature_bytes,manifest_data,padding.PKCS1v15(),hashes.SHA256())
    entries=manifest.get("files")
    assert isinstance(entries,list) and {v["path"] for v in entries}==FILES and len(entries)==2,"FILESET"
    for row in entries:
        actual=get(row["path"])
        assert sha(actual)==row["sha256"] and len(actual)==row["bytes"],"ASSET_SHA_"+row["path"]
        print("HARA054_ASSET_PASS="+row["path"])
    print("HARA054_PUBLIC_SIGNED_LINUX=PASS")
    print("HARA054_PUBLIC_MANIFEST_SHA256="+sha(manifest_data))
if __name__=="__main__":
    try:verify()
    except Exception as exc:
        name=type(exc).__name__
        print("HARA054_PUBLIC_RELEASE=HOLD_"+name)
        sys.exit(5)
