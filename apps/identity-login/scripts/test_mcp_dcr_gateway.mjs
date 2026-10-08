import assert from "node:assert/strict";
import { createServer } from "node:http";
import {
  classifyDcrRedirectUri,
  DCR_ADMISSION_LIMITS,
  validateDcrRegistration,
} from "../dcr-gateway/dcr-policy.mjs";
import { clientAddress, createDcrGatewayServer } from "../dcr-gateway/server.mjs";

assert.equal(classifyDcrRedirectUri("https://vscode.dev/redirect").type,"web");
assert.equal(classifyDcrRedirectUri("http://127.0.0.1:33418").type,"loopback");
assert.equal(classifyDcrRedirectUri("http://localhost:8787/callback").type,"loopback");
assert.equal(classifyDcrRedirectUri("cursor://anysphere.cursor-mcp/oauth/callback").type,"custom");
assert.throws(()=>classifyDcrRedirectUri("http://example.com/callback"),/SCHEME_FORBIDDEN/);
assert.throws(()=>classifyDcrRedirectUri("javascript:alert(1)"),/SCHEME_FORBIDDEN/);
assert.throws(()=>classifyDcrRedirectUri("file:///tmp/callback"),/SCHEME_FORBIDDEN/);

const vscode=validateDcrRegistration({
  client_name:"Visual Studio Code",
  application_type:"native",
  redirect_uris:["http://127.0.0.1:33418","https://vscode.dev/redirect"],
  grant_types:["authorization_code","refresh_token"],
  response_types:["code"],
  token_endpoint_auth_method:"none",
});
assert.equal(vscode.application_type,"native");
assert.equal(vscode.redirect_uris.length,2);

const cursor=validateDcrRegistration({
  client_name:"Cursor",
  application_type:"native",
  redirect_uris:[
    "cursor://anysphere.cursor-mcp/oauth/callback",
    "https://www.cursor.com/agents/mcp/oauth/callback",
    "http://localhost:8787/callback",
  ],
  grant_types:["authorization_code","refresh_token"],
  response_types:["code"],
  token_endpoint_auth_method:"none",
});
assert.equal(cursor.redirect_uris.length,3);

const inspector=validateDcrRegistration({
  client_name:"MCP Inspector",
  application_type:"native",
  redirect_uris:["http://127.0.0.1:6276/oauth/callback"],
});
assert.equal(inspector.application_type,"native");
assert.deepEqual(inspector.grant_types,["authorization_code","refresh_token"]);

assert.throws(()=>validateDcrRegistration({
  client_name:"Bad",
  redirect_uris:["http://example.com/callback"],
}),/SCHEME_FORBIDDEN/);
assert.throws(()=>validateDcrRegistration({
  client_name:"Bad",
  redirect_uris:["https://client.example/cb"],
  token_endpoint_auth_method:"client_secret_basic",
}),/PUBLIC_CLIENT_REQUIRED/);
assert.throws(()=>validateDcrRegistration({
  client_name:"Bad",
  application_type:"web",
  redirect_uris:["http://127.0.0.1:33418"],
}),/NATIVE_REDIRECT_REQUIRES_NATIVE_APP/);
assert.throws(()=>validateDcrRegistration({
  client_name:"Bad",
  redirect_uris:["https://client.example/cb"],
  grant_types:["client_credentials"],
}),/AUTHORIZATION_CODE_REQUIRED|GRANT_TYPE_NOT_ALLOWED/);
assert.equal(DCR_ADMISSION_LIMITS.max_document_bytes,65536);

const fakeReq=(headers={},remoteAddress="10.0.0.2")=>({
  headers,
  socket:{remoteAddress},
});
assert.equal(
  clientAddress(fakeReq({"cf-connecting-ip":"203.0.113.10","x-forwarded-for":"198.51.100.9"})),
  "cf:203.0.113.10",
);
assert.equal(
  clientAddress(fakeReq({"x-forwarded-for":"198.51.100.9"})),
  "socket:10.0.0.2",
);
assert.equal(
  clientAddress(fakeReq({"x-forwarded-for":"198.51.100.9"}),{trustCfConnectingIp:false,trustForwardedFor:true}),
  "xff:198.51.100.9",
);
assert.equal(
  clientAddress(fakeReq({"cf-connecting-ip":"not-an-ip"})),
  "socket:10.0.0.2",
);

const upstreamRequests=[];
const upstream=createServer(async(req,res)=>{
  const chunks=[];
  for await (const chunk of req) chunks.push(chunk);
  const body=Buffer.concat(chunks).toString("utf8");
  upstreamRequests.push({
    method:req.method,
    url:req.url,
    headers:req.headers,
    body,
  });
  if (req.method === "POST") {
    const input=JSON.parse(body);
    res.writeHead(201,{"content-type":"application/json"});
    return res.end(JSON.stringify({
      client_id:"123456",
      registration_access_token:"test-registration-token",
      registration_client_uri:"https://auth.haralabs.com.br/oauth/v2/register/123456",
      ...input,
    }));
  }
  if (req.method === "GET") {
    res.writeHead(200,{"content-type":"application/json"});
    return res.end(JSON.stringify({client_id:"123456",redirect_uris:["https://client.example/cb"]}));
  }
  res.writeHead(204);
  res.end();
});
await new Promise((resolve,reject)=>{
  upstream.once("error",reject);
  upstream.listen(0,"127.0.0.1",resolve);
});
const upstreamPort=upstream.address().port;

async function startGateway(options) {
  const server=createDcrGatewayServer({
    upstreamHost:"127.0.0.1",
    upstreamPort,
    externalHost:"auth.haralabs.com.br",
    ...options,
  });
  await new Promise((resolve,reject)=>{
    server.once("error",reject);
    server.listen(0,"127.0.0.1",resolve);
  });
  return server;
}

