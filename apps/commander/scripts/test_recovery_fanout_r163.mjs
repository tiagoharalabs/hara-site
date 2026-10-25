// #163 queue fanout source contract: real SQLite, synthetic IDs, injected queue
// and recipient. No native Queue binding, D1, cron, network or credentials used.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const fanout=await import('../src/recovery-fanout.mjs').catch(error=>({missing:error}));
const subject=()=>{assert.ifError(fanout.missing);return fanout;};
const NOW=Date.parse('2026-10-24T12:00:00.000Z');
const iso=offset=>new Date(NOW+offset).toISOString();
const deviceId=n=>'HARA-DEVICE-00000000-0000-4000-8000-'+n.toString(16).padStart(12,'0');
const eventId=n=>'HARA-REC-'+n.toString(16).padStart(48,'0');
const hash=value=>createHash('sha256').update(value).digest('hex');
const stable=value=>JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))));
const SCHEMA='hara.commander.recovery-work.v1';
const ORIGIN='https://synthetic-recipient.example.com';
const TARGET={tenant_id:'TENANT-A',id:'synthetic-r163',kind:'HTTPS_RECEIPT_V1',origin:ORIGIN,
 writePath:'/notify',readPath:'/receipt/',writeSecret:'SYNTHETIC_WRITE',readSecret:'SYNTHETIC_READ'};
