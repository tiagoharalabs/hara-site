import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {budgeted,BUDGET_SCHEMA,CAPS,withinBudget} from './recovery_queue_budget_r163.mjs';
function fixture(t,{reads=0,writes=0,deadline=Date.now()+60000,state='ACTIVE',activeUsed=0}={}){
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());db.exec(BUDGET_SCHEMA);
 db.prepare('INSERT INTO r163_qa_budget(id,state,start_ms,deadline_ms,rows_read,rows_written) VALUES(1,?,1,?,?,?)').run(state,deadline,reads,writes);
 db.prepare('UPDATE r163_qa_budget SET active_ms_used=?').run(activeUsed);db.exec('CREATE TABLE work(id INTEGER PRIMARY KEY)');const hooks={};
 const raw={prepare:sql=>({bind:(...args)=>({first:async()=>db.prepare(sql).get(...args)??null,
  all:async()=>{const r=db.prepare(sql).all(...args);await hooks.after?.();return {results:r,meta:{rows_read:r.length,rows_written:sql.startsWith('UPDATE')?1:0}};},
  run:async()=>{const r=db.prepare(sql).run(...args);await hooks.after?.();return {meta:{rows_read:1,rows_written:r.changes}};}})})};
 let sent=0;const env={ENVIRONMENT:'DEV',R163_QA_ISOLATED:'true',PRODUCT_DB:raw,RECOVERY_DELIVERY_QUEUE:{sendBatch:async e=>{sent+=e.length;}}};
 return {db,env,hooks,sent:()=>sent,row:()=>({...db.prepare('SELECT * FROM r163_qa_budget').get()})};
}
test('provider metadata accounted, queue upper reservation and no client reset',async t=>{
 const f=fixture(t);
 await budgeted(f.env,{reads:32,writes:32},async e=>{
  await e.PRODUCT_DB.prepare('INSERT INTO work VALUES(?)').bind(1).run();
  await e.RECOVERY_DELIVERY_QUEUE.sendBatch([{body:{}}]);
 });
 assert.equal(f.sent(),1);assert.equal(f.row().queue_ops_upper,12);
 assert.equal(f.row().rows_written,6);assert.equal(f.row().reserved_write,0);
});
for(const fields of [{reads:CAPS.reads-16},{writes:CAPS.writes-16},{deadline:Date.now()-1},{state:'STOPPED'}])
test('ceiling/deadline blocks before task '+JSON.stringify(fields),async t=>{
 const f=fixture(t,fields);let called=0;
 await assert.rejects(()=>budgeted(f.env,{reads:32,writes:32},async()=>called++),/HOLD_CAMPAIGN_BUDGET_OR_DEADLINE/);
 assert.equal(called,0);assert.equal(f.row().reserved_write,0);
});
test('concurrent reservations cannot oversubscribe the same D1 budget',async t=>{
 const f=fixture(t,{writes:CAPS.writes-40});let release;const waiting=new Promise(r=>release=r);
 const a=budgeted(f.env,{reads:32,writes:32},async()=>waiting);
 await new Promise(r=>setTimeout(r,1));
 await assert.rejects(()=>budgeted(f.env,{reads:32,writes:32},async()=>{}),/HOLD_CAMPAIGN_BUDGET_OR_DEADLINE/);
 release();await a;assert.ok(f.row().rows_written<=CAPS.writes);
});
test('missing native D1 metadata stops campaign permanently',async t=>{
 const f=fixture(t);const raw=f.env.PRODUCT_DB;
 f.env.PRODUCT_DB={prepare:sql=>{const p=raw.prepare(sql);return {bind:(...args)=>{const q=p.bind(...args);if(sql.includes('SELECT 42'))q.all=async()=>({results:[{answer:42}]});return q;}};}};
 await assert.rejects(()=>budgeted(f.env,{reads:32,writes:32},e=>e.PRODUCT_DB.prepare('SELECT 42').bind().all()),/HOLD_MISSING_D1_METER/);
 assert.equal(f.row().state,'STOPPED');assert.equal(f.row().anomaly,'HOLD_MISSING_D1_METER');
});
test('isolation is mandatory even with correct Queue binding',async t=>{
 const f=fixture(t);f.env.ENVIRONMENT='PROD';
 await assert.rejects(()=>budgeted(f.env,{reads:32,writes:32},async()=>{}),/HOLD_QA_ISOLATION/);
 assert.equal(f.row().invocations,0);
});
test('durable unreconciled crash reservations keep subsequent work closed',async t=>{
 const f=fixture(t);f.db.prepare('UPDATE r163_qa_budget SET reserved_write=?').run(CAPS.writes);
 await assert.rejects(()=>budgeted(f.env,{reads:32,writes:32},async()=>{}),/HOLD_CAMPAIGN_BUDGET_OR_DEADLINE/);
 assert.equal(f.row().reserved_write,CAPS.writes);
});
test('exact thresholds and event ceiling stop harness decisions',()=>{
 const row={state:'ACTIVE',deadline_ms:100,rows_read:0,rows_written:0,reserved_read:0,reserved_write:0,queue_ops_upper:0,events_reserved:500};
 assert.equal(withinBudget(row,99),true);assert.equal(withinBudget(row,100),false);
 for(const field of ['rows_read','rows_written','queue_ops_upper','events_reserved']){
  const ceiling={rows_read:CAPS.reads,rows_written:CAPS.writes,queue_ops_upper:CAPS.queue,events_reserved:501}[field];
  assert.equal(withinBudget({...row,[field]:ceiling},99),false);
 }
});
test('versioned config is restricted to the exact dedicated QA resources',async()=>{
 const {readFileSync}=await import('node:fs');
 const c=JSON.parse(readFileSync(new URL('../wrangler.r163-queue-qa.jsonc',import.meta.url),'utf8'));
 assert.equal(c.name,'hara-commander-r163-canary-20261024');assert.equal(c.vars.ENVIRONMENT,'DEV');
 assert.equal(c.routes,undefined);assert.equal(c.vars.R163_QA_AUTOMATIC_CRON,'false');
 assert.equal(c.d1_databases.length,1);assert.equal(c.d1_databases[0].database_id,'e769835e-0748-4f41-b868-c7c76b627fe9');
 assert.deepEqual(c.queues.consumers.slice(0,1),[{queue:'hara-commander-r163-recovery-dev-20261024',max_batch_size:1,max_batch_timeout:5,max_concurrency:1,max_retries:2,dead_letter_queue:'hara-commander-r163-recovery-dlq-dev-20261024'}]);
 assert.equal(c.queues.producers[0].binding,'RECOVERY_DELIVERY_QUEUE');
 assert.equal(c.queues.consumers[1].queue,c.queues.consumers[0].dead_letter_queue);
 assert.equal(c.queues.consumers[1].max_concurrency,1);
 assert.equal(c.queues.consumers[1].dead_letter_queue,undefined);
 assert.equal(c.vars.DEVICE_EVENT_V2_ENABLED,'false');
});
test('resume retains consumed active time, counters and reserved event budget',async t=>{
 const {startRecoveryBudget}=await import('./recovery_queue_budget_r163.mjs');
 const f=fixture(t,{state:'PAUSED',writes:123});f.db.exec('UPDATE r163_qa_budget SET events_reserved=50');
 const before=f.row();const row=await startRecoveryBudget(f.env.PRODUCT_DB,Date.now());
 assert.equal(row.state,'ACTIVE');assert.equal(row.start_ms,before.start_ms);assert.ok(row.deadline_ms<=Date.now()+CAPS.active_ms);assert.equal(row.active_ms_used,before.active_ms_used);assert.equal(row.rows_written,123);assert.equal(row.events_reserved,50);
});
for(const fields of [{state:'STOPPED'},{state:'PAUSED',deadline:Date.now()-1,activeUsed:CAPS.active_ms},{state:'PAUSED',writes:CAPS.writes}])
test('expired/anomalous/spent campaign cannot resume '+JSON.stringify(fields),async t=>{
 const {startRecoveryBudget}=await import('./recovery_queue_budget_r163.mjs');const f=fixture(t,fields);
 await assert.rejects(()=>startRecoveryBudget(f.env.PRODUCT_DB),/HOLD_CAMPAIGN_NOT_RESUMABLE/);
});
test('synthetic enrollment uses the exact existing base64url resolver contract',async()=>{
 const {enrollmentCredentialHash,repairSyntheticCredentialSql}=await import('./recovery_queue_qa_fixture_r163.mjs');
 const {createHash}=await import('node:crypto');
 assert.equal(await enrollmentCredentialHash('synthetic-credential'),createHash('sha256').update('synthetic-credential').digest('base64url'));
 assert.notEqual(await enrollmentCredentialHash('synthetic-credential'),createHash('sha256').update('synthetic-credential').digest('hex'));
 await assert.rejects(()=>repairSyntheticCredentialSql([],'PROD'),/HOLD_SYNTHETIC_FIXTURE_SCOPE/);
});
test('paused status reads are metered without activating or renewing a budget',async t=>{
 const {readRecoveryQaStatus}=await import('./recovery_queue_budget_r163.mjs');const f=fixture(t,{state:'PAUSED'});
 const before=f.row();const r=await readRecoveryQaStatus(f.env);
 assert.equal(r.budget.state,'PAUSED');assert.equal(r.budget.deadline_ms,before.deadline_ms);
 assert.equal(r.budget.rows_written,4);assert.ok(r.budget.rows_read>=4);assert.equal(r.budget.reserved_write,0);
});
test('status refuses reads when its reservation would exceed a cap',async t=>{
 const {readRecoveryQaStatus}=await import('./recovery_queue_budget_r163.mjs');const f=fixture(t,{reads:CAPS.reads-100});
 await assert.rejects(()=>readRecoveryQaStatus(f.env),/HOLD_STATUS_BUDGET/);
});
test('active load timer pauses without replenishing its 30-minute allowance',async t=>{
 const {startRecoveryBudget,pauseRecoveryBudget}=await import('./recovery_queue_budget_r163.mjs');const f=fixture(t,{state:'PAUSED',activeUsed:1500000});
 const a=await startRecoveryBudget(f.env.PRODUCT_DB,1000);assert.equal(a.deadline_ms,301000);
 await pauseRecoveryBudget(f.env.PRODUCT_DB,61000);assert.equal(f.row().active_ms_used,1560000);
 const b=await startRecoveryBudget(f.env.PRODUCT_DB,9000000);assert.equal(b.deadline_ms,9240000);
 await pauseRecoveryBudget(f.env.PRODUCT_DB,9240000);assert.equal(f.row().active_ms_used,CAPS.active_ms);
 await assert.rejects(()=>startRecoveryBudget(f.env.PRODUCT_DB,9240001),/HOLD_CAMPAIGN_NOT_RESUMABLE/);
});
