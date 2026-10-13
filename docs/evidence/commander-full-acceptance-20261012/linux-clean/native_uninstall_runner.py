#!/usr/bin/env python3
"""Check real support, uninstall, remote revoke and local cleanup on the QA guest."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
Q=Path("/home/commanderqa");F=Q/"commander-qa"
C=Q/".config/hara-commander/device.env";D=Q/".local/share/hara-commander"
parser=argparse.ArgumentParser();parser.add_argument("--expected-version",default="0.3.43",choices=["0.3.43","0.3.53"]);a=parser.parse_args()
assert os.getuid()==2000 and Path("/etc/hostname").read_text().strip()=="commander-linux-clean"
v=dict(line.split("=",1) for line in C.read_text().splitlines() if "=" in line)
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
assert v["HARA_COMMANDER_URL"]==DEV
keep=F/"unrelated-user-file.txt";keep.write_text("exclusive QA unrelated file must survive\n")
keep_sha=hashlib.sha256(keep.read_bytes()).hexdigest()
result={"schema":"hara.commander-linux-clean-native-uninstall.v1","device_id":v["HARA_DEVICE_ID"],"backend":"remote_DEV_worker","systemctl_backend":"real","private_credentials_exposed":False,"agent_version":a.expected_version}
def clean(text):return text.replace(v["HARA_DEVICE_TOKEN"],"[DEVICE_TOKEN_REDACTED]")
try:
 support=subprocess.run(["bash",str(F/"linux.sh"),"support"],capture_output=True,text=True,timeout=40)
 assert support.returncode==0
 report=json.loads(support.stdout.strip().splitlines()[-1])
 assert report["schema"]=="hara.commander-support-report.v2" and report["privacy"]["secret_material_exposed"] is False
 result["support_schema"]=report["schema"];result["support_privacy_pass"]=True
 uninstall=subprocess.run(["bash",str(F/"linux.sh"),"uninstall"],capture_output=True,text=True,timeout=90)
 text=clean(uninstall.stdout+uninstall.stderr)
 result["uninstall_exit_code"]=uninstall.returncode;result["output"]=text
 assert uninstall.returncode==0 and "HARA_COMMANDER_AGENT_UNINSTALL=PASS" in text and "SERVER_DEVICE_REVOKE=PASS" in text
 checks={
 "config_removed":not C.parent.exists(),"agent_data_removed":not D.exists(),
 "systemd_unit_removed":not (Q/".config/systemd/user/hara-commander-agent.service").exists(),
 "cli_removed":not (Q/".local/bin/hara-commander").exists(),
 "managed_wrapper_removed":not (Q/".local/bin/hara").exists(),
 "unrelated_file_preserved":hashlib.sha256(keep.read_bytes()).hexdigest()==keep_sha,
 "service_inactive":subprocess.run(["systemctl","--user","is-active","--quiet","hara-commander-agent.service"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0,
 }
 result["cleanup_checks"]=checks;assert all(checks.values())
 req=Request(DEV+"/api/device/heartbeat",data=json.dumps({"device_id":v["HARA_DEVICE_ID"],"platform":"LINUX","architecture":"x86_64","agent_version":a.expected_version}).encode(),method="POST",headers={"authorization":"Bearer "+v["HARA_DEVICE_TOKEN"],"content-type":"application/json","user-agent":"HARA-Commander-LinuxClean-DEV/1"})
 try:
  with urlopen(req,timeout=20) as response:status=response.status
 except HTTPError as error:status=error.code
 result["revoked_credential_http_status"]=status;assert status in (401,403)
 result["state"]="PASS_NATIVE_LINUX_UNINSTALL_REVOKE_CLEANUP"
except Exception as error:
 result.update(state="FAIL_NATIVE_LINUX_UNINSTALL_REVOKE_CLEANUP",error_type=type(error).__name__)
print(json.dumps(result))
raise SystemExit(0 if result["state"].startswith("PASS") else 1)
