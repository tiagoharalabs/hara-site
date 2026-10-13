#!/usr/bin/env python3
"""Read only normal QA2 portal metadata after the exact owned Windows54 uninstall."""
from pathlib import Path
import subprocess,json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/qa_normal_device_mcp_v54_combined.py"
EXPECTED="HARA-DEVICE-e55b1d52-f6aa-4c93-873b-f1c12412faf0"
PIN="85c4a94c1f80c4e8a3a9113b21423cb01a8347be4b43c129b43bb61b26686ae6"
def main():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==PIN
    remote="import types,contextlib,io,json,http.cookiejar,urllib.request,sys\nm=types.ModuleType('qa54_portal_uninstall_read');exec("+repr(SOURCE.read_text())+",m.__dict__)\n"
    remote+="b=io.StringIO();expected="+repr(EXPECTED)+"\n"
    remote+="with contextlib.redirect_stdout(b):\n s=m.load();p=s['portal'];assert p['user_id']=='394861028946477060';cf=m.pathlib.Path(p['cookie_file']);m.private_file(cf)\n jar=http.cookiejar.MozillaCookieJar(str(cf));jar.load(ignore_discard=True,ignore_expires=True);opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),m.NoRedirect(),urllib.request.HTTPSHandler(context=m.ssl.create_default_context()))\n c,d,h=m.portal_request(opener,m.DEV+'/api/portal/devices');m.need(c)\n"
    remote+="own=[x for x in d.get('devices',[]) if x.get('device_id')==expected]\n"
    remote+="ok=len(own)==1 and own[0].get('state')=='REVOKED' and own[0].get('online') is False and d.get('active_count')==0 and d.get('online_count')==0\n"
    remote+="print(json.dumps({'state':'PASS' if ok else 'FAIL','http_status':c,'device_id':expected,'device_state':own[0].get('state') if own else None,'online':own[0].get('online') if own else None,'active_count':d.get('active_count'),'online_count':d.get('online_count'),'normal_portal_cookie_used':True,'credential_values_exposed':False}));sys.exit(0 if ok else 1)\n"
    p=subprocess.run(["ssh","-o","BatchMode=yes","storage","sudo","/usr/bin/python3","-I","-B","-"],input=remote,text=True,capture_output=True,timeout=60)
    if not p.stdout:print(json.dumps({"state":"FAIL","safe_code":"QA54_PORTAL_EXECUTOR_FAILED"}));return 1
    report=json.loads(p.stdout);report["at_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
    ev=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/qa2_windows54_uninstall_portal_readback.json"
    assert not ev.exists();ev.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True));return p.returncode
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as e:print(json.dumps({"state":"FAIL","safe_code":type(e).__name__,"credential_values_exposed":False}));raise SystemExit(1)
