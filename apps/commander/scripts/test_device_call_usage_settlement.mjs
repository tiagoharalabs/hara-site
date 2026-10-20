#!/usr/bin/env node
// Actual completion handler + quota Durable Object over isolated SQLite.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { DatabaseSync } from "node:sqlite";
import { webcrypto } from "node:crypto";
import * as approval from "../src/approval-async-relay.mjs";
import * as storage from "../src/approval-relay-storage.mjs";

const app = new URL("../", import.meta.url);
const worker = fs.readFileSync(new URL("src/worker.js", app), "utf8");
let clock = Date.parse("2026-10-20T19:30:00.000Z");
class ClockDate extends Date {
  constructor(...args) { super(...(args.length ? args : [clock])); }
  static now() { return clock; }
}
const now = (offset=0) => new ClockDate(clock + offset * 1000).toISOString();
const quotaDb = new DatabaseSync(":memory:");
const pending = [];
class DurableObject { constructor(ctx) { this.ctx=ctx; } }
const quotaCtx = {
  blockConcurrencyWhile(fn) { const p=fn(); pending.push(p); return p; },
  storage: { sql: { exec(sql,...binds) {
    if (!binds.length && /CREATE TABLE IF NOT EXISTS|DELETE FROM period_usage;|DROP TRIGGER IF EXISTS/.test(sql)) {
      quotaDb.exec(sql); return [];
    }
    return quotaDb.prepare(sql).all(...binds);
  } } },
};
const classStart=worker.indexOf("export class TenantQuota extends DurableObject {");
const classEnd=worker.indexOf("\nasync function entitlementForTenant",classStart);
assert(classStart>=0 && classEnd>classStart);
const quotaRuntime=vm.createContext({DurableObject,Date:ClockDate,
  QUOTA_RESERVATION_TTL_SECONDS:600,ASYNC_APPROVAL_RESERVATION_TTL_SECONDS:1800});
vm.runInContext(worker.slice(classStart,classEnd).replace("export class","class")+"\nglobalThis.Quota=TenantQuota;",quotaRuntime);
const quota=new quotaRuntime.Quota(quotaCtx,{});
await Promise.all(pending);

const db=new DatabaseSync(":memory:");
for (const name of fs.readdirSync(new URL("migrations/",app)).filter(x=>x.endsWith(".sql")).sort()) {
  db.exec(fs.readFileSync(new URL(`migrations/${name}`,app),"utf8"));
}
const tenant="USAGE-TENANT", subject="USAGE-SUBJECT", deviceId="USAGE-DEVICE";
db.prepare("INSERT INTO tenants VALUES (?,?,'ACTIVE','DEV',?)").run(tenant,"Usage QA",now());
db.prepare("INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES (?,?,?,?,'ACTIVE','OWNER',?)")
  .run(subject,tenant,"https://fixture.invalid","subject",now());
db.prepare("INSERT INTO device_pairing_tokens (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc) VALUES ('USAGE-PAIR','USAGE-HASH',?,?,?,?)")
  .run(tenant,subject,now(),now(600));
db.prepare("INSERT INTO commander_devices (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,agent_version,tunnel_mode,credential_hash,state,created_at_utc,approval_mode) VALUES (?,'USAGE-PAIR',?,?,'Usage QA','LINUX','0.3.43','EVENT_V2','USAGE-CREDENTIAL','ACTIVE',?,'PERSISTENT_TRUSTED')")
  .run(deviceId,tenant,subject,now());
const wrap=(sql,binds=[])=>({
  async first() { return db.prepare(sql).get(...binds) || null; },
  async all() { return {results:db.prepare(sql).all(...binds)}; },
  async run() { return {meta:{changes:Number(db.prepare(sql).run(...binds).changes)}}; },
});
const env={PRODUCT_DB:{prepare(sql){return {bind(...args){return wrap(sql,args);}};}},
  TENANT_QUOTA:{getByName(id){assert.equal(id,tenant);return quota;}}};
const device={device_id:deviceId,tenant_id:tenant,agent_version:"0.3.43",platform:"LINUX"};
const extract=(name)=>{
  const match=new RegExp(`(?:async )?function ${name}\\(`).exec(worker);
  assert(match,`missing ${name}`);
  const end=worker.indexOf("\n}",match.index);
  assert(end>match.index);
  return worker.slice(match.index,end+2);
};
const runtime=vm.createContext({Date:ClockDate,TextEncoder,crypto:webcrypto,console,
  nowIso:(seconds=0)=>now(seconds),resolveDeviceCredential:async()=>device,
  safeCallResultMetadata:approval.safeCallResultMetadata,
  CALL_ROW_FIELDS:storage.CALL_ROW_FIELDS,settleCallUsage:storage.settleCallUsage,
  reconcileAgentVersion:async()=>{},deviceCallStoredContentMatches:async(a,b)=>a===b});
