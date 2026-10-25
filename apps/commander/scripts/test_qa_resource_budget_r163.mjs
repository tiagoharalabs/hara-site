// #163 resource-budget boundary tests. SQLite is real; all pins, admission rows,
// collector snapshots and D1 metadata below are synthetic fixtures, not native
// approval, measured Cloudflare usage, or permission to execute a campaign.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {BUDGET_SCHEMA} from './recovery_queue_budget_r163.mjs';
import {RESOURCE_BUDGET_SCHEMA,BILLING_METERS,OPERATION_DIMENSIONS,ResourceBudget}
 from '../src/qa-resource-budget.mjs';

const NOW=Date.parse('2026-10-25T03:00:00.000Z');
const BILLING=['worker_requests','worker_cpu_us','do_requests','do_active_gb_us',
 'do_storage_reads','do_storage_writes','do_storage_byte_seconds','d1_rows_read',
 'd1_rows_written','queue_billable_ops','dlq_billable_ops'];
const DIMENSIONS=[...BILLING,'do_alarms','ws_handshakes','ws_messages_in',
 'ws_messages_out','reconnect_attempts','events'];
const vector=value=>Object.fromEntries(DIMENSIONS.map(key=>[key,value]));
const upper=extra=>({...vector(0),worker_requests:1,worker_cpu_us:1000,
 d1_rows_read:128,d1_rows_written:32,events:1,...extra});

function fixture(t,{caps=vector(100000),charged=vector(0),meter=(_query,result)=>result}={}){
 const sqlite=new DatabaseSync(':memory:');t.after(()=>sqlite.close());
 sqlite.exec(BUDGET_SCHEMA);sqlite.exec(RESOURCE_BUDGET_SCHEMA);
 sqlite.exec('CREATE TABLE budget_work(id INTEGER PRIMARY KEY,value TEXT)');
 sqlite.prepare(`INSERT INTO r163_qa_budget
  (id,state,start_ms,deadline_ms,rows_read,rows_written,active_ms_used,
   reserved_read,reserved_write,queue_ops_upper,events_reserved,invocations)
  VALUES(1,'ACTIVE',?,?,?,?,?,?,?,?,?,?)`)
  .run(NOW-10000,NOW+600000,100,20,5000,0,0,0,0,7);
 const pins={admission:'a'.repeat(64),source:'b'.repeat(64),resource:'c'.repeat(64),profile:'d'.repeat(64)};
 const provider={...Object.fromEntries(BILLING.map(key=>[key,2])),d1_rows_read:100,d1_rows_written:20};
 sqlite.prepare(`INSERT INTO r163_qa_resource_budget
  (id,admission_sha256,source_sha256,resource_sha256,profile_sha256,caps_json,
   charged_upper_json,provider_json,provider_captured_ms,provider_complete_ms,revision)
  VALUES(1,?,?,?,?,?,?,?,?,?,0)`)
  .run(pins.admission,pins.source,pins.resource,pins.profile,JSON.stringify(caps),
       JSON.stringify(charged),JSON.stringify(provider),NOW-1000,NOW-1000);
 const queries=[];let sent=0;
 const queryInfo=(sql,method,inBatch)=>({sql,method,inBatch,
  isBusiness:/\bbudget_work\b/i.test(sql),
  isResourceDebit:/\bUPDATE\s+r163_qa_resource_budget\b/i.test(sql)&&/charged_upper_json/i.test(sql)});
 function statement(sql,args=[]){
  const executeRaw=method=>{
   const before=sqlite.prepare('SELECT total_changes() AS n').get().n;
   const prepared=sqlite.prepare(sql);
   const rows=method==='run'?(prepared.run(...args),[]):prepared.all(...args);
   const writes=sqlite.prepare('SELECT total_changes() AS n').get().n-before;
   return {success:true,results:rows,meta:{changes:writes,rows_read:Math.max(1,rows.length),rows_written:writes}};
  };
  const execute=async(method,inBatch=false)=>{
   const query=queryInfo(sql,method,inBatch);queries.push(query);
   const result=await meter(query,executeRaw(method));
   return method==='first'?result?.results?.[0]??null:result;
  };
  return {bind:(...bound)=>statement(sql,bound),all:()=>execute('all'),
   run:()=>execute('run'),first:()=>execute('first'),_raw:executeRaw,_sql:sql};
 }
 const database={prepare:sql=>statement(sql),batch:async statements=>{
  let results;
  sqlite.exec('BEGIN IMMEDIATE');
  try{results=statements.map(s=>s._raw('all'));sqlite.exec('COMMIT');}
  catch(error){sqlite.exec('ROLLBACK');throw error;}
  // The SQL batch commits atomically. Its response may then be lost or have
  // invalid metering; this must never turn an unknown debit into a refund.
  const returned=[];
  for(let i=0;i<statements.length;i++){
   const query=queryInfo(statements[i]._sql,'all',true);queries.push(query);
   returned.push(await meter(query,results[i]));
  }
  return returned;
 }};
 const env={ENVIRONMENT:'DEV',R163_QA_ISOLATED:'true',R163_QA_BUDGET_V2_ENABLED:'true',
  R163_QA_ADMISSION_SHA256:pins.admission,R163_QA_SOURCE_SHA256:pins.source,
  R163_QA_RESOURCE_SHA256:pins.resource,R163_QA_METER_PROFILE_SHA256:pins.profile,
  PRODUCT_DB:database,RECOVERY_DELIVERY_QUEUE:{sendBatch:async entries=>{sent+=entries.length;}}};
 const resource=()=>({...sqlite.prepare('SELECT * FROM r163_qa_resource_budget WHERE id=1').get()});
 return {sqlite,env,queries,pins,provider,resource,sent:()=>sent,
  parent:()=>({...sqlite.prepare('SELECT * FROM r163_qa_budget WHERE id=1').get()}),
  charged:()=>JSON.parse(resource().charged_upper_json),
  effects:()=>sqlite.prepare('SELECT * FROM budget_work ORDER BY id').all().map(row=>({...row})),
  budget:()=>new ResourceBudget(env,{now:()=>NOW})};
}
const invoke=(f,work=async()=>null,id='fixture-op-1',bound=upper())=>
 f.budget().run('WORKER_FETCH',bound,work,{operationId:id});

