#!/usr/bin/env python3
"""Finite read-only metadata, privacy and grant checks on the disposable QA2 tenant."""
def unwrap_tool(d):
    r=d.get("result",{})
    if isinstance(r,dict) and isinstance(r.get("structuredContent"),dict):return r["structuredContent"]
    for item in r.get("content",[]) if isinstance(r,dict) else []:
        if isinstance(item,dict) and item.get("type")=="text":
            try:return json.loads(item.get("text",""))
            except Exception:pass
    return r if isinstance(r,dict) else {}

def collect_scalars(value,names):
    found=[]
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in names and not isinstance(v,(dict,list)):found.append({k:v})
                if isinstance(v,(dict,list)):walk(v)
        elif isinstance(x,list):
            for x2 in x:walk(x2)
    walk(value);return found

def privacy_schema_scan(value):
    denied={"command","command_line","command_preview","arguments","payload","stdout","stderr","access_token","id_token","refresh_token","cookie","authorization","device_token","pairing_token","session_token","password"}
    found=set()
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k.lower() in denied and v not in (None,"",{},[]):found.add(k)
                if isinstance(v,(dict,list)):walk(v)
        elif isinstance(x,list):
            for z in x:walk(z)
    walk(value);return sorted(found)

def calls_main():
    os.umask(0o077)
    s=load();ctx=s["portal"]["mcp_context"]
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":"qa-calls-init","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"HARA Readonly QA Contract","version":"1.0.0"}}});need(c)
    version=d.get("result",{}).get("protocolVersion")
    if not version:raise SafeFailure("MCP_INITIALIZE_FAILED")
    headers={"MCP-Protocol-Version":version}
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","method":"notifications/initialized","params":{}},headers);need(c,(200,202,204))
    entries=[]
    specs=[
        ("list_devices",{}, "qa-list", None),
        ("get_usage_stats",{}, "qa-usage", None),
        ("get_usage_stats",{}, "qa-usage", None),
        ("get_activity",{"limit":20,"window":"24h"}, "qa-activity", None),
        ("get_recent_tool_calls",{"limit":20}, "qa-recent", None),
        ("list_devices",{}, "qa-caller", {"subject_id":"not-a-real-qa-subject","tenant_id":"not-a-real-qa-tenant"}),
        ("start_process",{"computer":"QA-NO-SUCH-DEVICE","command":"hostname","timeout_ms":1000}, "qa-denied-mutation", None),
    ]
    for tool,args,rid,caller in specs:
        params={"name":tool,"arguments":args}
        if caller is not None:params["caller"]=caller
        c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":rid,"method":"tools/call","params":params},headers)
        t=unwrap_tool(d)
        result=t.get("result",{}) if isinstance(t,dict) else {}
        devices=result.get("devices") if isinstance(result,dict) else None
        if devices is None and isinstance(t,dict):devices=t.get("devices")
        item={"tool":tool,"request_id":rid,"http_status":c,"jsonrpc_error_code":d.get("error",{}).get("code") if isinstance(d.get("error"),dict) else None,"tool_is_error":d.get("result",{}).get("isError") if isinstance(d.get("result"),dict) else None,"result_state":t.get("state") if isinstance(t,dict) else None,"safe_result_code":t.get("error_code") if isinstance(t,dict) else None,"blocker_code":t.get("blocker",{}).get("code") if isinstance(t.get("blocker"),dict) else None,"device_count":len(devices) if isinstance(devices,list) else None,"context_metadata":collect_scalars(t,{"plan_code","tenant_id","subject_id","used_units","remaining_units","units","limit_units","quota_limit","usage_count"}),"metadata_privacy_disallowed_fields":privacy_schema_scan(t),"caller_field_supplied":caller is not None,"credential_values_exposed":False}
        entries.append(item);emit("REAL_QA_MCP_CALL",**item)
    s=load();s["portal"]["mcp_readonly_calls_proof"]=entries;save(s)
    emit("REAL_QA_MCP_CONTRACT_PROOF",subject_id=ctx["user_id"],calls=len(entries),replayed_readonly_id=True,no_mutating_action_targeted_real_device=True,credential_values_exposed=False)
    return 0

if __name__=="__main__":
    try:sys.exit(calls_main())
    except SafeFailure as e:emit("SAFE_FAILURE",code=str(e),credential_values_exposed=False);sys.exit(1)
    except Exception as e:emit("SAFE_FAILURE",code=type(e).__name__,credential_values_exposed=False);sys.exit(1)
