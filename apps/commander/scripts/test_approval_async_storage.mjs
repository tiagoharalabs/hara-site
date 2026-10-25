import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { createHash } from "node:crypto";
import fs from "node:fs";
import vm from "node:vm";

// Exercise the real storage module with real SQLite and an idempotent quota
// double. No network, persisted database, credentials, Agent or wall-clock wait.
const modulePath=process.argv[2] || new URL("../src/approval-relay-storage.mjs",import.meta.url);
const moduleUrl=new URL(`file://${fs.realpathSync(modulePath)}`);
const storage=await import(moduleUrl.href);
const helpers=await import(new URL("approval-async-relay.mjs",moduleUrl).href);
const receipt="a".repeat(64);
const callId="HARA-CALL-894f394e-0ddc-437b-8310-7a642b248812";
const current={tenant_id:"TENANT-A",subject_id:"SUBJECT-A"};
const rawResult={state:"PASS",operational_authority:"HARA_COMMANDER",
  execution_authority:"HARA_COMMANDER_AGENT",mutation_performed:true,
  bridge_receipt_sha256:receipt,
  result:{function_id:"filesystem.write",risk_class:"FILESYSTEM_MUTATION",
    process_exit_code:0,stdout:"PRIVATE-RESULT-CONTENT",arguments:"PRIVATE-ARGS",nonce:"PRIVATE-NONCE"}};
const plain=(value)=>JSON.parse(JSON.stringify(value));
const hash=(value)=>createHash("sha256").update(String(value)).digest("hex");
const isRedacted=(value)=>typeof value==="string"&&value.startsWith("HARA_REDACTED_SHA256:");
const newMarker=async (value)=>"HARA_REDACTED_SHA256:"+hash(value);
const records=[];
const workerSource=fs.readFileSync(new URL("worker.js",moduleUrl),"utf8");
const completeStart=workerSource.indexOf("async function completeDeviceCall(");
const completeEnd=workerSource.indexOf("\nasync function deviceCallStatus(",completeStart);
assert.ok(completeStart>=0&&completeEnd>completeStart,"production completeDeviceCall missing");
const completeSource=workerSource.slice(completeStart,completeEnd);
// Run the customer projection directly from the production Worker so unknown
// effects cannot become false before the original response reaches the caller.
const projectionStart=workerSource.indexOf("function trimPublicText(");
const projectionEnd=workerSource.indexOf("\nfunction customerMcpDevicePayload(",projectionStart);
assert.ok(projectionStart>=0&&projectionEnd>projectionStart,"production customer projection missing");
const contracts=await import(new URL("device-tool-contract.mjs",moduleUrl).href);
const projectionRuntime=vm.createContext({
  deviceFunctionForTool:contracts.deviceFunctionForTool,
  isDeviceMutationTool:contracts.isDeviceMutationTool,
  isDeviceProcessTool:contracts.isDeviceProcessTool,
});
vm.runInContext(workerSource.slice(projectionStart,projectionEnd)+
  "\nglobalThis.project=projectCustomerToolResult;",projectionRuntime);
