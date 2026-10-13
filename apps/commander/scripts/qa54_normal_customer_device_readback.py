#!/usr/bin/env python3
"""Bounded normal QA2 portal selection plus real OAuth customer MCP read proof."""
from pathlib import Path
import argparse,subprocess,json,re,hashlib,datetime,os
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/qa_normal_device_mcp_v54_combined.py"
PROOF=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/normal_signup_windows54_mcp_read_receipt_proof.json"
PIN="85c4a94c1f80c4e8a3a9113b21423cb01a8347be4b43c129b43bb61b26686ae6"
def main():
    a=argparse.ArgumentParser();a.add_argument("--expected-device-id",required=True);args=a.parse_args()
    assert re.fullmatch(r"HARA-DEVICE-[0-9a-f-]{36}",args.expected_device_id),"QA54_EXPECTED_DEVICE"
    assert not PROOF.exists(),"QA54_PROOF_ALREADY_EXISTS"
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==PIN,"QA54_REVIEWED_HELPER_DRIFT"
    source=SOURCE.read_text()
    remote="import io,json,contextlib,types,sys,urllib.request,http.cookiejar\n"
    remote+="m=types.ModuleType('qa54_normal_mcp_helper');exec("+repr(source)+",m.__dict__)\n"
    remote+="expected="+repr(args.expected_device_id)+";events=io.StringIO();proof={};ret=1\n"
    remote+="try:\n"
    remote+=" with contextlib.redirect_stdout(events):\n"
    remote+="  s=m.load();p=s['portal'];assert p['user_id']=='394861028946477060'\n"
    remote+="  cf=m.pathlib.Path(p['cookie_file']);m.private_file(cf);jar=http.cookiejar.MozillaCookieJar(str(cf));jar.load(ignore_discard=True,ignore_expires=True)\n"
    remote+="  opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),m.NoRedirect(),urllib.request.HTTPSHandler(context=m.ssl.create_default_context()))\n"
    remote+="  c,d,h=m.portal_request(opener,m.DEV+'/api/portal/devices');m.need(c);devices=d.get('devices',[])\n"
    remote+="  assert all(x.get('device_id') in {expected,m.PRIOR_DEVICE} for x in devices),'QA54_PORTAL_DEVICE_ISOLATION'\n"
    remote+="  own=[x for x in devices if x.get('device_id')==expected];assert len(own)==1 and own[0].get('state')=='ACTIVE' and own[0].get('online') is True,'QA54_PORTAL_DEVICE_ACTIVE'\n"
    remote+="  req=urllib.request.Request(m.DEV+'/api/portal/devices/select',data=json.dumps({'device_id':expected}).encode(),method='POST',headers={'Origin':m.DEV,'Sec-Fetch-Site':'same-origin','User-Agent':m.UA,'Accept':'application/json','Content-Type':'application/json'})\n"
    remote+="  with opener.open(req,timeout=20) as r: c=r.status;d=json.load(r)\n"
    remote+="  assert c==200 and d.get('selected') is True,'QA54_PORTAL_NORMAL_SELECTION_FAILED'\n"
    remote+="  m.emit('QA54_NORMAL_PORTAL_SELECTION_PASS',http_status=c,device_id=expected,d1_manual_selection=False,credential_values_exposed=False)\n"
    remote+="  sys.argv=['qa54','--expected-device-id',expected,'--expected-version','0.3.54','--computer','HARAQA5312','--phase','WINDOWS54R2'];ret=m.normal_device_read()\n"
    remote+=" proof={'state':'PASS' if ret==0 else 'FAIL','events':[json.loads(x) for x in events.getvalue().splitlines() if x]}\n"
    remote+="except Exception as e:\n"
    remote+=" code=str(e) if isinstance(e,m.SafeFailure) else type(e).__name__;proof={'state':'FAIL','safe_code':code,'events':[json.loads(x) for x in events.getvalue().splitlines() if x]};ret=1\n"
    remote+="print(json.dumps(proof));sys.exit(ret)\n"
    p=subprocess.run(["ssh","-o","BatchMode=yes","storage","sudo","/usr/bin/python3","-I","-B","-"],input=remote,text=True,capture_output=True,timeout=150)
    try:data=json.loads(p.stdout)
    except Exception:print(json.dumps({"state":"FAIL","safe_code":"QA54_EXECUTOR_RESULT_INVALID","credential_values_exposed":False}));return 1
    data.update(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),helper_source_sha256=PIN,normal_qa2_customer_oauth=True,credential_values_exposed=False)
    if p.returncode==0:
        chain=[e for e in data["events"] if e.get("event")=="NORMAL_QA_DEVICE_MCP_CHAIN_PASS"]
        assert len(chain)==1 and chain[0].get("device_id")==args.expected_device_id
        PROOF.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
        print(json.dumps({"state":"PASS","device_id":args.expected_device_id,"receipt_sha256":chain[0]["device_info_receipt_sha256"],"usage_before":chain[0]["usage_before"],"usage_after":chain[0]["usage_after"],"credential_values_exposed":False}));return 0
    failure=PROOF.with_name("windows54-mcp-attempt-failed-"+datetime.datetime.now(datetime.timezone.utc).strftime("%H%M%S")+".json")
    failure.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"state":"FAIL","safe_code":data.get("safe_code","QA54_MCP_PROOF_FAILED"),"credential_values_exposed":False}));return 1
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as e:print(json.dumps({"state":"FAIL","safe_code":type(e).__name__,"credential_values_exposed":False}));raise SystemExit(1)
