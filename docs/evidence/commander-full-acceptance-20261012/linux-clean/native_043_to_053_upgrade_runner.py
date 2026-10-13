#!/usr/bin/env python3
"""Actual installed 0.3.43 -> signed 0.3.53 update and owned wrapper migration."""
import hashlib,json,os,stat,subprocess
from pathlib import Path
Q=Path("/home/commanderqa");F=Q/"commander-qa";D=Q/".local/share/hara-commander";A=D/"hara-commander-agent";C=Q/".config/hara-commander/device.env"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
OLD="3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7"
NEW="db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e"
INSTALL="dae0a39f12a02920261a8051834d5b8426866a07e8a0d0acb9676c6605c8e3f8"
LEGACY="f2e30d042dd00e894c5916afb81ed193ff46f0949bd048a98c3c51722e42acaf"
assert os.getuid()==2000 and Path("/etc/hostname").read_text().strip()=="commander-linux-clean"
v=dict(line.split("=",1) for line in C.read_text().splitlines() if "=" in line);assert v["HARA_COMMANDER_URL"]==DEV and v["HARA_COMMANDER_APPROVAL_MODE"]=="ASK_EVERY_ACTION"
before_config=C.read_bytes();old_started=json.loads((D/"runtime-status.json").read_text())["started_at_utc"]
assert hashlib.sha256(A.read_bytes()).hexdigest()==OLD
assert subprocess.check_output(["python3",str(A),"--version"],text=True).strip()=="0.3.43"
wrapper=Q/".local/bin/hara";old_wrapper_inode=wrapper.stat().st_ino;assert not wrapper.is_symlink() and hashlib.sha256(wrapper.read_bytes()).hexdigest()==LEGACY
result={"schema":"hara.commander-linux-clean-native-upgrade-043-053.v1","backend":"remote_DEV_worker","systemctl_backend":"real","device_id":v["HARA_DEVICE_ID"],"prior_version":"0.3.43","target_version":"0.3.53","old_wrapper_manually_changed":False,"customer_secrets_exposed":False}
try:
 tmp=F/"linux-053-download.sh"
 p=subprocess.run(["curl","-fsS","--max-time","30",DEV+"/install/linux.sh","-o",str(tmp)],capture_output=True,timeout=40)
 assert p.returncode==0 and hashlib.sha256(tmp.read_bytes()).hexdigest()==INSTALL,"SIGNED_053_INSTALLER_DOWNLOAD_OR_PIN"
 original=F/"linux-043-original.sh"
 if not original.exists():(F/"linux.sh").rename(original)
 tmp.replace(F/"linux.sh")
 p=subprocess.run(["bash",str(F/"linux.sh"),"update"],capture_output=True,text=True,timeout=150)
 text=(p.stdout+p.stderr).replace(v["HARA_DEVICE_TOKEN"],"[DEVICE_TOKEN_REDACTED]")
 result.update(update_exit_code=p.returncode,output=text)
 assert p.returncode==0 and "HARA_COMMANDER_AGENT_UPDATE=PASS" in text
 assert "HARA_COMMANDER_CLI_WRAPPER_STATE=LEGACY_MIGRATED" in text
 assert hashlib.sha256(A.read_bytes()).hexdigest()==NEW and subprocess.check_output(["python3",str(A),"--version"],text=True).strip()=="0.3.53"
 assert C.read_bytes()==before_config
 assert b"# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\n" in wrapper.read_bytes()
 snapshot=D/"installer-preimages"/("hara-wrapper-"+LEGACY+".preimage")
 assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==LEGACY and stat.S_IMODE(snapshot.stat().st_mode)==0o600 and snapshot.stat().st_uid==os.getuid()
 assert snapshot.stat().st_ino==old_wrapper_inode
 metadata=json.loads(snapshot.with_suffix(".json").read_text())
 assert metadata["schema"]=="hara.commander-owned-cli-preimage.v2" and metadata["displaced_inode"]==old_wrapper_inode
 runtime=json.loads((D/"runtime-status.json").read_text())
 assert runtime["agent_version"]=="0.3.53" and runtime["started_at_utc"]!=old_started
 active=subprocess.run(["systemctl","--user","is-active","--quiet","hara-commander-agent.service"],capture_output=True).returncode==0
 enabled=subprocess.run(["systemctl","--user","is-enabled","--quiet","hara-commander-agent.service"],capture_output=True).returncode==0
 assert active and not enabled
 result.update(state="PASS_NATIVE_043_TO_SIGNED_053_LEGACY_MIGRATION",new_agent_sha256=NEW,signed_installer_sha256=INSTALL,legacy_preimage_sha256=LEGACY,preimage_mode="0600",preimage_owner_uid=os.getuid(),legacy_actual_inode_preserved=True,source_version_attested=True,device_credentials_preserved=True,manual_boot_policy_preserved=True)
except Exception as error:
 result.update(state="FAIL_NATIVE_043_TO_SIGNED_053_LEGACY_MIGRATION",error_type=type(error).__name__,error_code=str(error) if isinstance(error,AssertionError) else "NATIVE_UPGRADE_PHASE_FAILED")
print(json.dumps(result))
raise SystemExit(0 if result["state"].startswith("PASS") else 1)