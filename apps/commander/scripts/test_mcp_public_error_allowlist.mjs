#!/usr/bin/env node
// Full and Simple share a public error allowlist; no network, no real secrets.
import assert from "node:assert/strict";
import {handleCustomerMcpRequest} from "../src/customer-mcp.mjs";
import {handleSimpleCustomerMcpRequest} from "../src/customer-mcp-simple.mjs";

let rpcId=0;
const CASES=[
  {name:"FULL",fn:handleCustomerMcpRequest,path:"/api/mcp",tool:"hara.ping"},
  {name:"SIMPLE",fn:handleSimpleCustomerMcpRequest,path:"/mcp",tool:"ping"},
];
async function invoke(profile, errorMessage) {
  const request = new Request("https://commander.example.invalid"+profile.path,{
    method:"POST",
    headers:{"content-type":"application/json",accept:"application/json, text/event-stream"},
    body:JSON.stringify({jsonrpc:"2.0",id:++rpcId,method:"tools/call",
       params:{name:profile.tool,arguments:{computer:"qa"}}}),
  });
  const resp=await profile.fn(request,{
    executeTool:async()=>{throw new Error(errorMessage)},
    authInfo:{token:"FAKE_QA_ONLY",clientId:"QA_ONLY",scopes:["openid"]},
    allowedHosts:["commander.example.invalid"],
  });
  assert.equal(resp.status,200);
  const ct=resp.headers.get("content-type")||"";
  const payload=ct.includes("application/json")?await resp.json():
    JSON.parse((await resp.text()).split(/\r?\n/).find(x=>x.startsWith("data: ")).slice(6));
  assert.equal(payload.result?.isError,true);
  return payload.result;
}
const report=[];
const madeUp=[
  "SYNTHETIC_API_TOKEN_"+("A9B8C7".repeat(8)),
  "FAKE_SESSION_KEY_"+("B7C3D9".repeat(7)),
  "TOTALLY_UNKNOWN_EXCEPTION_CODE_20261021",
];
for (const profile of CASES) {
  for (const sample of madeUp) {
    const r=await invoke(profile,sample);
    assert.equal(JSON.parse(r.content[0].text).code,"COMMANDER_MCP_TOOL_FAILED");
    report.push(profile.name+"_UNKNOWN_SYMBOL_REDACTED");
  }
  const policy=await invoke(profile,"POLICY_DENIED");
  assert.equal(JSON.parse(policy.content[0].text).code,"POLICY_DENIED");
  report.push(profile.name+"_POLICY_CODE_PRESERVED");
  const known=await invoke(profile,"FILE_PRECONDITION_FAILED");
  assert.equal(known.structuredContent.blocker.code,"FILE_PRECONDITION_FAILED");
  assert.equal(known.structuredContent.state,"CONFLICT");
  report.push(profile.name+"_OPERATIONAL_CODE_PRESERVED");
}
console.log(JSON.stringify({
 schema:"hara.commander.mcp-error-allowlist-acceptance.v1",
 checked:report.length, passed:report.length, no_network:true,
 real_credentials:false, cases:report,
},null,2));
