import importlib.util,json,subprocess,xml.etree.ElementTree as ET
VM="hara-win51-clean-20261012-r1";UUID="d35599c8-b9ea-45e5-9ae9-fa047e84b8ba";MAC="52:54:00:53:12:01"
def v(*args):
 r=subprocess.run(["virsh","--connect","qemu:///system",*args],check=True,text=True,capture_output=True,timeout=25);return r.stdout
x=ET.fromstring(v("dumpxml",VM))
assert x.findtext("uuid")==UUID,"CLONE_UUID_REQUIRED"
assert not x.findall("./devices/interface"),"CLONE_INTERFACE_COLLISION"
s=importlib.util.spec_from_file_location("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q=importlib.util.module_from_spec(s);s.loader.exec_module(q);q.VM=VM
code,out,err=q.powershell(r"""$ErrorActionPreference='Stop';$proof=Get-Content -LiteralPath 'C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1\sanitized-before-network.json' -Raw|ConvertFrom-Json;if($proof.state -cne 'PASS_CLONE_SANITIZED_BEFORE_NETWORK'){throw 'SANITIZATION_REQUIRED'};$cs=Get-CimInstance Win32_ComputerSystem;if($cs.UserName -notmatch '\\HARAQA$'){throw 'QA_INTERACTIVE_REQUIRED'};if(Test-Path 'C:\Users\HARAQA\AppData\Local\HARA Commander'){throw 'QA_COMMANDER_ROOT_COLLISION'};if(Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue){throw 'COMMANDER_TASK_COLLISION'};if(@(Get-CimInstance Win32_UserProfile|Where-Object{-not $_.Special}).Count -ne 1){throw 'ONLY_QA_PROFILE_REQUIRED'};'QA_CLEAN_NETWORK_GATE_PASS'""",wait=25)
assert code==0 and "QA_CLEAN_NETWORK_GATE_PASS" in out,(code,err[:300])
assert "<name>commander-win11</name>" in v("dumpxml","commander-win11"),"SOURCE_REQUIRED"
v("attach-interface",VM,"--type","network","--source","default","--model","e1000e","--mac",MAC,"--live","--config")
y=ET.fromstring(v("dumpxml",VM)); interfaces=y.findall("./devices/interface");assert len(interfaces)==1 and interfaces[0].find("mac").get("address")==MAC,"UNIQUE_CLONE_NIC_REQUIRED"
print(json.dumps({"schema":"hara.windows-clean-clone-network.v1","state":"PASS_SANITIZED_CLONE_NETWORK_ATTACHED","clone_uuid":UUID,"clone_name":VM,"unique_mac":MAC,"network":"default","mode":"NAT","sanitization_verified_before_network":True,"qa_profile_verified_clean":True,"source_running":v("domstate","commander-win11").strip()=="running","source_modified":False,"founder_identity_used":False}))
