#!/usr/bin/env python3
"""R16 offline release regression: runs 42 non-destructive Node test files.

No deployment, token writes, device revocations or PROD D1 access. Store report
outside the Git checkout by default. Does not replace real browser/device tests.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

APP=Path(__file__).resolve().parents[1]
def run_test(path: Path, node: str, timeout: float) -> dict:
    started=time.monotonic()
    try:
        result=subprocess.run([node,"--no-warnings",str(path)],cwd=APP,
          env={**os.environ,"CI":"1","NO_COLOR":"1"},
          capture_output=True,text=True,timeout=timeout)
        state="PASS" if result.returncode==0 else "FAIL"
        return {
          "name":path.name,"state":state,"exit_code":result.returncode,
          "duration_seconds":round(time.monotonic()-started,2),
          "failure_tail":(result.stdout+"\n"+result.stderr)[-900:] if state!="PASS" else ""
        }
    except subprocess.TimeoutExpired:
        return {"name":path.name,"state":"TIMEOUT","duration_seconds":round(time.monotonic()-started,2)}
    except Exception as exc:
        return {"name":path.name,"state":"HARNESS_ERROR","error_class":type(exc).__name__}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--report",type=Path,default=Path("/tmp/hara-commander-r16-matrix.json"))
    parser.add_argument("--node",default="/home/sartorius/.nvm/versions/node/v24.15.0/bin/node")
    parser.add_argument("--jobs",type=int,default=6)
    args=parser.parse_args()
    if not 1<=args.jobs<=8:raise SystemExit("INVALID_JOBS")
    tests=sorted((APP/"scripts").glob("test_*.mjs"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results=list(pool.map(lambda path:run_test(path,args.node,18),tests))
    summary={key:sum(x.get("state")==key for x in results)
      for key in ("PASS","FAIL","TIMEOUT","HARNESS_ERROR")}
    data={
      "schema":"hara.commander.r16.offline-launch-matrix.v1",
      "source_code_mutation":False,
      "production_mutation":False,
      "not_equivalent_to_browser_or_security_pentest":True,
      "utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "total":len(results),"summary":summary,"tests":results,
    }
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"total":len(results),"summary":summary,"report":str(args.report)},ensure_ascii=False))
    for item in results:
        if item["state"]!="PASS":print("FAILURE",item["name"],item.get("failure_tail","")[-350:].replace("\n"," | "))
    return 0 if summary["PASS"]==len(results) else 1
if __name__=="__main__":
    raise SystemExit(main())
