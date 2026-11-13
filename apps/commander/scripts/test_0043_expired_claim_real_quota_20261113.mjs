// H.A.R.A. Commander: 0043 expired claim + actual TenantQuota Durable Object.
// Workerd/Miniflare + isolated D1 SQLite. No Cloudflare/Agent/customer network.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {createRequire} from 'node:module';
import {DatabaseSync} from 'node:sqlite';
import {settleCallUsage,CALL_ROW_FIELDS} from '../src/approval-relay-storage.mjs';
const require=createRequire(import.meta.url);
const {Miniflare}=require('/tmp_hara/commander-capability-suite-20261110/node_modules/miniflare');
process.env.MINIFLARE_WORKERD_PATH='/home/sartorius/.npm/_npx/23be562fde961825/node_modules/workerd/bin/workerd';

const [bundle,store]=process.argv.slice(2);
assert.ok(bundle&&store&&path.resolve(store).startsWith('/tmp_hara/commander-0043-realquota-'));
const sha=s=>createHash('sha256').update(s).digest('hex');
const worker=readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
const migration=readFileSync(new URL('../migrations/0043_device_call_authorization.sql',import.meta.url),'utf8');
const WORKER_SHA='f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682';
const M43_SHA='7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3';
assert.equal(sha(worker),WORKER_SHA);assert.equal(sha(migration),M43_SHA);
const begin=worker.indexOf('async function redactExpiredDeviceCallContent(env, cutoff) {');
const end=worker.indexOf('\nasync function enqueueDeviceCall(',begin);
assert.ok(begin>=0&&end>begin);
const source=worker.slice(begin,end);
assert.ok(source.includes('claimedCloudQuota')&&source.includes('cleanupExpiredDeviceCalls'));

const MARKER='HARA_REDACTED_SHA256:',NOW='2026-11-13T22:00:00.000Z',PAST='2026-11-13T21:00:00.000Z';
const isMarker=x=>typeof x==='string'&&x.startsWith(MARKER);
const redact=async x=>x===null||isMarker(x)?x:MARKER+sha(String(x));
const deps={
 CALL_ROW_FIELDS,DEVICE_CALL_REDACTED_PREFIX:MARKER,
 DEVICE_CALL_CONTENT_REDACTION_MAX_BATCHES:3,
 DEVICE_CALL_CONTENT_REDACTION_BATCH:16,
 DEVICE_CALL_EXPIRY_MAINTENANCE_BATCH:16,
 nowIso:()=>NOW,isRedactedDeviceCallContent:isMarker,
 redactedDeviceCallContent:redact,settleCallUsage
};
const {redactExpiredDeviceCallContent,cleanupExpiredDeviceCalls}=new Function(
 ...Object.keys(deps),source+'\nreturn {redactExpiredDeviceCallContent,cleanupExpiredDeviceCalls};'
)(...Object.values(deps));
const columns=CALL_ROW_FIELDS.split(',');
const sqlSchema='CREATE TABLE commander_device_calls('+columns.map(c=>{
 if(c==='call_id')return 'call_id TEXT PRIMARY KEY';
 if(c==='request_id')return 'request_id TEXT UNIQUE';
 if(['usage_units','approval_timeout_seconds','execution_budget_ms'].includes(c))return c+' INTEGER';
 return c+' TEXT';
}).join(',')+');CREATE INDEX idx_device_calls_expiry ON commander_device_calls(state,expires_at_utc);';