function fixture(t){
 const db=new DatabaseSync(':memory:'),recipient=new DatabaseSync(':memory:');
 db.exec('PRAGMA foreign_keys=ON;CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);'+
  'CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,'+
  'revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT);'+
  "INSERT INTO tenants VALUES('TENANT-A'),('TENANT-B');");
 for(const file of ['0037_device_recovery_alerts.sql','0038_recovery_delivery.sql','0039_recovery_device_leases.sql'])
  db.exec(readFileSync(new URL('../migrations/'+file,import.meta.url),'utf8'));
 recipient.exec('CREATE TABLE receipt(event_id TEXT PRIMARY KEY,body TEXT NOT NULL,receipt TEXT NOT NULL)');
 const metrics={queries:[],batches:[],fetches:[]},hooks={};
 const adapter={prepare:sql=>({bind:(...args)=>{assert.ok(args.length<=100,'D1 bound-parameter budget exceeded');return {
  all:async()=>{await hooks.beforeQuery?.(sql,args);const rows=db.prepare(sql).all(...args);
   metrics.queries.push({sql,args,rows:rows.length});return {results:rows};},
  first:async()=>{await hooks.beforeQuery?.(sql,args);const row=db.prepare(sql).get(...args)??null;
   metrics.queries.push({sql,args,rows:row?1:0});return row;},
  run:async()=>{await hooks.beforeQuery?.(sql,args);const result=db.prepare(sql).run(...args);
   metrics.queries.push({sql,args,changes:result.changes});return {meta:{changes:result.changes}};},
 };}})};
 const env={ENVIRONMENT:'DEV',PRODUCT_DB:adapter,COMMANDER_RECOVERY_ALERTS_ENABLED:'true',
  COMMANDER_RECOVERY_FANOUT_ENABLED:'true',
  COMMANDER_RECOVERY_WORK_QUEUE:{async sendBatch(entries){
   assert.ok(Array.isArray(entries)&&entries.length>0&&entries.length<=100,'Queue sendBatch >100');
   metrics.batches.push(structuredClone(entries));
  }},
  COMMANDER_RECOVERY_DELIVERY_ENABLED:'false',
  COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS:JSON.stringify([ORIGIN]),
  COMMANDER_RECOVERY_DELIVERY_TARGETS:JSON.stringify([TARGET]),
  SYNTHETIC_WRITE:'synthetic-only-write-secret',SYNTHETIC_READ:'synthetic-only-read-secret'};
 const insertDevice=db.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)');
 const addDevice=(n,{tenant='TENANT-A',state='ACTIVE',mode='OUTBOUND_RELAY',
  approval='PERSISTENT_TRUSTED',seen=-300000,created=-86400000}={})=>{
  insertDevice.run(deviceId(n),tenant,state,state==='REVOKED'?iso(-1000):null,approval,mode,iso(seen),iso(created));
  return deviceId(n);
 };
 const insertEvent=db.prepare('INSERT INTO commander_device_recovery_events '+
  '(event_id,tenant_id,device_id,incident_id,generation,sequence,event_state,origin,'+
  'client_event_id,worker,detector,event_at_utc,payload_sha256,persisted_at_utc) '+
  'VALUES(?,?,?,?,1,1,\'STALLED\',\'AGENT\',?,\'executor\',\'LINUX_PROCESS_GUARDIAN\',?,?,?)');
 const addEvent=(n,device=1,tenant='TENANT-A')=>{
  const key=n.toString(16).padStart(32,'0');
  insertEvent.run(eventId(n),tenant,deviceId(device),'agent-'+key,key,iso(-1000),'f'.repeat(64),iso(-1000));
  return eventId(n);
 };
 const stage=(id,{state='PENDING',attempts=0,next=0,lease=0}={})=>db.prepare(
  'INSERT INTO recovery_delivery_outbox(event_id,binding_id,tenant_id,state,attempts,next_attempt_ms,lease_until_ms) VALUES(?,?,?,?,?,?,?)')
  .run(id,TARGET.id,TARGET.tenant_id,state,attempts,next,lease);
 const jobs=()=>metrics.batches.flat().map(entry=>{
  assert.ok(entry&&Object.hasOwn(entry,'body'),'native Queue entry must carry body');
  const body=typeof entry.body==='string'?JSON.parse(entry.body):entry.body;
  assert.equal(body.schema,SCHEMA);
  assert.deepEqual(Object.keys(body).sort(),['kind','schema',body.kind==='SCAN'?'device_ids':'event_ids'].sort());
  return body;
 });
 const fetchImpl=async(url,init)=>{
  const request=new Request(url,init);metrics.fetches.push({url,method:request.method});
  assert.equal(new URL(url).origin,ORIGIN);assert.equal(request.redirect,'error');
  if(request.method==='POST'){
   assert.equal(request.headers.get('authorization'),'Bearer '+env.SYNTHETIC_WRITE);
   const event=await request.json(),fingerprint=hash(stable(event));
   assert.equal(request.headers.get('idempotency-key'),event.event_id);
   const receipt={schema:'hara.commander.recovery-recipient.v1',state:'RECIPIENT_PERSISTED',
    event_id:event.event_id,recipient_id:TARGET.id,fingerprint,receipt_ref:'synthetic-'+event.event_id};
   recipient.prepare('INSERT OR IGNORE INTO receipt VALUES(?,?,?)').run(event.event_id,stable(event),JSON.stringify(receipt));
   const row=recipient.prepare('SELECT * FROM receipt WHERE event_id=?').get(event.event_id);
   assert.equal(row.body,stable(event),'recipient idempotency conflict');
   return Response.json(JSON.parse(row.receipt),{status:202});
  }
  assert.equal(request.method,'GET');assert.equal(request.headers.get('authorization'),'Bearer '+env.SYNTHETIC_READ);
  const id=decodeURIComponent(new URL(url).pathname.split('/').at(-1));
  const row=recipient.prepare('SELECT receipt FROM receipt WHERE event_id=?').get(id);
  return row?Response.json(JSON.parse(row.receipt)):Response.json({code:'NOT_FOUND'},{status:404});
 };
 const produce=options=>subject().enqueueRecoveryWork(env,{nowMs:NOW,...options});
 const consume=(body,options={})=>{
  const calls={ack:0,retry:[],atAck:null};
  const batch={messages:[{body,ack(){calls.ack++;calls.atAck=db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n;},
   retry(value){calls.retry.push(value);}}]};
  return subject().consumeRecoveryWork(batch,env,{nowMs:NOW,fetchImpl,timeoutMs:100,...options}).then(result=>({calls,result}));
 };
 t.after(()=>{db.close();recipient.close();});
 return {db,recipient,env,metrics,hooks,addDevice,addEvent,stage,jobs,fetchImpl,produce,consume};
}
const scan=ids=>({schema:SCHEMA,kind:'SCAN',device_ids:ids});
const delivery=ids=>({schema:SCHEMA,kind:'DELIVER',event_ids:ids});

