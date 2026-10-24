// #163 transport contract: real intake/SQLite/QA receiver, injected fetch only.
// The canonical DEV origin is never contacted by this suite.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,chmodSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {ingestRecoveryEvent,detectOfflineRecoveryEvents} from '../src/recovery-alerts.mjs';
import qaReceiver from './recovery_alert_review_sink_r163.mjs';
import {dispatchRecoveryDeliveries} from '../src/recovery-delivery.mjs';

const NOW=Date.parse('2026-10-24T12:00:00.000Z');
const ORIGIN='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev';
const TARGET={tenant_id:'TENANT-A',id:'qa-review-163',kind:'QA_RECIPIENT_V1',origin:ORIGIN,
 writePath:'/notify',readPath:'/receipt/',writeSecret:'SYNTHETIC_WRITE',readSecret:'SYNTHETIC_READ'};
const EVENT={schema:'hara.commander.recovery-alert.proposal.v1',event_id:'e'.repeat(32),
 client_incident_key:'a'.repeat(32),transition_seq:1,worker:'executor',state:'STALLED',
 observed_at_utc:'2026-10-24T11:59:59.000Z',detector:'LINUX_PROCESS_GUARDIAN'};
const digest=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',
 new TextEncoder().encode(value))),x=>x.toString(16).padStart(2,'0')).join('');
const fingerprint=value=>digest(JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)))));
const canonicalReceiptSha=receipt=>createHash('sha256').update(JSON.stringify(
 Object.fromEntries(Object.keys(receipt).sort().map(key=>[key,receipt[key]]))),'utf8').digest('hex');

function d1(connection,counts){
 return {prepare:sql=>({bind:(...args)=>({
  run:async()=>{counts.queries++;return {meta:{changes:connection().prepare(sql).run(...args).changes}};},
  first:async()=>{counts.queries++;return connection().prepare(sql).get(...args)??null;},
  all:async()=>{counts.queries++;return {results:connection().prepare(sql).all(...args)};},
 })})};
}
async function fixture(t,{tenantB=false,ingest=true}={}){
 const dir=mkdtempSync(join(tmpdir(),'hara-r163-transport-'));chmodSync(dir,0o700);
 const workerPath=join(dir,'worker.sqlite3'),sinkPath=join(dir,'recipient.sqlite3');
 let worker=new DatabaseSync(workerPath),sink=new DatabaseSync(sinkPath);
 chmodSync(workerPath,0o600);chmodSync(sinkPath,0o600);
 worker.exec('PRAGMA synchronous=FULL');sink.exec('PRAGMA synchronous=FULL');
 const counts={queries:0,sinkQueries:0};
 worker.exec('CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);'+
  'CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,'+
  'revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT)');
 worker.exec(readFileSync(new URL('../migrations/0037_device_recovery_alerts.sql',import.meta.url),'utf8'));
 worker.exec(readFileSync(new URL('../migrations/0038_recovery_delivery.sql',import.meta.url),'utf8'));
 sink.exec('CREATE TABLE qa_delivery_receipts(event_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,'+
  'receipt_ref TEXT NOT NULL,stored_at_utc TEXT NOT NULL)');
 for(const tenant of ['TENANT-A','TENANT-B']){
  worker.prepare('INSERT INTO tenants VALUES(?)').run(tenant);
  worker.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)').run('DEVICE-'+tenant,
   tenant,'ACTIVE',null,'PERSISTENT_TRUSTED','OUTBOUND_RELAY',
   new Date(NOW-300000).toISOString(),new Date(NOW-86400000).toISOString());
 }
 const env={ENVIRONMENT:'DEV',PRODUCT_DB:d1(()=>worker,counts),
  COMMANDER_RECOVERY_ALERTS_ENABLED:'true',COMMANDER_RECOVERY_DELIVERY_ENABLED:'true',
  COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS:JSON.stringify([ORIGIN]),
  COMMANDER_RECOVERY_DELIVERY_TARGETS:JSON.stringify([TARGET]),
  SYNTHETIC_WRITE:'synthetic-fixture-write-secret',SYNTHETIC_READ:'synthetic-fixture-read-secret'};
 const sinkCounts={queries:0};
 const sinkEnv={QA_SINK_DB:d1(()=>sink,sinkCounts),
  QA_SINK_WRITE_SHA256:await digest(env.SYNTHETIC_WRITE),QA_SINK_READ_SHA256:await digest(env.SYNTHETIC_READ)};
 const calls=[];
 const recipient=async(url,init)=>{
  const request=new Request(url,init);
  assert.equal(request.url.startsWith(ORIGIN+'/'),true,'no other destination is admitted');
  assert.equal(request.redirect,'error','redirects must never carry recipient credentials');
  assert.ok(request.signal instanceof AbortSignal);
  calls.push({method:request.method,url:request.url,
   authorization:request.headers.get('authorization'),body:request.method==='POST'?await request.clone().json():null});
  return qaReceiver.fetch(request,sinkEnv);
 };
 const intake=async(body=EVENT,tenant='TENANT-A')=>ingestRecoveryEvent(env,
  worker.prepare('SELECT * FROM commander_devices WHERE tenant_id=?').get(tenant),body,NOW);
 const ack=ingest?await intake():null;
 if(tenantB)await intake(EVENT,'TENANT-B');
 const rows=()=>worker.prepare('SELECT * FROM recovery_delivery_outbox ORDER BY tenant_id,event_id,binding_id').all();
 const reopen=()=>{worker.close();sink.close();worker=new DatabaseSync(workerPath);sink=new DatabaseSync(sinkPath);};
 t.after(()=>{worker.close();sink.close();rmSync(dir,{recursive:true,force:true});});
 return {env,counts,calls,recipient,intake,ack,rows,reopen,
  worker:()=>worker,sink:()=>sink,sinkEnv};
}
const options=fetchImpl=>({fetchImpl,nowMs:NOW,maxEvents:10,timeoutMs:100});

