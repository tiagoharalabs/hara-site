#!/usr/bin/env python3
"""Real DEV-only TLS socket loss and durable local replay recovery on own QA Agent."""
from __future__ import annotations
import argparse,hashlib,json,os,secrets,signal,subprocess,time
from pathlib import Path
import commander_full_acceptance_real_dev_soak as soak

WRAPPER = r'''import importlib.util,signal,socket,sys
from pathlib import Path
p=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("qa_event_loop",p)
loop=importlib.util.module_from_spec(spec);spec.loader.exec_module(loop)
current=[None]
original_load=loop.load_modules
def load():
    transport,agent=original_load()
    original_open=transport.open_event_socket
    def opened(*a,**k):
        current[0]=original_open(*a,**k)
        return current[0]
    transport.open_event_socket=opened
    return transport,agent
def fault(_signum,_frame):
    sock=current[0];current[0]=None
    if sock is not None:
        try:sock.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        sock.close()
loop.load_modules=load
signal.signal(signal.SIGUSR1,fault)
raise SystemExit(loop.main())
'''

class Recovery(soak.Runner):
    def stage(self):
        super().stage()
        self.wrapper=self.home/"qa_network_fault_wrapper.py"
        self.wrapper.write_text(WRAPPER);os.chmod(self.wrapper,0o600)
        self.audit["qa_fault_wrapper_sha256"]=hashlib.sha256(self.wrapper.read_bytes()).hexdigest()

    def start_agent(self,row):
        soak.require(not self.owned_pid(row),"SOAK_AGENT_ALREADY_ACTIVE")
        env=os.environ.copy();env["XDG_CONFIG_HOME"]=str(row["root"]/"xdg-config")
        env["XDG_DATA_HOME"]=str(row["root"]/"xdg-data");env["PYTHONDONTWRITEBYTECODE"]="1"
        self.cloud_budget(1)
        log=open(row["root"]/"agent.log","ab");os.chmod(row["root"]/"agent.log",0o600)
        row["proc"]=subprocess.Popen(["/usr/bin/python3","-B",str(self.wrapper),str(self.source)],
            env=env,cwd=row["root"],stdout=log,stderr=log,stdin=subprocess.DEVNULL)
        row["pid"]=row["proc"].pid;log.close()

    def test(self):
        err=None
        try:
            row=self.create_one(0);self.selection([row]);self.wait_ready([row])
            result=self.full_probe(row);before=self.ledger(row)
            status_path=row["root"]/"xdg-data/hara-commander/event-v2-status.json"
            oldstatus=soak.read_json(status_path);pid=row["pid"]
            soak.require(self.owned_pid(row),"NETWORK_FAULT_PID_GUARD")
            start=time.monotonic();os.kill(pid,signal.SIGUSR1)
            recovered=False
            while time.monotonic()-start<75:
                status=soak.read_json(status_path)
                if self.connected(row) and status.get("connected_at_utc")!=oldstatus.get("connected_at_utc"):
                    recovered=True;break
                time.sleep(.25)
            soak.require(recovered,"NETWORK_FAULT_RECONNECT_TIMEOUT")
            soak.require(row["pid"]==pid and self.owned_pid(row),"NETWORK_FAULT_PROCESS_CHANGED")
            self.cloud_budget(1)
            replay=soak.probe.transient_call(self.token,row["subject"],row["last_request_id"],
                "hara.functions.invoke",{"function_id":"device.info","arguments":{"argv":[]}})
            soak.probe.require_transient_common(replay)
            soak.require(replay.get("state")=="COMPLETED" and replay.get("execution_mode")=="REPLAY_ONLY","NETWORK_RECOVERY_REPLAY")
            soak.require(replay.get("receipt_sha256")==row["last_receipt"],"NETWORK_RECOVERY_RECEIPT")
            soak.require(before==self.ledger(row),"NETWORK_RECOVERY_LEDGER_CHANGED")
            self.audit.update(state="PASS",fault="OWN_AGENT_TLS_SOCKET_SHUTDOWN",
                process_pid_unchanged=True,old_connection=oldstatus.get("connected_at_utc"),
                new_connection=status.get("connected_at_utc"),reconnect_ms=(time.monotonic()-start)*1000,
                receipt_sha256=row["last_receipt"],request_id=row["last_request_id"],
                replay_only=True,ledger_unchanged=True,customer_commands_executed=False)
        except BaseException as exc:
            err=soak.error_code(exc);self.audit.update(state="FAIL",error_code=err)
        finally:
            try:self.cleanup_rows([r for r in self.rows if not r.get("cleaned")]);self.audit["cleanup_state"]="PASS"
            except Exception as exc:self.audit.update(cleanup_state="FAIL",cleanup_error_code=soak.error_code(exc))
            self.audit["finished_at_utc"]=soak.now();self.emit()
            print(json.dumps({k:self.audit.get(k) for k in ("state","error_code","cleanup_state","reconnect_ms","ledger_unchanged","process_pid_unchanged")}))
        return 0 if self.audit["state"]=="PASS" and self.audit["cleanup_state"]=="PASS" else 1

if __name__=="__main__":
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    parser=argparse.ArgumentParser();parser.add_argument("--run-id")
    args=parser.parse_args()
    run_id=args.run_id or ("soak-network-"+time.strftime("%Y%m%d%H%M%S",time.gmtime())+"-"+secrets.token_hex(3))
    runner=Recovery(run_id,24,2)
    runner.audit["network_driver_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    raise SystemExit(runner.test())