for(const flag of [undefined,'false','TRUE',true,1])test('fanout default OFF rejects non-exact flag '+String(flag),async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_FANOUT_ENABLED=flag;
 const result=await f.produce();assert.equal(result.state,'DISABLED');
 assert.equal(f.metrics.queries.length,0);assert.equal(f.metrics.batches.length,0);
 assert.equal(f.metrics.fetches.length,0);
});
for(const binding of [undefined,{}, {sendBatch:42}])test('missing admitted Queue binding is a scoped HOLD without D1',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_WORK_QUEUE=binding;
 const result=await f.produce();assert.equal(result.state,'HOLD_RECOVERY_QUEUE_BINDING');
 assert.equal(f.metrics.queries.length,0);assert.equal(f.metrics.fetches.length,0);
});
test('alerts gate remains independent from fanout opt-in',async t=>{
 const f=fixture(t);f.addDevice(1);f.env.COMMANDER_RECOVERY_ALERTS_ENABLED='false';
 await f.produce();assert.equal(f.metrics.batches.length,0);assert.equal(f.metrics.queries.length,0);
});
for(const flag of [undefined,'false',true])test('consumer fanout default OFF prevents D1 and HTTP: '+String(flag),async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_FANOUT_ENABLED=flag;
 await f.consume(scan([deviceId(1)]));
 assert.equal(f.metrics.queries.length,0);assert.equal(f.metrics.fetches.length,0);
});
test('20k real eligible rows become partitioned unique SCAN jobs without repeatedly selecting the first 200',async t=>{
 const f=fixture(t);f.db.exec('BEGIN');for(let n=1;n<=20000;n++)f.addDevice(n);f.db.exec('COMMIT');
 await f.produce();const jobs=f.jobs();
 assert.ok(jobs.length>=209&&jobs.length<=224);assert.ok(jobs.every(job=>job.kind==='SCAN'));
 assert.ok(jobs.every(job=>job.device_ids.length>=1&&job.device_ids.length<=96));
 const ids=jobs.flatMap(job=>job.device_ids);
 assert.equal(ids.length,20000);assert.equal(new Set(ids).size,20000);
 assert.deepEqual([...ids].sort(),Array.from({length:20000},(_,i)=>deviceId(i+1)).sort());
 assert.ok(f.metrics.batches.every(batch=>batch.length<=100));
 assert.equal(f.metrics.fetches.length,0,'producer must not perform recipient HTTP');
 console.log('R163_REAL_SQLITE_20K_SCAN_JOBS='+jobs.length);
});
test('long admitted device identities keep native sendBatch below its aggregate byte limit',async t=>{
 const f=fixture(t),insert=f.db.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)');
 f.db.exec('BEGIN');
 for(let n=0;n<2500;n++)insert.run('HARA-'+String(n).padStart(6,'0')+'x'.repeat(169),
  'TENANT-A','ACTIVE',null,'PERSISTENT_TRUSTED','OUTBOUND_RELAY',iso(-300000),iso(-86400000));
 f.db.exec('COMMIT');await f.produce();
 assert.equal(f.jobs().flatMap(job=>job.device_ids).length,2500);
 assert.ok(f.metrics.batches.length>1,'a count-only 100-job batch exceeds native bytes');
 for(const batch of f.metrics.batches)assert.ok(new TextEncoder().encode(JSON.stringify(batch)).length<=256000);
});
test('producer eligibility excludes stopped, revoked, fresh, ask and never-online devices',async t=>{
 const f=fixture(t);f.addDevice(1);f.addDevice(2,{tenant:'TENANT-B'});
 f.addDevice(3,{state:'REVOKED'});f.addDevice(4,{mode:'OUTBOUND_RELAY_OFFLINE'});
 f.addDevice(5,{approval:'ASK_EVERY_ACTION'});f.addDevice(6,{seen:-1000});
 f.addDevice(7,{created:-300000});
 await f.produce();assert.deepEqual(f.jobs().flatMap(job=>job.device_ids||[]).sort(),[deviceId(1),deviceId(2)].sort());
});
test('PROD fanout retains exact canary whitelist and rejects absent whitelist',async t=>{
 const f=fixture(t);f.env.ENVIRONMENT='PROD';f.addDevice(1);f.addDevice(2);
 await f.produce();assert.equal(f.jobs().length,0);
 f.env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS=deviceId(2);
 await f.produce();assert.deepEqual(f.jobs().flatMap(job=>job.device_ids||[]),[deviceId(2)]);
});
test('consumer rechecks refreshed heartbeat, revocation and manual stop after producer selected them',async t=>{
 const f=fixture(t);for(let n=1;n<=4;n++)f.addDevice(n);
 await f.produce();const jobs=f.jobs();assert.equal(jobs.flatMap(x=>x.device_ids).length,4);
 f.db.prepare('UPDATE commander_devices SET last_seen_at_utc=? WHERE device_id=?').run(iso(0),deviceId(1));
 f.db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id=?").run(iso(0),deviceId(2));
 f.db.prepare("UPDATE commander_devices SET tunnel_mode='OUTBOUND_RELAY_OFFLINE' WHERE device_id=?").run(deviceId(3));
 const results=[];for(const job of jobs)results.push(await f.consume(job));
 assert.deepEqual(f.db.prepare('SELECT device_id,event_state FROM commander_device_recovery_events').all()
  .map(row=>({...row})),[{device_id:deviceId(4),event_state:'DEGRADED'}]);
 assert.ok(results.every(r=>r.calls.ack===1&&r.calls.retry.length===0));
 assert.equal(results.at(-1).calls.atAck,1,'ack preceded durable incident persistence');
 assert.equal(f.metrics.fetches.length,0);
});
test('duplicate SCAN delivery is idempotent and consumes only its explicit device IDs',async t=>{
 const f=fixture(t);f.addDevice(1);f.addDevice(2);const job=scan([deviceId(2)]);
 assert.equal((await f.consume(job)).calls.ack,1);
 assert.equal((await f.consume(job)).calls.ack,1);
 const events=f.db.prepare('SELECT device_id FROM commander_device_recovery_events').all();
 assert.equal(events.length,1);assert.equal(events[0].device_id,deviceId(2));
});
test('PROD consumer cannot expand the canary whitelist from a queued job',async t=>{
 const f=fixture(t);f.addDevice(1);f.addDevice(2);f.env.ENVIRONMENT='PROD';
 f.env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS=deviceId(1);
 await f.consume(scan([deviceId(1),deviceId(2)]));
 assert.deepEqual(f.db.prepare('SELECT device_id FROM commander_device_recovery_events').all().map(row=>row.device_id),[deviceId(1)]);
});
test('96-device PROD job intersects its 16-canary fence within the D1 100-bind limit',async t=>{
 const f=fixture(t);for(let n=1;n<=96;n++)f.addDevice(n);
 f.env.ENVIRONMENT='PROD';f.env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS=
  Array.from({length:16},(_,i)=>deviceId(i+1)).join(',');
 const {calls}=await f.consume(scan(Array.from({length:96},(_,i)=>deviceId(i+1))));
 assert.equal(calls.ack,1);assert.deepEqual(calls.retry,[]);
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,16);
});
test('D1 failure retries one native message after 60s without acknowledging it',async t=>{
 const f=fixture(t);f.addDevice(1);f.hooks.beforeQuery=()=>{throw Error('SYNTHETIC_D1_UNAVAILABLE');};
 const {calls}=await f.consume(scan([deviceId(1)]));
 assert.equal(calls.ack,0);assert.deepEqual(calls.retry,[{delaySeconds:60}]);
 assert.equal(f.metrics.fetches.length,0);
});
test('native batch policy requires exactly one message before any D1 or HTTP operation',async t=>{
 const f=fixture(t);f.addDevice(1);let ack=0;const retries=[];
 const batch={messages:[1,2].map(()=>({body:scan([deviceId(1)]),ack(){ack++;},retry(value){retries.push(value);}}))};
 await subject().consumeRecoveryWork(batch,f.env,{nowMs:NOW,fetchImpl:f.fetchImpl,timeoutMs:100});
 assert.equal(f.metrics.queries.length,0);assert.equal(f.metrics.fetches.length,0);assert.equal(ack,0);
 assert.deepEqual(retries,[{delaySeconds:60},{delaySeconds:60}]);
});
for(const [name,body] of [
 ['unknown schema',{...scan([deviceId(1)]),schema:'unadmitted'}],
 ['unknown kind',{...scan([deviceId(1)]),kind:'EXECUTE'}],
 ['empty devices',scan([])],['97 devices',scan(Array.from({length:97},(_,i)=>deviceId(i+1)))],
 ['duplicate devices',scan([deviceId(1),deviceId(1)])],['non-string device',scan([42])],
 ['wrong device identity',scan(['../../private'])],
 ['forged tenant',{...scan([deviceId(1)]),tenant_id:'TENANT-B'}],
 ['forged destination',{...delivery([eventId(1)]),url:ORIGIN}],
 ['empty events',delivery([])],['11 events',delivery(Array.from({length:11},(_,i)=>eventId(i+1)))],
 ['duplicate events',delivery([eventId(1),eventId(1)])],['client event identity',delivery(['a'.repeat(32)])],
 ['non-object',null],['array',[]],
])test('invalid native job is acknowledged without effects: '+name,async t=>{
 const f=fixture(t);const {calls}=await f.consume(body);
 assert.equal(calls.ack,1);assert.deepEqual(calls.retry,[]);
 assert.equal(f.metrics.queries.length,0);assert.equal(f.metrics.fetches.length,0);
});
test('delivery fanout remains independently OFF without contacting a recipient',async t=>{
 const f=fixture(t);f.addDevice(1,{seen:-1000});f.addEvent(1);
 await f.produce();assert.equal(f.jobs().filter(job=>job.kind==='DELIVER').length,0);
 await f.consume(delivery([eventId(1)]));assert.equal(f.metrics.fetches.length,0);
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM recovery_delivery_outbox').get().n,0);
});
test('DELIVER producer queues only configured tenant targets and due non-terminal events',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';
 f.addDevice(1,{seen:-1000});f.addDevice(2,{tenant:'TENANT-B',seen:-1000});
 for(let n=1;n<=6;n++)f.addEvent(n);f.addEvent(7,2,'TENANT-B');
 f.stage(eventId(2),{state:'DELIVERED'});
 f.stage(eventId(3),{state:'RETRY',attempts:1,next:NOW+60000});
 f.stage(eventId(4),{state:'INFLIGHT',attempts:1,lease:NOW+60000});
 f.stage(eventId(5),{state:'EXHAUSTED',attempts:8});
 f.stage(eventId(6),{state:'RETRY',attempts:1,next:NOW-1});
 await f.produce();
 assert.deepEqual(f.jobs().filter(job=>job.kind==='DELIVER').flatMap(job=>job.event_ids).sort(),[eventId(1),eventId(6)].sort());
 assert.equal(f.metrics.fetches.length,0);
});
test('20k real native events become 2000 bounded unique DELIVER jobs',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';f.addDevice(1,{seen:-1000});
 f.db.exec('BEGIN');for(let n=1;n<=20000;n++)f.addEvent(n);f.db.exec('COMMIT');
 await f.produce();const jobs=f.jobs().filter(job=>job.kind==='DELIVER'),ids=jobs.flatMap(job=>job.event_ids);
 assert.equal(jobs.length,2000);assert.ok(jobs.every(job=>job.event_ids.length>=1&&job.event_ids.length<=10));
 assert.equal(ids.length,20000);assert.equal(new Set(ids).size,20000);
 assert.deepEqual([...ids].sort(),Array.from({length:20000},(_,i)=>eventId(i+1)).sort());
 assert.ok(f.metrics.batches.every(batch=>batch.length<=100));assert.equal(f.metrics.fetches.length,0);
 console.log('R163_REAL_SQLITE_20K_DELIVER_JOBS='+jobs.length);
});
test('DELIVER consumer persists independently verified receipt, then duplicate delivery causes no HTTP',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';
 f.addDevice(1,{seen:-1000});f.addEvent(1);f.addEvent(2);
 const result=await f.consume(delivery([eventId(2)]));assert.equal(result.calls.ack,1);assert.deepEqual(result.calls.retry,[]);
 const row=f.db.prepare('SELECT * FROM recovery_delivery_outbox').get();
 assert.equal(row.event_id,eventId(2));assert.equal(row.state,'DELIVERED');assert.match(row.receipt_sha256,/^[a-f0-9]{64}$/);
 assert.equal(f.recipient.prepare('SELECT count(*) AS n FROM receipt').get().n,1);
 const before=f.metrics.fetches.length;assert.equal((await f.consume(delivery([eventId(2)]))).calls.ack,1);
 assert.equal(f.metrics.fetches.length,before,'confirmed event replayed to recipient');
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM recovery_delivery_outbox').get().n,1,'unselected event dispatched');
});
test('DELIVER consumer rechecks enrollment revocation after queue production',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';
 f.addDevice(1,{seen:-1000});f.addEvent(1);await f.produce();
 const job=f.jobs().find(value=>value.kind==='DELIVER');assert.ok(job);
 f.db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id=?").run(iso(0),deviceId(1));
 await f.consume(job);assert.equal(f.metrics.fetches.length,0);
 assert.equal(f.recipient.prepare('SELECT count(*) AS n FROM receipt').get().n,0);
});
test('recipient outage retries only the selected message and later resumes without repeating delivery',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';f.addDevice(1,{seen:-1000});f.addEvent(1);
 const first=await f.consume(delivery([eventId(1)]),{fetchImpl:async()=>Response.json({code:'SYNTHETIC_DOWN'},{status:503})});
 assert.equal(first.calls.ack,0);assert.deepEqual(first.calls.retry,[{delaySeconds:60}]);
 assert.equal(f.db.prepare('SELECT state FROM recovery_delivery_outbox').get().state,'RETRY');
 const resumed=await f.consume(delivery([eventId(1)]),{nowMs:NOW+60000});
 assert.equal(resumed.calls.ack,1);assert.equal(f.db.prepare('SELECT state FROM recovery_delivery_outbox').get().state,'DELIVERED');
 assert.equal(f.recipient.prepare('SELECT count(*) AS n FROM receipt').get().n,1);
});

