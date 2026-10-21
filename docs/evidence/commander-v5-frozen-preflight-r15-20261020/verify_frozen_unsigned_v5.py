#!/usr/bin/env python3
"""Offline review of an UNSIGNED frozen HARA Commander v5 distribution tar.
Read-only, no signing key, no installer execution, no cloud deployment.
"""
import argparse,hashlib,io,json,posixpath,re,tarfile
from pathlib import Path

TRUSTED_FP="93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
REQUIRED_SHA="3ade217145e32899da47bedb43272897ee020e44658ae2b197b0eda61880970d"
ROOT="apps/commander/public/"
ASSETS=("agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1")
def sha(b):return hashlib.sha256(b).hexdigest()
def load(archive):
    blobs={}
    with tarfile.open(fileobj=archive,mode="r:gz") as tar:
        for m in tar.getmembers():
            p=m.name[2:] if m.name.startswith("./") else m.name
            p=posixpath.normpath(p)
            if p in ("","."):continue
            if p.startswith("../") or p.startswith("/") or not (m.isdir() or m.isfile()):
                raise ValueError("TAR_UNSAFE_ENTRY")
            if p in blobs:raise ValueError("TAR_DUPLICATE_ENTRY:"+p)
            blobs[p]=None if m.isdir() else tar.extractfile(m).read()
    return blobs
def first(pattern,raw,flag=re.M):
    hits=re.findall(pattern,raw,flag)
    if len(hits)!=1:raise ValueError("INVALID_PIN_OR_VERSION")
    return hits[0].decode("ascii") if isinstance(hits[0],bytes) else hits[0]
def inspect(blobs,archive_sha):
    failures=[]
    def fail(code):failures.append(code)
    def get(name):
        b=blobs.get(name)
        if not isinstance(b,bytes):fail("MISSING_OR_DIRECTORY:"+name);return b""
        return b
    a=lambda x:get(ROOT+x)
    status=json.loads(get("CANDIDATE_STATUS.json"))
    man_raw=a("release/agent-manifest.json");man=json.loads(man_raw)
    key=json.loads(a("release/release-signing-public.jwk"))
    v2_key=json.loads(a("release/v2/release-signing-public.jwk"))
    if archive_sha!=REQUIRED_SHA:fail("FROZEN_ARCHIVE_SHA_DRIFT")
    if status.get("state")!="AWAITING_OFFICIAL_SIGNATURE" or any(status.get(k) is not False for k in ("signature_present","private_key_read","production_mutation")):fail("UNSIGNED_STATUS_INVALID")
    if status.get("manifest_sha256")!=sha(man_raw):fail("STATUS_MANIFEST_SHA_DRIFT")
    if man.get("schema")!="hara.commander-agent-release.v1" or man.get("agent_version")!="0.3.43":fail("MANIFEST_VERSION_INVALID")
    rows=man.get("files",[])
    if len(rows)!=4 or {r.get("path") for r in rows if isinstance(r,dict)}!=set(ASSETS):fail("MANIFEST_FILESET_INVALID")
    for row in rows:
        if not isinstance(row,dict):continue
        name=row.get("path")
        if name not in ASSETS:continue
        raw=a(name)
        if row.get("bytes")!=len(raw) or row.get("sha256")!=sha(raw):fail("MANIFEST_ASSET_DRIFT:"+name)
    sums=a("release/SHA256SUMS").decode("ascii").splitlines()
    if sorted(sums)!=sorted(r.get("sha256","")+"  "+r.get("path","") for r in rows if isinstance(r,dict)):fail("SHA256SUMS_INVALID")
    if ROOT+"release/agent-manifest.sig.json" in blobs:fail("CANDIDATE_NOT_UNSIGNED")
    if key!=v2_key or key.get("kid")!="commander-release-v2" or any(f in key for f in ("d","p","q","dp","dq","qi")):fail("TRUST_ANCHOR_INVALID")
    if sha(json.dumps(key,sort_keys=True,separators=(",",":")).encode())!=TRUSTED_FP:fail("TRUST_ANCHOR_FINGERPRINT_INVALID")
    li=a("install/linux.sh");wi=a("install/windows.ps1")
    try:
        ln=first(rb'^RELEASE_SIGNING_N="([^"]+)"',li)
        le=first(rb'^RELEASE_SIGNING_E="([^"]+)"',li)
        lk=first(rb'^RELEASE_SIGNING_KID="([^"]+)"',li)
        wn=first(rb'^\$ReleaseSigningN = "([^"]+)"',wi)
        we=first(rb'^\$ReleaseSigningE = "([^"]+)"',wi)
        wk=first(rb'^\$ReleaseSigningKid = "([^"]+)"',wi)
        if (lk,ln,le)!=(key["kid"],key["n"],key["e"]) or (wk,wn,we)!=(key["kid"],key["n"],key["e"]):fail("INSTALLER_PINS_DIFFER")
        lv=first(rb'^AGENT_VERSION = "([^"]+)"',a("agent/linux.py"))
        wv=first(rb'^\$AgentVersion = "([^"]+)"',a("agent/windows.ps1"))
        if (lv,wv)!=(man.get("agent_version"),)*2:fail("AGENT_VERSION_DRIFT")
    except (ValueError,KeyError):fail("INSTALLER_PIN_OR_AGENT_VERSION_MISSING")
    for name,statuskey in (("agent/linux.py","linux_agent_sha256"),("install/linux.sh","linux_installer_sha256"),("install/windows.ps1","windows_installer_sha256")):
        if status.get(statuskey)!=sha(a(name)):fail("STATUS_ASSET_DRIFT:"+name)
    for name in ("index.html","app.js"):
        if status.get("current_static_sha256",{}).get(name)!=sha(a(name)):fail("STATUS_UI_DRIFT:"+name)
    return {"schema":"hara.commander.frozen-source-preflight.r15.v1",
       "state":"READY_FOR_AUTHORIZED_SIGNATURE" if not failures else "HOLD",
       "frozen_tar_sha256":archive_sha,"manifest_sha256":sha(man_raw),
       "source_version":man.get("agent_version"),"asset_checks":len(ASSETS),
       "public_key_fingerprint":TRUSTED_FP,"same_pins_both_installers":"INSTALLER_PINS_DIFFER" not in failures,
       "signed_release":False,"public_promotion_authorized":False,
       "production_mutation":False,"errors":sorted(set(failures))}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    raw=args.archive.read_bytes();blobs=load(io.BytesIO(raw))
    report=inspect(blobs,sha(raw))
    if args.self_test:
        assert report["state"]=="READY_FOR_AUTHORIZED_SIGNATURE",report
        variations=[("tampered_linux","agent/linux.py"),
          ("tampered_windows","agent/windows.ps1"),("tampered_installer","install/linux.sh"),
          ("tampered_manifest","release/agent-manifest.json")]
        for label,path in variations:
            edited=dict(blobs);edited[ROOT+path]=blobs[ROOT+path]+(b"\n" if path.endswith(".json") else b"\n# QA tamper\n")
            # An in-memory edit changes the archive, without writing any private key.
            neg=inspect(edited,REQUIRED_SHA)
            assert neg["state"]=="HOLD" and neg["errors"],(label,neg)
        wrong=inspect(blobs,"0"*64)
        assert wrong["state"]=="HOLD"
        report["negative_checks_passed"]=len(variations)+1
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["state"]=="READY_FOR_AUTHORIZED_SIGNATURE" else 2
if __name__=="__main__":raise SystemExit(main())
