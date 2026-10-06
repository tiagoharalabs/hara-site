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
  if (request.arguments?.path === "/__hara_conformance_error__") {
    throw new Error("CONFORMANCE_EXPECTED_ERROR");
  }
  return {
    state:"PASS",
    operational_authority:"HARA_COMMANDER",
    execution_authority:"HARA_COMMANDER_AGENT",
    runtime_authority_from_chatgpt:false,
    mutation_performed:false,
    customer_services_relay:false,
    result:{ok:true,echo:request.arguments},
  };
}

async function decode(response) {
  const text=await response.text();
  const contentType=String(response.headers.get("content-type") || "");
  if (contentType.includes("application/json")) return JSON.parse(text);
  const line=text.split(/\r?\n/).find((item)=>item.startsWith("data: "));
  assert.ok(line,"SSE data line missing");
  return JSON.parse(line.slice(6));
}

async function legacyRpc(protocolVersion,id,method,params=undefined) {
  const body={jsonrpc:"2.0",id,method};
  if (params !== undefined) body.params=params;
  const response=await handleSimpleCustomerMcpRequest(new Request(endpoint,{
    method:"POST",
    headers:{
      "content-type":"application/json",
      accept:"application/json, text/event-stream",
      "x-request-id":`legacy-${protocolVersion}-${id}`,
    },
    body:JSON.stringify(body),
  }),{
    executeTool,
    authInfo:{token:"redacted",clientId:"HARA-CONFORMANCE",scopes:["openid"]},
    allowedHosts:["mcp.haralabs.com.br"],
  });
  return {response,payload:await decode(response)};
}

function modernMeta() {
  return {
    "io.modelcontextprotocol/protocolVersion":"2026-07-28",
    "io.modelcontextprotocol/clientCapabilities":{},
    "io.modelcontextprotocol/clientInfo":{
      name:"hara-modern-conformance",
      version:"1",
    },
  };
}

async function modernRpc(id,method,params={},options={}) {
  const bodyParams={...params,_meta:modernMeta()};
  const body={jsonrpc:"2.0",id,method,params:bodyParams};
  const headers={
    "content-type":"application/json",
    accept:"application/json, text/event-stream",
    "x-request-id":`modern-${id}`,
  };
  if (!options.omitProtocolHeader) headers["MCP-Protocol-Version"]="2026-07-28";
  if (!options.omitMethodHeader) headers["Mcp-Method"]=method;
  if (params.name && !options.omitNameHeader) headers["Mcp-Name"]=params.name;
  const response=await handleSimpleCustomerMcpRequest(new Request(endpoint,{
    method:"POST",
    headers,
    body:JSON.stringify(body),
  }),{
    executeTool,
    authInfo:{token:"redacted",clientId:"HARA-CONFORMANCE",scopes:["openid"]},
    allowedHosts:["mcp.haralabs.com.br"],
  });
  return {response,payload:await decode(response)};
}

function assertToolContract(tools) {
  assert.deepEqual(tools.map((tool)=>tool.name),CUSTOMER_MCP_SIMPLE_TOOLS);
  assert.equal(tools.length,24);
  assert.ok(!tools.some((tool)=>tool.name.startsWith("hara.")));
  for (const tool of tools) {
    assert.equal(tool.inputSchema?.type,"object",`${tool.name}: input schema root`);
    assert.equal(tool.outputSchema?.type,"object",`${tool.name}: output schema root`);
    assert.equal(typeof tool.title,"string",`${tool.name}: title`);
    assert.ok(String(tool.description || "").length >= 10,`${tool.name}: description`);
    for (const hint of ["readOnlyHint","destructiveHint","idempotentHint","openWorldHint"]) {
      assert.equal(typeof tool.annotations?.[hint],"boolean",`${tool.name}: ${hint}`);
    }
    assert.deepEqual(tool._meta?.securitySchemes,[{type:"oauth2",scopes:["openid"]}]);
  }
  const read=tools.find((tool)=>tool.name==="read_file");
  assert.match(read.inputSchema?.properties?.computer?.description || "",/Optional enrolled computer name/);
}

