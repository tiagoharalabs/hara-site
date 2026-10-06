import assert from "node:assert/strict";
import nodeCrypto from "node:crypto";
import {
  CUSTOMER_MCP_SIMPLE_TOOLS,
  handleSimpleCustomerMcpRequest,
} from "../src/customer-mcp-simple.mjs";

if (!globalThis.crypto) {
  Object.defineProperty(globalThis, "crypto", {
    value: nodeCrypto.webcrypto,
    configurable: true,
  });
}

const endpoint="https://mcp.haralabs.com.br/mcp?profile=simple";
const calls=[];

async function executeTool(request) {
  calls.push(request);
  return {
    state:"PASS",
    operational_authority:"HARA_COMMANDER",
    runtime_authority_from_chatgpt:false,
    mutation_performed:false,
    tool_id:request.tool_id,
    result:{ok:true,echo:request.arguments},
  };
}

async function rpc(id,method,params=undefined) {
  const body={jsonrpc:"2.0",id,method};
  if (params !== undefined) body.params=params;
  const request=new Request(endpoint,{
    method:"POST",
    headers:{
      "content-type":"application/json",
      accept:"application/json, text/event-stream",
      "x-request-id":`simple-http-${id}`,
    },
    body:JSON.stringify(body),
  });
  const response=await handleSimpleCustomerMcpRequest(request,{
    executeTool,
    authInfo:{token:"redacted",clientId:"HARA-SIMPLE-TEST",scopes:["openid"]},
    allowedHosts:["mcp.haralabs.com.br"],
  });
  assert.equal(response.status,200);
  const contentType=String(response.headers.get("content-type") || "");
  if (contentType.includes("application/json")) return response.json();
  const text=await response.text();
  const dataLine=text.split(/\r?\n/).find((line)=>line.startsWith("data: "));
  assert.ok(dataLine);
  return JSON.parse(dataLine.slice(6));
}

await rpc(1,"initialize",{
  protocolVersion:"2025-06-18",
  capabilities:{},
  clientInfo:{name:"simple-test",version:"1"},
});

const listed=await rpc(2,"tools/list",{});
const tools=listed.result?.tools || [];
assert.deepEqual(tools.map((tool)=>tool.name),CUSTOMER_MCP_SIMPLE_TOOLS);
assert.equal(tools.length,24);
assert.ok(!tools.some((tool)=>tool.name.startsWith("hara.")));
assert.ok(tools.some((tool)=>tool.name==="read_file"));
assert.ok(tools.some((tool)=>tool.name==="write_file"));
assert.ok(tools.some((tool)=>tool.name==="start_process"));
assert.ok(tools.some((tool)=>tool.name==="read_process_output"));

const readCall=await rpc(3,"tools/call",{
  name:"read_file",
  arguments:{computer:"nucleo-a",path:"/tmp/a.txt",offset:2,length:10},
});
assert.equal(readCall.result?.isError,undefined);
assert.equal(calls.at(-1).tool_id,"hara.files.read");
assert.deepEqual(calls.at(-1).arguments,{
  computer:"nucleo-a",path:"/tmp/a.txt",offset:2,length:10,
});

await rpc(4,"tools/call",{
  name:"edit_block",
  arguments:{computer:"nucleo-a",path:"/tmp/a.txt",old_string:"A",new_string:"B"},
});
assert.equal(calls.at(-1).tool_id,"hara.files.edit");
assert.deepEqual(calls.at(-1).arguments,{
  computer:"nucleo-a",path:"/tmp/a.txt",old_text:"A",new_text:"B",replace_all:false,
});

await rpc(5,"tools/call",{
  name:"start_process",
  arguments:{computer:"nucleo-a",command:"printf hi"},
});
assert.equal(calls.at(-1).tool_id,"hara.process.run");
assert.equal(calls.at(-1).arguments.timeout_ms,3000);
assert.equal(calls.at(-1).arguments.max_lines,200);

await rpc(6,"tools/call",{
  name:"start_process",
  arguments:{computer:"nucleo-a",command:"python3 -i",interactive:true},
});
assert.equal(calls.at(-1).tool_id,"hara.process.start");
assert.equal(calls.at(-1).arguments.timeout_ms,1000);
assert.ok(!("max_lines" in calls.at(-1).arguments));

await rpc(7,"tools/call",{
  name:"search",
  arguments:{computer:"nucleo-a",path:"/srv/project",pattern:"TODO",search_type:"content"},
});
assert.equal(calls.at(-1).tool_id,"hara.files.search");
assert.equal(calls.at(-1).arguments.search_type,"content");

await rpc(8,"tools/call",{
  name:"get_activity",
  arguments:{computer:"nucleo-a",window:"24h",limit:10},
});
assert.equal(calls.at(-1).tool_id,"hara.activity.local");
assert.equal(calls.at(-1).arguments.computer,"nucleo-a");
assert.equal(calls.at(-1).arguments.window,"24h");
assert.equal(calls.at(-1).arguments.limit,10);

await rpc(9,"tools/call",{
  name:"get_recent_tool_calls",
  arguments:{computer:"nucleo-a",limit:20},
});
assert.equal(calls.at(-1).tool_id,"hara.calls.recent.local");
assert.equal(calls.at(-1).arguments.limit,20);

for (const tool of tools) {
  assert.deepEqual(tool._meta?.securitySchemes,[{type:"oauth2",scopes:["openid"]}]);
}

const mutating=new Set([
  "write_file","edit_block","create_directory","move_file","copy_file","delete_file",
  "start_process","interact_with_process","kill_process",
]);
for (const tool of tools) {
  assert.equal(tool.annotations?.readOnlyHint,!mutating.has(tool.name));
}

console.log("COMMANDER_SIMPLE_MCP_TOOL_COUNT=24");
console.log("COMMANDER_SIMPLE_MCP_HARA_PREFIX_EXPOSED=FALSE");
console.log("COMMANDER_SIMPLE_MCP_PROCESS_ONE_SHOT_DEFAULT=PASS");
console.log("COMMANDER_SIMPLE_MCP_INTERACTIVE_OPT_IN=PASS");
console.log("COMMANDER_SIMPLE_MCP_ALIAS_ROUTING=PASS");
console.log("COMMANDER_SIMPLE_MCP=PASS");