test('all billing meters and operation dimensions are explicit and complete',()=>{
 assert.deepEqual([...BILLING_METERS].sort(),[...BILLING].sort());
 assert.deepEqual([...OPERATION_DIMENSIONS].sort(),[...DIMENSIONS].sort());
 assert.equal(new Set(OPERATION_DIMENSIONS).size,17);
});

test('an opaque grant irreversibly charges every requested upper dimension',async t=>{
 const f=fixture(t);const request=upper({do_alarms:1,ws_handshakes:1,ws_messages_in:3,
  ws_messages_out:2,reconnect_attempts:1,queue_billable_ops:12,dlq_billable_ops:3});
 const provider=f.resource().provider_json;
 const grant=await f.budget().reserve('WORKER_FETCH',request,{operationId:'fixture-grant-1'});
 assert.ok(grant);assert.notEqual(grant,f.env);assert.notDeepEqual(grant,request);
 assert.deepEqual(f.charged(),request);assert.equal(f.resource().provider_json,provider);
 assert.equal(f.parent().state,'ACTIVE');
});

test('successful work keeps conservative charges separate from actual provider counters',async t=>{
 const f=fixture(t);const before=f.parent();const provider=f.resource().provider_json;
 const value=await invoke(f,async env=>{
  await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'measured fixture').run();
  return 'complete';
 });
 assert.equal(value,'complete');assert.deepEqual(f.charged(),upper());
 assert.equal(f.resource().provider_json,provider,'upper/model counts cannot overwrite collector actuals');
 assert.ok(f.parent().rows_read>=before.rows_read);assert.ok(f.parent().rows_written>=before.rows_written);
 assert.deepEqual(f.effects(),[{id:1,value:'measured fixture'}]);
});

