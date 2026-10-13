from pathlib import Path
import importlib.util,json,urllib.request,urllib.error,subprocess,uuid,time
ROOT=Path('/tmp_hara/commander-win50-utf8-20261012')
EVIDENCE=ROOT/'docs/evidence/commander-full-acceptance-20261012/windows-event-v2'
FIXTURE=ROOT/'apps/commander/.generated/full-acceptance-20261012/windows-event-20261012234230-f2551e72.json'
fx=json.loads(FIXTURE.read_text());origin=fx['dev_origin']
assert origin=='https://hara-commander-dev-v2.tiago-sartori.workers.dev'
device=json.loads((EVIDENCE/'live-enrollment-result.json').read_text())['device_id']
def load(name):
 p=ROOT/'apps/commander/scripts'/name;spec=importlib.util.spec_from_file_location(name[:-3],p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
wake=load('commander_event_v2_dev_wake_probe.py')
transient=load('commander_event_v2_transient_live_probe.py')
token=wake.load_token(Path(fx['canary_token_file']))
report={'schema':'hara.commander.windows.event-v2-live-dev.v1','origin':origin,'device_id':device,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'founder_runtime_mutated':False,'founder_credentials_used':False,'portal_oauth_login_real':False,'portal_session_qa_preseed':True,'windows_runtime':'PowerShell 5.1/CLR4','checks':[]}
def checkpoint(): (EVIDENCE/'live-integrated-result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,action):
 try:
  value=action();report['checks'].append({'name':name,'passed':True,'evidence':value})
 except Exception as e:
  report['checks'].append({'name':name,'passed':False,'error_type':type(e).__name__,'error_code':str(e)[:160]})
 checkpoint()
 if not report['checks'][-1]['passed']:raise RuntimeError(name+' failed; see sanitized evidence')
def qga(phase):
 p=subprocess.run(['ssh','-o','BatchMode=yes','nucleo-a','python3','/tmp_hara/run-live-event-v2-qga.py',phase],capture_output=True,text=True,timeout=55)
 if p.returncode:raise RuntimeError('QGA_'+phase.upper()+'_FAILED')
 return json.loads(p.stdout)
def status():
 x=qga('status');assert not x['process_exited'] and not x['stderr_present'] and x['event_status']['connected'];return x
def select():
 req=urllib.request.Request(origin+'/api/portal/devices/select',data=json.dumps({'device_id':device}).encode(),method='POST',headers={'Content-Type':'application/json','Cookie':'hara_commander_session='+fx['session_cookie'],'Origin':origin,'Referer':origin+'/'})
 try:
  with urllib.request.urlopen(req,timeout=20) as resp:data=json.load(resp);code=resp.status
 except urllib.error.HTTPError as e:
  try:body=json.load(e)
  except Exception:body={}
  raise RuntimeError('SELECT_HTTP_'+str(e.code)+'_'+str(body.get('code','UNKNOWN'))) from None
 return {'http_status':code,'selection_api':'/api/portal/devices/select','response_state':data.get('state'),'selected_device_id':data.get('device_id')}
check('native_wss_connected',status)
try:report['portal_selection_observation']={'state':'PASS','evidence':select()}
except Exception as exc:report['portal_selection_observation']={'state':'UNRESOLVED','error_code':str(exc)}
# Select the owned fixture explicitly through the normal DEV transient API.
post_transient=transient.post_json
def scoped_post(path,cred,body):
 if path=='/api/internal/device/transient-call':body=dict(body,device_id=device)
 return post_transient(path,cred,body)
transient.post_json=scoped_post
checkpoint()
check('durable_wake_health',lambda:wake.run_probe(token,fx['external_subject'],device,30))
def triplet():
 result=transient.run(token,fx['external_subject'],device,30)
 report['invoke_request_id']=result.get('request_id');report['receipt_sha256']=result.get('receipt_sha256')
 return result
check('transient_health_device_info_replay_and_quota',triplet)
check('native_wss_still_connected_after_calls',status)
report['passed']=sum(x['passed'] for x in report['checks']);report['failed']=sum(not x['passed'] for x in report['checks']);checkpoint()
print(json.dumps({'state':'PASS','device_id':device,'passed':report['passed'],'failed':report['failed'],'checks':[x['name'] for x in report['checks']]}))
