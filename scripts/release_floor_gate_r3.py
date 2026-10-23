#!/usr/bin/env python3
"""H.A.R.A. hara-site release-floor gate — fail closed, read-only, no network.

A site merge is NOT a Commander agent release. Passing version+digest checks cannot
replace signature verification, release-owner approval, or governed deployment.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, sys

EXPECTED = frozenset((
  "agent/linux.py", "agent/windows.ps1",
  "install/linux.sh", "install/windows.ps1"))
MANIFEST="apps/commander/public/release/agent-manifest.json"
PREFIX="apps/commander/public"
VERSION_RE=re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
LINUX_RE=re.compile(r'^AGENT_VERSION\s*=\s*["\']([0-9.]+)["\']\s*$',re.M)
WINDOWS_RE=re.compile(r'^\$AgentVersion\s*=\s*["\']([0-9.]+)["\']\s*$',re.M)
FLOORS={"manifest":(0,3,54),"linux":(0,3,54),"windows":(0,3,55)}

class Hold(Exception):pass

def check(condition,reason):
    if not condition:raise Hold(reason)
def version(raw):
    check(isinstance(raw,str) and bool(VERSION_RE.fullmatch(raw)),"INVALID_SEMVER")
    return tuple(int(x) for x in raw.split("."))
def safe_file(root,rel):
    check(not rel.startswith("/") and ".." not in pathlib.PurePosixPath(rel).parts,"PATH_TRAVERSAL")
    p=root/rel
    check(p.is_file() and not p.is_symlink(),"ARTIFACT_MISSING_OR_SYMLINK")
    check(p.resolve().is_relative_to(root.resolve()),"PATH_ESCAPED_ROOT")
    return p.read_bytes()
def digest(blob):
    return hashlib.sha256(blob).hexdigest()
def release_floor(root):
    return release_floor_public(pathlib.Path(root)/PREFIX)
def release_floor_public(public_root):
    root=pathlib.Path(public_root)
    check(root.is_dir() and not root.is_symlink(),"MISSING_PUBLIC_DIR")
    content=safe_file(root,"release/agent-manifest.json")
    try:m=json.loads(content)
    except ValueError:raise Hold("MANIFEST_BAD_JSON")
    check(isinstance(m,dict) and m.get("schema")=="hara.commander-agent-release.v1",
          "MANIFEST_SCHEMA")
    check(m.get("channel")=="stable","UNREVIEWED_CHANNEL")
    rows=m.get("files")
    check(isinstance(rows,list) and len(rows)==4,"MANIFEST_CARDINALITY")
    paths=[row.get("path") if isinstance(row,dict) else None for row in rows]
    check(set(paths)==EXPECTED and len(set(paths))==4,"MANIFEST_FILE_ALLOWLIST")
    inventory={}
    for item in rows:
        rel=item["path"]
        blob=safe_file(root,rel)
        check(type(item.get("bytes")) is int and item["bytes"]==len(blob),
              "ARTIFACT_SIZE_"+rel.replace("/","_"))
        check(isinstance(item.get("sha256"),str) and item["sha256"]==digest(blob),
              "ARTIFACT_SHA_"+rel.replace("/","_"))
        inventory[rel]=blob
    linux_txt=inventory["agent/linux.py"].decode("utf-8")
    windows_txt=inventory["agent/windows.ps1"].decode("utf-8")
    lx=LINUX_RE.findall(linux_txt);wx=WINDOWS_RE.findall(windows_txt)
    check(len(lx)==1 and len(wx)==1,"AGENT_VERSION_MARKER")
    versions={"manifest":version(m.get("agent_version")),
              "linux":version(lx[0]),"windows":version(wx[0])}
    for kind,floor in FLOORS.items():
        check(versions[kind]>=floor,"VERSION_BELOW_FLOOR_"+kind.upper())
    check(versions["linux"]>=versions["manifest"] and
          versions["windows"]>=versions["manifest"],"MANIFEST_GREATER_THAN_AGENT")
    return {
        "schema":"hara.site.release-floor-preflight.v1",
        "state":"PASS_VERSION_DIGEST_ONLY_NOT_RELEASE_APPROVAL",
        "versions":{k:".".join(map(str,v)) for k,v in versions.items()},
        "minimal_versions":{k:".".join(map(str,v)) for k,v in FLOORS.items()},
        "artifact_count":len(rows),"artifacts_exact_hashes":True,
        "signed_release_independently_attested":False,
        "release_owner_approved":False,
        "runtime_change_performed":False,"git_refs_mutated":False,"github_requests":0,
    }
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",required=True)
    args=ap.parse_args()
    try:
        result=release_floor(args.root)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Hold as exc:
        print(json.dumps({"schema":"hara.site.release-floor-preflight.v1",
                          "state":"HOLD_RELEASE_FLOOR","reason":str(exc),
                          "release_owner_approved":False,"runtime_change_performed":False,
                          "github_requests":0},sort_keys=True))
        return 2
if __name__=="__main__":
    sys.exit(main())