test('scoped detector uses enrollment primary-key lookups rather than a fleet rescan',async t=>{
 const f=fixture(t);for(let i=1;i<=100;i++)f.addDevice(i);
 await f.consume(scan([deviceId(99)]));
 const q=f.metrics.queries.find(q=>q.sql.includes('selected CROSS JOIN'));
 assert.ok(q);const plan=f.db.prepare('EXPLAIN QUERY PLAN '+q.sql).all(...q.args);
 assert.ok(plan.some(r=>r.detail.includes('SEARCH d USING INDEX')&&r.detail.includes('device_id=?')));
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,1);
});
test('duplicate consumers cannot both own an enrollment; lease release and replay remain safe',async t=>{
 const f=fixture(t);f.addDevice(1);f.env.COMMANDER_RECOVERY_SCAN_CONCURRENCY='4';
 const results=await Promise.all([f.consume(scan([deviceId(1)])),f.consume(scan([deviceId(1)]))]);
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,1);
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM recovery_device_leases').get().n,0);
 assert.equal(results.filter(r=>r.calls.retry.length).length,1);
 await f.consume(scan([deviceId(1)]));
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,1);
});
test('expired crash attempt cannot persist over a successor lease token',async t=>{
 const f=fixture(t);f.addDevice(1);let replaced=false;
 f.hooks.beforeQuery=(sql)=>{
  if(!replaced&&sql.startsWith('INSERT INTO commander_device_recovery_events')){
   replaced=true;f.db.prepare("UPDATE recovery_device_leases SET lease_token='SUCCESSOR',lease_until_ms=?").run(NOW+60000);
  }
 };
 const result=await f.consume(scan([deviceId(1)]));
 assert.equal(result.calls.retry.length,1);
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,0);
 assert.equal(f.db.prepare('SELECT lease_token FROM recovery_device_leases').get().lease_token,'SUCCESSOR');
});
test('exhausted delivery remains unacknowledged on every redelivery until native DLQ',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';f.addDevice(1,{seen:-1000});f.addEvent(1);
 f.stage(eventId(1),{state:'EXHAUSTED',attempts:8});
 for(let i=0;i<3;i++){const r=await f.consume(delivery([eventId(1)]));assert.equal(r.calls.ack,0);assert.equal(r.calls.retry.length,1);}
 assert.equal(f.metrics.fetches.length,0);
});
test('pending predecessor/due-time cannot acknowledge an unfinished delivery job',async t=>{
 const f=fixture(t);f.env.COMMANDER_RECOVERY_DELIVERY_ENABLED='true';f.addDevice(1,{seen:-1000});f.addEvent(1);
 f.stage(eventId(1),{state:'RETRY',attempts:1,next:NOW+60000});
 const r=await f.consume(delivery([eventId(1)]));assert.equal(r.calls.ack,0);assert.equal(r.calls.retry.length,1);assert.equal(f.metrics.fetches.length,0);
});
