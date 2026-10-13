import importlib.util,json,pathlib
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
q=mod("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q.VM="hara-win51-clean-20261012-r1"
b=mod("b","/tmp_hara/windows_clean_qga_bridge.py")
guest=b.CLEAN+chr(92)+"private-053-rc-r2"
script="$ErrorActionPreference='Stop';if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'};foreach($n in @('agent','install','release')){New-Item -ItemType Directory -Path (Join-Path '"+guest+"' $n) -Force|Out-Null};'CLONE_PRIVATE_SIGNED_STAGE_CREATED'"
code,out,err=q.powershell(script,wait=20)
assert code==0 and "CLONE_PRIVATE_SIGNED_STAGE_CREATED" in out,"CLONE_DIRECTORY_STAGE_FAILED"
result=[]
for name in ("agent/windows.ps1","install/windows.ps1","release/agent-manifest.json","release/agent-manifest.sig.json"):
 result.append(b.stage(b.CLONE,"/tmp_hara/commander-windows-clean-20261012-r1/signed-053-r2/"+name,guest+chr(92)+name.replace("/",chr(92))))
name="windows_clean_native_crypto_053_r2.ps1"
result.append(b.stage(b.CLONE,"/tmp_hara/"+name,b.CLEAN+chr(92)+name))
print(json.dumps(result));print(json.dumps(b.execute(b.CLONE,b.CLEAN+chr(92)+name)))
