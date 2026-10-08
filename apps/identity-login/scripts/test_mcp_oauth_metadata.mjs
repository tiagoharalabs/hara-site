import assert from "node:assert/strict";
import { createOAuthMetadataServer, oauthMetadataForIssuer } from "../oauth-metadata/server.mjs";
import { CIMD_ADMISSION_LIMITS, validateCimdClientIdUrl, validateCimdDocument } from "../oauth-metadata/cimd-policy.mjs";
import { resolveCimdPublicAddresses } from "../oauth-metadata/cimd-fetch.mjs";

const issuer="https://auth.haralabs.com.br";
const metadata=oauthMetadataForIssuer(issuer);
assert.equal(metadata.issuer,issuer);
assert.equal(metadata.authorization_endpoint,issuer+"/oauth/v2/authorize");
assert.equal(metadata.token_endpoint,issuer+"/oauth/v2/token");
assert.equal(metadata.introspection_endpoint,issuer+"/oauth/v2/introspect");
assert.equal(metadata.revocation_endpoint,issuer+"/oauth/v2/revoke");
assert.equal(metadata.jwks_uri,issuer+"/oauth/v2/keys");
assert.deepEqual(metadata.response_types_supported,["code"]);
assert.ok(metadata.grant_types_supported.includes("authorization_code"));
assert.ok(metadata.grant_types_supported.includes("refresh_token"));
assert.ok(metadata.code_challenge_methods_supported.includes("S256"));
assert.equal(metadata.client_id_metadata_document_supported,false);
assert.ok(!("registration_endpoint" in metadata));

const dcrMetadata=oauthMetadataForIssuer(issuer,{dcrRegistrationEnabled:true});
assert.equal(dcrMetadata.registration_endpoint,issuer+"/oauth/v2/register");
assert.equal(dcrMetadata.client_id_metadata_document_supported,false);

const cimdMetadata=oauthMetadataForIssuer(issuer,{cimdSupported:true});
assert.equal(cimdMetadata.client_id_metadata_document_supported,true);
assert.ok(!("registration_endpoint" in cimdMetadata));

const bothMetadata=oauthMetadataForIssuer(issuer,{cimdSupported:true,dcrRegistrationEnabled:true});
assert.equal(bothMetadata.client_id_metadata_document_supported,true);
assert.equal(bothMetadata.registration_endpoint,issuer+"/oauth/v2/register");
assert.throws(()=>oauthMetadataForIssuer("http://auth.example.test"),/HTTPS_REQUIRED/);

const server=createOAuthMetadataServer({issuer});
await new Promise((resolve,reject)=>{ server.once("error",reject); server.listen(0,"127.0.0.1",resolve); });
try {
  const address=server.address();
  const baseUrl=`http://127.0.0.1:${address.port}`;
  const get=await fetch(baseUrl+"/.well-known/oauth-authorization-server");
  assert.equal(get.status,200);
  assert.match(get.headers.get("content-type") || "",/application\/json/);
  assert.equal(get.headers.get("x-content-type-options"),"nosniff");
  assert.equal((await get.json()).issuer,issuer);
  const head=await fetch(baseUrl+"/.well-known/oauth-authorization-server",{method:"HEAD"});
  assert.equal(head.status,200);
  assert.equal(await head.text(),"");
  const post=await fetch(baseUrl+"/.well-known/oauth-authorization-server",{method:"POST"});
  assert.equal(post.status,405);
  const missing=await fetch(baseUrl+"/not-routed");
  assert.equal(missing.status,404);
  const health=await fetch(baseUrl+"/healthz");
  assert.equal(health.status,200);
  assert.equal((await health.json()).component,"hara-identity-oauth-metadata");
} finally {
  await new Promise((resolve)=>server.close(resolve));
}

const advertisedServer=createOAuthMetadataServer({
  issuer,
  cimdSupported:false,
  dcrRegistrationEnabled:true,
});
await new Promise((resolve,reject)=>{
  advertisedServer.once("error",reject);
  advertisedServer.listen(0,"127.0.0.1",resolve);
});
try {
  const address=advertisedServer.address();
  const baseUrl=`http://127.0.0.1:${address.port}`;
  const metadataResponse=await fetch(baseUrl+"/.well-known/oauth-authorization-server");
  const advertised=await metadataResponse.json();
  assert.equal(advertised.registration_endpoint,issuer+"/oauth/v2/register");
  assert.equal(advertised.client_id_metadata_document_supported,false);
  const healthResponse=await fetch(baseUrl+"/healthz");
  const health=await healthResponse.json();
  assert.equal(health.dcr_registration_enabled,true);
  assert.equal(health.cimd_supported,false);
} finally {
  await new Promise((resolve)=>advertisedServer.close(resolve));
}

