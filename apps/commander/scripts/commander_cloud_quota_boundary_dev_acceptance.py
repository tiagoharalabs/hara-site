#!/usr/bin/env python3
"""Live DEV TenantQuota boundary and native Windows receipt proof."""
import argparse, concurrent.futures, importlib.util, json, secrets, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
def load(name):
    spec=importlib.util.spec_from_file_location(name,APP/"scripts"/(name+".py"))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
fixtures=load("full_acceptance_dev_fixtures")
quota=load("commander_event_v2_dev_quota_probe")
def require(c,code):
    if not c:raise RuntimeError(code)
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",type=Path,required=True);parser.add_argument("--device-id",required=True)
    a=parser.parse_args();fixtures.guard();d=fixtures.read_private(a.fixture)
    report={"schema":"hara.dev-cloud-quota-boundary.v1","started_at":datetime.now(timezone.utc).isoformat(),"environment":"DEV","plan":"DEV_ONE_UNIT","unit_limit":1,
       "scope":"LIVE_QUOTA_CONTRACT_LIMIT_ONE_NOT_10000_COMPLETED_FREE_OPERATIONS","oauth_frontend_exercised":False,"identity_setup":"ISOLATED_QA_D1_SEED",
       "prod_mutated":False,"founder_mutated":False,"secret_output":False,"checks":{}}
    token=quota.load_token(Path(d["canary_token_file"])); reserved=[];all_ids=[]
    original_post=quota.post_json
    def bounded_post(path,token,body):
        if body.get("request_id"):all_ids.append(body["request_id"])
        for attempt in range(2):
            try:return original_post(path,token,body)
            except quota.ProbeError as e:
                if str(e)!="QUOTA_PROBE_NETWORK_ERROR" or attempt:raise
                report.setdefault("network_retries",[]).append({"path":path,"same_request_id":True})
                time.sleep(0.2)
    quota.post_json=bounded_post
    try:
        rows=fixtures.fresh.rows("SELECT e.plan_code,p.unit_limit FROM entitlements e JOIN plans p ON p.plan_code=e.plan_code WHERE e.entitlement_id="+fixtures.fresh.q(d["entitlement_id"])+";")
        require(rows==[{"plan_code":"DEV_ONE_UNIT","unit_limit":1}],"QA_QUOTA_PLAN_DRIFT")
        ids=["HARA-QA-LAST-SLOT-"+secrets.token_hex(12) for _ in range(8)]
        def authorize(rid):return rid,quota.authorize(token,d["external_subject"],rid)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: replies=list(pool.map(authorize,ids))
        allowed=[(rid,x) for rid,x in replies if x.get("allowed") is True]
        denied=[x for rid,x in replies if x.get("allowed") is False]
        reserved=[rid for rid,x in allowed]
        require(len(allowed)==1 and len(denied)==7,"LIVE_LAST_SLOT_CONCURRENCY_INVALID")
        require(all(x.get("code")=="QUOTA_EXCEEDED" for x in denied),"LIVE_LAST_SLOT_DENIAL_CODE_INVALID")
        winner,reserve=allowed[0]
        again=quota.authorize(token,d["external_subject"],winner)
        require(again.get("allowed") is True and (again.get("usage") or {}).get("existing") is True,"LIVE_RESERVE_IDEMPOTENCY_INVALID")
        released=quota.release(token,d["external_subject"],winner);reserved=[]
        require((released.get("usage") or {}).get("state")=="RELEASED","LIVE_RELEASE_INVALID")
        replay=quota.authorize(token,d["external_subject"],winner)
        require(replay.get("allowed") is False and replay.get("code")=="REQUEST_USAGE_TERMINAL","LIVE_RELEASE_REPLAY_INVALID")
        report["checks"]["last_slot_8_concurrent_one_allowed"]="PASS"
        report["checks"]["reserve_idempotency"]="PASS"
        report["checks"]["release_and_terminal_replay"]="PASS"
        report["concurrency"]={"attempts":8,"allowed":1,"quota_denied":7}
        proof=quota.run(token,d["external_subject"],a.device_id,40)
        report["native_windows_quota_proof"]=proof
        report["checks"]["authorize_real_invoke_receipt_commit"]="PASS"
        report["checks"]["idempotent_commit_no_double_charge"]="PASS"
        rid="HARA-QA-OVER-LIMIT-"+secrets.token_hex(12)
        denied=quota.authorize(token,d["external_subject"],rid)
        require(denied.get("allowed") is False and denied.get("code")=="QUOTA_EXCEEDED","LIVE_AFTER_COMMIT_LIMIT_NOT_DENIED")
        require(int((denied.get("usage") or {}).get("consumed_units") or 0)==1,"LIVE_COMMITTED_COUNT_NOT_ONE")
        report["checks"]["over_limit_after_commit"]="PASS"
        report["final_usage"]=denied.get("usage")
        report["state"]="PASS_LIVE_CLOUD_QUOTA_BOUNDARY_NATIVE_RECEIPT"
    except Exception as e:report["state"]="FAIL";report["error"]=str(e)[:180]
    finally:
        for rid in dict.fromkeys(all_ids):
            try:quota.release(token,d["external_subject"],rid)
            except Exception:report["reservation_cleanup_error"]=True
        report["request_ids"]=list(dict.fromkeys(all_ids))
        token=""
        report["completed_at"]=datetime.now(timezone.utc).isoformat()
        out=ROOT/"docs/evidence/commander-full-acceptance-20261012/client-quota/cloud-quota-boundary-live.json"
        out.write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report))
    return 0 if report["state"].startswith("PASS") else 1
if __name__=="__main__":raise SystemExit(main())