test('delivery defaults OFF without even querying D1 or contacting a destination',async()=>{
 for(const enabled of [undefined,'false','TRUE',true]){
  let queries=0,sends=0;
  const env={COMMANDER_RECOVERY_DELIVERY_ENABLED:enabled,
   PRODUCT_DB:{prepare(){queries++;throw Error('DISABLED_DB_ACCESS');}}};
  const result=await dispatchRecoveryDeliveries(env,options(async()=>{sends++;throw Error('DISABLED_NETWORK');}));
  assert.equal(result.state,'DISABLED');assert.equal(queries,0);assert.equal(sends,0);
 }
});

for(const [name,change] of [
 ['missing target',env=>delete env.COMMANDER_RECOVERY_DELIVERY_TARGETS],
 ['malformed JSON',env=>env.COMMANDER_RECOVERY_DELIVERY_TARGETS='{'],
 ['unbound secret reference',env=>delete env.SYNTHETIC_READ],
 ['origin not admitted',env=>env.COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS='[]'],
 ['HTTP origin',env=>{const target={...TARGET,origin:ORIGIN.replace('https:','http:')};
  env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([target]);env.COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS=JSON.stringify([target.origin]);}],
 ['literal IP origin',env=>{const target={...TARGET,origin:'https://127.0.0.1'};
  env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([target]);env.COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS=JSON.stringify([target.origin]);}],
 ['IPv6 literal origin',env=>{const target={...TARGET,origin:'https://[::1]'};
  env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([target]);env.COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS=JSON.stringify([target.origin]);}],
 ['origin query',env=>env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([{...TARGET,origin:ORIGIN+'?sink=other'}])],
 ['origin fragment',env=>env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([{...TARGET,origin:ORIGIN+'#other'}])],
 ['embedded credentials',env=>env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([{...TARGET,origin:ORIGIN.replace('https://','https://user:secret@')}])],
 ['network-relative write path',env=>env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([{...TARGET,writePath:'//different.invalid/notify'}])],
 ['QA receiver in production',env=>env.ENVIRONMENT='PROD'],
])test(`${name} fails closed before D1 or network`,async t=>{
 const f=await fixture(t);change(f.env);const before=f.counts.queries;
 const result=await dispatchRecoveryDeliveries(f.env,options(f.recipient));
 assert.equal(result.state,'HOLD_RECOVERY_TARGET_CONFIG');
 assert.equal(f.counts.queries,before);assert.equal(f.calls.length,0);
});

