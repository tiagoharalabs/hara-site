
def direct_value(t):
    r=t.get("result",{}) if isinstance(t,dict) else {}
    if isinstance(r,dict) and isinstance(r.get("stdout"),str):
        try:return json.loads(r["stdout"])
        except Exception:return {}
    return r if isinstance(r,dict) else {}

def device_main():
    s=load();ctx=s["portal"]["mcp_context"];headers={"MCP-Protocol-Version":"2025-03-26"}
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":"qa-device-init","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"HARA Normal QA Device Reader","version":"1.0.0"}}});need(c)
    headers["MCP-Protocol-Version"]=d.get("result",{}).get("protocolVersion","2025-03-26")
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","method":"notifications/initialized","params":{}},headers);need(c,(200,202,204))
    entries=[];receipt=None
    def call(tool,args,rid):
        c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":rid,"method":"tools/call","params":{"name":tool,"arguments":args}},headers)
        t=unwrap_tool(d);v=direct_value(t)
        safe={"tool":tool,"http_status":c,"tool_is_error":d.get("result",{}).get("isError"),"state":t.get("state"),"blocker_code":t.get("blocker",{}).get("code") if isinstance(t.get("blocker"),dict) else None,"safe_code":t.get("error_code") or t.get("code"),"execution_authority":t.get("execution_authority") or v.get("execution_authority"),"receipt_sha256":t.get("bridge_receipt_sha256"),"readback_metadata":{k:v[k] for k in ["agent_version","hostname","platform","architecture","os","os_caption","os_version","powershell_version","pong","function_id","state","mutation_class","payload_values_persisted","tool_id","request_id","device_id","completed_at_utc"] if k in v},"plan_metadata":collect_scalars(t,{"plan_code","remaining_units","used_units","consumed_units","units","state"}),"credential_values_exposed":False}
        emit("NORMAL_QA_DEVICE_MCP_CALL",**safe);entries.append(safe)
        return t,v,d
    t,v,d=call("list_devices",{},"qa-enumerate")
    computers=t.get("result",{}).get("computers",[])
    own=[x for x in computers if x.get("device_id")=="HARA-DEVICE-6644a8cb-8a82-4f0f-8828-879a1c5a3261"]
    if len(own)!=1 or len(computers)!=1:raise SafeFailure("QA_DEVICE_ISOLATION_MISMATCH")
    if own[0].get("state")!="ONLINE":raise SafeFailure("QA_DEVICE_NOT_ONLINE")
    for tool,args,rid in [("ping",{},"qa-ping"),("get_device_info",{},"qa-info")]:
        t,v,d=call(tool,args,rid)
        if t.get("state")!="PASS":raise SafeFailure("QA_READ_EXECUTION_NOT_PROVEN")
        receipt=t.get("bridge_receipt_sha256") or receipt
    if receipt:
        t,v,d=call("get_receipt",{"receipt_id_or_sha256":receipt},"qa-receipt")
        if t.get("state")!="PASS" or t.get("computer")!="HARAQA5312" or t.get("execution_authority")!="HARA_COMMANDER_AGENT" or v.get("state")!="PASS":raise SafeFailure("QA_RECEIPT_READ_NOT_PROVEN")
    else:raise SafeFailure("QA_DEVICE_RECEIPT_MISSING")
    call("get_usage_stats",{},"qa-usage-after-device")
    s=load();s["portal"]["normal_device_mcp_proof"]=entries;save(s)
    emit("NORMAL_QA_DEVICE_FULL_CHAIN_PASS",state="PASS_NORMAL_SIGNUP_PAIRING_WINDOWS53_REAL_OAUTH_MCP_READ_RECEIPT",subject_id=ctx["user_id"],device_id="HARA-DEVICE-6644a8cb-8a82-4f0f-8828-879a1c5a3261",device_count=1,trial_grants_only=True,credential_values_exposed=False)
    return 0
if __name__=="__main__":
    try:sys.exit(device_main())
    except SafeFailure as e:emit("SAFE_FAILURE",code=str(e),credential_values_exposed=False);sys.exit(1)
    except Exception as e:emit("SAFE_FAILURE",code=type(e).__name__,credential_values_exposed=False);sys.exit(1)
