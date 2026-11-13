// QA only: original Commander TenantQuota DO via real workerd/Miniflare,
// paired with real D1 cleanup + settleCallUsage against synthetic SQLite.
import assert from "node:assert/strict";
import path from "node:path";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {DatabaseSync} from "node:sqlite";
import {createRequire} from "node:module";
import {settleCallUsage,CALL_ROW_FIELDS} from "../src/approval-relay-storage.mjs";
const require=createRequire(import.meta.url);
const {Miniflare}=require("/tmp_hara/commander-capability-suite-20261110/node_modules/miniflare");
process.env.MINIFLARE_WORKERD_PATH="/home/sartorius/.npm/_npx/23be562fde961825/node_modules/workerd/bin/workerd";
const [bundle,storageRoot]=process.argv.slice(2);
assert.ok(bundle&&storageRoot&&path.resolve(storageRoot).startsWith("/tmp_hara/commander-real-quota-"));
const worker=readFileSync(new URL("../src/worker.js",import.meta.url),"utf8");
const migration=readFileSync(new URL("../migrations/0043_device_call_authorization.sql",import.meta.url),"utf8");
const sha=x=>createHash("sha256").update(x).digest("hex");
const WORKER_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682";
const M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3";
assert.equal(sha(worker),WORKER_SHA);assert.equal(sha(migration),M43_SHA);
const start=worker.indexOf("async function redactExpiredDeviceCallContent(env, cutoff) {");
const end=worker.indexOf("\nasync function enqueueDeviceCall(",start);
assert.ok(start>0&&end>start);
const code=worker.slice(start,end);
const MARKER="HARA_REDACTED_SHA256:";
const NOW="2026-11-13T21:00:00.000Z";
const PAST="2026-11-13T20:00:00.000Z";
const period="2026-11",subject="QA_SYNTHETIC_SUBJECT";
const redact=x=>x==null||String(x).startsWith(MARKER)?x:MARKER+sha(String(x));
const deps={
 CALL_ROW_FIELDS, DEVICE_CALL_REDACTED_PREFIX:MARKER,
 DEVICE_CALL_CONTENT_REDACTION_MAX_BATCHES:3,DEVICE_CALL_CONTENT_REDACTION_BATCH:16,
 DEVICE_CALL_EXPIRY_MAINTENANCE_BATCH:16,nowIso:()=>NOW,
 isRedactedDeviceCallContent:x=>typeof x==="string"&&x.startsWith(MARKER),
 redactedDeviceCallContent:async x=>redact(x),settleCallUsage
};
const realCleanup=new Function(...Object.keys(deps),code+"\nreturn {redactExpiredDeviceCallContent,cleanupExpiredDeviceCalls};")(...Object.values(deps));
const cols=CALL_ROW_FIELDS.split(",");
const sqlSchema="CREATE TABLE commander_device_calls("+
 cols.map(c=>c==="call_id"?"call_id TEXT PRIMARY KEY":c==="request_id"?"request_id TEXT UNIQUE": ["usage_units","approval_timeout_seconds","execution_budget_ms"].includes(c)?c+" INTEGER":c+" TEXT").join(",")+
 ");CREATE INDEX idx_device_calls_expiry ON commander_device_calls(state,expires_at_utc);";