test('actual Agent intake, independent recipient and authenticated readback produce a durable delivery receipt',async t=>{
 const f=await fixture(t);
 assert.equal(f.ack.ack,'PERSISTED');assert.equal(f.ack.external_delivery_confirmed,false);
 assert.equal(f.sink().prepare('SELECT count(*) AS n FROM qa_delivery_receipts').get().n,0);
 const result=await dispatchRecoveryDeliveries(f.env,options(f.recipient));
 assert.equal(result.delivered,1);assert.deepEqual(f.calls.map(x=>x.method),['POST','GET']);
 assert.equal(f.calls[0].authorization,'Bearer '+f.env.SYNTHETIC_WRITE);
 assert.equal(f.calls[1].authorization,'Bearer '+f.env.SYNTHETIC_READ);
 assert.deepEqual(f.calls[0].body,EVENT);
 const [row]=f.rows();assert.equal(row.state,'DELIVERED');assert.equal(row.event_id,f.ack.event_id);
 const receipt=f.sink().prepare('SELECT * FROM qa_delivery_receipts WHERE event_id=?').get(EVENT.event_id);
 assert.equal(row.receipt_ref,receipt.receipt_ref);assert.match(row.receipt_sha256,/^[0-9a-f]{64}$/);
 assert.equal(row.receipt_sha256,canonicalReceiptSha({
  schema:'hara.commander.review163.recipient-readback.v1',state:'QA_RECIPIENT_PERSISTED',...receipt}));
 f.reopen();
 const repeat=await dispatchRecoveryDeliveries(f.env,{...options(f.recipient),nowMs:NOW+600000});
 assert.equal(repeat.attempted,0);assert.equal(f.calls.length,2);assert.equal(f.rows().length,1);
});

test('POST acceptance without independent readback cannot claim delivery',async t=>{
 const f=await fixture(t);
 const fetchImpl=async(url,init)=>{
  const request=new Request(url,init);
  if(request.method==='GET')return Response.json({code:'SYNTHETIC_READBACK_DOWN'},{status:503});
  return f.recipient(request);
 };
 const result=await dispatchRecoveryDeliveries(f.env,options(fetchImpl));
 assert.equal(result.delivered,0);assert.equal(f.rows()[0].state,'RETRY');
 assert.equal(f.sink().prepare('SELECT count(*) AS n FROM qa_delivery_receipts').get().n,1);
 const again=await dispatchRecoveryDeliveries(f.env,{...options(f.recipient),nowMs:NOW+600000});
 assert.equal(again.delivered,1);
 assert.equal(f.sink().prepare('SELECT count(*) AS n FROM qa_delivery_receipts').get().n,1);
});

for(const [name,tamper] of [
 ['wrong fingerprint',body=>({...body,fingerprint:'0'.repeat(64)})],
 ['wrong event',body=>({...body,event_id:'f'.repeat(32)})],
 ['different receipt',body=>({...body,receipt_ref:'0'.repeat(64)})],
 ['human acknowledgement',body=>({...body,schema:'hara.commander.recovery-portal-ack.v1',state:'PORTAL_ACKNOWLEDGED'})],
 ['wrong schema',body=>({...body,schema:'hara.commander.review163.recipient-accepted.v1'})],
])test(`${name} on readback cannot confirm delivery`,async t=>{
 const f=await fixture(t);
 const fetchImpl=async(url,init)=>{
  const request=new Request(url,init);
  const reply=await f.recipient(request);
  return request.method==='GET'?Response.json(tamper(await reply.json())):reply;
 };
 const result=await dispatchRecoveryDeliveries(f.env,options(fetchImpl));
 assert.equal(result.delivered,0);assert.equal(f.rows()[0].state,'RETRY');
 assert.equal(f.rows()[0].receipt_ref,null);
});

test('HTTP redirects are not a recipient receipt and never forward credentials',async t=>{
 const f=await fixture(t);let sends=0;
 const fetchImpl=async()=>{sends++;return new Response(null,{status:302,headers:{location:'https://unadmitted.invalid/'}});};
 const result=await dispatchRecoveryDeliveries(f.env,options(fetchImpl));
 assert.equal(result.delivered,0);assert.equal(sends,1);assert.equal(f.rows()[0].state,'RETRY');
});

test('an oversized receiver body is rejected before it can become a receipt',async t=>{
 const f=await fixture(t);
 const fetchImpl=async()=>new Response(new ReadableStream({start(controller){
  controller.enqueue(new TextEncoder().encode('{"schema":"'+'x'.repeat(5000)+'"}'));controller.close();
 }}),{status:202,headers:{'content-type':'application/json'}});
 const result=await dispatchRecoveryDeliveries(f.env,options(fetchImpl));
 assert.equal(result.delivered,0);assert.equal(f.rows()[0].state,'RETRY');assert.equal(f.rows()[0].receipt_ref,null);
});