test('a callback crash retains its complete debit across a new budget instance',async t=>{
 const f=fixture(t);
 await assert.rejects(()=>invoke(f,async()=>{throw Error('SYNTHETIC_CALLBACK_CRASH');}),/SYNTHETIC|HOLD/);
 assert.deepEqual(f.charged(),upper());assert.equal(f.parent().state,'STOPPED');
 let entered=0;
 await assert.rejects(()=>invoke(f,async()=>{entered++;},'fixture-after-crash'));
 assert.equal(entered,0);assert.deepEqual(f.charged(),upper());
});

test('duplicate operation identities cannot obtain another grant or debit twice',async t=>{
 const f=fixture(t);const budget=f.budget();
 await budget.reserve('WORKER_FETCH',upper(),{operationId:'fixture-duplicate-1'});
 await assert.rejects(()=>budget.reserve('WORKER_FETCH',upper(),{operationId:'fixture-duplicate-1'}));
 assert.deepEqual(f.charged(),upper());
});

test('concurrent reservations fence all dimensions atomically, including the last dimension',async t=>{
 const f=fixture(t,{caps:{...vector(100000),events:1}});
 const outcomes=await Promise.allSettled([
  f.budget().reserve('WORKER_FETCH',upper(),{operationId:'fixture-concurrent-a'}),
  f.budget().reserve('WORKER_FETCH',upper(),{operationId:'fixture-concurrent-b'}),
 ]);
 assert.equal(outcomes.filter(x=>x.status==='fulfilled').length,1);
 assert.deepEqual(f.charged(),upper(),'a rejected all-dimension claim cannot partially debit other meters');
});

test('an exhausted dimension rejects without a partial resource debit',async t=>{
 const f=fixture(t,{caps:{...vector(100000),events:0}});
 await assert.rejects(()=>f.budget().reserve('WORKER_FETCH',upper(),{operationId:'fixture-over-cap'}));
 assert.deepEqual(f.charged(),vector(0));
});

test('DEV isolation and the default-OFF V2 flag precede every database or work operation',async t=>{
 for(const change of [{ENVIRONMENT:'PROD'},{R163_QA_ISOLATED:'false'},
  {R163_QA_BUDGET_V2_ENABLED:undefined},{R163_QA_BUDGET_V2_ENABLED:true}]){
  const f=fixture(t);Object.assign(f.env,change);let entered=0;
  await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.equal(entered,0);assert.equal(f.queries.length,0);
 }
});

test('all native identity and collector-profile pins must match the protected row',async t=>{
 for(const key of ['R163_QA_ADMISSION_SHA256','R163_QA_SOURCE_SHA256',
  'R163_QA_RESOURCE_SHA256','R163_QA_METER_PROFILE_SHA256']){
  const f=fixture(t);f.env[key]='e'.repeat(64);let entered=0;
  await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.equal(entered,0);assert.deepEqual(f.charged(),vector(0));
 }
});

test('arbitrary approved JSON cannot replace a missing native resource admission',async t=>{
 const f=fixture(t);f.sqlite.exec('DELETE FROM r163_qa_resource_budget');
 f.env.R163_QA_APPROVAL_JSON=JSON.stringify({approved:true,caps:vector(100000),...f.pins});
 let entered=0;await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
 assert.equal(entered,0);assert.equal(f.parent().state,'STOPPED');
});

test('a stale or incomplete provider snapshot stops the canonical parent before work',async t=>{
 for(const changes of [
  {provider_captured_ms:NOW-60001,provider_complete_ms:NOW-60001},
  {provider_captured_ms:NOW-1000,provider_complete_ms:NOW-60001},
  {provider_captured_ms:NOW-1000,provider_complete_ms:0},
 ]){
  const f=fixture(t);f.sqlite.prepare('UPDATE r163_qa_resource_budget SET provider_captured_ms=?,provider_complete_ms=?')
   .run(changes.provider_captured_ms,changes.provider_complete_ms);
  let entered=0;await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.equal(entered,0);assert.equal(f.parent().state,'STOPPED');
  assert.deepEqual(f.charged(),vector(0));
 }
});

