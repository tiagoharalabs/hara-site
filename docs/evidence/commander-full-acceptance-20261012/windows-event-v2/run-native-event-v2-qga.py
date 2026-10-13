from pathlib import Path
import base64,json,importlib.util,hashlib
payload=json.loads(Path('/tmp_hara/commander-eventv2-native-payload-root-r1.json').read_text())
p=Path('/tmp_hara/commander-win11-qga-readiness-20261011.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='b1aa2855dfffaaa92cc5afa016eab6e19720ac86b0bf283e15fdf7be4dcdb827'
spec=importlib.util.spec_from_file_location('q',p);q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
g=payload['guest_stage']
code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';New-Item -ItemType Directory -Path '"+g+"' -Force|Out-Null;'STAGE_READY'")
assert code==0,(code,err)
for rel,encoded in payload['files'].items():
 b=base64.b64decode(encoded)
 h=q.guest_call({'execute':'guest-file-open','arguments':{'path':g+'\\'+rel,'mode':'wb'}})
 if isinstance(h,dict):h=h['handle']
 try:
  for i in range(0,len(b),24576):
   part=b[i:i+24576];v=q.guest_call({'execute':'guest-file-write','arguments':{'handle':h,'buf-b64':base64.b64encode(part).decode()}});assert v['count']==len(part)
 finally:q.guest_call({'execute':'guest-file-close','arguments':{'handle':h}})
code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';& '"+g+"\\native-event-v2-baseline.ps1' -Stage '"+g+"'",wait=55)
result={'exit_code':code,'stdout':out,'stderr':err}
Path('/tmp_hara/commander-eventv2-native-result-root-r1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=True))
