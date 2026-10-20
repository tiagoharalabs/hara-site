#!/usr/bin/env python3
"""R7: race test for Agent process session capacity.
No real pty fork or customer process. Uses disposable HOME, fake fork with barrier.
Non-code-change verification of the actual process_start function.
"""
import os,sys,threading,importlib.util,json,tempfile,time,hashlib
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent
SOURCE=Path(os.environ.get("HARA_PEER_SOURCE",str(ROOT/"source")))
with tempfile.TemporaryDirectory(prefix="hara-r7-process-race-") as root:
    root=Path(root)
    for k,s in [("HOME","home"),("XDG_DATA_HOME","data"),("XDG_CONFIG_HOME","config")]:
        os.environ[k]=str(root/s);(root/s).mkdir()
    file=SOURCE/"apps/commander/public/agent/linux.py"
    spec=importlib.util.spec_from_file_location("hara_r7_agent",file)
    agent=importlib.util.module_from_spec(spec);sys.modules[spec.name]=agent;spec.loader.exec_module(agent)
    agent.PROCESS_SESSIONS.clear()
    agent.PROCESS_RESULT_TOMBSTONES.clear()
    agent.MAX_PROCESS_ACTIVE_SESSIONS=1
    agent.MAX_PROCESS_RETAINED_SESSIONS=48
    agent.append_console_event=lambda *a,**kw:None
    agent._collect_process_output=lambda session:None
    agent._process_output_payload=lambda session,**kw:{"text":"","partial":"","session_id":session["session_id"],"state":"RUNNING","exit_code":None}
    calls=[]
    barrier=threading.Barrier(2)
    guard=threading.Lock()
    fds=[]
    def fake_fork():
        fd=os.open("/dev/null",os.O_RDWR)
        with guard:
            pid=90001+len(calls);calls.append(pid);fds.append(fd)
        barrier.wait(timeout=2)
        return pid,fd
    agent.pty.fork=fake_fork
    values=[]
    def start_one(i):
        try:
            data=agent.process_start("echo noop",str(root),0,owner_request_id="R7-"+str(i),owner_subject_id="TEST")
            with guard:values.append({"index":i,"result":"STARTED","sid":data["session_id"]})
        except Exception as e:
            with guard:values.append({"index":i,"result":"DENIED","error":type(e).__name__+":"+str(e)})
    ts=[threading.Thread(target=start_one,args=(i,),daemon=True) for i in range(2)]
    try:
        for t in ts:t.start()
        for t in ts:t.join(timeout=4)
        if any(t.is_alive() for t in ts):raise RuntimeError("HARNESS_THREADS_NOT_COMPLETED")
        active=sum(s.get("exit_code") is None for s in agent.PROCESS_SESSIONS.values())
        failed=active>agent.MAX_PROCESS_ACTIVE_SESSIONS
        report={"schema":"hara.commander-r7-concurrent-process-policy.v1","observed_utc":datetime.now(timezone.utc).isoformat(),
                "agent_sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
                "test_method":"2 threads run actual process_start; fake pty fork enforces race after both have already checked capacity; no OS fork",
                "limit":agent.MAX_PROCESS_ACTIVE_SESSIONS,"active_after":active,"session_count":len(agent.PROCESS_SESSIONS),
                "results":values,"reproduced":failed,"production_processes_started":0}
        (ROOT/"r7-concurrent-process-results.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))
    finally:
        for fd in fds:
            try:os.close(fd)
            except OSError:pass
        agent.PROCESS_SESSIONS.clear()
    sys.exit(2 if failed else 0)
