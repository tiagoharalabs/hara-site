#!/usr/bin/env python3
"""Native wrapper/Agent setter tests in private HOME/XDG; no authority route."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[5]
BASELINE=HERE/"linux-install-053-baseline.sh"
CANDIDATE=HERE/"linux-install-wrapper-054-candidate.sh"
CAPDIR=HERE.parent/"managed-cap-candidate"
SIGNED53=CAPDIR/"linux-053-baseline.py"
CAPCANDIDATE=CAPDIR/"linux-managed-cap-candidate.py"
checks=[]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check(name,ok):
    assert ok,name
    checks.append(name)
def helper(path):
    code=Path(path).read_text().split("<<'PYHARAWRAPPER'\n",1)[1].split("\nPYHARAWRAPPER",1)[0]
    ns={"__name__":"private_native_wrapper_unit"}
    exec(compile(code,"installer-helper","exec"),ns)
    return ns
def call_helper(ns,mode,path,preimages):
    with contextlib.redirect_stdout(io.StringIO()):return ns["manage"](mode,path,preimages)
def environment(home):
    return {"HOME":str(home),"XDG_CONFIG_HOME":str(home/"cfg"),"XDG_DATA_HOME":str(home/"data"),"LANG":"C.UTF-8","PATH":"/usr/bin:/bin"}
def run(wrapper,args,env):
    # Args remain a subprocess vector, never an assembled shell command.
    return subprocess.run([str(wrapper),*args],env=env,text=True,encoding="utf-8",capture_output=True,timeout=5,check=False)
def private_home(root,name):
    home=root/name;home.mkdir(mode=0o700)
    (home/".local/bin").mkdir(parents=True,mode=0o700)
    (home/"cfg/hara-commander").mkdir(parents=True,mode=0o700)
    (home/"data/hara-commander").mkdir(parents=True,mode=0o700)
    return home
def write_wrapper(path,body):
    path.write_bytes(body);path.chmod(0o700)
def load_agent(path,env):
    original={key:os.environ.get(key) for key in ("HOME","XDG_CONFIG_HOME","XDG_DATA_HOME")}
    try:
        for key in original:os.environ[key]=env[key]
        spec=importlib.util.spec_from_file_location("wrapper_agent_unit_"+path.parent.name,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    finally:
        for key,value in original.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    return module

def main():
    check("baseline-installer-source-pin",sha(BASELINE)=="7600f844c24696c7d2e0113328fb39425fa3182ae4e93ab8573d7ce4b74926a2")
    check("candidate-installer-source-pin",sha(CANDIDATE)=="495069185d82d888cf53e1db156b60a264ec0fbfd7caf5b243e307bb07398cf0")
    old=helper(BASELINE);new=helper(CANDIDATE)
    check("historical-managed53-pin",new["MANAGED53_BODY"]==old["MANAGED_BODY"] and new["MANAGED53_SHA256"]==old["MANAGED_SHA256"]=="c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953")
    check("signed-agent53-pin",sha(SIGNED53)=="db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e")
    check("cap-candidate-source-pin",sha(CAPCANDIDATE)=="bbac34bc7e48d68a31f478e2c062905f30d4a7c486aada20e6f0e452e62ae71b")
    agent_results=[]
    with tempfile.TemporaryDirectory(prefix="hara-wrapper54-private-unit-",dir="/tmp") as tmp:
        root=Path(tmp);root.chmod(0o700)
        home=private_home(root,"argv-sink")
        env=environment(home);out=home/"sink-argv.json";env["QA_ARGV_OUTPUT"]=str(out)
        sink=home/"argv_sink.py"
        sink.write_text('import json,os,sys\nfrom pathlib import Path\nPath(os.environ["QA_ARGV_OUTPUT"]).write_text(json.dumps(sys.argv[1:],ensure_ascii=False))\n')
        entry=home/".local/bin/hara-commander"
        entry.write_text('#!/bin/sh\nset -eu\nexec /usr/bin/python3 -I -B "$HOME/argv_sink.py" "$@"\n');entry.chmod(0o700)
        wrapper=home/".local/bin/hara"
        write_wrapper(wrapper,old["MANAGED_BODY"])
        baseline=run(wrapper,["commander","approval-mode","session"],env)
        check("baseline-managed53-drops-second-argument",baseline.returncode==0 and json.loads(out.read_text())==["approval-mode"])
        write_wrapper(wrapper,new["MANAGED_BODY"])
        for label,arguments,wanted in [
            ("forward-mode-value",["commander","approval-mode","session"],["approval-mode","session"]),
            ("default-status-only-when-no-args",["commander"],["status"]),
            ("explicit-empty-first-argument-preserved",["commander",""],[""]),
            ("spaces-and-empty-remaining-args",["commander","space command","two  spaces",""],["space command","two  spaces",""]),
            ("unicode-argv-preserved",["commander","ação","日本","🚗"],["ação","日本","🚗"]),
            ("empty-command-with-more-args-preserved",["commander","","session"],["","session"]),
        ]:
            result=run(wrapper,arguments,env)
            check("sink-"+label,result.returncode==0 and json.loads(out.read_text())==wanted)
        for arguments in ([],["different","approval-mode","session"]):
            out.unlink()
            result=run(wrapper,arguments,env)
            check("sink-invalid-prefix-refused-"+str(len(arguments)),result.returncode==64 and not out.exists())
            out.write_text("[]")
        # Only known getter/setter commands run the real copied Agent.
        # Session status is deliberately omitted: that Agent path invokes systemctl.
        for label,source in (("signed53",SIGNED53),("capcandidate",CAPCANDIDATE)):
            home=private_home(root,"real-agent-"+label);env=environment(home)
            agent=home/"agent.py";shutil.copyfile(source,agent);agent.chmod(0o600)
            cfg=home/"cfg/hara-commander/device.env"
            cfg.write_text("HARA_COMMANDER_URL=https://example.invalid\nHARA_DEVICE_ID=QA-UNIT-WRAPPER54\nHARA_DEVICE_TOKEN=UNIT_NON_CREDENTIAL_PLACEHOLDER\nHARA_DEVICE_ARCH=linux-x86_64\nHARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION\n")
            cfg.chmod(0o600)
            entry=home/".local/bin/hara-commander"
            entry.write_text('#!/bin/sh\nset -eu\nexec /usr/bin/python3 -I -B "$HOME/agent.py" "$@"\n');entry.chmod(0o700)
            wrapper=home/".local/bin/hara";write_wrapper(wrapper,old["MANAGED_BODY"])
            first=run(wrapper,["commander","approval-mode","session"],env)
            check(label+"-baseline-real-agent-remains-ASK",first.returncode==0 and first.stdout.strip()=="HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION" and "HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION" in cfg.read_text())
            old_inode=wrapper.stat().st_ino
            state=call_helper(new,"install",wrapper,home/"data/hara-commander/installer-preimages")
            preimage=home/"data/hara-commander/installer-preimages"/("hara-wrapper-"+new["MANAGED53_SHA256"]+".preimage")
            check(label+"-known-managed53-migrates-actual-inode",state=="MANAGED53_MIGRATED" and preimage.stat().st_ino==old_inode and preimage.read_bytes()==old["MANAGED_BODY"] and stat.S_IMODE(preimage.stat().st_mode)==0o600)
            updated=run(wrapper,["commander","approval-mode","session"],env)
            check(label+"-candidate-real-agent-sets-SESSION",updated.returncode==0 and updated.stdout.strip()=="HARA_COMMANDER_APPROVAL_MODE=SESSION_TRUSTED" and "HARA_COMMANDER_APPROVAL_MODE=SESSION_TRUSTED" in cfg.read_text() and stat.S_IMODE(cfg.stat().st_mode)==0o600)
            getter=run(wrapper,["commander","approval-mode"],env)
            check(label+"-real-mode-getter-confirms-SESSION",getter.returncode==0 and getter.stdout.strip()=="HARA_COMMANDER_APPROVAL_MODE=SESSION_TRUSTED")
            module=load_agent(agent,env)
            check(label+"-TTL-remains43200",module.SESSION_MAX_SECONDS==43200)
            # Private native-function fixture binds the actual live test PID.
            # It is not a product CLI operator session or an ASK approval.
            session={"schema":"hara.commander-operator-session.v1","owner_pid":os.getpid(),"owner_start_marker":module._pid_start_marker(os.getpid()),"approval_mode":"SESSION_TRUSTED","started_at_epoch":time.time()}
            module.SESSION_FILE.write_text(json.dumps(session));module.SESSION_FILE.chmod(0o600)
            check(label+"-fresh-native-session-fixture-readable",module.read_operator_session()==session)
            session["started_at_epoch"]=time.time()-43201
            module.SESSION_FILE.write_text(json.dumps(session))
            check(label+"-native-session-fixture-expires-after12h",module.read_operator_session() is None)
            module.SESSION_FILE.unlink()
            restored=run(wrapper,["commander","approval-mode","ask"],env)
            check(label+"-real-mode-restored-ASK",restored.returncode==0 and restored.stdout.strip()=="HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION" and "HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION" in cfg.read_text())
            final=call_helper(new,"uninstall",wrapper,preimage.parent)
            check(label+"-owned-wrapper-uninstall-and-preimage-retained",final=="MANAGED_REMOVED" and not wrapper.exists() and preimage.stat().st_ino==old_inode and preimage.read_bytes()==old["MANAGED_BODY"])
            agent_results.append({"label":label,"agent_sha256":sha(agent),"baseline_mode":"ASK_EVERY_ACTION","candidate_mode":"SESSION_TRUSTED","final_mode":"ASK_EVERY_ACTION","session_max_seconds":module.SESSION_MAX_SECONDS})
    report={"schema":"hara.commander-wrapper54-native-units.v1","state":"PASS","scope":"UNIT_PRIVATE_HOME_XDG_REAL_WRAPPER_AND_REAL_AGENT_GETTER_SETTER_NO_EXTERNAL_ACCEPTANCE","checks":len(checks),"scenarios":checks,"agents":agent_results,"installer_sha256":sha(CANDIDATE),"managed_wrapper53_sha256":new["MANAGED53_SHA256"],"managed_wrapper54_sha256":new["MANAGED_SHA256"],"network_operations":0,"systemctl_operations":0,"agent_service_start_stop_operations":0,"vm_operations":0,"backend_mock_used":False,"systemctl_shim_used":False,"product_operator_session_created":False,"ask_response_created":False,"native_session_fixture_only":True}
    (HERE/"wrapper54-private-native-result.json").write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,sort_keys=True,ensure_ascii=False))
if __name__=="__main__":main()