test('missing, boolean or non-JSON provider meters never fall back to actual zero',async t=>{
 for(const mode of ['missing','boolean','NaN']){
  const f=fixture(t);const snapshot={...f.provider};
  if(mode==='missing')delete snapshot.do_active_gb_us;
  if(mode==='boolean')snapshot.worker_cpu_us=true;
  let json=JSON.stringify(snapshot);
  if(mode==='NaN')json=json.replace('"worker_cpu_us":2','"worker_cpu_us":NaN');
  f.sqlite.prepare('UPDATE r163_qa_resource_budget SET provider_json=?').run(json);
  let entered=0;await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.equal(entered,0);assert.equal(f.parent().state,'STOPPED');
 }
});

test('provider counters cannot decrease between native snapshot revisions',async t=>{
 const f=fixture(t);const budget=f.budget();
 await budget.reserve('WORKER_FETCH',upper(),{operationId:'fixture-before-meter'});
 f.sqlite.prepare('UPDATE r163_qa_resource_budget SET provider_json=?,revision=revision+1')
  .run(JSON.stringify({...f.provider,worker_requests:1}));
 await assert.rejects(()=>budget.reserve('WORKER_FETCH',upper(),{operationId:'fixture-after-meter'}));
 assert.equal(f.parent().state,'STOPPED');assert.deepEqual(f.charged(),upper());
});

test('strict upper shapes and integer values reject malformed debit vectors',async t=>{
 for(const change of [{events:-1},{worker_cpu_us:true},{do_active_gb_us:0.5},
  {worker_requests:Number.MAX_SAFE_INTEGER+1},{unknown_dimension:1}]){
  const f=fixture(t);await assert.rejects(()=>invoke(f,async()=>null,'fixture-bad-upper',upper(change)));
  assert.deepEqual(f.charged(),vector(0));
 }
 const f=fixture(t);const missing=upper();delete missing.ws_messages_out;
 await assert.rejects(()=>invoke(f,async()=>null,'fixture-missing-dim',missing));
 assert.deepEqual(f.charged(),vector(0));
});

test('D1 control escrow and a physical request are mandatory before work',async t=>{
 for(const change of [{d1_rows_read:63},{d1_rows_written:15},{worker_requests:0}]){
  const f=fixture(t);let entered=0;
  await assert.rejects(()=>invoke(f,async()=>{entered++;},'fixture-bad-minimum',upper(change)));
  assert.equal(entered,0);assert.deepEqual(f.charged(),vector(0));
 }
});

test('caps must contain every operation dimension with strict safe integer bounds',async t=>{
 for(const mode of ['missing','boolean']){
  const caps=vector(100000);
  if(mode==='missing')delete caps.do_storage_byte_seconds;else caps.ws_handshakes=true;
  const f=fixture(t,{caps});let entered=0;
  await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.equal(entered,0);assert.equal(f.parent().state,'STOPPED');
 }
});

test('a lost or invalid response after an atomic resource debit retains charge and starts no callback',async t=>{
 for(const mode of ['throw','missing-meta','negative-meta']){
  let injected=false;
  const f=fixture(t,{meter:(query,result)=>{
   if(query.isResourceDebit&&!injected){
    injected=true;
    if(mode==='throw')throw Error('SYNTHETIC_DEBIT_RESPONSE_LOST_AFTER_COMMIT');
    if(mode==='missing-meta')return {results:result.results};
    return {...result,meta:{...result.meta,rows_read:-1}};
   }
   return result;
  }});
  let entered=0;await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.ok(injected,mode);assert.equal(entered,0);assert.equal(f.parent().state,'STOPPED');
  for(const key of DIMENSIONS)assert.ok(f.charged()[key]>=upper()[key],key+' cannot be refunded on uncertainty');
 }
});

