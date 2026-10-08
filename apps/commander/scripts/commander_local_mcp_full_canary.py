#!/usr/bin/env python3
import argparse, json, pathlib, subprocess, sys, time, shutil

ap=argparse.ArgumentParser()
ap.add_argument("--execute",action="store_true")
ap.add_argument("--expect-version",default="0.3.41")
ap.add_argument("--commander",default=str(pathlib.Path.home()/".local/bin/hara-commander"))
args=ap.parse_args()
commander=pathlib.Path(args.commander).expanduser()
if not commander.is_file():
    raise SystemExit("COMMANDER_LOCAL_MCP_FULL_CANARY_BINARY=MISSING")
if not args.execute:
    print("COMMANDER_LOCAL_MCP_FULL_CANARY_BINARY=PASS")
    print("COMMANDER_LOCAL_MCP_FULL_CANARY_MUTATION=FALSE")
    print("COMMANDER_LOCAL_MCP_FULL_CANARY_READY=PASS")
    raise SystemExit(0)
CMD=[str(commander),"mcp"]
p=subprocess.Popen(CMD,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
seq=0
failures=[]
results={}

def rpc(name,args=None,method="tools/call"):
    global seq
    seq+=1
    req={"jsonrpc":"2.0","id":seq,"method":method}
    if method=="tools/call":
        req["params"]={"name":name,"arguments":args or {}}
    elif args is not None:
        req["params"]=args
    p.stdin.write(json.dumps(req,separators=(",",":"))+"\n"); p.stdin.flush()
    line=p.stdout.readline()
    if not line:
        raise RuntimeError("NO_RESPONSE:"+p.stderr.read()[-1000:])
    obj=json.loads(line)
    if obj.get("id")!=seq:
        raise RuntimeError(f"ID_MISMATCH:{obj}")
    return obj

def sc(resp):
    return (resp.get("result") or {}).get("structuredContent")

def inner(resp):
    s=sc(resp) or {}
    r=s.get("result") or {}
    raw=r.get("stdout")
    if isinstance(raw,str):
        try: return json.loads(raw)
        except Exception: return {}
    return {}

def check(label, cond, detail=None):
    results[label]="PASS" if cond else "FAIL"
    if not cond: failures.append((label,detail))

root=pathlib.Path("/tmp/hara-local-mcp-full-canary")
try:
    if root.exists(): shutil.rmtree(root)
    init=rpc("initialize",{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"hara-suite","version":"1"}},"initialize")
    check("initialize",(init.get("result") or {}).get("serverInfo",{}).get("version")==args.expect_version,init)

    tools=rpc("tools/list",{},"tools/list")
    names=[x.get("name") for x in (tools.get("result") or {}).get("tools",[])]
    check("tool_count",len(names)==24,len(names))

    conf=sc(rpc("get_config")) or {}
    check("get_config",conf.get("agent_version")=="0.3.41" and conf.get("transport")=="LOCAL_STDIO",conf)

    usage=sc(rpc("get_usage_stats")) or {}
    check("usage_zero_relay",usage.get("relay_calls_per_local_tool_call")==0 and usage.get("cloud_quota_consumed_by_local_tool_call") is False,usage)

    check("list_devices",bool((sc(rpc("list_devices")) or {}).get("devices")))
    check("ping",(sc(rpc("ping")) or {}).get("state")=="PASS")
    check("device_info",(sc(rpc("get_device_info")) or {}).get("state")=="PASS")

    cr=sc(rpc("create_directory",{"path":str(root),"parents":True})) or {}
    check("create_directory",cr.get("state")=="PASS",cr)

    wr=sc(rpc("write_file",{"path":str(root/"a.txt"),"content":"alpha\nneedle\n","mode":"rewrite"})) or {}
    check("write_file",wr.get("state")=="PASS",wr)

    rd=inner(rpc("read_file",{"path":str(root/"a.txt"),"offset":0,"length":20}))
    check("read_file","alpha" in rd.get("text",""),rd)

    ed=sc(rpc("edit_block",{"path":str(root/"a.txt"),"old_string":"alpha","new_string":"beta","replace_all":False})) or {}
    check("edit_block",ed.get("state")=="PASS",ed)

    cp=sc(rpc("copy_file",{"source":str(root/"a.txt"),"destination":str(root/"copy.txt")})) or {}
    check("copy_file",cp.get("state")=="PASS",cp)

    mv=sc(rpc("move_file",{"source":str(root/"copy.txt"),"destination":str(root/"moved.txt")})) or {}
    check("move_file",mv.get("state")=="PASS",mv)

    ls=inner(rpc("list_directory",{"path":str(root),"depth":2,"limit":50}))
    listed=json.dumps(ls)
    check("list_directory","a.txt" in listed and "moved.txt" in listed,ls)

    fi=inner(rpc("get_file_info",{"path":str(root/"a.txt")}))
    check("get_file_info",fi.get("is_file") is True or fi.get("type")=="file" or fi.get("kind")=="file",fi)

    many=inner(rpc("read_multiple_files",{"paths":[str(root/"a.txt"),str(root/"moved.txt")],"offset":0,"length":20}))
    check("read_multiple_files","beta" in json.dumps(many),many)

    sf=inner(rpc("search",{"path":str(root),"pattern":"moved","search_type":"files","max_results":20}))
    check("search_files","moved.txt" in json.dumps(sf),sf)

    scnt=inner(rpc("search",{"path":str(root),"pattern":"needle","search_type":"content","max_results":20}))
    check("search_content","a.txt" in json.dumps(scnt),scnt)

    procs=inner(rpc("list_processes",{"limit":10}))
    check("list_processes",len(procs.get("processes",[]))<=10 and len(procs.get("processes",[]))>0,procs)

    one=rpc("start_process",{"command":"printf HARA_SUITE_ONE_SHOT","timeout_ms":3000,"max_lines":20})
    onei=inner(one)
    check("process_one_shot",(sc(one) or {}).get("state")=="PASS" and onei.get("exit_code")==0 and "HARA_SUITE_ONE_SHOT" in onei.get("text",""),onei)

    exit7=rpc("start_process",{"command":"exit 7","interactive":True,"timeout_ms":1000})
    check("process_exit7",(sc(exit7) or {}).get("result",{}).get("process_exit_code")==7,sc(exit7))

    inter=rpc("start_process",{"command":"read x; echo ECHO:$x","interactive":True,"timeout_ms":500})
    interi=inner(inter); sid=interi.get("session_id")
    check("process_interactive_start",bool(sid) and interi.get("state")=="RUNNING",interi)
    if sid:
        iresp=rpc("interact_with_process",{"session_id":sid,"input":"hello","timeout_ms":1000})
        ii=inner(iresp); observed=[ii.get("text","") or "",ii.get("partial","") or ""]; cursor=int(ii.get("next_offset") or 0); oi={}
        deadline=time.monotonic()+2.0
        while time.monotonic()<deadline:
            oresp=rpc("read_process_output",{"session_id":sid,"offset":cursor,"length":20,"timeout_ms":250})
            oi=inner(oresp); observed.extend([oi.get("text","") or "",oi.get("partial","") or ""]); cursor=int(oi.get("next_offset") or cursor)
            if oi.get("exit_code") is not None: break
        combined="\n".join(observed)
        check("process_interact","ECHO:hello" in combined,{"interact":ii,"output":oi,"combined":combined})
        check("process_output",oi.get("exit_code")==0,{"output":oi,"combined":combined})

    longr=rpc("start_process",{"command":"sleep 30","timeout_ms":20000})
    longi=inner(longr); longsid=longi.get("session_id")
    check("long_auto_route",(sc(longr) or {}).get("result",{}).get("function_id")=="process.start" and bool(longsid),sc(longr))
    if longsid:
        kres=rpc("kill_process",{"session_id":longsid,"force":True})
        ki=inner(kres)
        check("kill_process",ki.get("state") in ("EXITED","TERMINATING"),ki)

    sess=inner(rpc("list_sessions"))
    check("list_sessions","sessions" in sess,sess)

    missing=sc(rpc("get_file_info",{"path":str(root/"missing.txt")})) or {}
    check("missing_structured",missing.get("state")=="NOT_FOUND" and (missing.get("blocker") or {}).get("retryable") is False,missing)

    parent=sc(rpc("write_file",{"path":str(root/"no-parent"/"x.txt"),"content":"x","mode":"rewrite"})) or {}
    check("parent_missing_structured",parent.get("state")=="NOT_FOUND" and (parent.get("result") or {}).get("recommended_tool")=="create_directory",parent)

    conflict=sc(rpc("copy_file",{"source":str(root/"a.txt"),"destination":str(root/"moved.txt")})) or {}
    check("conflict_structured",conflict.get("state")=="CONFLICT",conflict)

    delete1=sc(rpc("delete_file",{"path":str(root/"moved.txt")})) or {}
    delete2=sc(rpc("delete_file",{"path":str(root/"a.txt")})) or {}
    check("delete_file",delete1.get("state")=="PASS" and delete2.get("state")=="PASS",(delete1,delete2))

    act=sc(rpc("get_activity",{"limit":20,"window":"24h"})) or {}
    recent=sc(rpc("get_recent_tool_calls",{"limit":20,"window":"24h"})) or {}
    check("activity_metadata",act.get("metadata_only") is True,act)
    check("recent_metadata",recent.get("metadata_only") is True,recent)

finally:
    try:
        if root.exists(): shutil.rmtree(root)
    except Exception: pass
    try:
        p.stdin.close(); p.terminate()
    except Exception: pass

for k,v in results.items():
    print(f"HARA_LOCAL_0341_{k.upper()}={v}")
print(f"HARA_LOCAL_0341_TOTAL={len(results)}")
print(f"HARA_LOCAL_0341_FAILURES={len(failures)}")
if failures:
    for k,d in failures:
        print("FAIL",k,json.dumps(d,default=str)[:1000])
    raise SystemExit(1)
print("COMMANDER_LOCAL_MCP_FULL_CANARY_33_OF_33=PASS")
print("COMMANDER_LOCAL_MCP_FULL_CANARY=PASS")
