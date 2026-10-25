// #163/#322: uncertain execution is neither a proven denial nor a proven PASS.
// Journal/result bodies match the Windows recovery path. Only TenantQuota RPC
// is a fixture; call rows, scoped reads and metadata writes use real SQLite.
// No network, Cloudflare, signature, TTL extension or native quota mutation.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {CALL_ROW_FIELDS,settleCallUsage,acceptedCallStatus} from '../src/approval-relay-storage.mjs';
import {safeCallResultMetadata} from '../src/approval-async-relay.mjs';

const RECEIPT='a'.repeat(64);
const ID='HARA-CALL-11111111-2222-4333-8444-555555555555';
const unknownResult=withReceipt=>({
 state:'INDETERMINATE',runtime_authority_from_chatgpt:false,
 mutation_performed:null,result:{},blocker:{code:'CALL_OUTCOME_UNCERTAIN'},
 ...(withReceipt?{bridge_receipt_sha256:RECEIPT}:{}),
});

function fixture(t,{state='FAILED',error='CALL_OUTCOME_UNCERTAIN',result=unknownResult(false),metadata=null}={}){
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());
 const columns=CALL_ROW_FIELDS.split(',');
 const numeric=new Set(['usage_units','approval_timeout_seconds','execution_budget_ms']);
 db.exec('CREATE TABLE commander_device_calls('+columns.map(key=>key+' '+(numeric.has(key)?'INTEGER':'TEXT')).join(',')+',PRIMARY KEY(call_id))');
 const initial={
  call_id:ID,request_id:'synthetic-quota-request',tenant_id:'SYNTHETIC-TENANT-A',
  subject_id:'SYNTHETIC-SUBJECT-A',device_id:'SYNTHETIC-DEVICE-A',tool_id:'hara.files.write',state,
  created_at_utc:'2026-10-25T00:00:00.000Z',expires_at_utc:'2026-10-25T00:10:00.000Z',
  claimed_at_utc:'2026-10-25T00:01:00.000Z',completed_at_utc:'2026-10-25T00:02:00.000Z',
  payload_json:'{}',result_json:JSON.stringify(result),error_code:error,
  usage_mode:'CLOUD_QUOTA',usage_units:1,usage_period_key:'2026-10',usage_budget_id:null,
  approval_timeout_seconds:900,execution_budget_ms:10000,
  call_result_metadata_json:metadata?JSON.stringify(metadata):null,
 };
 db.prepare('INSERT INTO commander_device_calls('+columns.join(',')+') VALUES('+columns.map(()=>'?').join(',')+')')
  .run(...columns.map(key=>initial[key]));
 const writes=[],rpc=[],tenants=[];
 const reservation={state:'RESERVED',reserved_units:1,committed_units:0,released_units:0,transitions:0,receipt:null};
 const database={prepare:sql=>({bind:(...args)=>({
  first:async()=>db.prepare(sql).get(...args)??null,
  all:async()=>({results:db.prepare(sql).all(...args)}),
  run:async()=>{const actual=db.prepare(sql).run(...args);writes.push({sql,args});return {meta:{changes:actual.changes}};},
 })})};
 const env={PRODUCT_DB:database,TENANT_QUOTA:{getByName:tenant=>{
  tenants.push(tenant);
  return {settleDeviceCall:async(request,subject,period,units,receipt)=>{
   rpc.push({tenant,request,subject,period,units,receipt});
   assert.deepEqual({tenant,request,subject,period,units},{tenant:initial.tenant_id,
    request:initial.request_id,subject:initial.subject_id,period:initial.usage_period_key,units:1});
   // Existing RPC semantics: a null receipt RELEASES the reservation. Exact
   // repeated settlement is idempotent at the quota boundary, not a new debit.
   const next=receipt===null?'RELEASED':'COMMITTED';
   if(reservation.state==='RESERVED'){
    reservation.state=next;reservation.reserved_units=0;reservation.transitions++;
    reservation[next==='COMMITTED'?'committed_units':'released_units']=units;
    reservation.receipt=receipt;
   }
   return {ok:true,state:reservation.state};
  }};
 }}};
 let markerCalls=0;
 const options={nowUtc:'2026-10-25T00:03:00.000Z',
  expectedDeviceId:initial.device_id,
  isRedacted:raw=>{try{return JSON.parse(raw).redacted===true;}catch{return false;}},
  newMarker:async()=>{markerCalls++;return JSON.stringify({redacted:true});},
 };
 return {db,env,initial,result,writes,rpc,tenants,reservation,options,
  context:{tenant_id:initial.tenant_id,subject_id:initial.subject_id},
  row:()=>({...db.prepare('SELECT * FROM commander_device_calls WHERE call_id=?').get(ID)}),
  markerCalls:()=>markerCalls};
}

async function messageOf(work){
 try{await work();return null;}catch(error){return error.message;}
}
function requireUnsettled(f){
 assert.deepEqual(f.rpc,[],'uncertainty cannot be converted into a null-receipt quota RPC');
 assert.deepEqual(f.reservation,{state:'RESERVED',reserved_units:1,committed_units:0,
  released_units:0,transitions:0,receipt:null});
 assert.equal(f.writes.length,0,'no metadata may claim that uncertain execution was settled');
}

