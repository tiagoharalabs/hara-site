from pathlib import Path
import base64,json,importlib.util,hashlib,sys,time
p=Path('/tmp_hara/commander-win11-qga-readiness-20261011.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='b1aa2855dfffaaa92cc5afa016eab6e19720ac86b0bf283e15fdf7be4dcdb827'
spec=importlib.util.spec_from_file_location('q',p);q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
meta=Path('/tmp_hara/commander-eventv2-live-session-root-r2.json')
g=r'C:\ProgramData\HaraLabs\CommanderWinLab\20261012\event-v2-live-dev-root-r2'
phase=sys.argv[1]
if phase=='stage':
 v=json.loads(Path('/tmp_hara/commander-eventv2-live-payload-root-r2.json').read_text())
 code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';if(Test-Path '"+g+"'){throw 'STAGE_COLLISION'};New-Item -ItemType Directory -Path '"+g+"'|Out-Null;& icacls.exe '"+g+"' /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'|Out-Null;'READY'")
 assert code==0,(code,err)
 fs=v['files'];fs['pairing-fixture.json']=base64.b64encode(Path('/tmp_hara/commander-eventv2-live-pairing-root-r2.json').read_bytes()).decode()
 for rel,encoded in fs.items():
  b=base64.b64decode(encoded);h=q.guest_call({'execute':'guest-file-open','arguments':{'path':g+'\\'+rel,'mode':'wb'}})
  if isinstance(h,dict):h=h['handle']
  try:
   for i in range(0,len(b),24576):
    part=b[i:i+24576];a=q.guest_call({'execute':'guest-file-write','arguments':{'handle':h,'buf-b64':base64.b64encode(part).decode()}});assert a['count']==len(part)
  finally:q.guest_call({'execute':'guest-file-close','arguments':{'handle':h}})
 code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';& '"+g+"\\pair-dev-fixture.ps1' -Stage '"+g+"'",wait=55)
 Path('/tmp_hara/commander-eventv2-live-pairing-root-r2.json').unlink(missing_ok=True)
 assert code==0 and not err,(code,out,bool(err))
 a=json.loads(out);assert a['state']=='PASS';meta.write_text(json.dumps({'stage':g,'device_id':a['device_id']})+'\n');print(json.dumps(a))
elif phase=='start':
 a=json.loads(meta.read_text());v=q.guest_call({'execute':'guest-exec','arguments':{'path':q.EXE,'arg':['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',g+'\\run-event-v2-fixture.ps1'],'capture-output':True}});a['pid']=v['pid'];meta.write_text(json.dumps(a)+'\n');print(json.dumps({'state':'STARTED','device_id':a['device_id'],'fixture_pid':a['pid']}))
elif phase=='status':
 a=json.loads(meta.read_text());v=q.guest_call({'execute':'guest-exec-status','arguments':{'pid':a['pid']}})
 code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$f='"+g+"\\profile\\HARA Commander\\event-v2-status.json';if(Test-Path $f){Get-Content -Raw -LiteralPath $f}else{'{}'}")
 print(json.dumps({'state':'PASS','device_id':a['device_id'],'fixture_pid':a['pid'],'process_exited':bool(v.get('exited')),'exit_code':v.get('exitcode'),'stderr_present':bool(v.get('err-data')),'event_status':json.loads(out or '{}')}))
elif phase=='stop':
 a=json.loads(meta.read_text())
 code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$p=[IO.Pipes.NamedPipeClientStream]::new('.','hara-commander-event-v2-rc-stop',[IO.Pipes.PipeDirection]::Out);try{$p.Connect(1500);'STOP_REQUESTED'}finally{$p.Dispose()}")
 assert code==0,(code,err)
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  v=q.guest_call({'execute':'guest-exec-status','arguments':{'pid':a['pid']}})
  if v.get('exited'):break
  time.sleep(.5)
 assert v.get('exited'), 'FIXTURE_SHUTDOWN_TIMEOUT'
 code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';Get-Content -Raw -LiteralPath '"+g+"\\profile\\HARA Commander\\event-v2-status.json'")
 assert code==0 and not err
 print(json.dumps({'state':'STOPPED','fixture_pid':a['pid'],'exit_code':v.get('exitcode'),'stderr_present':bool(v.get('err-data')),'event_status':json.loads(out)}))
elif phase=='revoke':
 script="$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$root='"+g+"\\profile\\HARA Commander';$path=Join-Path $root 'device.json';$cfg=Get-Content -Raw -LiteralPath $path|ConvertFrom-Json;if($cfg.base_url-ne'https://hara-commander-dev-v2.tiago-sartori.workers.dev'){throw 'DEV_REQUIRED'};$secure=ConvertTo-SecureString $cfg.encrypted_device_token;$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure);try{$token=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr);$r=Invoke-RestMethod -Uri ($cfg.base_url+'/api/device/revoke-self') -Method Post -ContentType 'application/json; charset=utf-8' -Headers @{Accept='application/json';Authorization=('Bearer '+$token)} -Body '{}' -TimeoutSec 15 -MaximumRedirection 0;if(-not$r.ok-or$r.state-ne'REVOKED'-or$r.device_id-ne$cfg.device_id){throw 'REVOKE_INVALID'};Remove-Item -LiteralPath ('"+g+"\\profile') -Recurse -Force;[ordered]@{state=$r.state;device_id=$r.device_id;private_fixture_profile_removed=$true;founder_runtime_mutated=$false}|ConvertTo-Json -Compress}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr);$token=$null;$secure.Dispose()}"
 code,out,err=q.powershell(script,wait=35)
 assert code==0 and not err,(code,bool(err))
 print(out)
else:raise RuntimeError('PHASE_INVALID')
