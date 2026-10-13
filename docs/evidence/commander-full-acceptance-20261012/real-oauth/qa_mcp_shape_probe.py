
def shape(x,path="",depth=0):
    rows=[]
    if depth>4:return rows
    if isinstance(x,dict):
        for k,v in x.items():
            q=path+"/"+k
            rows.append({"path":q,"kind":type(v).__name__,"length":len(v) if isinstance(v,(dict,list)) else None})
            if isinstance(v,(dict,list)):rows+=shape(v,q,depth+1)
    elif isinstance(x,list) and x:rows+=shape(x[0],path+"/0",depth+1)
    return rows

def safe_probe_main():
    import re
    s=load();ctx=s["portal"]["mcp_context"];headers={"MCP-Protocol-Version":"2025-03-26"}
    for name,args in [("list_devices",{}),("start_process",{"computer":"QA-NO-SUCH-DEVICE","command":"hostname","timeout_ms":1000})]:
        c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":"qa-shape-"+name,"method":"tools/call","params":{"name":name,"arguments":args}},headers)
        t=unwrap_tool(d)
        content=d.get("result",{}).get("content",[])
        codes=sorted({a for x in content if isinstance(x,dict) for a in re.findall(r"\b[A-Z][A-Z0-9_]{3,79}\b",str(x.get("text","")))})
        counts=collect_scalars(t,{"count","total","device_count","online_count","active_count","plan_code","error_code","code"})
        arrays=[]
        def find(x,p=""):
            if isinstance(x,dict):
                for k,v in x.items():
                    if isinstance(v,list):arrays.append({"path":p+"/"+k,"length":len(v)})
                    elif isinstance(v,dict):find(v,p+"/"+k)
        find(t)
        emit("MCP_SAFE_SHAPE",tool=name,http_status=c,tool_is_error=d.get("result",{}).get("isError"),shape=shape(t),metadata_counts=counts,array_lengths=arrays,safe_uppercase_codes=codes,credential_values_exposed=False)
    return 0
if __name__=="__main__":
    try:sys.exit(safe_probe_main())
    except Exception as e:emit("SAFE_FAILURE",code=type(e).__name__,credential_values_exposed=False);sys.exit(1)
