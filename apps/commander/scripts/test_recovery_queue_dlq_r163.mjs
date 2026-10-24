import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
import {BUDGET_SCHEMA} from './recovery_queue_budget_r163.mjs';
import {acceptR163Dlq} from './recovery_queue_dlq_r163.mjs';
const DLQ='hara-commander-r163-recovery-dlq-dev-20261024';
function fixture(t){
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());db.exec(BUDGET_SCHEMA);
 db.prepare("INSERT INTO r163_qa_budget(id,state,start_ms,deadline_ms,rows_read,rows_written) VALUES(1,'ACTIVE',1,?,0,0)").run(Date.now()+60000);
 const env={ENVIRONMENT:'DEV',R163_QA_ISOLATED:'true',PRODUCT_DB:{prepare:q=>({bind:(...a)=>({
  first:async()=>db.prepare(q).get(...a)??null,
  all:async()=>({results:db.prepare(q).all(...a),meta:{rows_read:1,rows_written:0}}),
  run:async()=>({meta:{rows_read:1,rows_written:db.prepare(q).run(...a).changes}})
 })})}};
 let ack=0;const body={schema:'hara.commander.recovery-work.v1',kind:'SCAN',device_ids:['R163-QA-DLQ-FAULT']};
 const batch={queue:DLQ,messages:[{id:'synthetic-native-message',body,ack(){assert.equal(db.prepare('SELECT count(*) AS n FROM r163_qa_dlq').get().n,1);ack++;}}]};
 return {db,env,batch,acks:()=>ack};
}
test('native DLQ receipt is durable before ACK and duplicate delivery is idempotent',async t=>{
 const f=fixture(t);await acceptR163Dlq(f.batch,f.env);await acceptR163Dlq(f.batch,f.env);
 assert.equal(f.acks(),2);const r=f.db.prepare('SELECT * FROM r163_qa_dlq').get();
 assert.equal(r.body_sha256,createHash('sha256').update(JSON.stringify(f.batch.messages[0].body)).digest('hex'));
 assert.equal(r.queue_name,DLQ);assert.equal(f.db.prepare('SELECT count(*) AS n FROM r163_qa_dlq').get().n,1);
});
for(const problem of ['prod','wrong-queue','wrong-batch','unisolated'])test('DLQ rejects boundary '+problem,async t=>{
 const f=fixture(t);if(problem==='prod')f.env.ENVIRONMENT='PROD';if(problem==='wrong-queue')f.batch.queue='hara-commander-prod';
 if(problem==='wrong-batch')f.batch.messages.push(f.batch.messages[0]);if(problem==='unisolated')f.env.R163_QA_ISOLATED='false';
 await assert.rejects(()=>acceptR163Dlq(f.batch,f.env),/HOLD_QA_DLQ_IDENTITY/);assert.equal(f.acks(),0);
 assert.equal(f.db.prepare('SELECT invocations FROM r163_qa_budget').get().invocations,0);
});
test('conflicting stored receipt cannot acknowledge a native message',async t=>{
 const f=fixture(t);f.db.prepare('INSERT INTO r163_qa_dlq VALUES(?,?,?,?)').run(f.batch.messages[0].id,DLQ,'forged',1);
 await assert.rejects(()=>acceptR163Dlq(f.batch,f.env),/HOLD_DLQ_RECEIPT_CONFLICT/);assert.equal(f.acks(),0);
 assert.equal(f.db.prepare('SELECT state FROM r163_qa_budget').get().state,'STOPPED');
});
test('oversized payload stops before durable ACK',async t=>{
 const f=fixture(t);f.batch.messages[0].body='x'.repeat(32001);
 await assert.rejects(()=>acceptR163Dlq(f.batch,f.env),/HOLD_DLQ_PAYLOAD/);assert.equal(f.acks(),0);
});
