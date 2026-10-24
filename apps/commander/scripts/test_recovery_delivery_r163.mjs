// #163: intake persistence terminates Agent retries; it is not recipient delivery.
// Two independent private SQLite files model the Agent journal and Worker D1.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,chmodSync,readFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {RecoveryAlertOutbox} from './recovery_alert_outbox.mjs';
import {ingestRecoveryEvent} from '../src/recovery-alerts.mjs';

const NOW=Date.parse('2026-10-24T12:00:00.000Z');
const EVENT_ID='a'.repeat(31)+'1';
const event=(sequence=1,state='STALLED')=>({
 schema:'hara.commander.recovery-alert.proposal.v1',
 event_id:'a'.repeat(31)+sequence,client_incident_key:'b'.repeat(32),
 transition_seq:sequence,worker:'executor',state,
 observed_at_utc:'2026-10-24T11:59:59.000Z',detector:'LINUX_PROCESS_GUARDIAN',
});
const ack=(id=EVENT_ID)=>({
 schema:'hara.commander.recovery-ingest.v1',ack:'PERSISTED',
 event_id:'HARA-REC-'+'c'.repeat(48),client_event_id:id,
 duplicate:false,external_delivery_confirmed:false,
});

async function fixture(t,policy={}){
 const dir=mkdtempSync(join(tmpdir(),'hara-r163-intake-'));
 chmodSync(dir,0o700);
 const localPath=join(dir,'agent.sqlite3'),remotePath=join(dir,'worker-d1.sqlite3');
 let local=new DatabaseSync(localPath),remote=new DatabaseSync(remotePath);
 chmodSync(localPath,0o600);chmodSync(remotePath,0o600);
 local.exec('PRAGMA synchronous=FULL');remote.exec('PRAGMA synchronous=FULL');
 const store={run:(sql,args=[])=>local.prepare(sql).run(...args),
  first:(sql,args=[])=>local.prepare(sql).get(...args)??null};
 const outbox=new RecoveryAlertOutbox(store,{timeoutMs:30,leaseMs:100,
  retryBaseMs:10,retryCapMs:100,maxAttempts:3,random:()=>0,...policy});
 await outbox.initialize();
 remote.exec('CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);'+
  'CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,'+
  'state TEXT,revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,'+
  'last_seen_at_utc TEXT,created_at_utc TEXT)');
 remote.exec(readFileSync(new URL('../migrations/0037_device_recovery_alerts.sql',import.meta.url),'utf8'));
 remote.prepare('INSERT INTO tenants VALUES (?)').run('SYNTHETIC-TENANT');
 remote.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)').run(
  'SYNTHETIC-DEVICE','SYNTHETIC-TENANT','ACTIVE',null,'PERSISTENT_TRUSTED',
  'OUTBOUND_RELAY','2026-10-24T11:59:59.000Z','2026-10-23T00:00:00.000Z');
 const db={prepare:sql=>({bind:(...args)=>({
  run:async()=>({meta:{changes:remote.prepare(sql).run(...args).changes}}),
  first:async()=>remote.prepare(sql).get(...args)??null,
  all:async()=>({results:remote.prepare(sql).all(...args)}),
 })})};
 const env={PRODUCT_DB:db,COMMANDER_RECOVERY_ALERTS_ENABLED:'true'};
 const send=body=>ingestRecoveryEvent(env,
  remote.prepare('SELECT * FROM commander_devices WHERE device_id=?').get('SYNTHETIC-DEVICE'),body,NOW);
 const count=()=>remote.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n;
 const reopen=()=>{local.close();remote.close();
  local=new DatabaseSync(localPath);remote=new DatabaseSync(remotePath);};
 t.after(()=>{local.close();remote.close();rmSync(dir,{recursive:true,force:true});});
 return {outbox,send,count,reopen,store};
}

test('durable Worker PERSISTED is terminal for intake without claiming remote delivery',async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());let sends=0;
 const send=async(body,context)=>{sends++;
  assert.equal(context.idempotencyKey,body.event_id);
  assert.ok(context.signal instanceof AbortSignal);
  return f.send(body);};
 const result=await f.outbox.dispatchIngest({send,nowMs:1000});
 assert.equal(result.state,'PERSISTED');assert.equal(f.count(),1);
 const saved=await f.outbox.inspect(EVENT_ID);
 assert.equal(saved.state,'PERSISTED');assert.notEqual(saved.state,'DELIVERED');
 f.reopen();
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:2000})).state,'EMPTY');
 assert.equal((await f.outbox.inspect(EVENT_ID)).attempts,1);assert.equal(sends,1);
});

