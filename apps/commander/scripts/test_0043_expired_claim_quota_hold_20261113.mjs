// H.A.R.A. Commander - original cleanupExpiredDeviceCalls, real SQL/0043 migration,
// real settleCallUsage, synthetic-only quota and DB. NO Agent/Cloudflare/Stripe.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {settleCallUsage,CALL_ROW_FIELDS} from '../src/approval-relay-storage.mjs';

const worker=readFileSync(new URL('../src/worker.js',import.meta.url),'utf8');
const migration=readFileSync(new URL('../migrations/0043_device_call_authorization.sql',import.meta.url),'utf8');
const sourceSha=createHash('sha256').update(worker).digest('hex');
const migrationSha=createHash('sha256').update(migration).digest('hex');
const WORKER_EXPECTED='f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682';
const M43_EXPECTED='7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3';
assert.equal(sourceSha,WORKER_EXPECTED);
assert.equal(migrationSha,M43_EXPECTED);
const sourceStart=worker.indexOf('async function redactExpiredDeviceCallContent(env, cutoff) {');
const sourceEnd=worker.indexOf('\nasync function enqueueDeviceCall(',sourceStart);
assert.ok(sourceStart>0&&sourceEnd>sourceStart);
const src=worker.slice(sourceStart,sourceEnd);
assert.ok(src.includes('async function cleanupExpiredDeviceCalls(env)'));
assert.ok(src.includes("SET state = 'EXPIRED'"));
assert.ok(src.includes('await settleCallUsage(env,row,raw)'));
const MARKER='HARA_REDACTED_SHA256:';
const NOW='2026-11-13T20:00:00.000Z',PAST='2026-11-13T19:00:00.000Z';
const hash=(value)=>createHash('sha256').update(String(value)).digest('hex');
const isRedacted=value=>typeof value==='string'&&value.startsWith(MARKER);
const redact=value=>value==null||isRedacted(value)?value:MARKER+hash(value);
const dependencies={
 CALL_ROW_FIELDS,DEVICE_CALL_REDACTED_PREFIX:MARKER,
 DEVICE_CALL_CONTENT_REDACTION_MAX_BATCHES:3,
 DEVICE_CALL_CONTENT_REDACTION_BATCH:16,
 DEVICE_CALL_EXPIRY_MAINTENANCE_BATCH:16,
 nowIso:()=>NOW,
 isRedactedDeviceCallContent:isRedacted,
 redactedDeviceCallContent:async v=>redact(v),
 settleCallUsage
};
const tools=new Function(...Object.keys(dependencies),src+'\nreturn {redactExpiredDeviceCallContent,cleanupExpiredDeviceCalls};')(...Object.values(dependencies));
const cols=CALL_ROW_FIELDS.split(',');
const sqlSchema='CREATE TABLE commander_device_calls('+cols.map(c=>{
 if(c==='call_id')return 'call_id TEXT PRIMARY KEY';
 if(c==='request_id')return 'request_id TEXT UNIQUE';
 if(['usage_units','approval_timeout_seconds','execution_budget_ms'].includes(c))return c+' INTEGER';
 return c+' TEXT';
}).join(',')+');CREATE INDEX idx_device_calls_expiry ON commander_device_calls(state,expires_at_utc);';
let created=0,closed=0;
function fixture({claimed=true,mode='CLOUD_QUOTA',approval=0,state='EXPIRED',result=null,failHold=false,failMetadata=false}={}) {
 const db=new DatabaseSync(':memory:');created++;
 db.exec(sqlSchema);
 assert.equal(db.prepare("PRAGMA table_info(commander_device_calls)").all().length,21);
 db.exec(migration);
 assert.equal(db.prepare("PRAGMA table_info(commander_device_calls)").all().length,22);
 const row={
  call_id:'QA_CALL_EXPIRED_'+created,request_id:'QA_REQ_'+created,tenant_id:'QA_TENANT',
  subject_id:'QA_SUBJECT',device_id:'QA_DEVICE',tool_id:'hara.device.info',
  state,created_at_utc:'2026-11-13T18:00:00.000Z',
  expires_at_utc:PAST,claimed_at_utc:claimed?'2026-11-13T18:10:00.000Z':null,
  completed_at_utc:state==='EXPIRED'?PAST:null,
  payload_json:JSON.stringify({qa_synthetic_only:true,seq:created}),
  result_json:result==null?null:JSON.stringify(result),error_code:state==='EXPIRED'?'DEVICE_CALL_EXPIRED':null,
  usage_mode:mode,usage_units:mode==='CLOUD_QUOTA'?1:0,usage_period_key:'2026-11',
  usage_budget_id:null,approval_timeout_seconds:approval,execution_budget_ms:0,
  call_result_metadata_json:null
 };
 const names=[...cols,'authorization_context_json'];
 db.prepare('INSERT INTO commander_device_calls('+names.join(',')+') VALUES('+names.map(()=>'?').join(',')+')')
 .run(...cols.map(c=>row[c]),'QA_0043_CONTEXT_SYNTHETIC');
 const attempts=[];
 const quota={
  async holdDeviceCall(requestId,subjectId,period,units) {
   attempts.push({operation:'HOLD',requestId,subjectId,period,units});
   if(failHold)return {ok:false,code:'QA_SYNTHETIC_HOLD_UNAVAILABLE'};
   return {ok:true,state:'HELD',units,execution_started:true,
      reconciliation_required:true,reconciled:false,settlement_already_terminal:false};
  },
  async settleDeviceCall() {
   attempts.push({operation:'SETTLE'});
   throw Error('QA_UNEXPECTED_QUOTA_RELEASE');
  }
 };
 const adapter={
  prepare(query){return {bind(...args){return {
   all:async()=>({results:db.prepare(query).all(...args)}),
   first:async()=>db.prepare(query).get(...args)??null,
   run:async()=>{
    if(failMetadata && query.includes('SET call_result_metadata_json=?'))
       throw Error('QA_SYNTHETIC_METADATA_D1_OUTAGE');
    const v=db.prepare(query).run(...args);return {meta:{changes:v.changes}};
   }
  };}};},
  async batch(statements){for(const q of statements)await q.run();return [];}
 };
 const env={PRODUCT_DB:adapter,TENANT_QUOTA:{getByName(n){assert.equal(n,row.tenant_id);return quota;}}};
 return {env,db,attempts,row:()=>db.prepare('SELECT * FROM commander_device_calls').get(),close(){db.close();closed++;}};
}
const cases=[];
async function check(name,options,act){
 const f=fixture(options);
 try{const result=await act(f);cases.push({name,state:'PASS',...result});}
 finally{f.close();}
}
const isMarker=r=>r.payload_json.startsWith(MARKER);
await check('CLAIMED_CLOUD_QUOTA_EXPIRED_REQUIRES_HOLD_BEFORE_REDACTION',{},async f=>{
 const result=await tools.redactExpiredDeviceCallContent(f.env,NOW);
 assert.equal(f.attempts.filter(x=>x.operation==='HOLD').length,1,
  'claimed non-900 expired call was scrubbed without protecting uncertain Cloud quota');
 assert.equal(f.attempts.filter(x=>x.operation==='SETTLE').length,0);
 assert.equal(result.redacted,1);
 assert.equal(isMarker(f.row()),true);
 assert.ok(f.row().call_result_metadata_json);
 return {protected_before_redaction:true,redacted:result.redacted};
});
await check('FAILED_QUOTA_HOLD_MUST_NOT_SCRUB_UNCERTAIN_CLAIM',{failHold:true},async f=>{
 const before=f.row().payload_json;
 const result=await tools.redactExpiredDeviceCallContent(f.env,NOW);
 assert.equal(f.attempts.filter(x=>x.operation==='HOLD').length,1);
 assert.equal(result.redacted,0,'no redaction can claim success when quota hold failed');
 assert.equal(f.row().payload_json,before,'unproven settlement needs original evidence');
 return {redaction_blocked_on_hold_failure:true};
});
await check('ASYNC_900_PROFILE_STILL_PRESERVES_EXISTING_QUOTA_HOLD',{approval:900},async f=>{
 const result=await tools.redactExpiredDeviceCallContent(f.env,NOW);
 assert.equal(result.redacted,1);assert.equal(f.attempts.length,1);
 assert.equal(f.attempts[0].operation,'HOLD');
 return {existing_async_behavior_preserved:true};
});
await check('UNMETERED_EXPIRED_CALL_CAN_REDACT_WITHOUT_CLOUD_QUOTA',{mode:'UNMETERED'},async f=>{
 const result=await tools.redactExpiredDeviceCallContent(f.env,NOW);
 assert.equal(result.redacted,1);assert.equal(f.attempts.length,0);
 return {unmetered_redacted:true};
});
await check('UNCLAIMED_EXPIRED_PENDING_NO_EXECUTION_HOLD',{claimed:false},async f=>{
 const result=await tools.redactExpiredDeviceCallContent(f.env,NOW);
 assert.equal(result.redacted,1);assert.equal(f.attempts.length,0);
 return {no_agent_claim:true};
});
await check('EXPIRY_MAINTENANCE_MARKS_AND_HOLDS_CLAIMED_CLOUD_QUOTA',{state:'EXECUTING'},async f=>{
 const result=await tools.cleanupExpiredDeviceCalls(f.env);
 assert.equal(result.expired,1);assert.equal(result.redacted,1);
 assert.equal(f.row().state,'EXPIRED');
 assert.equal(f.attempts.filter(x=>x.operation==='HOLD').length,1);
 return {expired:result.expired,quota_held:true};
});
await check('METADATA_D1_WRITE_ERROR_PREVENTS_REDACTION',{failMetadata:true},async f=>{
 const before=f.row().payload_json;
 const result=await tools.redactExpiredDeviceCallContent(f.env,NOW);
 assert.equal(f.attempts.filter(x=>x.operation==='HOLD').length,1);
 assert.equal(result.redacted,0);
 assert.equal(f.row().payload_json,before);
 return {metadata_unproven_fail_closed:true};
});
await check('REPEATED_MAINTENANCE_DOES_NOT_RELEASE_OR_DISPATCH',{state:'EXECUTING'},async f=>{
 const first=await tools.cleanupExpiredDeviceCalls(f.env);
 const second=await tools.cleanupExpiredDeviceCalls(f.env);
 assert.equal(first.expired,1);assert.equal(first.redacted,1);
 assert.equal(second.expired,0);assert.equal(second.redacted,0);
 assert.equal(f.attempts.filter(x=>x.operation==='SETTLE').length,0);
 return {idempotent_cleanup:true,automatic_retry:false};
});
assert.equal(created,closed);
console.log(JSON.stringify({
 schema:'hara.commander.p0-expired-cloud-quota-reconciliation-local.v1',
 state:'EXPIRED_CLAIM_QUOTA_PROTECTION_QA_PASS',
 worker_source_sha256:sourceSha,migration_0043_sha256:migrationSha,
 real_worker_cleanup_source_exercised:true,real_settleCallUsage_exercised:true,
 total_cases:cases.length,cases,synthetic_databases_closed:closed,
 cloudflare_called:false,real_agent_dispatched:false,
 customer_data_used:false,production_mutated:false,
 production_cutover_authorized:false
}));