// #163: an internal QA campaign may address only its explicitly selected native events.
// Real intake/SQLite/QA receiver; fetch is injected and no network is contacted.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
import {mkdtempSync,chmodSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {ingestRecoveryEvent} from '../src/recovery-alerts.mjs';
import {dispatchRecoveryDeliveries} from '../src/recovery-delivery.mjs';
import qaReceiver from './recovery_alert_review_sink_r163.mjs';

const NOW=Date.parse('2026-10-24T12:00:00.000Z');
const ORIGIN='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev';
const TARGET={tenant_id:'SYNTHETIC-TENANT',id:'qa-scope-163',kind:'QA_RECIPIENT_V1',origin:ORIGIN,
 writePath:'/notify',readPath:'/receipt/',writeSecret:'SYNTHETIC_WRITE',readSecret:'SYNTHETIC_READ'};
const hash=value=>createHash('sha256').update(value,'utf8').digest('hex');
const nativeId=hex=>'HARA-REC-'+hex.repeat(48);
function adapter(connection,metrics){
 return {prepare:sql=>({bind:(...args)=>({
  run:async()=>{metrics.queries++;return {meta:{changes:connection().prepare(sql).run(...args).changes}};},
  first:async()=>{metrics.queries++;return connection().prepare(sql).get(...args)??null;},
  all:async()=>{metrics.queries++;return {results:connection().prepare(sql).all(...args)};},
 })})};
}
async function fixture(t){
 const directory=mkdtempSync(join(tmpdir(),'hara-r163-scope-'));chmodSync(directory,0o700);
 const worker=new DatabaseSync(join(directory,'worker.sqlite3'));
 const recipient=new DatabaseSync(join(directory,'recipient.sqlite3'));
 chmodSync(join(directory,'worker.sqlite3'),0o600);chmodSync(join(directory,'recipient.sqlite3'),0o600);
 worker.exec('PRAGMA synchronous=FULL');recipient.exec('PRAGMA synchronous=FULL');
 worker.exec('CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);'+
  'CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,'+
  'revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT);'+
  "INSERT INTO tenants VALUES('SYNTHETIC-TENANT');"+
  "INSERT INTO commander_devices VALUES('SYNTHETIC-DEVICE','SYNTHETIC-TENANT','ACTIVE',NULL,"+
  "'PERSISTENT_TRUSTED','OUTBOUND_RELAY','2026-10-24T11:59:59.000Z','2026-10-23T00:00:00.000Z')");
 for(const migration of ['0037_device_recovery_alerts.sql','0038_recovery_delivery.sql'])
  worker.exec(readFileSync(new URL('../migrations/'+migration,import.meta.url),'utf8'));
 recipient.exec('CREATE TABLE qa_delivery_receipts(event_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,'+
  'receipt_ref TEXT NOT NULL,stored_at_utc TEXT NOT NULL)');
 const metrics={queries:0};
 const env={ENVIRONMENT:'DEV',PRODUCT_DB:adapter(()=>worker,metrics),
  COMMANDER_RECOVERY_ALERTS_ENABLED:'true',COMMANDER_RECOVERY_DELIVERY_ENABLED:'true',
  COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS:JSON.stringify([ORIGIN]),
  COMMANDER_RECOVERY_DELIVERY_TARGETS:JSON.stringify([TARGET]),
  SYNTHETIC_WRITE:'synthetic-scope-write-secret',SYNTHETIC_READ:'synthetic-scope-read-secret'};
 const sinkEnv={QA_SINK_DB:adapter(()=>recipient,{queries:0}),
  QA_SINK_WRITE_SHA256:hash(env.SYNTHETIC_WRITE),QA_SINK_READ_SHA256:hash(env.SYNTHETIC_READ)};
 const calls=[];
 const fetchImpl=async(url,init)=>{
  const request=new Request(url,init);assert.equal(new URL(request.url).origin,ORIGIN);
  assert.equal(request.redirect,'manual');
  calls.push({method:request.method,body:request.method==='POST'?await request.clone().json():null});
  return qaReceiver.fetch(request,sinkEnv);
 };
 const intake=async(incident='a'.repeat(32),sequence=1)=>{
  const body={schema:'hara.commander.recovery-alert.proposal.v1',event_id:hash(incident+':'+sequence).slice(0,32),
   client_incident_key:incident,transition_seq:sequence,worker:'executor',
   state:sequence===1?'STALLED':'RECOVERED',observed_at_utc:'2026-10-24T11:59:59.000Z',
   detector:'LINUX_PROCESS_GUARDIAN'};
  const device=worker.prepare('SELECT * FROM commander_devices').get();
  return {body,ack:await ingestRecoveryEvent(env,device,body,NOW)};
 };
 const stage=id=>worker.prepare("INSERT INTO recovery_delivery_outbox(event_id,binding_id,tenant_id,state) VALUES(?,?,?,'PENDING')")
  .run(id,TARGET.id,TARGET.tenant_id);
 const rows=()=>worker.prepare('SELECT * FROM recovery_delivery_outbox ORDER BY event_id').all();
 const run=extra=>dispatchRecoveryDeliveries(env,{fetchImpl,nowMs:NOW,maxEvents:10,timeoutMs:100,...extra});
 t.after(()=>{worker.close();recipient.close();rmSync(directory,{recursive:true,force:true});});
 return {env,metrics,calls,intake,stage,rows,run};
}

test('explicit event IDs restrict staging and recipient calls to the requested native events',async t=>{
 const f=await fixture(t);const outside=await f.intake(),selected=await f.intake('b'.repeat(32));
 assert.notEqual(outside.ack.event_id,selected.ack.event_id);
 const result=await f.run({eventIds:[selected.ack.event_id]});
 assert.equal(result.staged,1);assert.equal(result.delivered,1);
 assert.deepEqual(f.rows().map(row=>row.event_id),[selected.ack.event_id]);
 assert.deepEqual(f.calls.filter(x=>x.method==='POST').map(x=>x.body.event_id),[selected.body.event_id]);
 const count=f.calls.length;
 assert.equal((await f.run({eventIds:[selected.ack.event_id]})).attempted,0);
 assert.equal(f.calls.length,count,'an already delivered selection must not cause another event to send');
});

test('an unselected event already staged remains pending without any recipient contact',async t=>{
 const f=await fixture(t);const outside=await f.intake(),selected=await f.intake('b'.repeat(32));
 f.stage(outside.ack.event_id);
 const result=await f.run({eventIds:[selected.ack.event_id]});
 assert.equal(result.delivered,1);
 assert.deepEqual(f.calls.filter(x=>x.method==='POST').map(x=>x.body.event_id),[selected.body.event_id]);
 const untouched=f.rows().find(row=>row.event_id===outside.ack.event_id);
 assert.equal(untouched.state,'PENDING');assert.equal(untouched.attempts,0);
});

test('predecessors outside the selected scope still fence incident sequence ordering',async t=>{
 const f=await fixture(t);const first=await f.intake(),second=await f.intake('a'.repeat(32),2);
 const blocked=await f.run({eventIds:[second.ack.event_id]});
 assert.equal(blocked.attempted,0);assert.equal(blocked.delivered,0);assert.equal(f.calls.length,0);
 assert.ok(f.rows().every(row=>row.event_id===second.ack.event_id));
 assert.equal((await f.run({eventIds:[first.ack.event_id]})).delivered,1);
 assert.equal((await f.run({eventIds:[second.ack.event_id]})).delivered,1);
 assert.deepEqual(f.calls.filter(x=>x.method==='POST').map(x=>x.body.transition_seq),[1,2]);
});

test('omitting the scope retains dispatch of all eligible events',async t=>{
 const f=await fixture(t);await f.intake();await f.intake('b'.repeat(32));
 const result=await f.run();assert.equal(result.delivered,2);
 assert.equal(f.calls.filter(x=>x.method==='POST').length,2);
 assert.ok(f.rows().every(row=>row.state==='DELIVERED'));
});

for(const [name,eventIds] of [
 ['empty array',[]],['duplicate IDs',[nativeId('a'),nativeId('a')]],
 ['more than ten IDs',Array.from({length:11},(_,i)=>'HARA-REC-'+i.toString(16).padStart(48,'0'))],
 ['plain string',nativeId('a')],['null',null],['object',{event_id:nativeId('a')}],
 ['client identity',['a'.repeat(32)]],['uppercase digest',[nativeId('A')]],
 ['short digest',['HARA-REC-'+'a'.repeat(47)]],['non-string element',[42]],
 ['wrong native prefix',['HARA-DEV-'+'a'.repeat(48)]],
])test(`invalid scope (${name}) is rejected before D1 or network`,async t=>{
 const f=await fixture(t);await f.intake();const queries=f.metrics.queries;
 await assert.rejects(()=>f.run({eventIds}),/RECOVERY_DELIVERY_SCOPE_INVALID/);
 assert.equal(f.metrics.queries,queries);assert.equal(f.calls.length,0);
});

test('default OFF remains a no-op even when a caller supplies an invalid scope',async()=>{
 for(const eventIds of [[],null,['not-native']]){
  let queries=0,sends=0;
  const result=await dispatchRecoveryDeliveries({
   PRODUCT_DB:{prepare(){queries++;throw Error('DISABLED_DB_ACCESS');}},
  },{eventIds,fetchImpl:async()=>{sends++;throw Error('DISABLED_NETWORK');}});
  assert.equal(result.state,'DISABLED');assert.equal(queries,0);assert.equal(sends,0);
 }
});