test('tenant target scope never forwards another tenant event',async t=>{
 const f=await fixture(t,{tenantB:true});await dispatchRecoveryDeliveries(f.env,options(f.recipient));
 assert.equal(f.rows().length,1);assert.equal(f.rows()[0].tenant_id,'TENANT-A');
 assert.equal(f.calls.filter(x=>x.method==='POST').length,1);
});

test('revocation fences previously persisted events before recipient transport',async t=>{
 const f=await fixture(t);
 f.worker().prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE tenant_id=?").run(new Date(NOW).toISOString(),'TENANT-A');
 const result=await dispatchRecoveryDeliveries(f.env,options(f.recipient));
 assert.equal(result.delivered,0);assert.equal(f.calls.length,0);
 assert.equal(f.rows().filter(x=>x.state==='DELIVERED').length,0);
});

test('parallel dispatchers atomically claim one delivery intent',async t=>{
 const f=await fixture(t);let release,posts=0;
 const fetchImpl=async(url,init)=>{
  const request=new Request(url,init);
  if(request.method==='POST'){posts++;await new Promise(resolve=>{release=resolve;});}
  return f.recipient(request);
 };
 const first=dispatchRecoveryDeliveries(f.env,{...options(fetchImpl),timeoutMs:500});
 while(!release)await new Promise(resolve=>setImmediate(resolve));
 const second=await dispatchRecoveryDeliveries(f.env,{...options(fetchImpl),timeoutMs:500});
 release();const completed=await first;
 assert.equal(second.attempted,0);assert.equal(completed.delivered,1);assert.equal(posts,1);
 assert.equal(f.rows().length,1);assert.equal(f.rows()[0].attempts,1);
});

test('persistent receiver failure reaches eight attempts and stops without fabricating a receipt',async t=>{
 const f=await fixture(t);let sends=0;
 const fetchImpl=async()=>{sends++;return Response.json({code:'SYNTHETIC_DOWN'},{status:503});};
 for(let n=0;n<9;n++)await dispatchRecoveryDeliveries(f.env,{...options(fetchImpl),nowMs:NOW+n*3600000});
 const [row]=f.rows();assert.equal(row.state,'EXHAUSTED');assert.equal(row.attempts,8);
 assert.equal(sends,8);assert.equal(row.receipt_ref,null);assert.equal(row.receipt_sha256,null);
});

test('an unresponsive recipient times out, releases the lease and later recovers',async t=>{
 const f=await fixture(t);
 const result=await dispatchRecoveryDeliveries(f.env,{...options(async()=>new Promise(()=>{})),timeoutMs:15});
 assert.equal(result.delivered,0);assert.equal(f.rows()[0].state,'RETRY');
 const recovered=await dispatchRecoveryDeliveries(f.env,{...options(f.recipient),nowMs:NOW+600000});
 assert.equal(recovered.delivered,1);assert.equal(f.rows()[0].state,'DELIVERED');
});

test('server detector events are held for a QA receiver without inventing an Agent envelope',async t=>{
 const f=await fixture(t,{ingest:false});
 await detectOfflineRecoveryEvents(f.env,NOW);
 assert.ok(f.worker().prepare("SELECT count(*) AS n FROM commander_device_recovery_events WHERE origin='SERVER'").get().n>0);
 const result=await dispatchRecoveryDeliveries(f.env,options(f.recipient));
 assert.ok(result.held>0);assert.equal(result.delivered,0);assert.equal(f.calls.length,0);
});