test('the next contiguous transition follows PERSISTED without waiting for a recipient or human',async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());
 await f.outbox.enqueue(event(2,'RECOVERING'));await f.outbox.enqueue(event(3,'RECOVERED'));
 const states=[];
 const send=async body=>{states.push(body.state);return f.send(body);};
 for(let n=0;n<3;n++)assert.equal((await f.outbox.dispatchIngest({send,nowMs:1000+n})).state,'PERSISTED');
 assert.deepEqual(states,['STALLED','RECOVERING','RECOVERED']);assert.equal(f.count(),3);
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:2000})).state,'EMPTY');
});

test('lost response retries the same intent, resolves the duplicate and then stops',async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());let first=true;const bodies=[];
 const send=async body=>{bodies.push(JSON.stringify(body));const reply=await f.send(body);
  if(first){first=false;throw Error('SYNTHETIC_REPLY_LOST_AFTER_PERSIST');}
  assert.equal(reply.duplicate,true);return reply;};
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1000})).state,'RETRY');
 f.reopen();assert.equal(f.count(),1);
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1200})).state,'PERSISTED');
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1500})).state,'EMPTY');
 assert.equal(f.count(),1);assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);
});

for(const [name,response] of [
 ['human incident ACK',{schema:'hara.commander.recovery-portal-ack.v1',ack:'PORTAL_ACKNOWLEDGED',event_id:ack().event_id}],
 ['different client event',{...ack(),client_event_id:'d'.repeat(32)}],
 ['missing client correlation',Object.fromEntries(Object.entries(ack()).filter(([key])=>key!=='client_event_id'))],
 ['invalid server identity',{...ack(),event_id:'not-a-server-receipt'}],
 ['different schema',{...ack(),schema:'hara.commander.recovery-inbox.v1'}],
 ['false delivery assertion',{...ack(),external_delivery_confirmed:true}],
 ['missing separation of delivery',Object.fromEntries(Object.entries(ack()).filter(([key])=>key!=='external_delivery_confirmed'))],
 ['non-boolean delivery flag',{...ack(),external_delivery_confirmed:'false'}],
])test(`${name} cannot acknowledge intake`,async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());
 const result=await f.outbox.dispatchIngest({send:async()=>response,nowMs:1000});
 assert.equal(result.state,'RETRY');assert.equal((await f.outbox.inspect(EVENT_ID)).state,'RETRY');
});

test('HTTP unavailability retries with bounded backoff and unchanged identity',async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());const ids=[];
 const send=async body=>{ids.push(body.event_id);throw Error('HTTP_503');};
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1000})).state,'RETRY');
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1001})).state,'EMPTY');
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1200})).state,'RETRY');
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1400})).state,'EXHAUSTED');
 assert.equal((await f.outbox.dispatchIngest({send,nowMs:1600})).state,'EMPTY');
 assert.deepEqual(ids,[EVENT_ID,EVENT_ID,EVENT_ID]);
});

test('an ingestion timeout does not leave an unbounded active claim',async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());
 const result=await f.outbox.dispatchIngest({send:async()=>new Promise(()=>{}),nowMs:1000});
 assert.equal(result.state,'RETRY');
 assert.equal((await f.outbox.dispatchIngest({send:async()=>ack(),nowMs:1200})).state,'PERSISTED');
});

test('a late successful attempt cannot overwrite a newer persisted receipt',async t=>{
 const f=await fixture(t,{timeoutMs:200,leaseMs:300});await f.outbox.enqueue(event());
 let release;
 const older=f.outbox.dispatchIngest({send:async()=>new Promise(resolve=>{release=resolve;}),nowMs:1000});
 while(!release)await new Promise(resolve=>setImmediate(resolve));
 const newer=await f.outbox.dispatchIngest({send:async()=>ack(),nowMs:1400});
 assert.equal(newer.state,'PERSISTED');release(ack());
 assert.equal((await older).state,'STALE_ATTEMPT');
 const row=await f.outbox.inspect(EVENT_ID);assert.equal(row.state,'PERSISTED');assert.equal(row.attempts,2);
});

test('recipient dispatch cannot resend an event already persisted at intake',async t=>{
 const f=await fixture(t);await f.outbox.enqueue(event());
 assert.equal((await f.outbox.dispatchIngest({send:async()=>ack(),nowMs:1000})).state,'PERSISTED');
 let sends=0;
 const value=await f.outbox.dispatch({nowMs:2000,
  send:async()=>{sends++;return {};},verifyReceipt:async()=>({
   kind:'DELIVERY_CONFIRMED',eventId:EVENT_ID,receiptRef:'SYNTHETIC-ONLY',
  })});
 assert.equal(value.state,'EMPTY');assert.equal(sends,0);
 assert.equal((await f.outbox.inspect(EVENT_ID)).state,'PERSISTED');
});
