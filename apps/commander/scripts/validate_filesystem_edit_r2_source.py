#!/usr/bin/env python3
"""Deterministic, offline exact-source QA of H.A.R.A. Commander editmode R2.

Uses disposable files only; does not install or enroll an Agent.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
REL="apps/commander/public/agent/linux.py"
BASE="e5176b3c5bfa60a1528109d736bb1e15ee8fa997"
PRE_SHA="a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733"
POST_SHA="4d1de56697329b2936778351a4988092e355d8a0d8a6f6cf17cce57880275733"
EVIDENCE=ROOT/"docs/evidence/commander-filesystem-editmode-r1-20261115"
PATCH=EVIDENCE/"agent_0383_filesystem_edit_mode_r2.patch"
PATCH_SHA="abbac2a26f4696e02217194ad43ce2ec03b441ac198ddd6c8ba8512fb1bc2082"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def run(argv, **kw):
    proc=subprocess.run(argv,capture_output=True,timeout=50,**kw)
    if proc.returncode:
        raise RuntimeError("QA_SUBPROCESS_FAILED:"+str(argv[0])+":"+str(proc.returncode)+":"+proc.stderr.decode("utf-8",errors="replace")[-160:])
    return proc.stdout

def main():
    if len(sys.argv)!=1: raise SystemExit("USAGE: validate_filesystem_edit_r2_source.py")
    assert PATCH.is_file()
    pre=run(["git","-C",str(ROOT),"show",BASE+":"+REL])
    candidate=(ROOT/REL).read_bytes()
    assert digest(pre)==PRE_SHA,"BASE_SOURCE_SHA_MISMATCH"
    assert digest(candidate)==POST_SHA,"INTEGRATED_SOURCE_SHA_MISMATCH"
    assert digest(PATCH.read_bytes())==PATCH_SHA,"PATCH_SHA_MISMATCH"
    with tempfile.TemporaryDirectory(prefix="hara-commander-editmode-r2-") as temp:
        t=Path(temp)
        (t/"agent.original.py").write_bytes(pre)
        (t/"agent.candidate.r2.py").write_bytes(candidate)
        rebuilt=t/"rebuild.py"
        run(["patch","-s","-o",str(rebuilt),str(t/"agent.original.py")],input=PATCH.read_bytes())
        assert digest(rebuilt.read_bytes())==POST_SHA,"PATCH_REBUILD_SHA_MISMATCH"
        env=os.environ.copy()
        env["HARA_MODEFIX_SOURCE_DIR"]=str(t)
        env["XDG_DATA_HOME"]=str(t/"isolated-data")
        env["XDG_CONFIG_HOME"]=str(t/"isolated-config")
        outcomes={}
        for script,key,expected in (
            ("test_modefix_r2.py","regression","PASS"),
            ("test_modefix_acl_r2.py","posix_acl","PASS_POSIX_ACL_EXACT"),
        ):
            output=run([sys.executable,"-I","-B",str(EVIDENCE/script)],env=env)
            payload=json.loads(output)
            assert payload["state"]==expected,(script,payload["state"])
            if key=="regression":
                assert payload["total"]==14 and len(payload["checks"])==14
                if os.geteuid()==0: assert payload["positive_gid"]
            else: assert payload["xattr_count"]>=1
            outcomes[key]={"state":payload["state"],"checks":payload.get("total"),"positive_gid":payload.get("positive_gid")}
        output=run([sys.executable,"-I","-B",str(ROOT/REL),"--self-test"],env=env)
        assert b"COMMANDER_LOCAL_MCP_TOOL_COUNT=41" in output,"COMMANDER_SELFTEST_FAIL"
        outcomes["selftest"]={"state":"PASS","mcp_tool_count":41}
    print(json.dumps({"state":"SOURCE_INTEGRATION_R2_QA_PASS",
      "base":BASE,"preimage_sha256":PRE_SHA,"integrated_sha256":POST_SHA,
      "patch_sha256":PATCH_SHA,"outcomes":outcomes,"runtime_mutated":False,
      "product_release_authorized":False},sort_keys=True))

if __name__=="__main__": main()
