#!/usr/bin/env node
// Offline opaque-token fan-out and provider-failure regression; no real IdP.
import assert from "node:assert/strict";
import fs from "node:fs";
import {
  haraIdentityCustomerMcpProviderFailure,
  haraIdentityCustomerMcpUnavailable,
  verifyHaraIdentityCustomerMcpBearer,
} from "../src/mcp-hara-identity-customer.mjs";

let scenario=0;
const audience="QA-PROJECT";
const introspectionClientId="QA-INTROSPECTION";
const request=new Request("https://commander.haralabs.com.br/api/mcp",{
  headers:{authorization:"Bearer opaque-r3-fixture"},
});
function config(){
  const issuer=`https://auth-r3-${++scenario}.invalid/`;
  return {ENVIRONMENT:"PROD",CUSTOMER_MCP_EDGE_ENABLED:"true",AUTH_ISSUER:issuer,
    HARA_IDENTITY_MCP_DCR_PROJECT_AUD:audience,
    HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_ID:introspectionClientId,
    HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_SECRET:"QA-ONLY-SECRET"};
}
function mockProvider(env,{delayMs=0,inactive=false,unavailable=false,userInfoRejected=false}={}){
  const counts={discovery:0,introspection:0,userinfo:0,signals:0};
  const metadata={issuer:env.AUTH_ISSUER,authorization_endpoint:env.AUTH_ISSUER+"authorize",
    token_endpoint:env.AUTH_ISSUER+"token",jwks_uri:env.AUTH_ISSUER+"jwks",
    introspection_endpoint:env.AUTH_ISSUER+"introspect",
    userinfo_endpoint:env.AUTH_ISSUER+"userinfo",code_challenge_methods_supported:["S256"]};
  globalThis.fetch=async(url,options={})=>{
    assert.equal(options.signal instanceof AbortSignal,true,"OIDC_FETCH_MISSING_DEADLINE_SIGNAL");
    counts.signals++;
    if(delayMs) await new Promise(resolve=>setTimeout(resolve,delayMs));
    if(String(url).endsWith(".well-known/openid-configuration")) {
      counts.discovery++;
      return unavailable ? Response.json({}, {status:503}) : Response.json(metadata);
    }
    if(String(url).endsWith("introspect")) {
      counts.introspection++;
      return Response.json({active:!inactive,iss:env.AUTH_ISSUER,client_id:"QA-CLIENT",
        aud:[audience,introspectionClientId,"QA-CLIENT"],scope:"openid email",
        sub:"QA-SUBJECT",exp:Math.floor(Date.now()/1000)+300});
    }
    if(String(url).endsWith("userinfo")) {
      counts.userinfo++;
      if(userInfoRejected) return new Response(null,{status:401});
      return Response.json({sub:"QA-SUBJECT"});
    }
    throw new Error("UNEXPECTED_QA_URL");
  };
  return counts;
}

