from pathlib import Path
import json,hashlib,urllib.request,urllib.error,concurrent.futures,datetime
origin="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
old=Path("/tmp_hara/commander-win50-utf8-20261012/apps/commander/release-bundles/commercial-0.3.54-v14-rc-r2")
root=Path("/tmp_hara/commander-win50-utf8-20261012")
rels=("agent/linux.py","agent/windows.ps1","install/linux.sh","install/windows.ps1","release/agent-manifest.json","release/agent-manifest.sig.json","release/release-signing-public.jwk","release/SHA256SUMS")
def req(path,data=None):
    q=urllib.request.Request(origin+path,data=data,headers={"User-Agent":"HARA-Commander-Owned-DEV-Acceptance/1","Cache-Control":"no-cache","Accept":"application/json","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(q,timeout=20) as r:return r.status,r.read(),dict(r.headers)
    except urllib.error.HTTPError as e:return e.code,e.read(),dict(e.headers)
def check(rel):
    status,raw,headers=req("/"+rel)
    digest=hashlib.sha256(raw).hexdigest()
    expected=hashlib.sha256((old/rel).read_bytes()).hexdigest()
    assert status==200 and digest==expected,"DEV_SIGNED_ASSET_DRIFT"
    return {"path":rel,"status":status,"sha256":digest,"bytes":len(raw)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:assets=list(pool.map(check,rels))
status,raw,head=req("/api/health")
assert status==200 and json.loads(raw)=={"ok":True,"service":"hara-commander"}
ctype=next((v for k,v in head.items() if k.lower()=="content-type"),"")
assert ctype.lower()=="application/json; charset=utf-8"
status,raw,head=req("/api/mcp?profile=simple",json.dumps({"jsonrpc":"2.0","id":"anonymous-gate","method":"tools/list","params":{}}).encode())
assert status==401,"MCP_ANONYMOUS_NOT_DENIED"
report={"schema":"hara.full054-dev-readback.v1","state":"PASS","at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"health_http":200,"health_content_type":ctype,"mcp_no_bearer_http":status,"signed_public54_files":assets,"all_eight_exact":True,"production_mutation":False}
p=root/"docs/evidence/commander-full-acceptance-20261012/full-054/dev-readback-r2.json";p.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
print(json.dumps(report,sort_keys=True))