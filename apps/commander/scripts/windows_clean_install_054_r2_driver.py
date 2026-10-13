import argparse,hashlib,json,stat,subprocess,urllib.request,shlex
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--pairing-file",required=True);a=p.parse_args()
src=Path(a.pairing_file);allowed=Path("/tmp_hara/commander-win50-utf8-20261012/apps/commander/.generated/full-acceptance-20261012/windows-clean")
assert src.parent==allowed and not src.is_symlink() and stat.S_IMODE(src.stat().st_mode)==0o600,"PRIVATE_NORMAL_PAIRING_FILE_REQUIRED"
dev="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
for route,pin in (("/release/agent-manifest.json","e1c7c23de1b4313093e2d8c52be1ec52f6419f72d5ef59d675c7e5a279b1a13d"),("/install/windows.ps1","ea9f046bebf9ed85feefae05590ac915a75e9b491aefe1833d40bf316d414cc7")):
 response=subprocess.run(["curl","--fail","--silent","--show-error","--max-time","30",dev+route],check=True,capture_output=True,timeout=35)
 raw=response.stdout;assert len(raw)<131072,"PUBLIC_ASSET_BOUND_REQUIRED"
 assert hashlib.sha256(raw).hexdigest()==pin,"FINAL_054_NORMAL_HTTPS_READBACK_REQUIRED"
fixture=json.loads(src.read_text());assert fixture["dev_origin"]==dev and fixture["pairing_token"],"NORMAL_QA_PAIRING_REQUIRED";fixture=None
remote="/tmp_hara/commander-windows-clean-20261012-r1/phase-054-private.json"
subprocess.run(["scp","-q",str(src),"nucleo-a:"+remote],check=True,timeout=30)
code='import importlib.util,json,os,stat;s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b);p="'+remote+'";os.chmod(p,0o600);assert stat.S_IMODE(os.stat(p).st_mode)==0o600;b.stage(b.CLONE,p,b.CLEAN+chr(92)+"phase-054-private.json");r=b.execute(b.CLONE,b.CLEAN+chr(92)+"windows_clean_native_install_054_r2.ps1");print(json.dumps({"state":"NORMAL_QA2_054_INSTALL_LAUNCHED","guest_pid":r["pid"],"secret_material_printed":False}))'
subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a","python3 -I -B -c "+shlex.quote(code)],check=True,timeout=60)