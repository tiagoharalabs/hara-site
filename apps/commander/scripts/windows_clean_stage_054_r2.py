import importlib.util,json,hashlib
from pathlib import Path
s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
s=importlib.util.spec_from_file_location("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q=importlib.util.module_from_spec(s);s.loader.exec_module(q);q.VM=b.CLONE
ps=r"$ErrorActionPreference='Stop';if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'QA_UUID_REQUIRED'};$root='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1\private-054-rc-r2';foreach($d in @('agent','install','release')){New-Item -Path (Join-Path $root $d) -ItemType Directory -Force|Out-Null};[ordered]@{state='QA_PUBLIC_STAGE_DIRECTORY_READY'}|ConvertTo-Json -Compress"
rc,out,err=q.powershell(ps,wait=25);assert rc==0 and not err,"STAGE_DIRECTORY_FAILED"
root=Path("/tmp_hara/commander-windows-clean-20261012-r1/windows-clean-054-r2-public-stage")
pins={"agent/windows.ps1":"fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62","install/windows.ps1":"ea9f046bebf9ed85feefae05590ac915a75e9b491aefe1833d40bf316d414cc7","release/agent-manifest.json":"e1c7c23de1b4313093e2d8c52be1ec52f6419f72d5ef59d675c7e5a279b1a13d","release/agent-manifest.sig.json":"530627e5f1fe39d2582f8312fbafb32f219b9cdbdcec8777b5725aaefa73c4e8"}
for rel,pin in pins.items():
 p=root/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==pin,"PUBLIC_STAGE_PIN_MISMATCH"
 b.stage(b.CLONE,str(p),b.CLEAN+chr(92)+"private-054-rc-r2"+chr(92)+rel.replace("/",chr(92)))
for name in ("windows_clean_native_crypto_054_r2.ps1","windows_clean_native_install_054_r2.ps1","windows_clean_minimal_lifecycle_054_r2.ps1"):
 p=Path("/tmp_hara/commander-windows-clean-20261012-r1")/name
 b.stage(b.CLONE,str(p),b.CLEAN+chr(92)+name)
parse=r"""
$ErrorActionPreference='Stop';$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Cases=@()
foreach($Name in @('windows_clean_native_install_054_r2.ps1','windows_clean_minimal_lifecycle_054_r2.ps1','windows_clean_normal_start_054.ps1')){
 $T=$null;$E=$null;$A=[Management.Automation.Language.Parser]::ParseFile((Join-Path $Box $Name),[ref]$T,[ref]$E)
 if(@($E).Count -gt 0){throw 'NATIVE_PARENT_PARSE_FAILED'}
 $Children=@($A.FindAll({param($N) $N -is [Management.Automation.Language.StringConstantExpressionAst] -and [string]$N.StringConstantType -match 'HereString'},$true))
 foreach($Child in $Children){$T=$null;$E=$null;$Parsed=[Management.Automation.Language.Parser]::ParseInput([string]$Child.Value,[ref]$T,[ref]$E);if(@($E).Count -gt 0){throw 'NATIVE_CHILD_PARSE_FAILED'}}
 $Cases+=[ordered]@{file=$Name;parent_pass=$true;children=$Children.Count;child_pass=$true}
}
[ordered]@{state='PASS';schema='hara.windows-clean-native-54-r2-harness-parser.v1';cases=$Cases;source_executed=$false}|ConvertTo-Json -Depth 4 -Compress
"""
rc,out,err=q.powershell(parse,wait=25);assert rc==0 and not err,"NATIVE_HARNESS_PARSE_FAILED";print(out.strip())
print(json.dumps({"state":"PUBLIC_054_R2_FIXTURES_STAGED","crypto_pid":b.execute(b.CLONE,b.CLEAN+chr(92)+"windows_clean_native_crypto_054_r2.ps1")["pid"],"profile_modified":False}))
