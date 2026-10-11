import assert from "node:assert/strict";
import { CUSTOMER_MCP_SIMPLE_TOOLS, handleSimpleCustomerMcpRequest } from "../src/customer-mcp-simple.mjs";

const endpoint="https://mcp.haralabs.com.br/mcp?profile=simple";
let id=0;
const calls=[];
async function rpc(name,args){
  const request=new Request(endpoint,{
    method:"POST",
    headers:{"content-type":"application/json",accept:"application/json, text/event-stream","x-request-id":"admin-"+(++id)},
    body:JSON.stringify({jsonrpc:"2.0",id,method:"tools/call",params:{name,arguments:args}}),
  });
  const response=await handleSimpleCustomerMcpRequest(request,{
    executeTool:async call=>{calls.push(call);return {state:"PASS",result:{ok:true,echo:call.arguments}};},
    authInfo:{token:"redacted",clientId:"ADMIN_PROFILE_TEST",scopes:["openid"]},
    allowedHosts:["mcp.haralabs.com.br"],
  });
  assert.equal(response.status,200);
  const ct=String(response.headers.get("content-type")||"");
  let payload;
  if(ct.includes("application/json")) payload=await response.json();
  else {
    const line=(await response.text()).split(/\r?\n/).find(x=>x.startsWith("data: "));
    assert.ok(line);payload=JSON.parse(line.slice(6));
  }
  assert.notEqual(payload.result?.isError,true);
  return calls.at(-1);
}

assert.equal(CUSTOMER_MCP_SIMPLE_TOOLS.length,32);
for(const n of ["get_system_uptime","get_system_resources","inspect_workspace","hash_file","diff_files"]){
  assert.ok(CUSTOMER_MCP_SIMPLE_TOOLS.includes(n));
}

let c=await rpc("get_system_uptime",{computer:"services"});
assert.equal(c.tool_id,"hara.system.uptime");
assert.deepEqual(c.arguments,{computer:"services"});

c=await rpc("get_system_resources",{computer:"services"});
assert.equal(c.tool_id,"hara.system.resources");
assert.deepEqual(c.arguments,{computer:"services"});

c=await rpc("inspect_workspace",{computer:"services",path:"/srv/hara",max_entries:17});
assert.equal(c.tool_id,"hara.workspace.inspect");
assert.deepEqual(c.arguments,{computer:"services",path:"/srv/hara",max_entries:17});

c=await rpc("hash_file",{computer:"services",path:"/etc/hostname"});
assert.equal(c.tool_id,"hara.files.hash");
assert.deepEqual(c.arguments,{computer:"services",path:"/etc/hostname"});

c=await rpc("diff_files",{computer:"services",left:"/tmp/a",right:"/tmp/b",max_lines:37});
assert.equal(c.tool_id,"hara.files.diff");
assert.deepEqual(c.arguments,{computer:"services",left:"/tmp/a",right:"/tmp/b",max_lines:37});

for(const c of calls) {
  assert.equal(c.mcp_request_id!==undefined,true);
  assert.ok(c.transport_request_id);
}
console.log(JSON.stringify({schema:"hara.commander-admin-profile.v1",checked:5,passed:5,failed:0,tool_count:CUSTOMER_MCP_SIMPLE_TOOLS.length}));