const originalFetch=globalThis.fetch;
try {
  const env=config();
  const counts=mockProvider(env);
  for(let i=0;i<25;i++) {
    const identity=await verifyHaraIdentityCustomerMcpBearer(request,env);
    assert.equal(identity.token_format,"OPAQUE");
    assert.equal(identity.provider_fetches_started,2);
  }
  assert.deepEqual(counts,{discovery:1,introspection:25,userinfo:25,signals:51});
  const revokedCounts=mockProvider(env,{inactive:true});
  await assert.rejects(verifyHaraIdentityCustomerMcpBearer(request,env),error=>
    error.message==="HARA_IDENTITY_MCP_INTROSPECTION_INACTIVE");
  assert.equal(revokedCounts.introspection,1);
  assert.equal(revokedCounts.userinfo,1);
  console.log("COMMANDER_OPAQUE_SEQUENTIAL_RECHECKS_REVOCATION_NO_TOKEN_CACHE=PASS");

  const burstEnv=config();
  const burstCounts=mockProvider(burstEnv,{delayMs:15});
  const identities=await Promise.all(Array.from({length:10},()=>verifyHaraIdentityCustomerMcpBearer(request,burstEnv)));
  assert(identities.every(value=>value.subject==="QA-SUBJECT"));
  assert.equal(identities.filter(value=>value.provider_fetches_started===2).length,1);
  assert.equal(identities.filter(value=>value.provider_fetches_started===0).length,9);
  assert.deepEqual(burstCounts,{discovery:1,introspection:1,userinfo:1,signals:3});
  console.log("COMMANDER_OPAQUE_CONCURRENT_DISCOVERY_AND_TOKEN_CHECK_COALESCED=PASS");

  const distinctEnv=config();
  const distinctCounts=mockProvider(distinctEnv,{delayMs:15});
  const otherRequest=new Request(request.url,{headers:{authorization:"Bearer opaque-other-fixture"}});
  await Promise.all([verifyHaraIdentityCustomerMcpBearer(request,distinctEnv),
    verifyHaraIdentityCustomerMcpBearer(otherRequest,distinctEnv)]);
  assert.equal(distinctCounts.discovery,1);
  assert.equal(distinctCounts.introspection,2);
  assert.equal(distinctCounts.userinfo,2);
  console.log("COMMANDER_OPAQUE_DIFFERENT_TOKENS_NEVER_SHARE_CHECK=PASS");

  const inactiveEnv=config();
  mockProvider(inactiveEnv,{inactive:true});
  await assert.rejects(verifyHaraIdentityCustomerMcpBearer(request,inactiveEnv),error=>
    error.message==="HARA_IDENTITY_MCP_INTROSPECTION_INACTIVE"
    && !haraIdentityCustomerMcpProviderFailure(error));
  console.log("COMMANDER_OPAQUE_INACTIVE_TOKEN_STAYS_UNAUTHORIZED=PASS");

  const rejectedEnv=config();
  mockProvider(rejectedEnv,{userInfoRejected:true});
  await assert.rejects(verifyHaraIdentityCustomerMcpBearer(request,rejectedEnv),error=>
    error.message==="OIDC_USERINFO_TOKEN_REJECTED"
    && !haraIdentityCustomerMcpProviderFailure(error));
  console.log("COMMANDER_USERINFO_TOKEN_REJECTION_STAYS_401=PASS");

  const unavailableEnv=config();
  mockProvider(unavailableEnv,{unavailable:true});
  await assert.rejects(verifyHaraIdentityCustomerMcpBearer(request,unavailableEnv),error=>
    error.message==="OIDC_DISCOVERY_FAILED" && haraIdentityCustomerMcpProviderFailure(error));
  const unavailableResponse=haraIdentityCustomerMcpUnavailable();
  assert.equal(unavailableResponse.status,503);
  assert.equal(unavailableResponse.headers.get("retry-after"),"5");
  assert.equal(unavailableResponse.headers.get("cache-control"),"no-store");
  console.log("COMMANDER_PROVIDER_OUTAGE_CLASSIFIED_503_WITH_RETRY_AFTER=PASS");

  const stalledEnv=config();
  let sawSignal=false;
  globalThis.fetch=(_url,options={})=>{
    sawSignal=options.signal instanceof AbortSignal;
    return new Promise(()=>{}); // deliberately ignores abort: app deadline must still settle
  };
  const started=Date.now();
  await assert.rejects(verifyHaraIdentityCustomerMcpBearer(request,stalledEnv),error=>
    error.message==="OIDC_PROVIDER_TIMEOUT" && haraIdentityCustomerMcpProviderFailure(error));
  assert(sawSignal && Date.now()-started<4000);
  console.log("COMMANDER_PROVIDER_STALL_HAS_APPLICATION_DEADLINE=PASS");

  const worker=fs.readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
  assert(worker.includes("haraIdentityCustomerMcpProviderFailure(error)"));
  assert(worker.includes("return haraIdentityCustomerMcpUnavailable()"));
  assert(!worker.includes("console.warn(error)"));
  console.log("COMMANDER_PUBLIC_MCP_PROVIDER_CLASSIFICATION_WIRED=PASS");
} finally {
  globalThis.fetch=originalFetch;
}
