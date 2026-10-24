#!/usr/bin/env python3
"""Bounded Cloudflare DEV health ramp; HTTP smoke, not 1,000 distinct users.

No credentials, cookies, account creation, Stripe calls, D1 mutations or MCP
device calls. Only GET /api/health against a fixed DEV allowlisted domain.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone

URL = "https://hara-commander-dev-v2.tiago-sartori.workers.dev/api/health"
PHASES = ((10,100),(25,300),(50,600))
TOTAL = sum(requests for _,requests in PHASES)
MAX_BODY = 512

def once(_):
    req = urllib.request.Request(
        URL, method="GET",
        headers={"User-Agent":"HARA-Commander-Scale-Synthetic/1.0",
                 "Accept":"application/json"})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=10) as response:
            status=response.status
            data=response.read(MAX_BODY+1)
        ok=(status==200 and len(data)<=MAX_BODY
            and json.loads(data)=={"ok":True,"service":"hara-commander"})
        return (ok,status,round((time.perf_counter()-start)*1000,3))
    except urllib.error.HTTPError as e:
        return (False,e.code,round((time.perf_counter()-start)*1000,3))
    except (TimeoutError,urllib.error.URLError,ValueError):
        return (False,0,round((time.perf_counter()-start)*1000,3))

def percentile(values,fraction):
    ordered=sorted(values)
    return round(ordered[min(len(ordered)-1,int((len(ordered)-1)*fraction))],2)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    if not args.execute:
        print("COMMANDER_DEV_HEALTH_RAMP_PLAN=1000_REQUESTS_3_PHASES")
        print("CLIENTS_CERTIFIED=FALSE")
        return 0
    results=[]
    phases=[]
    for workers,requests in PHASES:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            samples=list(pool.map(once,range(requests)))
        lat=[x[2] for x in samples if x[0]]
        errors=Counter(str(x[1]) for x in samples if not x[0])
        phase={"concurrency":workers,"requests":requests,
               "success":len(lat),"errors":dict(errors),
               "p50_ms":percentile(lat,.50) if lat else None,
               "p95_ms":percentile(lat,.95) if lat else None,
               "p99_ms":percentile(lat,.99) if lat else None,
               "max_ms":round(max(lat),2) if lat else None}
        phases.append(phase)
        results.extend(samples)
    all_good=[x[2] for x in results if x[0]]
    data={"schema":"hara.commander-dev-http-ramp.v1",
          "at_utc":datetime.now(timezone.utc).isoformat(),
          "target":"DEV_HEALTH_ONLY","total_requests":TOTAL,
          "success":len(all_good),"failed":TOTAL-len(all_good),
          "p50_ms":percentile(all_good,.5) if all_good else None,
          "p95_ms":percentile(all_good,.95) if all_good else None,
          "p99_ms":percentile(all_good,.99) if all_good else None,
          "phases":phases,"real_distinct_users":0,
          "authenticated_mcp_calls":0,
          "concurrent_users_certified":False,
          "production_mutations":False,
          "cost_certified":False}
    print(json.dumps(data,sort_keys=True))
    return 0 if data["failed"]==0 else 1
if __name__=="__main__":
    raise SystemExit(main())
