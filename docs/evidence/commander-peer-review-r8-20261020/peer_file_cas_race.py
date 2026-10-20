#!/usr/bin/env python3
"""R8: Real competing OS processes call Agent.filesystem_edit with SAME CAS hash.
Only synthetic temporary files and XDG storage. No network and no Agent service.
Barriers force simultaneous passage through the mutation precondition to
demonstrate whether the hash guard is atomic across local processes.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,multiprocessing as mp,os,sys,tempfile,time
ROOT=Path(__file__).resolve().parent
SOURCE=Path(os.environ.get("HARA_PEER_SOURCE",str(ROOT/"source")))/"apps/commander/public/agent/linux.py"
def load(name):
    spec=importlib.util.spec_from_file_location(name,SOURCE)
    a=importlib.util.module_from_spec(spec);sys.modules[name]=a;spec.loader.exec_module(a)
    return a
def worker(root,target,start_hash,desired,barrier,q):
    os.environ["HOME"]=str(root/"home")
    os.environ["XDG_DATA_HOME"]=str(root/"data")
    os.environ["XDG_CONFIG_HOME"]=str(root/"config")
    try:
        a=load("hara_r8_agent_"+desired)
        original=a._assert_path_matches_preimage
        def intercept(path,preimage):
            validated=original(path,preimage)
            barrier.wait(timeout=5)
            return validated
        a._assert_path_matches_preimage=intercept
        result=a.filesystem_edit({"call_id":"R8-"+desired},str(target),"BASE",desired,False,start_hash)
        q.put({"desired":desired,"outcome":"ACCEPTED","precondition_checked":result["precondition_checked"],
               "previous_sha256":result["previous_sha256"],"reported_sha256":result["sha256"]})
    except Exception as exc:
        q.put({"desired":desired,"outcome":"DENIED","code":type(exc).__name__+":"+str(exc)})
def main():
    assert SOURCE.is_file()
    with tempfile.TemporaryDirectory(prefix="hara-r8-two-writers-") as d:
        root=Path(d)
        for leaf in ("home","data","config"): (root/leaf).mkdir()
        os.environ["HOME"]=str(root/"home")
        os.environ["XDG_DATA_HOME"]=str(root/"data")
        os.environ["XDG_CONFIG_HOME"]=str(root/"config")
        target=root/"test-only.txt"
        target.write_text("BASE",encoding="utf-8")
        initial=hashlib.sha256(target.read_bytes()).hexdigest()
        a=load("hara_r8_seq")
        first=a.filesystem_edit({"call_id":"R8-SEQUENTIAL-1"},str(target),"BASE","FIRST",False,initial)
        try:
            a.filesystem_edit({"call_id":"R8-SEQUENTIAL-2"},str(target),"BASE","SECOND",False,initial)
            seq="INCORRECTLY_ACCEPTED"
        except ValueError as e: seq=str(e)
        assert seq=="FILE_PRECONDITION_FAILED" and target.read_text()=="FIRST",("control",seq)
        target.write_text("BASE",encoding="utf-8")
        results=[]
        ctx=mp.get_context("spawn")
        q=ctx.Queue()
        barrier=ctx.Barrier(2)
        children=[ctx.Process(target=worker,args=(root,target,initial,d,barrier,q)) for d in ("WRITER_A","WRITER_B")]
        for p in children:p.start()
        for p in children:p.join(timeout=8)
        if any(p.is_alive() for p in children):
            for p in children:
                if p.is_alive():p.terminate()
            for p in children:p.join(timeout=2)
            raise RuntimeError("HARNESS_TIMEOUT")
        while not q.empty():results.append(q.get())
        q.close()
        report={"schema":"hara.commander-peer-file-cas-r8.v1","observed_utc":datetime.now(timezone.utc).isoformat(),
                "source_head":(ROOT/"source-head.txt").read_text().strip(),
                "source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "scope":"two OS processes on disposable file; actual filesystem_edit and preimage; barrier after successful path+hash recheck only",
                "sequential_control":seq,"original_sha256":initial,"parallel_results":sorted(results,key=lambda x:x["desired"]),
                "parallel_accepted":sum(r["outcome"]=="ACCEPTED" for r in results),
                "final_file":target.read_text(),"final_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                "reproduced":sum(r["outcome"]=="ACCEPTED" for r in results)==2,
                "real_customer_files_modified":False,"network_requests":0}
        (ROOT/"r8-file-cas-results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 2 if report["reproduced"] else 0
if __name__=="__main__":sys.exit(main())