const validClientId="https://client.example.com/oauth/mcp-client.json";
assert.equal(validateCimdClientIdUrl(validClientId),validClientId);
const valid=validateCimdDocument({
  client_id:validClientId,
  client_name:"Example MCP Client",
  redirect_uris:["https://client.example.com/oauth/callback","http://127.0.0.1:33418","http://[::1]:33418"],
  response_types:["code"],
  grant_types:["authorization_code","refresh_token"],
  token_endpoint_auth_method:"none",
},validClientId);
assert.equal(valid.client_id,validClientId);
assert.equal(valid.token_endpoint_auth_method,"none");
assert.equal(valid.redirect_uris.length,3);
assert.equal(CIMD_ADMISSION_LIMITS.max_document_bytes,65536);
assert.equal(CIMD_ADMISSION_LIMITS.max_redirect_uris,16);

for (const bad of [
  "http://client.example.com/oauth/client.json",
  "https://client.example.com/",
  "https://user:pass@client.example.com/oauth/client.json",
  "https://client.example.com/oauth/client.json?x=1",
  "https://client.example.com/oauth/client.json#frag",
  "https://localhost/oauth/client.json",
  "https://foo.local/oauth/client.json",
  "https://127.0.0.1/oauth/client.json",
  "https://10.1.2.3/oauth/client.json",
  "https://192.168.1.4/oauth/client.json",
  "https://[::1]/oauth/client.json",
]) assert.throws(()=>validateCimdClientIdUrl(bad),/CIMD_/);

assert.throws(()=>validateCimdDocument({client_id:validClientId,client_name:"Bad",redirect_uris:["http://example.com/callback"]},validClientId),/REDIRECT_URI/);
assert.throws(()=>validateCimdDocument({client_id:validClientId,client_name:"Bad",redirect_uris:["https://client.example.com/callback"],response_types:["token"]},validClientId),/RESPONSE_TYPE/);
assert.throws(()=>validateCimdDocument({client_id:validClientId,client_name:"Bad",redirect_uris:["https://client.example.com/callback"],token_endpoint_auth_method:"client_secret_basic"},validClientId),/PUBLIC_CLIENT_REQUIRED/);
assert.throws(()=>validateCimdDocument({client_id:validClientId,client_name:"Mismatch",redirect_uris:["https://client.example.com/callback"]},"https://other.example.com/oauth/client.json"),/CLIENT_ID_MISMATCH/);

const fakePublicResolver=async()=>[{address:"93.184.216.34",family:4},{address:"2606:2800:220:1:248:1893:25c8:1946",family:6}];
assert.equal((await resolveCimdPublicAddresses("client.example.com",fakePublicResolver)).length,2);
for (const address of ["127.0.0.1","10.0.0.1","192.168.1.1","169.254.1.1","203.0.113.7","::1","fc00::1","fe80::1","2001:db8::1"]) {
  const resolver=async()=>[{address,family:address.includes(":")?6:4}];
  await assert.rejects(()=>resolveCimdPublicAddresses("client.example.com",resolver),/PRIVATE_ADDRESS_FORBIDDEN/);
}

console.log("HARA_IDENTITY_RFC8414_ADAPTER_METADATA=PASS");
console.log("HARA_IDENTITY_RFC8414_ADAPTER_HTTP=PASS");
console.log("HARA_IDENTITY_RFC8414_CIMD_NOT_ADVERTISED=PASS");
console.log("HARA_IDENTITY_RFC8414_DCR_NOT_ADVERTISED=PASS");
console.log("HARA_IDENTITY_RFC8414_DCR_CONDITIONAL_ADVERTISEMENT=PASS");
console.log("HARA_IDENTITY_RFC8414_CIMD_CONDITIONAL_ADVERTISEMENT=PASS");
console.log("HARA_IDENTITY_CIMD_URL_POLICY=PASS");
console.log("HARA_IDENTITY_CIMD_REDIRECT_POLICY=PASS");
console.log("HARA_IDENTITY_CIMD_PUBLIC_CLIENT_POLICY=PASS");
console.log("HARA_IDENTITY_CIMD_DNS_SSRF_GUARD=PASS");
console.log("HARA_IDENTITY_MCP_METADATA_SOURCE=PASS");
