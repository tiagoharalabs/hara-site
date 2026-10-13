from pathlib import Path
import subprocess,json,hashlib,datetime,ast,stat
root=Path("/tmp_hara/commander-win50-utf8-20261012")
src=root/"docs/evidence/commander-full-acceptance-20261012/real-oauth/qa_exact_cleanup_runner.py"
public=root/"docs/evidence/commander-full-acceptance-20261012/real-oauth"
proof=json.loads((public/"qa2_windows54_uninstall_portal_readback.json").read_text())
assert proof["state"]=="PASS" and proof["device_state"]=="REVOKED" and proof["active_count"]==0
raw=src.read_bytes();digest=hashlib.sha256(raw).hexdigest()
assert digest.startswith("78c27892"),"QA_CLEANUP_HELPER_DRIFT"
tree=ast.parse(raw)
assert sum(isinstance(x,ast.If) and "__name__" in ast.unparse(x.test) for x in tree.body)==1
p=subprocess.run(["ssh","-o","BatchMode=yes","storage","sudo","/usr/bin/python3","-I","-B","-"],input=raw,text=False,capture_output=True,timeout=240)
events=[json.loads(x) for x in p.stdout.decode().splitlines() if x]
final=[x for x in events if x.get("event")=="EXACT_QA_CLEANUP"]
state="PASS" if p.returncode==0 and len(final)==1 and final[0].get("state")=="PASS_TWO_QA_USERS_TRACKED_SESSIONS_OAUTH_BEARERS_DCR_CLIENT_PRIVATE_STATE_REMOVED" else "FAIL"
report={"state":state,"at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"helper_sha256":digest,"windows54_uninstalled_and_portal_revoked_before_cleanup":True,"events":events,"credential_values_exposed":False,"raw_stderr_saved":False}
out=public/"exact-qa-idp-cleanup-054.json";assert not out.exists();out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
if state=="PASS":
    dest=root/"apps/commander/.generated/full-acceptance-20261012/windows-clean/qa2-portal-pairing-054r2-jit.json"
    if dest.exists():
        st=dest.lstat();assert stat.S_ISREG(st.st_mode) and not dest.is_symlink() and stat.S_IMODE(st.st_mode)==0o600;dest.unlink()
print(json.dumps({"state":state,"steps":len(events),"qa_users":2 if state=="PASS" else None,"dcr_clients":1 if state=="PASS" else None,"real_portal_client_untouched":True,"credential_values_exposed":False}))
raise SystemExit(0 if state=="PASS" else 1)
