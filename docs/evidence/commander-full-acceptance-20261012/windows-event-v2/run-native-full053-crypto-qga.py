from pathlib import Path
import base64,json,importlib.util,hashlib
v=json.loads(Path('/tmp_hara/commander-full053-native-crypto-payload-root-r2.json').read_text())
p=Path('/tmp_hara/commander-win11-qga-readiness-20261011.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='b1aa2855dfffaaa92cc5afa016eab6e19720ac86b0bf283e15fdf7be4dcdb827'
s=importlib.util.spec_from_file_location('q',p);q=importlib.util.module_from_spec(s);s.loader.exec_module(q)
g=r'C:\ProgramData\HaraLabs\CommanderWinLab\20261012\full-053-native-crypto-root-r2'
code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';if(Test-Path '"+g+"'){throw 'CRYPTO_STAGE_EXISTS'};New-Item -ItemType Directory -Path '"+g+"',('"+g+"\\agent'),('"+g+"\\install'),('"+g+"\\release')|Out-Null;'READY'")
assert code==0 and not err
for rel,encoded in v['files'].items():
 b=base64.b64decode(encoded);h=q.guest_call({'execute':'guest-file-open','arguments':{'path':g+'\\'+rel.replace('/','\\'),'mode':'wb'}})
 if isinstance(h,dict):h=h['handle']
 try:
  for i in range(0,len(b),24576):
   part=b[i:i+24576];r=q.guest_call({'execute':'guest-file-write','arguments':{'handle':h,'buf-b64':base64.b64encode(part).decode()}});assert r['count']==len(part)
 finally:q.guest_call({'execute':'guest-file-close','arguments':{'handle':h}})
code,out,err=q.powershell("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';& '"+g+"\\native-full053-signature-selftest.ps1' -BundleRoot '"+g+"'",wait=55)
result={'exit_code':code,'stdout':out,'stderr_present':bool(err)}
if code==0 and not err:
 a=json.loads(out);assert a['state']=='PASS' and a['manifest_sha256']=='d8f6d0165253b13a5efcade628564900f41dfbeacf4a062f61439486fb1ad395';result['native']=a
Path('/tmp_hara/commander-full053-native-crypto-result-root-r2.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
