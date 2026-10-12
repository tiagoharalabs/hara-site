#!/usr/bin/env python3
"""Guarded resume of the existing Agent Task; observer starts first. No MCP replay."""
import argparse,contextlib,hashlib,importlib.util,io,json,time
from pathlib import Path
H=Path("/tmp_hara/commander-win48-private-rc-20261012-r1")
PINS={
 "windows_048_existing_task_resume.ps1":"4a55d882fb3039eb4ad0087a2b6a0673c692096d5fcfef645fc482a571967647",
 "commander_win48_user_pending_watch_dynamic.py":"e073fb4f55091d5267137dda0551db53fdf0a560ee4a286bfedb4cbdea8c7439",
}
def emit(x): print(json.dumps(x,sort_keys=True),flush=True)
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--action",choices=["Inspect","Resume"],default="Inspect")
 parser.add_argument("--root-confirmed-call-pending-unclaimed",action="store_true")
 parser.add_argument("--notify-on-active",action="store_true")
 args=parser.parse_args()
 if args.action=="Resume" and not args.root_confirmed_call_pending_unclaimed:
  raise SystemExit("ROOT_FRESH_CALL_CONFIRMATION_REQUIRED")
 for name,sha in PINS.items():
  if hashlib.sha256((H/name).read_bytes()).hexdigest()!=sha:
   raise SystemExit("RECOVERY_SCRIPT_CHANGED")
 s=importlib.util.spec_from_file_location("watch",H/"commander_win48_user_pending_watch_dynamic.py")
 watch=importlib.util.module_from_spec(s);s.loader.exec_module(watch)
 if args.action=="Resume": watch.start()
 s=importlib.util.spec_from_file_location("op","/tmp_hara/hara_win11_operator_window_control_20261011.py")
 op=importlib.util.module_from_spec(s);s.loader.exec_module(op)
 p=r"C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-048-rc-r1\windows_048_existing_task_resume.ps1"
 op.ACTIONS["inspect"]="$ErrorActionPreference='Stop';$p='"+p+"';if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne '"+PINS["windows_048_existing_task_resume.ps1"]+"'){throw 'RESUME_HELPER_CHANGED'};& $p -Action "+args.action
 capture=io.StringIO()
 with contextlib.redirect_stdout(capture): op.execute("inspect")
 lines=[line[7:] for line in capture.getvalue().splitlines() if line.startswith("RESULT ")]
 if len(lines)!=1: raise SystemExit("RECOVERY_RESULT_UNAVAILABLE")
 result=json.loads(lines[0]);emit({"resume_result":result})
 if result.get("state")!="PASS" or args.action=="Inspect":return
 deadline=time.monotonic()+45
 while True:
  sample=watch.sample(args.notify_on_active)
  if sample.get("pending_active") or time.monotonic()>=deadline:
   emit({"watch_result":sample,"same_queued_request_only":True,"new_mcp_call_generated":False,"approval_generated":False})
   break
  time.sleep(.1)
if __name__=="__main__":main()
