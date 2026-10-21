import {handleCustomerMcpRequest} from "./apps/commander/src/customer-mcp.mjs";
import {handleSimpleCustomerMcpRequest} from "./apps/commander/src/customer-mcp-simple.mjs";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
const synthetic="SYNTHETIC_API_TOKEN_"+("A9B8C7".repeat(8));
const profiles=[
  {name:"FULL",fn:handleCustomerMcpRequest,path:"/api/mcp",tool:"hara.ping"},
  {name:"SIMPLE",fn:handleSimpleCustomerMcpRequest,path:"/mcp",tool:"ping"},
];
let nextId=0;
async function rpc(profile,msg){
 const request=new Request("https://commander.example.invalid"+profile.path,{
  method:"POST",
  headers:{"content-type":"application/json",accept:"application/json, text/event-stream"},
  body:JSON.stringify({jsonrpc:"2.0",id:++nextId,method:"tools/call",
    params:{name:profile.tool,arguments:{computer:"QA_ONLY"}}})
 });
 const response=await profile.fn(request,{
  executeTool:async()=>{throw new Error(msg);},
  authInfo:{token:"SYNTHETIC_ONLY",clientId:"PEER_QA",scopes:["openid"]},
  allowedHosts:["commander.example.invalid"],
 });
 assert.equal(response.status,200);
 const ctype=response.headers.get("content-type")||"";
 const json=ctype.includes("application/json")?await response.json():
  JSON.parse((await response.text()).split(/\r?\n/).find(x=>x.startsWith("data: ")).slice(6));
 return json.result;
}
const checks=[];
for(const p of profiles){
 const m=await rpc(p,synthetic);
 const code=JSON.parse(m.content[0].text).code;
 const permitted=await rpc(p,"POLICY_DENIED");
 const permittedCode=JSON.parse(permitted.content[0].text).code;
 const native=await rpc(p,"FILE_PRECONDITION_FAILED");
 checks.push({
  profile:p.name,
  synthetic_code_was_repeated:code===synthetic,
  synthetic_code_was_redacted:code==="COMMANDER_MCP_TOOL_FAILED",
  policy_denied_preserved:permittedCode==="POLICY_DENIED",
  known_operational_code_preserved:native.structuredContent?.blocker?.code==="FILE_PRECONDITION_FAILED",
  is_error:m.isError===true,
 });
}
const report={
 schema:"hara.commander.peer-r17-error-symbol-allowlist.v1",
 source_sha_full:createHash("sha256").update(await (await import("node:fs/promises")).readFile("./apps/commander/src/customer-mcp.mjs")).digest("hex"),
 source_sha_simple:createHash("sha256").update(await (await import("node:fs/promises")).readFile("./apps/commander/src/customer-mcp-simple.mjs")).digest("hex"),
 scope:"real full and simple MCP handlers, synthetic exception, no network",
 checks,
 exposure_reproduced:checks.some(c=>c.synthetic_code_was_repeated),
 no_real_secrets_used:true,
 production_mutation:false,
};
console.log(JSON.stringify(report,null,2));
process.exitCode=report.exposure_reproduced?2:0;