let mf,namespace;
async function boot(){
 mf=new Miniflare({
  host:'127.0.0.1',port:0,modules:true,
  modulesRoot:path.dirname(bundle),scriptPath:bundle,
  compatibilityDate:'2026-09-21',
  durableObjects:{
    TENANT_QUOTA:{className:'TenantQuota',useSQLite:true},
    DEVICE_CHANNEL:{className:'DeviceChannel',useSQLite:true},
    STRICT_RATE_LIMIT:{className:'SecurityRateLimit',useSQLite:true}
  },
  durableObjectsPersist:path.join(store,'durable-objects'),
  d1Databases:['PRODUCT_DB'],d1Persist:path.join(store,'d1'),
  bindings:{
    ENVIRONMENT:'DEV',STORAGE_MODE:'ISOLATED_QA',
    CUSTOMER_MCP_EDGE_ENABLED:'false',DEVICE_EVENT_V2_ENABLED:'false',
    STRIPE_CHECKOUT_ENABLED:'false',AUTH_ISSUER:'https://qa-realquota.invalid/',
    AUTH_CLIENT_ID:'synthetic-only'
  },
  outboundService:async()=>{throw Error('QA_EXTERNAL_EGRESS_DENIED')}
 });
 const address=await mf.ready;
 assert.equal(address.hostname,'127.0.0.1');
 namespace=await mf.getDurableObjectNamespace('TENANT_QUOTA');
}
const actorByTenant=tenant=>namespace.get(namespace.idFromName(tenant));
let created=0,closed=0;
async function fixture({state='EXPIRED',approval=0,wrongSubject=false,fault=null}={}){
 const idx=++created;
 const db=new DatabaseSync(':memory:');
 db.exec(sqlSchema);
 assert.equal(db.prepare("PRAGMA table_info(commander_device_calls)").all().length,21);
 db.exec(migration);
 assert.equal(db.prepare("PRAGMA table_info(commander_device_calls)").all().length,22);
 const subject='QA_SUBJECT', period='2026-11';
 const tenant='QA_REAL_QUOTA_TENANT_'+idx;
 const request='QA_REAL_QUOTA_REQUEST_'+idx,callId='QA_REAL_QUOTA_CALL_'+idx;
 const quota=actorByTenant(tenant);
 const reserved=await quota.reserve(request,wrongSubject?'QA_OTHER_SUBJECT':subject,period,'tool:qa',30);
 assert.equal(reserved.ok,true);
 assert.equal((await quota.startDeviceCall(request,wrongSubject?'QA_OTHER_SUBJECT':subject,period,1)).ok,true);
 const row={
  call_id:callId,request_id:request,tenant_id:tenant,subject_id:subject,
  device_id:'QA_DEVICE',tool_id:'hara.device.info',state,
  created_at_utc:'2026-11-13T20:00:00.000Z',
  expires_at_utc:PAST,claimed_at_utc:'2026-11-13T20:10:00.000Z',
  completed_at_utc:state==='EXPIRED'?PAST:null,
  payload_json:JSON.stringify({synthetic:true,case:idx}),result_json:null,
  error_code:state==='EXPIRED'?'DEVICE_CALL_EXPIRED':null,
  usage_mode:'CLOUD_QUOTA',usage_units:1,usage_period_key:period,
  usage_budget_id:null,approval_timeout_seconds:approval,execution_budget_ms:0,
  call_result_metadata_json:null
 };
 const names=[...columns,'authorization_context_json'];
 db.prepare('INSERT INTO commander_device_calls('+names.join(',')+') VALUES('+names.map(()=>'?').join(',')+')')
  .run(...columns.map(c=>row[c]),'QA_0043_SYNTHETIC_CONTEXT');
 const counts={holdRequests:0,settleRequests:0};
 let faultMode=fault;
 const quotaCall={
  async holdDeviceCall(...args){
   counts.holdRequests++;
   if(faultMode==='hold-transport')throw Error('QA_SYNTHETIC_DO_RPC_OUTAGE');
   return quota.holdDeviceCall(...args);
  },
  async settleDeviceCall(...args){
   counts.settleRequests++;
   return quota.settleDeviceCall(...args);
  }
 };
 const adapter={
  prepare(query){return {bind(...args){return {
   all:async()=>({results:db.prepare(query).all(...args)}),
   first:async()=>db.prepare(query).get(...args)??null,
   run:async()=>{
    if(faultMode==='metadata-d1'&&query.includes('SET call_result_metadata_json=?'))
       throw Error('QA_SYNTHETIC_METADATA_D1_OUTAGE');
    const r=db.prepare(query).run(...args);return {meta:{changes:r.changes}};
   }
  };}};},
  async batch(statements){for(const statement of statements)await statement.run();return []}
 };
 const env={PRODUCT_DB:adapter,TENANT_QUOTA:{
  getByName(name){assert.equal(name,tenant);return quotaCall}
 }};
 return {
  env,quota,counts,tenant,request,subject,period,
  row:()=>db.prepare('SELECT * FROM commander_device_calls').get(),
  setFault:x=>{faultMode=x},
  async witness(label){return quota.cutoverFenceWitness(label)},
  async usage(){return quota.status(period,30)},
  close(){db.close();closed++}
 };
}