test('a swallowed D1 meter fault fences later SQL, queue sends and success',async t=>{
 const f=fixture(t,{meter:(query,result)=>query.isBusiness?{results:result.results}:result});
 await assert.rejects(()=>invoke(f,async env=>{
  try{await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'unknown spend').run();}catch{}
  try{await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(2,'must not run').run();}catch{}
  try{await env.RECOVERY_DELIVERY_QUEUE.sendBatch([{body:{id:'must-not-send'}}]);}catch{}
  return 'invalid success';
 },'fixture-caught-fault',upper({queue_billable_ops:12})));
 assert.deepEqual(f.effects(),[{id:1,value:'unknown spend'}]);
 assert.equal(f.queries.filter(query=>query.isBusiness).length,1);assert.equal(f.sent(),0);
 assert.equal(f.parent().state,'STOPPED');assert.deepEqual(f.charged(),upper({queue_billable_ops:12}));
});

test('a paused or stopped canonical campaign cannot be resumed by a new ResourceBudget',async t=>{
 for(const state of ['PAUSED','STOPPED']){
  const f=fixture(t);f.sqlite.prepare('UPDATE r163_qa_budget SET state=?').run(state);
  const before=f.parent();let entered=0;
  await assert.rejects(async()=>invoke(f,async()=>{entered++;}));
  assert.equal(entered,0);assert.notEqual(f.parent().state,'ACTIVE');
  assert.equal(f.parent().start_ms,before.start_ms);assert.equal(f.parent().active_ms_used,before.active_ms_used);
  assert.ok(f.parent().rows_read>=before.rows_read);assert.deepEqual(f.charged(),vector(0));
 }
});

test('explicit stop is durable and preserves native identity, charges and historical counters',async t=>{
 const f=fixture(t);const budget=f.budget();
 await budget.reserve('WORKER_FETCH',upper(),{operationId:'fixture-before-stop'});
 const before=f.parent(),resource=f.resource();await budget.stop('SYNTHETIC_TEST_STOP');
 assert.equal(f.parent().state,'STOPPED');assert.deepEqual(f.charged(),upper());
 assert.equal(f.parent().start_ms,before.start_ms);assert.equal(f.parent().deadline_ms,before.deadline_ms);
 assert.equal(f.parent().active_ms_used,before.active_ms_used);assert.ok(f.parent().rows_read>=before.rows_read);
 for(const key of ['admission_sha256','source_sha256','resource_sha256','profile_sha256','caps_json','provider_json'])
  assert.equal(f.resource()[key],resource[key]);
 await assert.rejects(()=>f.budget().reserve('WORKER_FETCH',upper(),{operationId:'fixture-after-stop'}));
 assert.deepEqual(f.charged(),upper());
});

test('fresh review: a failed second batch statement rolls back the first SQL effect',async t=>{
 const f=fixture(t);let rejected;
 try{
  await invoke(f,env=>env.PRODUCT_DB.batch([
   env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'must roll back'),
   env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'duplicate primary key'),
  ]),'fixture-atomic-batch');
 }catch(error){rejected=error;}
 assert.ok(rejected,'the duplicate primary key must reject the whole native D1 batch');
 assert.deepEqual(f.effects(),[],'metering wrappers must preserve actual batch atomicity');
 assert.equal(f.parent().state,'STOPPED');
 assert.deepEqual(f.charged(),upper(),'a SQL rollback cannot refund the conservative resource debit');
});

