import importlib.util,json,hashlib
from pathlib import Path
s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
s=importlib.util.spec_from_file_location("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q=importlib.util.module_from_spec(s);s.loader.exec_module(q);q.VM=b.CLONE
ps=r"$ErrorActionPreference='Stop';if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'QA_UUID_REQUIRED'};$root='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1\private-054-rc-r1';foreach($d in @('agent','install','release')){New-Item -Path (Join-Path $root $d) -ItemType Directory -Force|Out-Null};[ordered]@{state='QA_PUBLIC_STAGE_DIRECTORY_READY'}|ConvertTo-Json -Compress"
rc,out,err=q.powershell(ps,wait=25);assert rc==0 and not err,"STAGE_DIRECTORY_FAILED"
root=Path("/tmp_hara/commander-windows-clean-20261012-r1/windows-clean-054-public-stage")
pins={"agent/windows.ps1":"fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62","install/windows.ps1":"ea9f046bebf9ed85feefae05590ac915a75e9b491aefe1833d40bf316d414cc7","release/agent-manifest.json":"ff88de00063b45bb38cf872d73cb70ba6cdb036a2a883afcbf6eb4057ad522d3","release/agent-manifest.sig.json":"5710137656fbdaeabb814c68559102b71f15e512be2eafbd39274fa836bfd43d"}
records=[]
for rel,pin in pins.items():
 p=root/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==pin,"PUBLIC_STAGE_PIN_MISMATCH"
 records.append(b.stage(b.CLONE,str(p),b.CLEAN+chr(92)+"private-054-rc-r1"+chr(92)+rel.replace("/",chr(92))))
for name in ("windows_clean_native_crypto_054_r1.ps1","windows_clean_native_install_054_r1.ps1","windows54_signed_runtime_regression.ps1"):
 p=Path("/tmp_hara/commander-windows-clean-20261012-r1")/name
 records.append(b.stage(b.CLONE,str(p),b.CLEAN+chr(92)+name))
print(json.dumps({"state":"PUBLIC_054_AND_ACCEPTANCE_FIXTURES_STAGED","files":records,"signed_sources_modified":False}))
print(json.dumps({"crypto_pid":b.execute(b.CLONE,b.CLEAN+chr(92)+"windows_clean_native_crypto_054_r1.ps1")["pid"]}))
print(json.dumps({"runtime_regression_pid":b.execute(b.CLONE,b.CLEAN+chr(92)+"windows54_signed_runtime_regression.ps1")["pid"]}))
