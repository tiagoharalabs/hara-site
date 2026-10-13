#!/usr/bin/env python3
"""File staging and bounded execution for the isolated Windows acceptance lane."""
import argparse, base64, hashlib, json, os, stat, subprocess, sys
from pathlib import Path
NATIVE = r"C:\ProgramData\HaraLabs\CommanderWinLab\20261012\windows-clean-native-root-r1"
CLEAN = r"C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
CLONE = "hara-win51-clean-20261012-r1"
PRIMARY = "commander-win11"
PRIVATE = Path("/tmp_hara/commander-windows-clean-20261012-r1/qga-results")
EXE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
def call(vm, payload):
    assert vm in (PRIMARY, CLONE)
    p = subprocess.run(["virsh","--connect","qemu:///system","qemu-agent-command",vm,json.dumps(payload,separators=(",",":"))],capture_output=True,text=True,timeout=15)
    if p.returncode: raise RuntimeError("QGA_TRANSPORT_FAILED")
    r=json.loads(p.stdout)
    if "error" in r: raise RuntimeError("QGA_"+str(r["error"].get("class","ERROR")))
    return r.get("return",{})
def guard(vm, path):
    allowed=[NATIVE] if vm==PRIMARY else [NATIVE,CLEAN]
    assert any(path.lower().startswith(root.lower()+"\\") for root in allowed), "GUEST_ACCEPTANCE_PATH_REQUIRED"
    assert ".." not in path and "/" not in path
    if vm == PRIMARY: assert path.lower().endswith((".ps1",".json",".txt")), "PRIMARY_NATIVE_FILE_ONLY"
def execute(vm, path):
    guard(vm,path)
    return call(vm,{"execute":"guest-exec","arguments":{"path":EXE,"arg":["-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",path],"capture-output":True}})
def stage(vm, source, target):
    guard(vm,target)
    data=Path(source).read_bytes()
    handle=call(vm,{"execute":"guest-file-open","arguments":{"path":target,"mode":"wb"}})
    try:
        for start in range(0,len(data),1536):
            chunk=data[start:start+1536]
            r=call(vm,{"execute":"guest-file-write","arguments":{"handle":handle,"buf-b64":base64.b64encode(chunk).decode()}})
            assert r.get("count")==len(chunk), "QGA_WRITE_SHORT"
    finally: call(vm,{"execute":"guest-file-close","arguments":{"handle":handle}})
    return {"state":"STAGED","bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"vm":vm,"guest_path":target}
def status(vm,pid):
    PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    assert stat.S_IMODE(PRIVATE.stat().st_mode)==0o700
    cache=PRIVATE/(vm+"-"+str(pid)+"-result.json")
    if cache.exists():
        return json.loads(cache.read_text())
    r=call(vm,{"execute":"guest-exec-status","arguments":{"pid":pid}})
    if not r.get("exited"): return {"state":"RUNNING","guest_pid":pid,"vm":vm}
    out=base64.b64decode(r.get("out-data","") or "")
    err=base64.b64decode(r.get("err-data","") or "")
    for name,raw in (("stdout",out),("stderr",err)):
        file=PRIVATE/(vm+"-"+str(pid)+"-"+name+".raw")
        if not file.exists():
            fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"wb") as stream:stream.write(raw)
    text=out.decode("utf-8-sig","replace").strip()
    parsed=None
    for line in reversed(text.splitlines()):
        try: parsed=json.loads(line);break
        except Exception:pass
    report={"state":"EXITED","vm":vm,"guest_pid":pid,"exit_code":r.get("exitcode"),"result":parsed,"stdout_sha256":hashlib.sha256(out).hexdigest(),"stderr_sha256":hashlib.sha256(err).hexdigest(),"stderr_present":bool(err),"raw_logs_private":True,"output_truncated":bool(r.get("out-truncated") or r.get("err-truncated"))}
    fd=os.open(cache,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w") as file:json.dump(report,file,sort_keys=True)
    return report
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["stage","start","status"]);p.add_argument("--vm",choices=[PRIMARY,CLONE],required=True);p.add_argument("--source");p.add_argument("--target");p.add_argument("--pid",type=int);a=p.parse_args()
    try:
        if a.action=="stage":r=stage(a.vm,a.source,a.target)
        elif a.action=="start":r={"state":"STARTED","vm":a.vm,"guest_pid":execute(a.vm,a.target)["pid"]}
        else:r=status(a.vm,a.pid)
        print(json.dumps(r,sort_keys=True))
    except Exception as e:
        print(json.dumps({"state":"HOLD","reason":str(e) if str(e).replace("_","").isalnum() else type(e).__name__}));sys.exit(1)
if __name__=="__main__":main()