test('INDETERMINATE without a receipt holds quota and repeated settlement makes no RPC',async t=>{
 const f=fixture(t);const errors=[];
 const journalBody={call_id:ID,state:'FAILED',result:f.result,error_code:'CALL_OUTCOME_UNCERTAIN'};
 for(let i=0;i<3;i++)errors.push(await messageOf(()=>settleCallUsage(f.env,f.row(),journalBody.result)));
 requireUnsettled(f);
 assert.deepEqual(errors,Array(3).fill('CALL_EXECUTION_OUTCOME_UNKNOWN'));
 assert.equal(f.row().call_result_metadata_json,null);
});

test('INDETERMINATE with a preserved receipt still cannot prove commit or safe release',async t=>{
 const f=fixture(t,{result:unknownResult(true)});
 const error=await messageOf(()=>settleCallUsage(f.env,f.row(),f.result));
 requireUnsettled(f);assert.equal(error,'CALL_EXECUTION_OUTCOME_UNKNOWN');
 assert.equal(f.row().call_result_metadata_json,null);
 assert.equal(JSON.parse(f.row().result_json).bridge_receipt_sha256,RECEIPT);
});

test('redacted UNKNOWN metadata replays preserve the reservation and original metadata bytes',async t=>{
 const f=fixture(t,{result:unknownResult(true)});
 const metadata=safeCallResultMetadata(f.result,f.row());
 assert.equal(metadata.state,'UNKNOWN');assert.equal(metadata.mutation_performed,null);
 const encoded=JSON.stringify(metadata),redacted=JSON.stringify({redacted:true});
 f.db.prepare('UPDATE commander_device_calls SET call_result_metadata_json=?,result_json=? WHERE call_id=?')
  .run(encoded,redacted,ID);
 const errors=[];
 for(let i=0;i<3;i++)errors.push(await messageOf(()=>acceptedCallStatus(f.env,f.context,ID,f.options)));
 requireUnsettled(f);assert.deepEqual(errors,Array(3).fill('CALL_EXECUTION_OUTCOME_UNKNOWN'));
 assert.equal(f.row().call_result_metadata_json,encoded);
 assert.equal(f.row().result_json,redacted);assert.equal(f.markerCalls(),0);
});

test('a proven denial with mutation_performed false still releases exactly the existing reservation',async t=>{
 const denied={state:'DENIED',runtime_authority_from_chatgpt:false,mutation_performed:false,
  result:{},blocker:{code:'LOCAL_OPERATOR_DENIED'}};
 const f=fixture(t,{result:denied,error:'LOCAL_OPERATOR_DENIED'});
 for(let i=0;i<2;i++)await settleCallUsage(f.env,f.row(),denied);
 assert.equal(f.rpc.length,2);assert.ok(f.rpc.every(call=>call.receipt===null));
 assert.equal(f.reservation.state,'RELEASED');assert.equal(f.reservation.transitions,1);
 assert.equal(f.reservation.released_units,1);assert.equal(f.reservation.committed_units,0);
 const metadata=JSON.parse(f.row().call_result_metadata_json);
 assert.equal(metadata.usage.state,'RELEASED');assert.equal(metadata.usage.units,0);
 assert.equal(metadata.usage.period_key,'2026-10');
});

test('COMPLETED PASS with a correlated receipt still commits once and repeats idempotently',async t=>{
 const passed={state:'PASS',runtime_authority_from_chatgpt:false,mutation_performed:true,
  bridge_receipt_sha256:RECEIPT,result:{function_id:'filesystem.write',risk_class:'FILESYSTEM_MUTATION'}};
 const f=fixture(t,{state:'COMPLETED',error:null,result:passed});
 for(let i=0;i<2;i++)await settleCallUsage(f.env,f.row(),passed);
 assert.equal(f.rpc.length,2);assert.ok(f.rpc.every(call=>call.receipt===RECEIPT));
 assert.equal(f.reservation.state,'COMMITTED');assert.equal(f.reservation.transitions,1);
 assert.equal(f.reservation.committed_units,1);assert.equal(f.reservation.released_units,0);
 const metadata=JSON.parse(f.row().call_result_metadata_json);
 assert.equal(metadata.usage.state,'COMMITTED');assert.equal(metadata.usage.units,1);
 assert.equal(metadata.usage.period_key,'2026-10');
});

test('scoped status rejects other tenants or subjects before quota access and keeps the original period',async t=>{
 const denied={state:'DENIED',runtime_authority_from_chatgpt:false,mutation_performed:false,result:{}};
 const f=fixture(t,{result:denied,error:'LOCAL_OPERATOR_DENIED'});
 for(const context of [{...f.context,tenant_id:'OTHER-TENANT'},
  {...f.context,subject_id:'OTHER-SUBJECT'}]){
  await assert.rejects(()=>acceptedCallStatus(f.env,context,ID,f.options),/DEVICE_CALL_NOT_FOUND/);
 }
 assert.equal(f.rpc.length,0);assert.equal(f.writes.length,0);assert.equal(f.tenants.length,0);
 const status=await acceptedCallStatus(f.env,f.context,ID,f.options);
 assert.deepEqual(f.tenants,[f.context.tenant_id]);
 assert.deepEqual(f.rpc,[{tenant:f.context.tenant_id,request:f.initial.request_id,
  subject:f.context.subject_id,period:'2026-10',units:1,receipt:null}]);
 assert.equal(status.metadata.usage.period_key,f.initial.usage_period_key);
 assert.equal(f.reservation.transitions,1);
});
