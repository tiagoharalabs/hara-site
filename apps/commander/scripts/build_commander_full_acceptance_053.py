#!/usr/bin/env python3
"""Sign frozen 0.3.53 full-platform RC assets using the existing v2 authority.

Historical bundles and the source tree are preserved. Deployment is a separate
operation. Signing material stays inside the canonical signer.
"""
from pathlib import Path
import argparse,importlib.util,json,hashlib,re,shutil
ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
VERSION="0.3.53"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def signer():
    spec=importlib.util.spec_from_file_location("full053_signer",APP/"scripts/build_commander_commercial_signed_v2.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.VERSION=VERSION
    return m
def prepare(stage,bundle_name):
    m=signer();stage=m.protect(str(stage))
    assert re.fullmatch(r"commercial-0\.3\.53-v13-rc-r[2-9][0-9]*",bundle_name),"FULL053_BUNDLE_NAME_INVALID"
    bundle=APP/"release-bundles"/bundle_name
    assert not stage.exists() and not bundle.exists(),"IMMUTABLE_TARGET_EXISTS"
    linux=APP/"public/agent/linux.py";windows=APP/"public/agent/windows.ps1"
    assert sha(linux)=="db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e","LINUX_REVIEWED_SOURCE_DRIFT"
    assert sha(windows)=="f67ebcee909ee2ce93187262c951b57b38bc976fec73413bd30555d9bcf62299","WINDOWS_REVIEWED_SOURCE_DRIFT"
    assert linux.read_text().count('AGENT_VERSION = "0.3.53"')==1
    assert windows.read_text().count('$AgentVersion = "0.3.53"')==1
    before={f:sha(APP/"public"/f) for f in m.FILESET}
    m.populate(stage);m.sign(stage)
    pub=stage/"apps/commander/public"
    manifest=json.loads((pub/"release/agent-manifest.json").read_bytes())
    assert manifest["agent_version"]==VERSION
    bundle.mkdir(parents=True)
    for relative in (*m.FILESET,"release/agent-manifest.json","release/agent-manifest.sig.json","release/release-signing-public.jwk","release/SHA256SUMS"):
        dest=bundle/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pub/relative,dest)
    assert before=={f:sha(APP/"public"/f) for f in m.FILESET},"SOURCE_CHANGED_DURING_PREPARATION"
    evidence=ROOT/"docs/evidence/commander-full-acceptance-20261012/full-053"
    evidence.mkdir(parents=True,exist_ok=True)
    report={"schema":"hara.full-platform-053-preparation.v1","state":"SIGNED_PREPARED_NOT_DEPLOYED","version":VERSION,"bundle":str(bundle.relative_to(ROOT)),"manifest_sha256":sha(bundle/"release/agent-manifest.json"),"signature_sha256":sha(bundle/"release/agent-manifest.sig.json"),"platform_versions_match_manifest":True,"source_files":before,"signed_files":{r["path"]:r["sha256"] for r in manifest["files"]},"historical_bundles_changed":False,"private_key_printed":False,"production_deployed":False}
    (evidence/("preparation-"+bundle_name+".json")).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage",type=Path,required=True)
    p.add_argument("--bundle-name",default="commercial-0.3.53-v13-rc-r2")
    a=p.parse_args();prepare(a.stage,a.bundle_name)
if __name__=="__main__": main()