test('commercial receipt adapter carries only persisted metadata and binds the recipient identity',async t=>{
 const f=await fixture(t,{ingest:false});await detectOfflineRecoveryEvents(f.env,NOW);
 const target={...TARGET,kind:'HTTPS_RECEIPT_V1',id:'synthetic-authorized-recipient'};
 f.env.COMMANDER_RECOVERY_DELIVERY_TARGETS=JSON.stringify([target]);
 const requests=[];let readback=null;
 const fetchImpl=async(url,init)=>{
  const request=new Request(url,init);
  assert.equal(request.redirect,'error');
  requests.push(request.method);
  if(request.method==='POST'){
   const body=await request.json();
   assert.equal(body.schema,'hara.commander.recovery-notification.v1');assert.equal(body.origin,'SERVER');
   assert.equal(body.worker,null);assert.equal(body.detector,null);
   assert.deepEqual(Object.keys(body).sort(),['schema','event_id','incident_id','generation','sequence','state',
    'at_utc','error_code','origin','worker','detector'].sort());
   const hash=await fingerprint(body);const reference=await digest(body.event_id+'|'+hash+'|'+target.id);
   f.sink().prepare('INSERT OR IGNORE INTO qa_delivery_receipts VALUES(?,?,?,?)').run(body.event_id,hash,reference,new Date(NOW).toISOString());
   return Response.json({schema:'hara.commander.recovery-recipient.v1',state:'RECIPIENT_PERSISTED',
    event_id:body.event_id,fingerprint:hash,receipt_ref:reference,recipient_id:target.id},{status:202});
  }
  const id=new URL(request.url).pathname.slice(target.readPath.length);
  const receipt=f.sink().prepare('SELECT * FROM qa_delivery_receipts WHERE event_id=?').get(id);
  assert.ok(receipt);
  readback={schema:'hara.commander.recovery-recipient.v1',state:'RECIPIENT_PERSISTED',
   ...receipt,recipient_id:target.id};
  return Response.json(readback);
 };
 const result=await dispatchRecoveryDeliveries(f.env,options(fetchImpl));
 assert.equal(result.delivered,1);assert.deepEqual(requests,['POST','GET']);
 assert.equal(f.rows()[0].state,'DELIVERED');
 assert.ok(readback);assert.equal(f.rows()[0].receipt_sha256,canonicalReceiptSha(readback));
});

test('partial staging preserves twelve incident transitions despite identical persistence timestamps',async t=>{
 const f=await fixture(t,{ingest:false});
 const incident='0123456789abcdef'.repeat(2);
 const states=['STALLED','RECOVERING','DEGRADED','RECOVERED'];
 for(let sequence=1;sequence<=12;sequence++)await f.intake({...EVENT,
  event_id:(await digest('sequence-fixture-'+sequence)).slice(0,32),
  client_incident_key:incident,transition_seq:sequence,state:states[(sequence-1)%states.length]});
 assert.equal(f.worker().prepare('SELECT count(DISTINCT persisted_at_utc) AS n FROM commander_device_recovery_events').get().n,1);
 for(let n=0;n<12;n++)await dispatchRecoveryDeliveries(f.env,{...options(f.recipient),nowMs:NOW+n,maxEvents:1});
 const delivered=f.calls.filter(x=>x.method==='POST').map(x=>x.body.transition_seq);
 assert.deepEqual(delivered,Array.from({length:12},(_,n)=>n+1));
 assert.equal(f.rows().length,12);assert.ok(f.rows().every(row=>row.state==='DELIVERED'));
 const count=f.calls.length;
 for(let n=0;n<3;n++)assert.equal((await dispatchRecoveryDeliveries(f.env,
  {...options(f.recipient),nowMs:NOW+100+n,maxEvents:1})).attempted,0);
 assert.equal(f.calls.length,count,'terminal transitions must never be resent');
});

test('a distinct recurrence starts its own sequence and preserves both incident receipts',async t=>{
 const f=await fixture(t,{ingest:false});const incidents=['a'.repeat(32),'b'.repeat(32)];
 for(const incident of incidents)for(const sequence of [1,2])await f.intake({...EVENT,
  event_id:(await digest('recurrence-'+incident+'-'+sequence)).slice(0,32),
  client_incident_key:incident,transition_seq:sequence,state:sequence===1?'STALLED':'RECOVERED'});
 for(let n=0;n<4;n++)await dispatchRecoveryDeliveries(f.env,{...options(f.recipient),nowMs:NOW+n,maxEvents:1});
 const sent=f.calls.filter(x=>x.method==='POST').map(x=>x.body);
 for(const incident of incidents)assert.deepEqual(sent.filter(x=>x.client_incident_key===incident).map(x=>x.transition_seq),[1,2]);
 assert.equal(new Set(sent.map(x=>x.event_id)).size,4);
 assert.equal(f.sink().prepare('SELECT count(*) AS n FROM qa_delivery_receipts').get().n,4);
 assert.equal(f.rows().length,4);assert.ok(f.rows().every(row=>row.state==='DELIVERED'));
 assert.equal((await dispatchRecoveryDeliveries(f.env,{...options(f.recipient),nowMs:NOW+100})).attempted,0);
});