for (const version of ["2025-06-18","2025-11-25"]) {
  const init=await legacyRpc(version,1,"initialize",{
    protocolVersion:version,
    capabilities:{},
    clientInfo:{name:"hara-legacy-conformance",version:"1"},
  });
  assert.equal(init.response.status,200);
  assert.equal(init.payload.result?.protocolVersion,version);
  assert.equal(init.payload.result?.serverInfo?.name,"H.A.R.A. Commander Simple");
  assert.equal(init.payload.result?.serverInfo?.title,"H.A.R.A. Commander");
  assert.equal(init.payload.result?.serverInfo?.version,"1.1.0");
  assert.equal(init.payload.result?.serverInfo?.websiteUrl,"https://commander.haralabs.com.br");
  assert.match(init.payload.result?.serverInfo?.description || "",/client-neutral/);
  assert.equal(init.payload.result?.serverInfo?.icons?.[0]?.mimeType,"image/webp");
  assert.match(init.payload.result?.instructions || "",/client-neutral/);
  assert.ok(init.payload.result?.capabilities?.tools);
  assert.equal(init.payload.result?.capabilities?.prompts,undefined);
  assert.equal(init.payload.result?.capabilities?.resources,undefined);

  const listed=await legacyRpc(version,2,"tools/list",{});
  assert.equal(listed.response.status,200);
  assertToolContract(listed.payload.result?.tools || []);
  console.log("COMMANDER_MCP_CONFORMANCE_LEGACY_"+version.replaceAll("-","_")+"=PASS");
}

const discover=await modernRpc(10,"server/discover",{});
assert.equal(discover.response.status,200);
assert.ok(discover.payload.result?.supportedVersions?.includes("2026-07-28"));
assert.ok(discover.payload.result?.capabilities?.tools);
assert.equal(discover.payload.result?.capabilities?.prompts,undefined);
assert.equal(discover.payload.result?.capabilities?.resources,undefined);
assert.equal(discover.payload.result?.resultType,"complete");
assert.equal(discover.payload.result?._meta?.["io.modelcontextprotocol/serverInfo"]?.version,"1.1.0");
assert.equal(discover.payload.result?._meta?.["io.modelcontextprotocol/serverInfo"]?.title,"H.A.R.A. Commander");
assert.equal(discover.payload.result?._meta?.["io.modelcontextprotocol/serverInfo"]?.websiteUrl,"https://commander.haralabs.com.br");

const modernList=await modernRpc(11,"tools/list",{});
assert.equal(modernList.response.status,200);
assert.equal(modernList.payload.result?.resultType,"complete");
assertToolContract(modernList.payload.result?.tools || []);

const modernCall=await modernRpc(12,"tools/call",{
  name:"read_file",
  arguments:{computer:"nucleo-a",path:"/tmp/a.txt",offset:0,length:10},
});
assert.equal(modernCall.response.status,200);
assert.equal(modernCall.payload.result?.isError,undefined);
assert.equal(modernCall.payload.result?.resultType,"complete");
assert.equal(modernCall.payload.result?.structuredContent?.state,"PASS");
assert.equal(calls.at(-1)?.tool_id,"hara.files.read");
assert.equal(calls.at(-1)?.transport_request_id,"modern-12");

const expectedError=await modernRpc(13,"tools/call",{
  name:"read_file",
  arguments:{path:"/__hara_conformance_error__"},
});
assert.equal(expectedError.response.status,200);
assert.equal(expectedError.payload.result?.isError,true);
assert.match(expectedError.payload.result?.content?.[0]?.text || "",/CONFORMANCE_EXPECTED_ERROR/);

const missingProtocol=await modernRpc(14,"server/discover",{},{
  omitProtocolHeader:true,
});
assert.equal(missingProtocol.response.status,400);
assert.match(missingProtocol.payload.error?.message || "",/MCP-Protocol-Version/i);

const missingMethod=await modernRpc(15,"server/discover",{},{
  omitMethodHeader:true,
});
assert.equal(missingMethod.response.status,400);
assert.match(missingMethod.payload.error?.message || "",/Mcp-Method/i);

console.log("COMMANDER_MCP_CONFORMANCE_MODERN_2026_07_28=PASS");
console.log("COMMANDER_MCP_CONFORMANCE_OUTPUT_SCHEMA=PASS");
console.log("COMMANDER_MCP_CONFORMANCE_SERVER_INSTRUCTIONS=PASS");
console.log("COMMANDER_MCP_CONFORMANCE_ANNOTATIONS=PASS");
console.log("COMMANDER_MCP_CONFORMANCE_SECURITY_SCHEMES=PASS");
console.log("COMMANDER_MCP_CONFORMANCE_FAIL_CLOSED_HEADERS=PASS");
console.log("COMMANDER_MCP_CLIENT_CONFORMANCE=PASS");
