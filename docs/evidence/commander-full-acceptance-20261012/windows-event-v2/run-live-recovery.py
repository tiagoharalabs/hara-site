from pathlib import Path
import importlib.util,json,subprocess,time,urllib.request,urllib.error,hashlib
ROOT=Path('/tmp_hara/commander-win50-utf8-20261012');E=ROOT/'docs/evidence/commander-full-acceptance-20261012/windows-event-v2'
fx=json.loads((ROOT/'apps/commander/.generated/full-acceptance-20261012/windows-event-20261012234230-f2551e72.json').read_text())
proof=json.loads((E/'live-integrated-result.json').read_text());device=proof['device_id'];origin=fx['dev_origin']
sp=importlib.util.spec_from_file_location('probe',ROOT/'apps/commander/scripts/commander_event_v2_transient_live_probe.py');t=importlib.util.module_from_spec(sp);sp.loader.exec_module(t);token=t.load_token(Path(fx['canary_token_file']))
report={'schema':'hara.commander.windows.event-v2-live-recovery.v1','device_id':device,'founder_runtime_mutated':False,'checks':[]}
def save(): (E/'live-recovery-result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,fn):
 try:v=fn();report['checks'].append({'name':name,'passed':True,'evidence':v})
 except Exception as exc:report['checks'].append({'name':name,'passed':False,'error_type':type(exc).__name__,'error_code':str(exc)[:160]})
 save()
 if not report['checks'][-1]['passed']:raise RuntimeError(name+' failed; sanitized evidence')
def qga(phase):
 p=subprocess.run(['ssh','-o','BatchMode=yes','nucleo-a','python3','/tmp_hara/run-live-event-v2-qga.py',phase],capture_output=True,text=True,timeout=55)
 if p.returncode:raise RuntimeError('QGA_'+phase.upper()+'_FAILED')
 return json.loads(p.stdout)
def stop():
 r=qga('stop');assert r['exit_code']==0 and not r['stderr_present'] and r['event_status']['connected'] is False
 return r
def wait_connected():
 end=time.monotonic()+20
 while time.monotonic()<end:
  r=qga('status')
  if r['event_status'].get('connected') and not r['process_exited'] and not r['stderr_present']:return r
  time.sleep(.5)
 raise RuntimeError('RESTART_CONNECTION_TIMEOUT')
def replay():
 r=t.post_json('/api/internal/device/transient-call',token,{'issuer':t.DEV_ISSUER,'subject':fx['external_subject'],'tool_id':'hara.functions.invoke','request_id':proof['invoke_request_id'],'device_id':device,'payload':{'function_id':'device.info','arguments':{'argv':[]}}})
 t.require_transient_common(r);assert r['state']=='COMPLETED' and r['execution_mode']=='REPLAY_ONLY' and r['receipt_sha256']==proof['receipt_sha256'] and r['learning_signal']['outcome']=='REPLAYED'
 return {'state':r['state'],'execution_mode':r['execution_mode'],'receipt_sha256':r['receipt_sha256'],'learning_outcome':r['learning_signal']['outcome'],'quota_state':r['usage']['state'],'device_id':r['device_id']}
check('graceful_disconnect_before_restart',stop)
check('restart_owned_qa_runtime',lambda:qga('start'))
check('wss_reconnect_same_dpapi_identity',wait_connected)
check('persistent_replay_same_receipt_after_restart',replay)
check('final_graceful_shutdown',stop)
report['passed']=sum(x['passed'] for x in report['checks']);report['failed']=sum(not x['passed'] for x in report['checks']);save()
print(json.dumps({'state':'PASS','device_id':device,'passed':report['passed'],'failed':report['failed']}))