vm.runInContext(["cleanId","boundedJson","completeDeviceCall"].map(extract).join("\n")+"\nglobalThis.complete=completeDeviceCall;",runtime);

function seed(id, period="LIFETIME") {
  db.prepare("INSERT INTO commander_device_calls (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,created_at_utc,expires_at_utc,claimed_at_utc,usage_mode,usage_units,usage_period_key,approval_timeout_seconds,execution_budget_ms) VALUES (?,?,?,?,?,'hara.files.read','{}','EXECUTING',?,?,?,'CLOUD_QUOTA',1,?,0,1000)")
    .run(id,id,tenant,subject,deviceId,now(),now(30),now(),period);
  assert.equal(quota.reserve(id,subject,period,"tool:hara.files.read",5000).state,"RESERVED");
}
const receipt=(char)=>char.repeat(64);
const result=(id,code="a")=>({call_id:id,state:"COMPLETED",result:{state:"PASS",
  mutation_performed:false,bridge_receipt_sha256:receipt(code),result:{process_exit_code:0,stdout:"QA"}}});
const quotaState=(id)=>quotaDb.prepare("SELECT state,units FROM request_state WHERE request_id=?").get(id);
const callState=(id)=>db.prepare("SELECT state,usage_settled_at_utc FROM commander_device_calls WHERE call_id=?").get(id);

seed("NORMAL");
assert.equal((await runtime.complete(env,{},result("NORMAL"))).ok,true);
assert.equal(callState("NORMAL").state,"COMPLETED");
assert(callState("NORMAL").usage_settled_at_utc);
assert.equal(quotaState("NORMAL").state,"COMMITTED");
clock+=601000; quota.status("LIFETIME",5000);
assert.equal(quotaState("NORMAL").state,"COMMITTED");
assert.equal((await runtime.complete(env,{},result("NORMAL"))).existing,true);
assert.equal(quota.status("LIFETIME",5000).consumed_units,1);
console.log("COMMANDER_NORMAL_COMPLETION_SETTLES_WITHOUT_CLIENT_READ=PASS");

seed("DO-FAIL");
const realSettle=quota.settleDeviceCall.bind(quota);
let failOnce=true;
quota.settleDeviceCall=(...args)=>{if(failOnce){failOnce=false;throw Error("SYNTHETIC_DO_UNAVAILABLE");}return realSettle(...args);};
await assert.rejects(runtime.complete(env,{},result("DO-FAIL")),/SYNTHETIC_DO_UNAVAILABLE/);
assert.equal(callState("DO-FAIL").state,"COMPLETED");
assert.equal(callState("DO-FAIL").usage_settled_at_utc,null);
assert.equal((await runtime.complete(env,{},result("DO-FAIL"))).existing,true);
assert.equal(quotaState("DO-FAIL").state,"COMMITTED");
assert(callState("DO-FAIL").usage_settled_at_utc);
console.log("COMMANDER_DO_FAILURE_RETRY_SETTLES_SAME_RECEIPT=PASS");

seed("NO-RETRY");
quota.settleDeviceCall=(...args)=>{throw Error("SYNTHETIC_DO_UNAVAILABLE");};
await assert.rejects(runtime.complete(env,{},result("NO-RETRY")),/SYNTHETIC_DO_UNAVAILABLE/);
clock+=601000; quota.status("LIFETIME",5000);
assert.equal(quotaState("NO-RETRY").state,"RELEASED");
quota.settleDeviceCall=realSettle;
const reconciled=await storage.reconcileUnsettledCallUsage(env,{limit:20});
assert(reconciled.settled>=1);
assert.equal(quotaState("NO-RETRY").state,"COMMITTED");
assert(callState("NO-RETRY").usage_settled_at_utc);
assert.equal(quota.status("LIFETIME",5000).consumed_units,3);
console.log("COMMANDER_ORPHANED_COMPLETION_RECONCILES_AFTER_TTL=PASS");

seed("DENIED");
const denied={call_id:"DENIED",state:"FAILED",error_code:"LOCAL_APPROVAL_DENIED",
  result:{state:"DENIED",mutation_performed:false,blocker:{code:"LOCAL_APPROVAL_DENIED"},result:{}}};
assert.equal((await runtime.complete(env,{},denied)).ok,true);
assert.equal(quotaState("DENIED").state,"RELEASED");
clock+=601000; quota.status("LIFETIME",5000);
assert.equal(quotaState("DENIED").state,"RELEASED");
assert.equal(quota.status("LIFETIME",5000).consumed_units,3);
console.log("COMMANDER_UNEXECUTED_DENIAL_RELEASES_QUOTA=PASS");

db.close();quotaDb.close();
