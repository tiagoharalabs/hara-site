import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {detectOfflineRecoveryDevices,detectOfflineRecoveryEvents} from '../src/recovery-alerts.mjs';
import {consumeRecoveryWork} from '../src/recovery-fanout.mjs';
function fixture(t,batched=true){
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());const now=Date.now();
 db.exec('PRAGMA foreign_keys=ON;CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);'+
 'CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT);'+
 "INSERT INTO tenants VALUES('A'),('B')");
 for(const n of ['0037_device_recovery_alerts.sql','0038_recovery_delivery.sql','0039_recovery_device_leases.sql'])db.exec(readFileSync(new URL('../migrations/'+n,import.meta.url),'utf8'));
 const hooks={},sql=[];
 const adapter={prepare:q=>({bind:(...a)=>({
  all:async()=>{await hooks.before?.(q,a);sql.push(q);const r=db.prepare(q).all(...a);await hooks.after?.(q,a);return {results:r};},
  first:async()=>{await hooks.before?.(q,a);sql.push(q);return db.prepare(q).get(...a)??null;},
  run:async()=>{await hooks.before?.(q,a);sql.push(q);const r=db.prepare(q).run(...a);await hooks.after?.(q,a);return {meta:{changes:r.changes}};}
 })})};
 const env={ENVIRONMENT:'DEV',PRODUCT_DB:adapter,COMMANDER_RECOVERY_ALERTS_ENABLED:'true',COMMANDER_RECOVERY_FANOUT_ENABLED:'true',
  COMMANDER_RECOVERY_SCAN_BATCHED:batched?'true':'false',COMMANDER_RECOVERY_SCAN_CONCURRENCY:'4',
  COMMANDER_RECOVERY_QUEUE_RETRY_SECONDS:'15',RECOVERY_DELIVERY_QUEUE:{sendBatch:async()=>{}}};
 const add=(id,tenant='A')=>db.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)').run(id,tenant,'ACTIVE',null,'PERSISTENT_TRUSTED','OUTBOUND_RELAY',new Date(now-121000).toISOString(),new Date(now-86400000).toISOString());
 const count=()=>db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n;
 const consume=async ids=>{
  const calls={ack:0,retry:[]};const r=await consumeRecoveryWork({messages:[{body:{schema:'hara.commander.recovery-work.v1',kind:'SCAN',device_ids:ids},ack:()=>calls.ack++,retry:r=>calls.retry.push(r)}]},env,{nowMs:now});return {r,calls};
 };
 return {db,env,hooks,sql,add,count,consume,now};
}
test('batch event bytes and identity match existing server detector exactly',async t=>{
 const a=fixture(t,true),b=fixture(t,false);a.add('D');b.add('D');
 const anchor=new Date(a.now-121000).toISOString();b.db.prepare('UPDATE commander_devices SET last_seen_at_utc=?').run(anchor);
 await detectOfflineRecoveryDevices(a.env,['D'],a.now);await detectOfflineRecoveryEvents(b.env,a.now);
 assert.deepEqual({...a.db.prepare('SELECT * FROM commander_device_recovery_events').get()}, {...b.db.prepare('SELECT * FROM commander_device_recovery_events').get()});
 assert.equal(a.sql.length,5);assert.equal(a.db.prepare('SELECT count(*) AS n FROM recovery_device_leases').get().n,0);
});
test('96-device transaction stays scoped, bounded and idempotent across replay',async t=>{
 const f=fixture(t);for(let i=0;i<97;i++)f.add('D'+i,i%2?'A':'B');
 const ids=Array.from({length:96},(_,i)=>'D'+i);assert.equal((await f.consume(ids)).calls.ack,1);assert.equal(f.count(),96);
 assert.equal((await f.consume(ids)).calls.ack,1);assert.equal(f.count(),96);
 assert.equal(f.db.prepare("SELECT count(*) AS n FROM commander_device_recovery_events WHERE device_id='D96'").get().n,0);
});
for(const action of ['heartbeat','revoke','stop','tenant'])test('batch CAS rejects changed '+action,async t=>{
 const f=fixture(t);f.add('D');f.hooks.before=q=>{
  if(q.startsWith('INSERT INTO commander_device_recovery_events')){
   const sql={heartbeat:"UPDATE commander_devices SET last_seen_at_utc='2099-01-01T00:00:00Z'",revoke:"UPDATE commander_devices SET revoked_at_utc='REVOKED'",stop:"UPDATE commander_devices SET tunnel_mode='OUTBOUND_RELAY_OFFLINE'",tenant:"UPDATE commander_devices SET tenant_id='B'"}[action];f.db.exec(sql);
  }
 };
 await f.consume(['D']);assert.equal(f.count(),0);
});
test('successor token defeats stale insert/release and retries instead of ACK',async t=>{
 const f=fixture(t);f.add('D');f.hooks.before=q=>{if(q.startsWith('INSERT INTO commander_device_recovery_events'))f.db.exec("UPDATE recovery_device_leases SET lease_token='SUCCESSOR'");};
 const r=await f.consume(['D']);assert.equal(f.count(),0);assert.equal(r.calls.ack,0);assert.deepEqual(r.calls.retry,[{delaySeconds:15}]);
 assert.equal(f.db.prepare('SELECT lease_token FROM recovery_device_leases').get().lease_token,'SUCCESSOR');
});
test('expired native SQL clock defeats an unreclaimed token',async t=>{
 const f=fixture(t);f.add('D');f.hooks.before=q=>{if(q.startsWith('INSERT INTO commander_device_recovery_events'))f.db.exec('UPDATE recovery_device_leases SET lease_until_ms=0');};
 assert.equal((await f.consume(['D'])).calls.retry.length,1);assert.equal(f.count(),0);
});
test('crash after claiming retains leases; restarted job reclaims after expiry',async t=>{
 const f=fixture(t);f.add('D');let once=true;f.hooks.after=q=>{if(once&&q.startsWith('INSERT INTO recovery_device_leases')){once=false;throw Error('CRASH');}};
 assert.equal((await f.consume(['D'])).calls.retry.length,1);assert.equal(f.count(),0);
 assert.equal(f.db.prepare('SELECT count(*) AS n FROM recovery_device_leases').get().n,1);
 f.db.exec('UPDATE recovery_device_leases SET lease_until_ms=0');assert.equal((await f.consume(['D'])).calls.ack,1);assert.equal(f.count(),1);
});
test('lost commit response is replay-safe after restart',async t=>{
 const f=fixture(t);f.add('D');let once=true;f.hooks.after=q=>{if(once&&q.startsWith('INSERT INTO commander_device_recovery_events')){once=false;throw Error('LOST_COMMIT_RESPONSE');}};
 assert.equal((await f.consume(['D'])).calls.retry.length,1);assert.equal(f.count(),1);
 assert.equal((await f.consume(['D'])).calls.ack,1);assert.equal(f.count(),1);
});
test('batch query plans use selected enrollment/lease keys, not low-selectivity fleet scans',async t=>{
 const f=fixture(t);for(let i=0;i<100;i++)f.add('D'+i);const plans=[];
 f.hooks.before=(q,a)=>{if(q.includes('json_each'))plans.push(...f.db.prepare('EXPLAIN QUERY PLAN '+q).all(...a).map(r=>r.detail));};
 await f.consume(['D99']);assert.equal(f.count(),1);
 assert.ok(plans.some(p=>p.includes('SEARCH d USING INDEX')&&p.includes('device_id=?')));
 assert.ok(!plans.some(p=>p.includes('idx_recovery_watch_devices')));
});