try {
  const closed=await startGateway({mode:"closed"});
  try {
    const base=`http://127.0.0.1:${closed.address().port}`;
    const health=await fetch(base+"/healthz");
    assert.equal(health.status,200);
    const healthBody=await health.json();
    assert.equal(healthBody.mode,"closed");
    assert.equal(healthBody.registration_limit_per_client,10);
    assert.equal(healthBody.registration_global_limit,200);
    assert.equal(healthBody.trust_cf_connecting_ip,true);
    assert.equal(healthBody.trust_forwarded_for,false);

    const denied=await fetch(base+"/oauth/v2/register",{
      method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify(vscode),
    });
    assert.equal(denied.status,404);
    assert.equal(upstreamRequests.length,0);
  } finally {
    await new Promise((resolve)=>closed.close(resolve));
  }

  const guarded=await startGateway({mode:"guarded",registrationLimit:10});
  try {
    const base=`http://127.0.0.1:${guarded.address().port}`;
    const registered=await fetch(base+"/oauth/v2/register",{
      method:"POST",
      headers:{
        "content-type":"application/json",
        "cf-connecting-ip":"203.0.113.40",
        "x-forwarded-for":"198.51.100.200",
      },
      body:JSON.stringify({...cursor,untrusted_extension:"DROP_ME"}),
    });
    assert.equal(registered.status,201);
    const response=await registered.json();
    assert.equal(response.client_id,"123456");
    assert.equal(response.untrusted_extension,undefined);
    assert.equal(upstreamRequests.at(-1).headers.host,"auth.haralabs.com.br");
    assert.equal(upstreamRequests.at(-1).headers["x-forwarded-proto"],"https");
    assert.equal(upstreamRequests.at(-1).headers["cf-connecting-ip"],undefined);
    assert.equal(upstreamRequests.at(-1).headers["x-forwarded-for"],undefined);
    const forwarded=JSON.parse(upstreamRequests.at(-1).body);
    assert.equal(forwarded.untrusted_extension,undefined);
    assert.equal(forwarded.token_endpoint_auth_method,"none");

    const noToken=await fetch(base+"/oauth/v2/register/123456");
    assert.equal(noToken.status,401);

    const managed=await fetch(base+"/oauth/v2/register/123456",{
      headers:{authorization:"Bearer registration-token"},
    });
    assert.equal(managed.status,200);
    assert.equal(upstreamRequests.at(-1).headers.authorization,"Bearer registration-token");

    const bad=await fetch(base+"/oauth/v2/register",{
      method:"POST",
      headers:{"content-type":"application/json","cf-connecting-ip":"203.0.113.41"},
      body:JSON.stringify({client_name:"Bad",redirect_uris:["http://evil.example/cb"]}),
    });
    assert.equal(bad.status,400);
  } finally {
    await new Promise((resolve)=>guarded.close(resolve));
  }

  const limited=await startGateway({
    mode:"guarded",
    registrationLimit:1,
    registrationGlobalLimit:50,
    registrationWindowMs:60000,
  });
  try {
    const base=`http://127.0.0.1:${limited.address().port}`;
    const payload=JSON.stringify(vscode);
    const first=await fetch(base+"/oauth/v2/register",{
      method:"POST",
      headers:{"content-type":"application/json","cf-connecting-ip":"203.0.113.50"},
      body:payload,
    });
    assert.equal(first.status,201);
    const second=await fetch(base+"/oauth/v2/register",{
      method:"POST",
      headers:{"content-type":"application/json","cf-connecting-ip":"203.0.113.50"},
      body:payload,
    });
    assert.equal(second.status,429);
    assert.ok(Number(second.headers.get("retry-after")) >= 1);
  } finally {
    await new Promise((resolve)=>limited.close(resolve));
  }
  const globallyLimited=await startGateway({
    mode:"guarded",
    registrationLimit:10,
    registrationGlobalLimit:2,
    registrationWindowMs:60000,
  });
  try {
    const base=`http://127.0.0.1:${globallyLimited.address().port}`;
    const payload=JSON.stringify(vscode);
    for (const ip of ["203.0.113.61","203.0.113.62"]) {
      const response=await fetch(base+"/oauth/v2/register",{
        method:"POST",
        headers:{"content-type":"application/json","cf-connecting-ip":ip},
        body:payload,
      });
      assert.equal(response.status,201);
    }
    const third=await fetch(base+"/oauth/v2/register",{
      method:"POST",
      headers:{"content-type":"application/json","cf-connecting-ip":"203.0.113.63"},
      body:payload,
    });
    assert.equal(third.status,429);
    assert.ok(Number(third.headers.get("retry-after")) >= 1);
  } finally {
    await new Promise((resolve)=>globallyLimited.close(resolve));
  }

} finally {
  await new Promise((resolve)=>upstream.close(resolve));
}

console.log("HARA_IDENTITY_DCR_POLICY_VSCODE=PASS");
console.log("HARA_IDENTITY_DCR_POLICY_CURSOR=PASS");
console.log("HARA_IDENTITY_DCR_POLICY_INSPECTOR=PASS");
console.log("HARA_IDENTITY_DCR_PUBLIC_CLIENT_ONLY=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_CLOSED_FAIL_CLOSED=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_GUARDED_PROXY=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_METADATA_SANITIZED=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_MANAGEMENT_TOKEN=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_RATE_LIMIT=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_GLOBAL_RATE_LIMIT=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_CF_IP_TRUST=PASS");
console.log("HARA_IDENTITY_DCR_GATEWAY_SOURCE=PASS");
