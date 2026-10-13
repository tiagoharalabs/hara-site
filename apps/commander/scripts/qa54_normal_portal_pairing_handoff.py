#!/usr/bin/env python3
"""Create normal QA2 portal pairing on Storage and transfer into an owner-only handoff."""
from pathlib import Path
import subprocess,json,os,stat,hashlib,datetime
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/qa_normal_device_mcp_v54_combined.py"
DEST=ROOT/"apps/commander/.generated/full-acceptance-20261012/windows-clean/qa2-portal-pairing-054r2-jit.json"
REPORT=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/qa2-normal-pairing-054r2-jit.json"
EXPECTED_SOURCE="85c4a94c1f80c4e8a3a9113b21423cb01a8347be4b43c129b43bb61b26686ae6"
def main():
    os.umask(0o077)
    assert not DEST.exists() and not DEST.is_symlink(),"QA54_HANDOFF_ALREADY_EXISTS"
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED_SOURCE,"QA54_REVIEWED_HELPER_DRIFT"
    source=SOURCE.read_text()
    # Existing reviewed helper code, not private state, is sent as stdin.
    remote="import io,json,contextlib,types,stat,pathlib\n"
    remote+="m=types.ModuleType('qa54_normal_portal_helper')\n"
    remote+="exec("+repr(source)+",m.__dict__)\n"
    remote+="b=io.StringIO()\n"
    remote+="with contextlib.redirect_stdout(b):\n"
    remote+=" s=m.load();assert s['portal']['user_id']=='394861028946477060';m.normal_pairing()\n"
    remote+="q=m.PRIVATE/'qa2-portal-pairing.json';m.private_file(q);handoff=json.loads(q.read_text())\n"
    remote+="print(json.dumps({'handoff':handoff,'events':[json.loads(x) for x in b.getvalue().splitlines() if x]}))\n"
    p=subprocess.run(["ssh","-o","BatchMode=yes","storage","sudo","/usr/bin/python3","-I","-B","-"],input=remote,text=True,capture_output=True,timeout=75)
    if p.returncode:
        # No raw exception, response, stderr or secret-bearing output is surfaced.
        print(json.dumps({"state":"FAIL_NORMAL_PAIRING","safe_code":"STORAGE_EXECUTOR_FAILED","private_state_preserved":True}));return 1
    data=json.loads(p.stdout);h=data["handoff"]
    assert h["dev_origin"]=="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
    assert h["tenant_id"]=="HARA-TENANT-BNRKHV5P7_1SBJSL8FZ_HYYR"
    assert h["idp_subject_id"]=="394861028946477060" and h["source"]=="NORMAL_PORTAL_PAIRING_API"
    assert h.get("pairing_token") and h.get("pairing_id")
    DEST.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    assert not DEST.parent.is_symlink()
    fd=os.open(DEST,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w") as f:json.dump(h,f,separators=(",",":"));f.write("\n")
    st=DEST.stat();assert stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600
    report={"state":"PASS_NORMAL_PORTAL_QA2_PAIRING_CREATED","at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"pairing_id":h["pairing_id"],"expires_at_utc":h.get("expires_at_utc"),"normal_portal_cookie_used":True,"d1_seed_performed":False,"private_file_mode":"0600","credential_values_exposed":False,"helper_source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),"private_handoff_path":str(DEST)}
    REPORT.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True));return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as e:print(json.dumps({"state":"FAIL_NORMAL_PAIRING","safe_code":type(e).__name__,"credential_values_exposed":False}));raise SystemExit(1)
