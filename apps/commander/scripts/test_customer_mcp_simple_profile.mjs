import assert from "node:assert/strict";
import {
  CUSTOMER_MCP_SIMPLE_TOOLS,
  handleSimpleCustomerMcpRequest,
} from "../src/customer-mcp-simple.mjs";

const endpoint="https://mcp.haralabs.com.br/mcp?profile=simple";
const calls=[];

async function executeTool(request) {
  calls.push(request);
  if (request.arguments?.computer === "__offline__") throw new Error("DEVICE_OFFLINE");
  if (request.arguments?.computer === "__missing__") throw new Error("FILENOTFOUNDERROR");
  if (request.arguments?.computer === "__parent_missing__") throw new Error("PARENT_DIRECTORY_NOT_FOUND");
  if (request.arguments?.computer === "__winparent__") throw new Error("FILESYSTEM_PARENT_NOT_FOUND");
  if (request.arguments?.computer === "__winexists__") throw new Error("FILESYSTEM_PATH_EXISTS");
  if (request.arguments?.computer === "__windir__") throw new Error("FILESYSTEM_NOT_DIRECTORY");
  if (request.arguments?.computer === "__session_missing__") throw new Error("PROCESS_SESSION_NOT_FOUND");
  if (request.arguments?.computer === "__busy__") throw new Error("DEVICE_BUSY");
  if (request.arguments?.computer === "__timeout__") throw new Error("DEVICE_CALL_TIMEOUT");
  if (request.arguments?.computer === "__exists__") throw new Error("DESTINATION_EXISTS");
  if (request.arguments?.computer === "__ambiguous__") throw new Error("COMPUTER_NAME_AMBIGUOUS");
  if (request.arguments?.computer === "__denied__") throw new Error("POLICY_DENIED");
  if (request.arguments?.computer === "__local_tunnel__") throw new Error("DEVICE_LOCAL_TUNNEL_DIRECT_PATH_REQUIRED");
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
assert.equal(tools.length,27);
assert.ok(!tools.some((tool)=>tool.name.startsWith("hara.")));
assert.ok(tools.some((tool)=>tool.name==="read_file"));
assert.ok(tools.some((tool)=>tool.name==="write_file"));
assert.ok(tools.some((tool)=>tool.name==="start_process"));
assert.ok(tools.some((tool)=>tool.name==="read_process_output"));
assert.ok(tools.some((tool)=>tool.name==="list_file_preimages"));
assert.ok(tools.some((tool)=>tool.name==="rollback_file"));
assert.ok(tools.some((tool)=>tool.name==="get_receipt"));

const schema=(name)=>tools.find((tool)=>tool.name===name)?.inputSchema?.properties || {};
assert.equal(schema("read_file").offset.maximum,1000000);
assert.equal(schema("read_file").length.maximum,400);
assert.equal(schema("read_multiple_files").offset.maximum,1000000);
assert.equal(schema("read_multiple_files").length.maximum,100);
assert.equal(schema("write_file").content.maxLength,65536);
assert.equal(schema("edit_block").old_string.maxLength,32768);
assert.equal(schema("edit_block").new_string.maxLength,32768);
assert.equal(schema("list_file_preimages").limit.maximum,100);
assert.equal(schema("get_receipt").receipt_id_or_sha256.maxLength,256);
assert.equal(schema("rollback_file").preimage_id.type,"string");
assert.equal(schema("list_directory").depth.maximum,5);
assert.equal(schema("list_directory").limit.maximum,200);
assert.equal(schema("search").pattern.maxLength,256);
assert.equal(schema("search").max_results.maximum,100);
assert.equal(schema("search").file_glob.maxLength,180);
assert.equal(schema("list_processes").limit.maximum,200);
assert.equal(schema("read_process_output").session_id.maxLength,180);
assert.equal(schema("read_process_output").offset.maximum,1000000);
assert.equal(schema("read_process_output").timeout_ms.maximum,3000);
assert.equal(schema("interact_with_process").session_id.maxLength,180);
assert.equal(schema("interact_with_process").input.maxLength,4096);
assert.equal(schema("interact_with_process").timeout_ms.maximum,3000);

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

await rpc(101,"tools/call",{name:"list_file_preimages",arguments:{
  computer:"nucleo-a",path:"/tmp/a.txt",limit:20,
}});
assert.equal(calls.at(-1).tool_id,"hara.files.preimages.list");
assert.deepEqual(calls.at(-1).arguments,{computer:"nucleo-a",path:"/tmp/a.txt",limit:20});

const preimageId="HARA-PREIMAGE-"+"a".repeat(32);
await rpc(102,"tools/call",{name:"rollback_file",arguments:{
  computer:"nucleo-a",preimage_id:preimageId,
}});
assert.equal(calls.at(-1).tool_id,"hara.files.rollback");
assert.deepEqual(calls.at(-1).arguments,{computer:"nucleo-a",preimage_id:preimageId});

await rpc(103,"tools/call",{name:"get_receipt",arguments:{
  computer:"nucleo-a",receipt_id_or_sha256:"receipt-sha-test",
}});
assert.equal(calls.at(-1).tool_id,"hara.receipts.get");
assert.deepEqual(calls.at(-1).arguments,{computer:"nucleo-a",receipt_id_or_sha256:"receipt-sha-test"});

await rpc(104,"tools/call",{name:"list_directory",arguments:{
  computer:"nucleo-a",path:"/tmp",limit:10,depth:2,offset:55,
}});
assert.equal(calls.at(-1).tool_id,"hara.files.list");
assert.deepEqual(calls.at(-1).arguments,{
  computer:"nucleo-a",path:"/tmp",limit:10,depth:2,offset:55,
});

await rpc(6,"tools/call",{
  name:"start_process",
  arguments:{computer:"nucleo-a",command:"python3 -i",interactive:true},
});
assert.equal(calls.at(-1).tool_id,"hara.process.start");
assert.equal(calls.at(-1).arguments.timeout_ms,1000);
assert.ok(!("max_lines" in calls.at(-1).arguments));

const longProcess = await rpc(60,"tools/call",{
  name:"start_process",
  arguments:{computer:"nucleo-a",command:"sleep 12",timeout_ms:20000},
});
assert.equal(longProcess.result?.isError,undefined);
assert.equal(calls.at(-1).tool_id,"hara.process.start");
assert.equal(calls.at(-1).arguments.timeout_ms,3000);
assert.ok(!("max_lines" in calls.at(-1).arguments));

await rpc(7,"tools/call",{
  name:"search",
  arguments:{computer:"nucleo-a",path:"/srv/project",pattern:"TODO",search_type:"content"},
});
assert.equal(calls.at(-1).tool_id,"hara.files.search");
assert.equal(calls.at(-1).arguments.search_type,"content");

await rpc(8,"tools/call",{
  name:"get_recent_tool_calls",
  arguments:{computer:"nucleo-a",limit:20},
});
assert.equal(calls.at(-1).tool_id,"hara.calls.recent");
assert.equal(calls.at(-1).arguments.limit,20);

const offlinePing = await rpc(9,"tools/call",{
  name:"ping",
  arguments:{computer:"__offline__"},
});
assert.equal(offlinePing.result?.isError,undefined);
assert.equal(offlinePing.result?.structuredContent?.state,"UNAVAILABLE");
assert.equal(offlinePing.result?.structuredContent?.blocker?.code,"DEVICE_OFFLINE");
assert.equal(offlinePing.result?.structuredContent?.blocker?.retryable,true);
assert.equal(offlinePing.result?.structuredContent?.computer,"__offline__");

const missingInfo = await rpc(91,"tools/call",{name:"get_file_info",arguments:{computer:"__missing__",path:"/tmp/missing"}});
assert.equal(missingInfo.result?.isError,undefined);
assert.equal(missingInfo.result?.structuredContent?.state,"NOT_FOUND");
assert.equal(missingInfo.result?.structuredContent?.blocker?.code,"FILENOTFOUNDERROR");

const parentMissing = await rpc(92,"tools/call",{name:"write_file",arguments:{computer:"__parent_missing__",path:"/tmp/no-parent/file",content:"x",mode:"rewrite"}});
assert.equal(parentMissing.result?.structuredContent?.state,"NOT_FOUND");
assert.equal(parentMissing.result?.structuredContent?.result?.recommended_tool,"hara.files.create_directory");

const sessionMissing = await rpc(93,"tools/call",{name:"read_process_output",arguments:{computer:"__session_missing__",session_id:"missing",length:20}});
assert.equal(sessionMissing.result?.structuredContent?.state,"NOT_FOUND");
assert.equal(sessionMissing.result?.structuredContent?.result?.recommended_tool,"hara.process.sessions");

const busy = await rpc(94,"tools/call",{name:"ping",arguments:{computer:"__busy__"}});
assert.equal(busy.result?.structuredContent?.state,"BUSY");
assert.equal(busy.result?.structuredContent?.blocker?.retryable,true);

const timeout = await rpc(95,"tools/call",{name:"start_process",arguments:{computer:"__timeout__",command:"sleep 1",timeout_ms:500}});
assert.equal(timeout.result?.structuredContent?.state,"TIMEOUT");
assert.equal(timeout.result?.structuredContent?.blocker?.retryable,true);

const conflict = await rpc(96,"tools/call",{name:"copy_file",arguments:{computer:"__exists__",source:"/tmp/a",destination:"/tmp/b"}});
assert.equal(conflict.result?.structuredContent?.state,"CONFLICT");

const winParent = await rpc(961,"tools/call",{name:"write_file",arguments:{computer:"__winparent__",path:"C:/missing/file",content:"x",mode:"rewrite"}});
assert.equal(winParent.result?.structuredContent?.state,"NOT_FOUND");
assert.equal(winParent.result?.structuredContent?.result?.recommended_tool,"hara.files.create_directory");
const winExists = await rpc(962,"tools/call",{name:"create_directory",arguments:{computer:"__winexists__",path:"C:/exists"}});
assert.equal(winExists.result?.structuredContent?.state,"CONFLICT");
const winDir = await rpc(963,"tools/call",{name:"list_directory",arguments:{computer:"__windir__",path:"C:/file"}});
assert.equal(winDir.result?.structuredContent?.state,"INVALID_TARGET");

const ambiguous = await rpc(97,"tools/call",{name:"ping",arguments:{computer:"__ambiguous__"}});
assert.equal(ambiguous.result?.structuredContent?.state,"NEEDS_INPUT");
assert.equal(ambiguous.result?.structuredContent?.result?.selection_required,true);

const localTunnel = await rpc(99,"tools/call",{name:"ping",arguments:{computer:"__local_tunnel__"}});
assert.equal(localTunnel.result?.isError,undefined);
assert.equal(localTunnel.result?.structuredContent?.state,"DIRECT_PATH_REQUIRED");
assert.equal(localTunnel.result?.structuredContent?.blocker?.retryable,false);
assert.equal(localTunnel.result?.structuredContent?.result?.recommended_transport,"LOCAL_TUNNEL");
assert.equal(localTunnel.result?.structuredContent?.result?.remote_relay_required,false);

const denied = await rpc(98,"tools/call",{name:"ping",arguments:{computer:"__denied__"}});
assert.equal(denied.result?.isError,true);
assert.match(denied.result?.content?.[0]?.text || "",/POLICY_DENIED/);

for (const tool of tools) {
  assert.deepEqual(tool._meta?.securitySchemes,[{type:"oauth2",scopes:["openid"]}]);
}

const mutating=new Set([
  "write_file","edit_block","create_directory","move_file","copy_file","delete_file",
  "rollback_file","start_process","interact_with_process","kill_process",
]);
for (const tool of tools) {
  assert.equal(tool.annotations?.readOnlyHint,!mutating.has(tool.name));
}
assert.equal(tools.find((x)=>x.name==="start_process")?.annotations?.destructiveHint,true);
assert.equal(tools.find((x)=>x.name==="rollback_file")?.annotations?.destructiveHint,true);
console.log("COMMANDER_SIMPLE_MCP_PROCESS_RISK_HONEST=PASS");

console.log("COMMANDER_SIMPLE_MCP_TOOL_COUNT=27");
console.log("COMMANDER_SIMPLE_MCP_ROLLBACK_AND_AUDIT=PASS");
console.log("COMMANDER_SIMPLE_MCP_HARA_PREFIX_EXPOSED=FALSE");
console.log("COMMANDER_SIMPLE_MCP_PROCESS_ONE_SHOT_DEFAULT=PASS");
console.log("COMMANDER_SIMPLE_MCP_INTERACTIVE_OPT_IN=PASS");
console.log("COMMANDER_SIMPLE_MCP_ALIAS_ROUTING=PASS");
console.log("COMMANDER_SIMPLE_MCP_DOWNSTREAM_BOUNDS=PASS");
console.log("COMMANDER_SIMPLE_MCP=PASS");