test('fresh review: raw and previous-grant statements are rejected before any batch effect',async t=>{
 const outcomes=[];
 for(const origin of ['raw','previous-grant']){
  const f=fixture(t);const budget=f.budget();let foreign,rejected;
  if(origin==='raw')foreign=f.env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(2,'foreign effect');
  else await budget.run('WORKER_FETCH',upper(),async env=>{
   foreign=env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(2,'expired-grant effect');
  },{operationId:'fixture-prior-grant'});
  try{
   await budget.run('WORKER_FETCH',upper(),env=>env.PRODUCT_DB.batch([
    env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'must not begin'),foreign,
   ]),{operationId:'fixture-foreign-batch'});
  }catch(error){rejected=error;}
  outcomes.push({origin,rejected:Boolean(rejected),effects:f.effects(),state:f.parent().state});
 }
 assert.deepEqual(outcomes.map(({origin,effects})=>({origin,effects})),[
  {origin:'raw',effects:[]},{origin:'previous-grant',effects:[]},
 ],'every statement must belong to this exact live metered grant before a raw batch starts');
 assert.ok(outcomes.every(x=>x.rejected&&x.state==='STOPPED'));
});

test('fresh review: a grant cannot execute SQL after the canonical campaign deadline',async t=>{
 const f=fixture(t);let current=NOW,rejected;
 const budget=new ResourceBudget(f.env,{now:()=>current});
 try{
  await budget.run('WORKER_FETCH',upper(),async env=>{
   current=f.parent().deadline_ms+1;
   await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'expired grant effect').run();
  },{operationId:'fixture-expired-grant'});
 }catch(error){rejected=error;}
 assert.deepEqual(f.effects(),[],'ACTIVE alone is not permission to spend after deadline_ms');
 assert.ok(rejected);assert.equal(f.parent().state,'STOPPED');
 assert.deepEqual(f.charged(),upper());
});

test('fresh review: changed native pins or a decreased provider baseline fence the next effect',async t=>{
 const outcomes=[];
 for(const change of ['native-pin','provider-decrease']){
  const f=fixture(t);let rejected;
  try{
   await invoke(f,async env=>{
    // Simulate an out-of-band native-owner observation after reservation. The
    // work callback must not continue using a materially obsolete admission.
    if(change==='native-pin')f.sqlite.prepare(
     'UPDATE r163_qa_resource_budget SET admission_sha256=?,revision=revision+1')
     .run('f'.repeat(64));
    else f.sqlite.prepare('UPDATE r163_qa_resource_budget SET provider_json=?,revision=revision+1')
     .run(JSON.stringify({...f.provider,worker_requests:1}));
    await env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'stale authority effect').run();
   },'fixture-revalidate-grant');
  }catch(error){rejected=error;}
  outcomes.push({change,rejected:Boolean(rejected),effects:f.effects(),state:f.parent().state});
  assert.deepEqual(f.charged(),upper());
 }
 assert.deepEqual(outcomes.map(({change,effects})=>({change,effects})),[
  {change:'native-pin',effects:[]},{change:'provider-decrease',effects:[]},
 ]);
 assert.ok(outcomes.every(x=>x.rejected&&x.state==='STOPPED'));
});


test('settled grants cannot fund detached background effects',async t=>{
 const f=fixture(t);let late;
 await invoke(f,async env=>{late=()=>env.PRODUCT_DB.prepare('INSERT INTO budget_work VALUES(?,?)').bind(1,'late').run();});
 await assert.rejects(late,/HOLD_/);assert.deepEqual(f.effects(),[]);
});

test('DO storage alarm and socket effects stop before crossing the same grant upper bounds',async t=>{
 const f=fixture(t);let effects=0;
 await assert.rejects(()=>f.budget().run('DO_ALARM',upper({do_requests:1,do_alarms:1,do_storage_writes:1,ws_messages_out:1}),async(_env,grant)=>{
  await grant.effect({do_storage_writes:1,do_alarms:1},async()=>{effects++;});
  grant.consume({ws_messages_out:1});
  await grant.effect({do_storage_writes:1},async()=>{effects++;});
 },{operationId:'fixture-do-effects'}),/HOLD_/);
 assert.equal(effects,1);assert.equal(f.parent().state,'STOPPED');
});
