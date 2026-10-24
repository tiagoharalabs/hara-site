import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,chmodSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {RecoveryAlertOutbox,HOLD_REMOTE_ALERT_OWNER_163} from './recovery_alert_outbox.mjs';

function fixture(t){
 const directory=mkdtempSync(join(tmpdir(),'hara-recovery-alert-'));
 const path=join(directory,'private.sqlite3');let db=new DatabaseSync(path);chmodSync(path,0o600);
 const store={run:(sql,args=[])=>db.prepare(sql).run(...args),first:(sql,args=[])=>db.prepare(sql).get(...args)??null,all:(sql,args=[])=>db.prepare(sql).all(...args)};
 const outbox=new RecoveryAlertOutbox(store,{timeoutMs:30,leaseMs:100,retryBaseMs:10,retryCapMs:100,maxAttempts:3,random:()=>0});
 t.after(()=>{db.close();rmSync(directory,{recursive:true,force:true});});
 return {store,outbox,reopen:()=>{db.close();db=new DatabaseSync(path);}};
}
const event=(seq=1,state='STALLED')=>({schema:'hara.commander.recovery-alert.proposal.v1',event_id:'e'.repeat(31)+String(seq),client_incident_key:'a'.repeat(32),transition_seq:seq,worker:'executor',state,observed_at_utc:'2026-10-24T00:00:00.000Z',detector:'LINUX_PROCESS_GUARDIAN'});
const receipt=(row)=>({kind:'DELIVERY_CONFIRMED',eventId:row.event_id,receiptRef:'fixture-delivery-proof'});

test('no transport binding preserves pending metadata and calls nobody',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());
 const value=await outbox.dispatch({nowMs:1000});
 assert.equal(value.state,HOLD_REMOTE_ALERT_OWNER_163);assert.equal((await outbox.inspect(event().event_id)).attempts,0);
});
test('restart and duplicate enqueue retain one stable intent',async t=>{
 const f=fixture(t);await f.outbox.initialize();await f.outbox.enqueue(event());f.reopen();await f.outbox.enqueue(event());
 assert.equal((await f.store.all('SELECT * FROM commander_recovery_delivery_outbox')).length,1);
 await assert.rejects(()=>f.outbox.enqueue({...event(),state:'RECOVERING'}),/ALERT_IDEMPOTENCY_CONFLICT/);
});
test('metadata allowlist rejects credentials, tenant claims and content',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();
 for(const field of ['token','command','payload','result','tenant_id','device_id','destination'])await assert.rejects(()=>outbox.enqueue({...event(),[field]:'forbidden'}),/ALERT_METADATA_DENIED/);
});
test('human SLO acknowledgement cannot mark remote delivery',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());
 const r=await outbox.dispatch({nowMs:1000,send:async()=>({acknowledged_at_utc:'2026-10-24T00:00:00Z'}),verifyReceipt:async()=>({kind:'INCIDENT_ACKNOWLEDGED',eventId:event().event_id,receiptRef:'/api/portal/slo/ack'})});
 assert.equal(r.state,'RETRY');assert.notEqual((await outbox.inspect(event().event_id)).state,'DELIVERED');
});
test('ingest acceptance alone is not delivery confirmation',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());
 const r=await outbox.dispatch({nowMs:1000,send:async()=>({ok:true,persisted:true}),verifyReceipt:async()=>({kind:'PERSISTED_ONLY'})});
 assert.equal(r.state,'RETRY');assert.equal((await outbox.inspect(event().event_id)).receipt_ref,null);
});
test('delivery receipt is bound to event identity',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());
 const r=await outbox.dispatch({nowMs:1000,send:async()=>({}),verifyReceipt:async()=>({...receipt(event()),eventId:'wrong'})});
 assert.equal(r.state,'RETRY');
});
test('verified fixture delivery is durable and never resent',async t=>{
 const f=fixture(t);await f.outbox.initialize();await f.outbox.enqueue(event());let calls=0;
 const transport={nowMs:1000,send:async row=>{calls++;return row;},verifyReceipt:async row=>receipt(row)};
 assert.equal((await f.outbox.dispatch(transport)).state,'DELIVERED');f.reopen();
 assert.equal((await f.outbox.dispatch({...transport,nowMs:2000})).state,'EMPTY');assert.equal(calls,1);
});
test('timeouts retry the same event with finite backoff and no concurrent lease',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());const ids=[];
 const send=async row=>{ids.push(row.event_id);return new Promise(()=>{});};
 const verifyReceipt=async row=>receipt(row);
 const first=outbox.dispatch({nowMs:1000,send,verifyReceipt});
 assert.equal((await outbox.dispatch({nowMs:1001,send,verifyReceipt})).state,'EMPTY');
 assert.equal((await first).state,'RETRY');assert.equal((await outbox.dispatch({nowMs:1001,send,verifyReceipt})).state,'EMPTY');
 assert.equal((await outbox.dispatch({nowMs:1100,send,verifyReceipt})).state,'RETRY');
 assert.equal((await outbox.dispatch({nowMs:1300,send,verifyReceipt})).state,'EXHAUSTED');
 assert.equal(new Set(ids).size,1);assert.equal(ids.length,3);
});
test('incident transitions are ordered and gaps are rejected',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await assert.rejects(()=>outbox.enqueue(event(2,'RECOVERING')),/ALERT_SEQUENCE_GAP/);
 await outbox.enqueue(event());await outbox.enqueue(event(2,'RECOVERING'));
 let first=true;const send=async row=>row;
 const verifyReceipt=async row=>first?{kind:'PERSISTED_ONLY'}:receipt(row);
 await outbox.dispatch({nowMs:1000,send,verifyReceipt});
 assert.equal((await outbox.dispatch({nowMs:1001,send,verifyReceipt})).state,'EMPTY');
 first=false;await outbox.dispatch({nowMs:1200,send,verifyReceipt});
 assert.equal((await outbox.dispatch({nowMs:1201,send,verifyReceipt})).eventId,event(2).event_id);
});
test('expired lease permits takeover without accepting the stale receipt',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());
 const older=await outbox.claim(1000);const newer=await outbox.claim(1200);
 assert.equal(older.event_id,newer.event_id);assert.equal(newer.attempts,older.attempts+1);
 assert.equal(await outbox.confirm(older,receipt(event())),false);
 assert.equal(await outbox.confirm(newer,receipt(event())),true);
});

test('crashes during delivery cannot bypass the retry ceiling',async t=>{
 const {outbox}=fixture(t);await outbox.initialize();await outbox.enqueue(event());
 assert.equal((await outbox.claim(1000)).attempts,1);
 assert.equal((await outbox.claim(1200)).attempts,2);
 assert.equal((await outbox.claim(1400)).attempts,3);
 assert.equal(await outbox.claim(1600),null);
 assert.equal((await outbox.inspect(event().event_id)).state,'EXHAUSTED');
});