const project=(tool,result)=>plain(projectionRuntime.project(tool,result));
function fixture(overrides={},quotaFault=null){
  const db=new DatabaseSync(":memory:");
  db.exec(`CREATE TABLE commander_devices (
    device_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,state TEXT NOT NULL,revoked_at_utc TEXT
  );
  INSERT INTO commander_devices VALUES('DEVICE-A','TENANT-A','ACTIVE',NULL);
  CREATE TABLE commander_device_calls (
    call_id TEXT PRIMARY KEY,request_id TEXT,tenant_id TEXT,subject_id TEXT,
    device_id TEXT,tool_id TEXT,state TEXT,created_at_utc TEXT,expires_at_utc TEXT,
    claimed_at_utc TEXT,completed_at_utc TEXT,payload_json TEXT,result_json TEXT,
    error_code TEXT,usage_mode TEXT,usage_units INTEGER,usage_period_key TEXT,
    usage_budget_id TEXT,approval_timeout_seconds INTEGER,execution_budget_ms INTEGER,
    call_result_metadata_json TEXT
  );`);
  const row={call_id:callId,request_id:"ORIGINAL-R1",tenant_id:"TENANT-A",subject_id:"SUBJECT-A",
    device_id:"DEVICE-A",tool_id:"hara.files.write",state:"COMPLETED",
    created_at_utc:"2026-10-12T18:00:00.000Z",expires_at_utc:"2026-10-12T18:16:11.000Z",
    claimed_at_utc:"2026-10-12T18:00:01.000Z",completed_at_utc:"2026-10-12T18:00:03.000Z",
    payload_json:"HARA_REDACTED_SHA256:"+"b".repeat(64),result_json:JSON.stringify(rawResult),
    error_code:null,usage_mode:"CLOUD_QUOTA",usage_units:1,usage_period_key:"2026-10",
    usage_budget_id:null,approval_timeout_seconds:900,execution_budget_ms:10000,
    call_result_metadata_json:null,...overrides};
  if (!Object.hasOwn(overrides,"call_result_metadata_json")&&row.result_json&&!isRedacted(row.result_json)) {
    row.call_result_metadata_json=JSON.stringify(helpers.safeCallResultMetadata(JSON.parse(row.result_json),row));
  }
  const fields=Object.keys(row);
  db.prepare(`INSERT INTO commander_device_calls (${fields.join(",")}) VALUES (${fields.map(()=>"?").join(",")})`).run(...Object.values(row));
  const sql=[];const quotaCalls=[];
  let quotaState="RESERVED",quotaReceipt=null,fault=quotaFault,heldCommit=null;
  const quota={async settleDeviceCall(request,subject,period,units,commitReceipt){
    quotaCalls.push({request,subject,period,units,receipt:commitReceipt});
    assert.equal(request,"ORIGINAL-R1");assert.equal(subject,"SUBJECT-A");
    assert.equal(period,"2026-10");assert.equal(units,1);
    if (fault==="CONCURRENT"&&quotaCalls.length===1) {
      await new Promise((resolve)=>{heldCommit=resolve;});
    } else if (fault==="CONCURRENT"&&heldCommit) {
      heldCommit();heldCommit=null;
    }
    if (fault==="BEFORE") {fault=null;throw new Error("QUOTA_RPC_RESPONSE_FAILED");}
    const next=commitReceipt ? "COMMITTED" : "RELEASED";
    if (quotaState!=="RESERVED"&&(quotaState!==next||quotaReceipt!==commitReceipt)) {
      return {ok:false,code:"IDEMPOTENCY_CONFLICT"};
    }
    const existing=quotaState!=="RESERVED";
    quotaState=next;quotaReceipt=commitReceipt;
    if (fault==="AFTER") {fault=null;throw new Error("QUOTA_RPC_RESPONSE_FAILED");}
    return {ok:true,state:next,existing};
  }};
  const env={
    TENANT_QUOTA:{getByName(tenant){assert.equal(tenant,"TENANT-A");return quota;}},
    PRODUCT_DB:{prepare(statement){return {bind(...binds){return {
      async first(){sql.push({statement,binds,operation:"first"});return db.prepare(statement).get(...binds)||null;},
      async all(){sql.push({statement,binds,operation:"all"});return {results:db.prepare(statement).all(...binds)};},
      async run(){sql.push({statement,binds,operation:"run"});const result=db.prepare(statement).run(...binds);return {meta:{changes:Number(result.changes)}};},
    };}};}},
  };
  const completionRuntime=vm.createContext({
    resolveDeviceCredential:async ()=>({tenant_id:"TENANT-A",device_id:"DEVICE-A"}),
    cleanId:(value)=>String(value),boundedJson:(value)=>JSON.stringify(value),
    nowIso:()=>"2026-10-12T18:00:03.000Z",CALL_ROW_FIELDS:storage.CALL_ROW_FIELDS,
    safeCallResultMetadata:helpers.safeCallResultMetadata,settleCallUsage:storage.settleCallUsage,
    deviceCallStoredContentMatches:async (stored,candidate)=>stored===candidate||stored===await newMarker(candidate),
    reconcileAgentVersion:async ()=>undefined,console,
  });
  vm.runInContext(completeSource+"\nglobalThis.complete=completeDeviceCall;",completionRuntime);
  return {env,sql,quotaCalls,
    row(){return plain(db.prepare("SELECT * FROM commander_device_calls WHERE call_id=?").get(callId));},
    state(){return quotaState;},
    status(context=current,options={}){return storage.acceptedCallStatus(env,context,callId,
      {expectedDeviceId:"DEVICE-A",nowUtc:"2026-10-12T18:01:00.000Z",newMarker,isRedacted,...options});},
    public(status){return storage.publicAcceptedCallStatus(status,"windows-a",(tool,result)=>{
      assert.equal(tool,row.tool_id,"status must project the original tool");return project(tool,result);
    });},close(){db.close();},
    complete(result=rawResult){return completionRuntime.complete(env,{},
      {call_id:callId,state:"COMPLETED",result});},
  };
}
async function check(name,callback,overrides,quotaFault){
  const f=fixture(overrides,quotaFault);
  try {await callback(f);records.push(name);} finally {f.close();}
}
await check("tenant-subject-device-scopes-deny-before-usage-or-writes",async (f)=>{
  for (const context of [{tenant_id:"TENANT-B",subject_id:"SUBJECT-A"},
    {tenant_id:"TENANT-A",subject_id:"SUBJECT-B"}]) {
    assert.equal(await storage.readScopedCall(f.env,context,callId),null);
    await assert.rejects(()=>f.status(context),/DEVICE_CALL_NOT_FOUND/);
  }
  await assert.rejects(()=>f.status(current,{expectedDeviceId:"FOREIGN-DEVICE"}),/DEVICE_CALL_NOT_FOUND/);
  assert.equal(f.quotaCalls.length,0);assert.equal(f.sql.filter((x)=>x.operation==="run").length,0);
});
await check("pending-status-does-not-settle-redact-or-dispatch",async (f)=>{
  const result=await f.status();const output=f.public(result);
  assert.equal(output.state,"PENDING");assert.equal(output.mutation_performed,null);
  assert.equal(output.result.execution_outcome,"UNKNOWN");assert.equal(output.result.automatic_retry_allowed,false);
  assert.equal(output.result.session_id,callId);
  assert.equal(output.product.quota.state,"RESERVED");
  assert.equal(output.product.quota.original_units,1);assert.equal(output.product.quota.additional_usage_units,0);
  assert.equal(f.quotaCalls.length,0);assert.equal(f.sql.filter((x)=>x.operation==="run").length,0);
},{state:"EXECUTING",completed_at_utc:null,result_json:null,call_result_metadata_json:null});
await check("original-success-settles-before-content-consumed",async (f)=>{
  const result=await f.status();const output=f.public(result);
  assert.equal(result.result.bridge_receipt_sha256,receipt);
  assert.equal(output.result.stdout,"PRIVATE-RESULT-CONTENT");
  assert.equal(f.state(),"COMMITTED");assert.equal(f.quotaCalls.length,1);
  assert.equal(f.quotaCalls[0].receipt,receipt);
  assert.ok(isRedacted(f.row().result_json));
  const metadata=JSON.parse(f.row().call_result_metadata_json);
  for (const text of ["PRIVATE-RESULT-CONTENT","PRIVATE-ARGS","PRIVATE-NONCE"]) assert.ok(!JSON.stringify(metadata).includes(text));
  assert.equal(metadata.bridge_receipt_sha256,receipt);assert.equal(metadata.usage.state,"COMMITTED");
  assert.equal(metadata.result.risk_class,"FILESYSTEM_MUTATION");
});
await check("normalized-receipt-keeps-settlement-and-replay-consistent",async (f)=>{
  await f.status();assert.equal(f.quotaCalls[0].receipt,receipt);
  const replay=f.public(await f.status());assert.equal(replay.bridge_receipt_sha256,receipt);
  assert.equal(f.state(),"COMMITTED");
},{result_json:JSON.stringify({...rawResult,bridge_receipt_sha256:" "+receipt.toUpperCase()+" "})});
for (const fault of ["BEFORE","AFTER"]) await check(`quota-${fault.toLowerCase()}-commit-fault-retains-content-for-safe-retry`,async (f)=>{
  const original=f.row().result_json;
  await assert.rejects(()=>f.status(),/QUOTA_RPC_RESPONSE_FAILED/);
  assert.equal(f.row().result_json,original,"failed settlement consumed the result");
  assert.equal(f.sql.filter((x)=>/SET result_json/.test(x.statement)).length,0);
  const recovered=await f.status();assert.equal(recovered.result.bridge_receipt_sha256,receipt);
  assert.equal(f.state(),"COMMITTED");assert.ok(isRedacted(f.row().result_json));
  assert.equal(f.quotaCalls.length,2);
  assert.deepEqual(f.quotaCalls[0],f.quotaCalls[1],"retry changed original usage binding");
},undefined,fault);
await check("two-concurrent-readers-have-one-content-winner",async (f)=>{
  const results=await Promise.all([f.status(),f.status()]);
  assert.equal(results.filter((x)=>Boolean(x.result)).length,1);
  const outputs=results.map((x)=>f.public(x));
  assert.equal(outputs.filter((x)=>x.result.stdout==="PRIVATE-RESULT-CONTENT").length,1);
  assert.equal(outputs.filter((x)=>x.replayed===true).length,1);
  for (const output of outputs) assert.equal(output.bridge_receipt_sha256,receipt);
  assert.equal(f.state(),"COMMITTED");assert.ok(isRedacted(f.row().result_json));
});
await check("redacted-replay-preserves-original-receipt-and-tool",async (f)=>{
  await f.status();const replay=f.public(await f.status());
  assert.equal(replay.replayed,true);assert.equal(replay.content_redacted,true);
  assert.equal(replay.original_tool_id,"hara.files.write");assert.equal(replay.bridge_receipt_sha256,receipt);
  assert.equal(replay.result.stdout,undefined);assert.equal(replay.result.risk_class,"FILESYSTEM_MUTATION");
  assert.equal(replay.retrieval.new_call_enqueued,false);assert.equal(replay.retrieval.additional_usage_units,0);
  assert.equal(f.state(),"COMMITTED");
});
for (const [label,value,expected] of [
  ["true",true,true],["false",false,false],["null",null,null],
  ["missing",undefined,null],["unknown-string","UNKNOWN",null],
  ["string-false","false",null],["number-zero",0,null],["number-one",1,null],
]) {
  const raw={...rawResult,result:{...rawResult.result,function_id:"process.run",risk_class:"PROCESS_EXECUTION"}};
  if (value===undefined) delete raw.mutation_performed;
  else raw.mutation_performed=value;
  await check(`process-effect-${label}-survives-original-and-redacted-replay`,async (f)=>{
    const original=f.public(await f.status());
    assert.equal(original.mutation_performed,expected);
    assert.equal(original.result.risk_class,"PROCESS_EXECUTION");
    assert.equal(original.result.stdout,"PRIVATE-RESULT-CONTENT");
    const replay=f.public(await f.status());
    assert.equal(replay.mutation_performed,expected);
    assert.equal(replay.result.risk_class,"PROCESS_EXECUTION");
    assert.equal(replay.bridge_receipt_sha256,receipt);
    assert.equal(replay.original_tool_id,"hara.process.run");
    assert.equal(replay.replayed,true);assert.equal(replay.content_redacted,true);
    for (const privateText of ["PRIVATE-RESULT-CONTENT","PRIVATE-ARGS","PRIVATE-NONCE"]) {
      assert.ok(!JSON.stringify(replay).includes(privateText));
      assert.ok(!f.row().call_result_metadata_json.includes(privateText));
    }
    assert.equal(replay.retrieval.new_call_enqueued,false);
    assert.equal(replay.retrieval.additional_usage_units,0);
    assert.equal(replay.product.quota.state,"COMMITTED");
    assert.equal(replay.product.quota.units,1);
    for (const settlement of f.quotaCalls) {
      assert.equal(settlement.request,"ORIGINAL-R1");assert.equal(settlement.receipt,receipt);
      assert.equal(settlement.units,1);
    }
    assert.equal(f.sql.filter((entry)=>/INSERT|DELETE/.test(entry.statement)).length,0,
      "status replay must not dispatch or create a new call");
  },{tool_id:"hara.process.run",result_json:JSON.stringify(raw)});
}
for (const [label,risk] of [["unknown","PRIVATE-RISK-CONTENT"],["object",{value:"PRIVATE-RISK-CONTENT"}]]) {
  const raw={...rawResult,result:{...rawResult.result,risk_class:risk}};
  await check(`unrecognized-risk-${label}-is-redacted-without-a-guess`,async (f)=>{
    await f.status();const replay=f.public(await f.status());
    assert.equal(replay.result.risk_class,null);
    assert.ok(!JSON.stringify(replay).includes("PRIVATE-RISK-CONTENT"));
    assert.equal(replay.mutation_performed,true);
    assert.equal(replay.retrieval.additional_usage_units,0);
  },{result_json:JSON.stringify(raw)});
}
await check("unclaimed-expiry-refunds-original-reservation-once",async (f)=>{
  const result=await f.status();assert.equal(result.row.state,"EXPIRED");
  assert.equal(f.row().state,"EXPIRED");assert.equal(f.state(),"RELEASED");
  assert.equal(f.quotaCalls[0].receipt,null);
  const replay=f.public(await f.status());assert.equal(replay.mutation_performed,false);
  assert.equal(replay.product.quota.state,"RELEASED");assert.equal(f.state(),"RELEASED");
},{state:"PENDING",expires_at_utc:"2026-10-12T18:00:50.000Z",claimed_at_utc:null,completed_at_utc:null,result_json:null,call_result_metadata_json:null});
await check("claimed-expiry-does-not-fabricate-refund-or-execution",async (f)=>{
  const result=await f.status();const output=f.public(result);
  assert.equal(result.row.state,"EXPIRED");assert.equal(output.state,"RESULT_METADATA_UNAVAILABLE");
  assert.equal(output.mutation_performed,null);assert.equal(f.quotaCalls.length,0);assert.equal(f.state(),"RESERVED");
  assert.equal(output.execution_outcome,"UNKNOWN");assert.equal(output.automatic_retry_allowed,false);
},{state:"EXECUTING",expires_at_utc:"2026-10-12T18:00:50.000Z",completed_at_utc:null,result_json:null,call_result_metadata_json:null});
await check("legacy-redacted-result-is-explicitly-unavailable",async (f)=>{
  const output=f.public(await f.status());assert.equal(output.state,"RESULT_METADATA_UNAVAILABLE");
  assert.equal(output.bridge_receipt_sha256,undefined);assert.equal(output.mutation_performed,null);
  assert.equal(f.quotaCalls.length,0);
},{result_json:"HARA_REDACTED_SHA256:"+"c".repeat(64),call_result_metadata_json:null});
await check("malformed-json-metadata-does-not-trigger-settlement",async (f)=>{
  const output=f.public(await f.status());assert.equal(output.state,"RESULT_METADATA_UNAVAILABLE");
  assert.equal(f.quotaCalls.length,0);assert.equal(f.state(),"RESERVED");
},{result_json:"HARA_REDACTED_SHA256:"+"c".repeat(64),call_result_metadata_json:"{malformed"});
for (const key of ["schema","call_id","request_id","tool_id","call_state"]) {
  const correct=helpers.safeCallResultMetadata(rawResult,{call_id:callId,request_id:"ORIGINAL-R1",tool_id:"hara.files.write",state:"COMPLETED"});
  correct[key]="FOREIGN";
  await check(`wrong-bound-metadata-${key}-cannot-charge-original-request`,async (f)=>{
    try {
      const output=f.public(await f.status());assert.equal(output.state,"RESULT_METADATA_UNAVAILABLE");
    } catch (error) {
      assert.match(String(error.message),/CALL_RESULT_METADATA_(?:INVALID|UNAVAILABLE)/);
    }
    assert.equal(f.quotaCalls.length,0);assert.equal(f.state(),"RESERVED");
    assert.equal(f.sql.filter((x)=>/SET result_json/.test(x.statement)).length,0);
  },{result_json:"HARA_REDACTED_SHA256:"+"c".repeat(64),call_result_metadata_json:JSON.stringify(correct)});
}
await check("revoked-completion-cannot-settle-or-change-an-executing-call",async (f)=>{
  await f.env.PRODUCT_DB.prepare("UPDATE commander_devices SET state=\'REVOKED\',revoked_at_utc=? WHERE device_id=?")
    .bind("2026-10-12T18:00:02.000Z","DEVICE-A").run();
  await assert.rejects(()=>f.complete(),/DEVICE_AUTH_INVALID/);
  assert.equal(f.quotaCalls.length,0);assert.equal(f.state(),"RESERVED");
  assert.equal(f.row().state,"EXECUTING");assert.equal(f.row().result_json,null);
},{state:"EXECUTING",completed_at_utc:null,result_json:null,call_result_metadata_json:null});
await check("concurrent-completions-settle-the-fresh-terminal-row",async (f)=>{
  const results=await Promise.allSettled([f.complete(),f.complete()]);
  for (const result of results) {
    assert.equal(result.status,"fulfilled",String(result.reason?.message));
    assert.equal(result.value.ok,true);
  }
  assert.equal(results.filter((result)=>result.value.existing===true).length,1);
  assert.equal(f.state(),"COMMITTED");assert.equal(f.row().state,"COMPLETED");
  assert.ok(f.quotaCalls.length>=2);
  for (const call of f.quotaCalls) assert.equal(call.receipt,receipt,"stale EXECUTING snapshot refunded a completed call");
  const metadata=JSON.parse(f.row().call_result_metadata_json);
  assert.equal(metadata.call_state,"COMPLETED");assert.equal(metadata.usage.state,"COMMITTED");
},{state:"EXECUTING",completed_at_utc:null,result_json:null,call_result_metadata_json:null},"CONCURRENT");
await check("lost-completion-response-retries-after-terminal-persistence",async (f)=>{
  await assert.rejects(()=>f.complete(),/QUOTA_RPC_RESPONSE_FAILED/);
  assert.equal(f.row().state,"COMPLETED");assert.equal(f.row().result_json,JSON.stringify(rawResult));
  const result=await f.complete();assert.equal(result.ok,true);assert.equal(result.existing,true);
  assert.equal(f.state(),"COMMITTED");assert.equal(f.quotaCalls.length,2);
  for (const call of f.quotaCalls) assert.equal(call.receipt,receipt);
  assert.equal((await f.status()).result.bridge_receipt_sha256,receipt);
},{state:"EXECUTING",completed_at_utc:null,result_json:null,call_result_metadata_json:null},"AFTER");
await check("completion-replay-with-conflicting-result-does-not-settle",async (f)=>{
  await f.complete();const usageCalls=f.quotaCalls.length;
  await assert.rejects(()=>f.complete({...rawResult,bridge_receipt_sha256:"b".repeat(64)}),/IDEMPOTENCY_CONFLICT/);
  assert.equal(f.quotaCalls.length,usageCalls);assert.equal(f.state(),"COMMITTED");
},{state:"EXECUTING",completed_at_utc:null,result_json:null,call_result_metadata_json:null});
console.log(JSON.stringify({schema:"hara.commander-approval-async-storage-tests.v1",state:"PASS",
  scenarios:records.length,checks:records,sqlite:"IN_MEMORY_REAL_SQLITE",production_module_exercised:true,
  remote_services_used:false,module_sha256:hash(fs.readFileSync(moduleUrl,"utf8")),worker_sha256:hash(workerSource)}));