let mf,quota;
let db,ctx;
const nsName="QA_REAL_QUOTA_0043_EXPIRY_20261113";
async function boot(){
 mf=new Miniflare({
  host:"127.0.0.1",port:0,modules:true,
  modulesRoot:path.dirname(bundle),scriptPath:bundle,
  compatibilityDate:"2026-09-21",
  durableObjects:{
    TENANT_QUOTA:{className:"TenantQuota",useSQLite:true},
    DEVICE_CHANNEL:{className:"DeviceChannel",useSQLite:true},
    STRICT_RATE_LIMIT:{className:"SecurityRateLimit",useSQLite:true}
  },
  durableObjectsPersist:path.join(storageRoot,"do"),
  d1Databases:["PRODUCT_DB"],d1Persist:path.join(storageRoot,"d1"),
  bindings:{ENVIRONMENT:"DEV",STORAGE_MODE:"ISOLATED_QA",CUSTOMER_MCP_EDGE_ENABLED:"false",
   DEVICE_EVENT_V2_ENABLED:"false",STRIPE_CHECKOUT_ENABLED:"false"},
  outboundService:async()=>{throw Error("QA_EXTERNAL_EGRESS_DENIED");}
 });
 const ready=await mf.ready;assert.equal(ready.hostname,"127.0.0.1");
 const ns=await mf.getDurableObjectNamespace("TENANT_QUOTA");
 quota=ns.get(ns.idFromName(nsName));
}
function makeDb(){
 db=new DatabaseSync(":memory:");
 db.exec(sqlSchema);
 assert.equal(db.prepare("PRAGMA table_info(commander_device_calls)").all().length,21);
 db.exec(migration);
 assert.equal(db.prepare("PRAGMA table_info(commander_device_calls)").all().length,22);
 const tenant=nsName,call="QA_REAL_QUOTA_CALL",request="QA_REAL_QUOTA_REQUEST";
 const row={
  call_id:call,request_id:request,tenant_id:tenant,subject_id:subject,
  device_id:"QA_NO_REAL_AGENT",tool_id:"hara.device.info",
  state:"EXECUTING",created_at_utc:"2026-11-13T19:00:00.000Z",
  expires_at_utc:PAST,claimed_at_utc:"2026-11-13T19:30:00.000Z",
  completed_at_utc:null,payload_json:JSON.stringify({synthetic:true}),
  result_json:null,error_code:null,usage_mode:"CLOUD_QUOTA",usage_units:1,
  usage_period_key:period,usage_budget_id:null,approval_timeout_seconds:0,
  execution_budget_ms:0,call_result_metadata_json:null
 };
 const names=[...cols,"authorization_context_json"];
 db.prepare("INSERT INTO commander_device_calls("+names.join(",")+") VALUES("+names.map(()=>"?").join(",")+")")
 .run(...cols.map(n=>row[n]),"QA_SYNTHETIC_0043_CONTEXT");
 const adapter={
  prepare(sql){return{bind(...values){return{
   all:async()=>({results:db.prepare(sql).all(...values)}),
   first:async()=>db.prepare(sql).get(...values)??null,
   run:async()=>{const result=db.prepare(sql).run(...values);return{meta:{changes:result.changes}};}
  };}};},
  async batch(statements){for(const q of statements)await q.run();return[];}
 };
 return {env:{PRODUCT_DB:adapter,TENANT_QUOTA:{getByName(name){
  assert.equal(name,tenant);return quota;}}},
  row:()=>db.prepare("SELECT * FROM commander_device_calls").get()};
}
const cases=[];
const test=async(name,action)=>{const obj=await action();cases.push({name,state:"PASS",...obj});};
try{
 await boot();
 await test("real TenantQuota reserves and starts a synthetic call",async()=>{
  assert.equal((await quota.reserve("QA_REAL_QUOTA_REQUEST",subject,period,"qa:synthetic",30)).ok,true);
  const started=await quota.startDeviceCall("QA_REAL_QUOTA_REQUEST",subject,period,1);
  assert.equal(started.ok,true);
  assert.equal(started.execution_started,true);
  const status=await quota.status(period,30);
  assert.equal(status.consumed_units,1);
  return {quota_reserved:1,execution_started:true};
 });
 ctx=makeDb();
 await test("real cleanup EXPIRED calls real DO hold before redaction",async()=>{
  const result=await realCleanup.cleanupExpiredDeviceCalls(ctx.env);
  assert.equal(result.expired,1);assert.equal(result.redacted,1);
  const row=ctx.row();assert.equal(row.state,"EXPIRED");
  assert.ok(row.payload_json.startsWith(MARKER));
  const metadata=JSON.parse(row.call_result_metadata_json);
  assert.equal(metadata.usage.reconciliation_required,true);
  assert.equal(metadata.usage.execution_started,true);
  assert.equal(metadata.manual_reconciliation_required,true);
  const fence=await quota.cutoverFenceWitness("QA_REAL_QUOTA_HOLD_AFTER_EXPIRY");
  assert.equal(fence.protected_rows,1);assert.equal(fence.protected_units,1);
  const status=await quota.status(period,30);
  assert.equal(status.consumed_units,1);
  return {expired:1,redacted:1,quota_reserved:1,protected:1};
 });
 await test("real quota DO refuses premature automatic settlement of unknown effect",async()=>{
  const settlement=await quota.settleDeviceCall("QA_REAL_QUOTA_REQUEST",subject,period,1,null);
  assert.equal(settlement.ok,false);assert.equal(settlement.code,"CALL_RECONCILIATION_REQUIRED");
  const same=await quota.holdDeviceCall("QA_REAL_QUOTA_REQUEST",subject,period,1);
  assert.equal(same.ok,true);assert.equal(same.reconciliation_required,true);
  assert.equal((await quota.status(period,30)).consumed_units,1);
  return {automatic_release_blocked:true,idempotent_hold:true};
 });
 await test("repeating cleanup does not reexecute or release",async()=>{
  const result=await realCleanup.cleanupExpiredDeviceCalls(ctx.env);
  assert.equal(result.expired,0);assert.equal(result.redacted,0);
  assert.equal((await quota.status(period,30)).consumed_units,1);
  return {duplicate_cleanup_effects:0};
 });
 await mf.dispose();mf=null;await boot();
 await test("actual workerd restart preserves protected reservation",async()=>{
  const witness=await quota.cutoverFenceWitness("QA_REAL_QUOTA_AFTER_RESTART");
  assert.equal(witness.protected_rows,1);
  assert.equal(witness.protected_units,1);
  const status=await quota.status(period,30);
  assert.equal(status.consumed_units,1);
  const settlement=await quota.settleDeviceCall("QA_REAL_QUOTA_REQUEST",subject,period,1,null);
  assert.equal(settlement.code,"CALL_RECONCILIATION_REQUIRED");
  return {persisted_protected_units:1,settle_still_blocked:true};
 });
 assert.equal(cases.length,5);
 console.log(JSON.stringify({
  schema:"hara.commander-0043-real-tenant-quota-expiry-workerd.v1",
  state:"REAL_TENANT_QUOTA_EXPIRED_CLAIM_HOLD_WORKERD_PASS",
  worker_sha256:WORKER_SHA,migration_0043_sha256:M43_SHA,
  actual_tenantquota_worker_rpc:true,real_settleCallUsage:true,real_worker_cleanup:true,
  workerd_restart_preserved:true,protected_quota_units:1,
  cases,case_count:cases.length,provider_called:false,
  customer_data_used:false,agent_dispatched:false,production_mutated:false,
  cloudflare_hosted_proven:false,global_quiescence_proven:false,
  commercial_cutover_authorized:false
 }));
} finally {
 if(db)db.close();
 if(mf)await mf.dispose();
}