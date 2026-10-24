// Measured local SQLite FULL/WAL scan of 20k enrollments, with real clock and
// bounded concurrent jobs. Fault runs use explicit fixture lease expiry; they
// are correctness evidence, never a hosted latency or native Queue assertion.
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,readFileSync,writeFileSync,chmodSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {enqueueRecoveryWork,consumeRecoveryWork} from '../src/recovery-fanout.mjs';
import {boundedRecoveryMap} from '../src/recovery-scan-leases.mjs';
const output=process.argv[2];assert.ok(output);const N=20000;
const hash=x=>createHash('sha256').update(x).digest('hex');
const sourceNames=['recovery-alerts.mjs','recovery-fanout.mjs','recovery-scan-leases.mjs','recovery-scan-batch.mjs'];
const sourceHash=()=>Object.fromEntries(sourceNames.map(n=>[n,hash(readFileSync(new URL('../src/'+n,import.meta.url)))]));
const pinned=sourceHash();const evidence={schema:'hara.commander.r163.local-scan-scale.v1',devices:N,source_only:true,hosted:false,real_sqlite_full_wal:true,
 source_sha256:pinned,ramps:[],faults:[],scope:'OFFLINE_DETECTION_NOT_WEBSOCKET_CAPACITY'};
const dir=mkdtempSync(join(tmpdir(),'hara-r163-scan-'));chmodSync(dir,0o700);
function dbFor(label){
 const file=join(dir,label+'.sqlite'),db=new DatabaseSync(file);chmodSync(file,0o600);
 db.exec('PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;PRAGMA foreign_keys=ON;'+
 'CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT)');
 for(const n of ['0037_device_recovery_alerts.sql','0038_recovery_delivery.sql','0039_recovery_device_leases.sql'])db.exec(readFileSync(new URL('../migrations/'+n,import.meta.url),'utf8'));
 const now=Date.now(),anchor=new Date(now-121000).toISOString(),created=new Date(now-86400000).toISOString();
 db.exec('BEGIN');for(let t=0;t<16;t++)db.prepare('INSERT INTO tenants VALUES(?)').run('T'+t);
 const insert=db.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)');
 for(let i=0;i<N;i++)insert.run('R163-SCALE-'+i,'T'+i%16,'ACTIVE',null,'PERSISTENT_TRUSTED','OUTBOUND_RELAY',anchor,created);
 db.exec('COMMIT');return {db,anchor};
}
async function run(concurrency,fault=null){
 const {db,anchor}=dbFor('c'+concurrency+'-'+(fault||'clean'));const jobs=[];let queryCount=0,injected=0,queriesForJob=[],retryCount=0;
 const before=q=>{
  if(fault==='stale-preimage'&&injected===0&&q.startsWith('INSERT INTO commander_device_recovery_events')){
   injected++;db.prepare("UPDATE commander_devices SET revoked_at_utc='FIXTURE_REVOKED' WHERE device_id=?").run('R163-SCALE-0');
   db.prepare("UPDATE commander_devices SET last_seen_at_utc=? WHERE device_id=?").run(new Date().toISOString(),'R163-SCALE-1');
  }
  if(fault==='successor-token'&&injected===0&&q.startsWith('INSERT INTO commander_device_recovery_events')){
   injected++;db.exec("UPDATE recovery_device_leases SET lease_token='FIXTURE_SUCCESSOR'");
  }
 };
 const after=q=>{
  if(injected)return;
  if((fault==='crash-after-lease'&&q.startsWith('INSERT INTO recovery_device_leases'))||
   (fault==='lost-commit-response'&&q.startsWith('INSERT INTO commander_device_recovery_events'))){injected++;throw Error(fault);}
 };
 const env={ENVIRONMENT:'DEV',COMMANDER_RECOVERY_ALERTS_ENABLED:'true',COMMANDER_RECOVERY_FANOUT_ENABLED:'true',COMMANDER_RECOVERY_SCAN_BATCHED:'true',
  COMMANDER_RECOVERY_SCAN_CONCURRENCY:String(concurrency),COMMANDER_RECOVERY_QUEUE_RETRY_SECONDS:'15',
  RECOVERY_DELIVERY_QUEUE:{sendBatch:async entries=>jobs.push(...entries.map(e=>e.body))},
  PRODUCT_DB:{prepare:q=>({bind:(...a)=>{
   assert.ok(a.length<=100);return {
    all:async()=>{queryCount++;before(q);const r=db.prepare(q).all(...a);after(q);return {results:r};},
    first:async()=>{queryCount++;before(q);const r=db.prepare(q).get(...a)??null;after(q);return r;},
    run:async()=>{queryCount++;before(q);const r=db.prepare(q).run(...a);after(q);return {meta:{changes:r.changes}};}
   };
  }})}};
 const started=performance.now(),plan=await enqueueRecoveryWork(env,{nowMs:Date.now()});const pending=[];
 const consume=async body=>{
  const q=queryCount;let ack=0,retry=0;
  await consumeRecoveryWork({messages:[{body,ack(){ack++;},retry(){retry++;}}]},env);
  queriesForJob.push(queryCount-q);assert.equal(ack+retry,1);
  if(retry){retryCount++;pending.push(body);}
 };
 await boundedRecoveryMap(jobs,concurrency,consume);
 if(fault){
  // Only a local fixture advances expired lease state. No hosted clock or
  // production lease is edited, and fault timing does not receive SLO PASS.
  if(fault==='crash-after-lease'||fault==='successor-token')db.exec('UPDATE recovery_device_leases SET lease_until_ms=0');
  if(fault==='stale-preimage'){
   db.prepare('UPDATE commander_devices SET revoked_at_utc=NULL,last_seen_at_utc=? WHERE device_id IN (?,?)').run(anchor,'R163-SCALE-0','R163-SCALE-1');
   pending.push({schema:'hara.commander.recovery-work.v1',kind:'SCAN',device_ids:['R163-SCALE-0','R163-SCALE-1']});
  }
  const retried=pending.splice(0);for(const body of retried)await consume(body);
  assert.equal(pending.length,0,'fault did not recover');assert.equal(injected,1);
 }
 const wall=performance.now()-started;
 assert.equal(db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,N);
 assert.equal(db.prepare('SELECT count(DISTINCT device_id) AS n FROM commander_device_recovery_events').get().n,N);
 assert.equal(db.prepare(`SELECT count(*) AS n FROM commander_device_recovery_events r JOIN commander_devices d ON d.device_id=r.device_id WHERE r.tenant_id<>d.tenant_id`).get().n,0);
 assert.equal(db.prepare('SELECT count(*) AS n FROM recovery_device_leases').get().n,0);
 const countBefore=db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n;
 for(const body of jobs.slice(0,3))await consume(body);
 assert.equal(db.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,countBefore);
 const result={concurrency,devices:N,jobs:jobs.length,queries:queryCount,wall_ms:wall,from_121s_anchor:121+wall/1000,
  retries:retryCount,fault,simulated_lease_expiry:Boolean(fault),hosted_slo_pass:false,unique_events:N,duplicate_events:0,cross_tenant:0,scope:'LOCAL_SQLITE_ONLY'};
 if(!fault){assert.ok(wall<45000,'LOCAL_SCAN_PROCESSING_OVER_45S');result.local_processing_under_45s=true;}
 db.close();console.log(JSON.stringify(result));return result;
}
try{
 for(const c of [1,2,4])evidence.ramps.push(await run(c));
 for(const fault of ['stale-preimage','successor-token','crash-after-lease','lost-commit-response'])evidence.faults.push(await run(4,fault));
 assert.deepEqual(sourceHash(),pinned,'source changed during measurement');evidence.state='PASS_LOCAL_SCALE_AND_FAULTS';
 writeFileSync(output,JSON.stringify(evidence,null,2)+'\n',{flag:'wx',mode:0o600});
 console.log(JSON.stringify({state:evidence.state,output,sha256:hash(readFileSync(output))}));
}finally{rmSync(dir,{recursive:true,force:true});}