const cases=[],persist=[];
async function check(name,options,run){
 const f=await fixture(options);
 try{const more=await run(f);cases.push({name,state:'PASS',...more})}
 finally{f.close()}
}
try{
 await boot();
 await check('claimed_expired_quota_real_DO_hold_and_redact',{},async f=>{
  assert.equal((await f.usage()).consumed_units,1);
  assert.equal((await f.witness('QA_BEFORE_HOLD_CASE_1')).protected_rows,0);
  const r=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(r.redacted,1);assert.equal(f.counts.holdRequests,1);
  assert.equal(f.counts.settleRequests,0);assert.equal(isMarker(f.row().payload_json),true);
  assert.equal((await f.usage()).consumed_units,1);
  const w=await f.witness('QA_AFTER_HOLD_CASE_1');
  assert.equal(w.protected_rows,1);assert.equal(w.protected_units,1);
  persist.push({tenant:f.tenant,request:f.request,subject:f.subject,period:f.period});
  return {quota_do_real:true,hold_before_redaction:true,held_units:1};
 });
 await check('claimed_expired_async_profile_900_remains_protected',{approval:900},async f=>{
  const r=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(r.redacted,1);assert.equal(f.counts.holdRequests,1);
  assert.equal((await f.witness('QA_ASYNC_PROFILE_900_HOLD')).protected_units,1);
  return {async_profile_900:true};
 });
 await check('real_quota_RPC_failure_prevents_scrub',{fault:'hold-transport'},async f=>{
  const old=f.row().payload_json;
  const r=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(r.redacted,0);assert.equal(f.counts.holdRequests,1);
  assert.equal(f.row().payload_json,old);
  assert.equal((await f.usage()).consumed_units,1);
  assert.equal((await f.witness('QA_RPC_OUTAGE_UNHELD')).protected_rows,0);
  f.setFault(null);
  const resumed=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(resumed.redacted,1);
  assert.equal((await f.witness('QA_RPC_RECOVERED_HELD')).protected_units,1);
  return {failure_fail_closed:true,recovery_did_not_release_reservation:true};
 });
 await check('real_quota_subject_mismatch_fails_closed',{wrongSubject:true},async f=>{
  const original=f.row().payload_json;
  const r=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(r.redacted,0);
  assert.equal(f.row().payload_json,original);
  assert.equal((await f.usage()).consumed_units,1);
  assert.equal((await f.witness('QA_BINDING_MISMATCH')).protected_rows,0);
  return {binding_mismatch_denied:true,quota_consumed_unchanged:true};
 });
 await check('real_quota_hold_survives_D1_metadata_write_error',{fault:'metadata-d1'},async f=>{
  const original=f.row().payload_json;
  const r=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(r.redacted,0);
  assert.equal(f.row().payload_json,original);
  assert.equal((await f.witness('QA_METADATA_ERROR_PROTECTED')).protected_units,1);
  assert.equal((await f.usage()).consumed_units,1);
  f.setFault(null);
  const retried=await redactExpiredDeviceCallContent(f.env,NOW);
  assert.equal(retried.redacted,1);
  assert.equal((await f.witness('QA_METADATA_RECOVERED')).protected_units,1);
  return {D1_failure_detected:true,hold_persisted:true};
 });
 await check('real_quota_cleanup_EXECUTING_to_EXPIRED_preserves_hold',{state:'EXECUTING'},async f=>{
  const r=await cleanupExpiredDeviceCalls(f.env);
  assert.equal(r.expired,1);assert.equal(r.redacted,1);
  assert.equal(f.row().state,'EXPIRED');
  assert.equal((await f.witness('QA_EXPIRED_FROM_EXECUTING')).protected_units,1);
  assert.equal((await f.usage()).consumed_units,1);
  const repeated=await cleanupExpiredDeviceCalls(f.env);
  assert.deepEqual(repeated,{expired:0,redacted:0});
  return {expiring_execution_protected:true,idempotent:true};
 });
 await mf.dispose();mf=null;
 await boot();
 for(const item of persist){
  const quota=actorByTenant(item.tenant);
  const w=await quota.cutoverFenceWitness('QA_AFTER_WORKERD_RESTART_PERSISTENT');
  assert.equal(w.protected_rows,1);assert.equal(w.protected_units,1);
  assert.equal((await quota.status(item.period,30)).consumed_units,1);
  const held=await quota.holdDeviceCall(item.request,item.subject,item.period,1);
  assert.equal(held.ok,true);assert.equal(held.existing,true);
  assert.equal((await quota.status(item.period,30)).consumed_units,1);
 }
 cases.push({name:'real_quota_protected_reservation_survives_workerd_restart',state:'PASS',
  persisted_actors:persist.length,quota_units_held:1,hold_idempotent_after_restart:true});
 assert.equal(created,closed);
 console.log(JSON.stringify({
  schema:'hara.commander-0043-real-tenantquota-workerd.v1',
  state:'REAL_TENANT_QUOTA_EXPIRY_RECONCILIATION_WORKERD_PASS_GLOBAL_HOLD',
  worker_sha256:WORKER_SHA,migration_sha256:M43_SHA,
  cases,total_cases:cases.length,
  synthetic_d1_databases_closed:closed,
  real_tenant_quota_rpc_exercised:true,
  durable_object_persistence_after_restart:true,
  had_failing_real_quota_RPC_simulated:true,
  migration_original_0043_exercised:true,
  cloudflare_provider_called:false,real_agent_dispatched:false,customer_data_used:false,
  production_mutated:false,production_ledger_cutover_authorized:false
 }));
}finally{
 if(mf)await mf.dispose();
}