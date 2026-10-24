// Repeatable SOURCE capacity measurement. Real private SQLite, actual ingestion,
// dispatcher and independent receiver code; no HTTPS, Cloudflare or customer data.
// Never labels a SQL model as hosted Event V2/20k admission.
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
import {mkdtempSync,chmodSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {ingestRecoveryEvent,detectOfflineRecoveryEvents} from '../src/recovery-alerts.mjs';
import {dispatchRecoveryDeliveries} from '../src/recovery-delivery.mjs';
import {enqueueRecoveryWork,consumeRecoveryWork} from '../src/recovery-fanout.mjs';
import receiver from './recovery_alert_review_sink_r163.mjs';

const args=process.argv.slice(2),count=Number(args[0]||20000),output=args[1];
const fanout=args[2]==='--fanout';
if(!Number.isInteger(count)||count<16||count>20000||!output)throw Error('USAGE_devices_16_to_20000_output_json');
if(args.length>3||(args[2]&&!fanout))throw Error('USAGE_optional_fanout');
const dir=mkdtempSync(join(tmpdir(),'hara-r163-capacity-'));chmodSync(dir,0o700);
const hash=text=>createHash('sha256').update(text).digest('hex');
const origin='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev';
const now=Date.now(),iso=new Date(now).toISOString(),created=new Date(now-86400000).toISOString();
const queries={worker:0,recipient:0,worker_rows_written:0,recipient_rows_written:0};
const latencies={ingest:[],delivery_tick:[]};let worker,sink;
function adapter(db,key){return {prepare:sql=>({bind:(...values)=>({
 first:async()=>{queries[key]++;return db.prepare(sql).get(...values)??null;},
 all:async()=>{queries[key]++;return {results:db.prepare(sql).all(...values)};},
 run:async()=>{queries[key]++;const r=db.prepare(sql).run(...values);
  queries[key+'_rows_written']+=r.changes;return {meta:{changes:r.changes}};},
})})};}
function percentiles(values){
 const sorted=[...values].sort((a,b)=>a-b);
 return {samples:sorted.length,p50_ms:sorted[Math.floor((sorted.length-1)*.50)]??null,
  p95_ms:sorted[Math.floor((sorted.length-1)*.95)]??null,p99_ms:sorted[Math.floor((sorted.length-1)*.99)]??null};
}
try{
 worker=new DatabaseSync(join(dir,'worker.sqlite3'));sink=new DatabaseSync(join(dir,'recipient.sqlite3'));
 for(const [db,name] of [[worker,'worker.sqlite3'],[sink,'recipient.sqlite3']]){
  chmodSync(join(dir,name),0o600);db.exec('PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;PRAGMA foreign_keys=ON');
 }
 worker.exec(`CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);
  CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT,state TEXT,
   revoked_at_utc TEXT,approval_mode TEXT,tunnel_mode TEXT,last_seen_at_utc TEXT,created_at_utc TEXT)`);
 for(const name of ['0037_device_recovery_alerts.sql','0038_recovery_delivery.sql'])
  worker.exec(readFileSync(new URL('../migrations/'+name,import.meta.url),'utf8'));
 sink.exec('CREATE TABLE qa_delivery_receipts(event_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,receipt_ref TEXT NOT NULL,stored_at_utc TEXT NOT NULL)');
 const tenants=Array.from({length:16},(_,i)=>'SYNTH-T'+i);
 const targets=tenants.map((tenant,i)=>({tenant_id:tenant,id:'qa'+i,kind:'QA_RECIPIENT_V1',origin,
  writePath:'/notify',readPath:'/receipt/',writeSecret:'SYNTHETIC_WRITE',readSecret:'SYNTHETIC_READ'}));
 const env={ENVIRONMENT:'DEV',PRODUCT_DB:adapter(worker,'worker'),COMMANDER_RECOVERY_ALERTS_ENABLED:'true',
  COMMANDER_RECOVERY_DELIVERY_ENABLED:'true',COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS:JSON.stringify([origin]),
  COMMANDER_RECOVERY_DELIVERY_TARGETS:JSON.stringify(targets),SYNTHETIC_WRITE:'synthetic-capacity-write-only',SYNTHETIC_READ:'synthetic-capacity-read-only'};
 const jobs=[];let maxBatchBytes=0,maxJobQueries=0,maxJobMs=0;
 if(fanout){env.COMMANDER_RECOVERY_FANOUT_ENABLED='true';env.COMMANDER_RECOVERY_WORK_QUEUE={sendBatch:async entries=>{
  assert.ok(entries.length<=100);const bytes=new TextEncoder().encode(JSON.stringify(entries)).length;
  assert.ok(bytes<=256000);maxBatchBytes=Math.max(maxBatchBytes,bytes);jobs.push(...entries.map(x=>x.body));
 }};}
 const consume=async(body,nowMs,fetchImpl)=>{
  let ack=0,retry=0;const before=queries.worker,started=performance.now();
  const result=await consumeRecoveryWork({messages:[{body,ack(){ack++;},retry(){retry++;}}]},env,{nowMs,fetchImpl});
  maxJobQueries=Math.max(maxJobQueries,queries.worker-before);maxJobMs=Math.max(maxJobMs,performance.now()-started);
  assert.ok(queries.worker-before<=1000);assert.equal(ack,1);assert.equal(retry,0);return result.result;
 };
 const sinkEnv={QA_SINK_DB:adapter(sink,'recipient'),QA_SINK_WRITE_SHA256:hash(env.SYNTHETIC_WRITE),QA_SINK_READ_SHA256:hash(env.SYNTHETIC_READ)};
 const addDevice=worker.prepare('INSERT INTO commander_devices VALUES(?,?,?,?,?,?,?,?)');
 const devices=[];worker.exec('BEGIN');
 for(const tenant of tenants)worker.prepare('INSERT INTO tenants VALUES(?)').run(tenant);
 for(let i=0;i<count;i++){
  const device={device_id:'SYNTH-DEVICE-'+i,tenant_id:tenants[i%16],state:'ACTIVE',revoked_at_utc:null};
  addDevice.run(device.device_id,device.tenant_id,'ACTIVE',null,'PERSISTENT_TRUSTED','OUTBOUND_RELAY',iso,created);devices.push(device);
 }
 worker.exec('COMMIT');
 const started=performance.now();let firstEvent,firstAck;
 for(let i=0;i<count;i++){
  const event={schema:'hara.commander.recovery-alert.proposal.v1',event_id:hash('event|'+i).slice(0,32),
   client_incident_key:hash('incident|'+i).slice(0,32),transition_seq:1,worker:'executor',state:'STALLED',
   observed_at_utc:iso,detector:i%2?'LINUX_PROCESS_GUARDIAN':'WINDOWS_JOB_GUARDIAN'};
  const t=performance.now();const ack=await ingestRecoveryEvent(env,devices[i],event,now);latencies.ingest.push(performance.now()-t);
  assert.equal(ack.ack,'PERSISTED');assert.equal(ack.external_delivery_confirmed,false);
  if(i===0){firstEvent=event;firstAck=ack;}
 }
 assert.equal((await ingestRecoveryEvent(env,devices[0],firstEvent,now)).duplicate,true);
 assert.equal(worker.prepare('SELECT count(*) AS n FROM commander_device_recovery_events').get().n,count);
 const ingestMs=performance.now()-started;
 let httpCalls=0,delivered=0,ticks=0;
 const fetchImpl=(url,init)=>{httpCalls++;const req=new Request(url,init);
  assert.equal(new URL(req.url).origin,origin);assert.equal(req.redirect,'error');return receiver.fetch(req,sinkEnv);};
 const deliveryStart=performance.now();
 const deliveryPlan=fanout?await enqueueRecoveryWork(env,{nowMs:now}):null;
 const deliveryJobs=jobs.splice(0);
 while(delivered<count){
  const t=performance.now();const result=fanout?await consume(deliveryJobs[ticks],now,fetchImpl):
   await dispatchRecoveryDeliveries(env,{fetchImpl,nowMs:now,maxEvents:10,timeoutMs:5000});
  latencies.delivery_tick.push(performance.now()-t);ticks++;delivered+=result.delivered;
  if(result.held||!result.delivered)throw Error('CAPACITY_TRANSPORT_STALLED_'+JSON.stringify(result));
  if(ticks%100===0)console.log(JSON.stringify({phase:'delivery',ticks,delivered,total:count}));
 }
 const deliveryMs=performance.now()-deliveryStart;
 assert.equal(sink.prepare('SELECT count(*) AS n FROM qa_delivery_receipts').get().n,count);
 assert.equal(worker.prepare("SELECT count(*) AS n FROM recovery_delivery_outbox WHERE state='DELIVERED'").get().n,count);
 assert.equal(httpCalls,count*2);
 const replayCalls=httpCalls;
 await dispatchRecoveryDeliveries(env,{fetchImpl,nowMs:now+60000});assert.equal(httpCalls,replayCalls);
 assert.equal(worker.prepare(`SELECT count(*) AS n FROM recovery_delivery_outbox o
  JOIN commander_device_recovery_events r ON r.event_id=o.event_id WHERE r.tenant_id<>o.tenant_id`).get().n,0);
 assert.equal(worker.prepare('SELECT count(DISTINCT tenant_id) AS n FROM recovery_delivery_outbox').get().n,16);
 // Measure the exact current default scanner on a full eligible outage, with
 // simulated cron time. This deliberately exposes a budget/SLO failure.
 worker.prepare('UPDATE commander_devices SET last_seen_at_utc=?').run(new Date(now-121000).toISOString());
 const scanStart=performance.now();let scanned=0,scanTicks=0,maxDetectionSeconds=0;
 const scanPlan=fanout?await enqueueRecoveryWork(env,{nowMs:now}):null;
 const scanJobs=jobs.splice(0);
 while(scanned<count){
  const at=fanout?now:now+scanTicks*60000;
  const r=fanout?await consume(scanJobs[scanTicks],at,fetchImpl):await detectOfflineRecoveryEvents(env,at);
  assert.ok(r.persisted>0);scanned+=r.persisted;scanTicks++;
  maxDetectionSeconds=fanout?121+(performance.now()-scanStart)/1000:(at-(now-121000))/1000;
 }
 const result={schema:'hara.commander.r163.source-capacity.v1',devices:count,tenants:16,
  source_only:true,real_sqlite_files:true,sqlite_sync:'FULL_WAL',actual_ingest_dispatch_receiver_code:true,
  network_used:false,hosted_cloudflare_load:false,windows_native_acceptance:false,event_v2_20k_admission:false,
  ingest:{...percentiles(latencies.ingest),wall_ms:ingestMs,events_per_second:count/(ingestMs/1000)},
  delivery:{...percentiles(latencies.delivery_tick),wall_ms:deliveryMs,events:delivered,independent_receipts:count,
   authenticated_fixture_requests:httpCalls,ticks_run_without_sleep:ticks,scope:'IN_PROCESS_INDEPENDENT_SQLITE_RECIPIENT',
   scheduled_default_events_per_minute:fanout?null:10,scheduled_minimum_drain_minutes:fanout?null:Math.ceil(count/10),replay_sent:0},
  scanner:{events:scanned,ticks:scanTicks,default_limit:fanout?96:200,wall_ms:performance.now()-scanStart,
   last_detection_seconds_under_minute_cron:fanout?null:maxDetectionSeconds,slo_seconds:180,
   sequential_local_scan_plus_121s_age:fanout?maxDetectionSeconds:null,
   slo_met:fanout?null:maxDetectionSeconds<=180},
  fanout:fanout?{queue_binding_synthetic:true,native_queue_used:false,delivery_plan:deliveryPlan,scan_plan:scanPlan,
   max_batch_bytes:maxBatchBytes,max_queries_per_job:maxJobQueries,max_job_ms:maxJobMs,
   source_sha256:Object.fromEntries(['recovery-alerts.mjs','recovery-delivery.mjs','recovery-fanout.mjs'].map(name=>
    [name,hash(readFileSync(new URL('../src/'+name,import.meta.url)))]))}:null,
  database:{...queries,cloudflare_rows_read_not_measured:true,index_write_amplification_not_in_counters:true,
   event_query_plan:worker.prepare('EXPLAIN QUERY PLAN SELECT device_id FROM commander_devices WHERE state=? AND approval_mode=? AND tunnel_mode=? AND last_seen_at_utc<? LIMIT 200')
    .all('ACTIVE','PERSISTENT_TRUSTED','OUTBOUND_RELAY',iso)},
  cost_model:{month_days:30,device_count:count,minute_cron_invocations_month:43200,
   event_v2_idle_liveness_requests_month:count*4*30,outbound_60s_heartbeat_requests_month:count*1440*30,
   event_v2_hourly_restart_storm_upgrades_month:count*24*30,
   all_device_scanner_read_upper_model_month:count*1440*30,
   worker_request_usd_per_million_over_included:.30,worker_cpu_usd_per_million_ms_over_included:.02,
   d1_read_usd_per_million_over_included:.001,d1_write_usd_per_million_over_included:1,
   do_request_usd_per_million_over_included:.15,
   account_shared_included_quotas_not_assumed_available:true,
   sources:['https://developers.cloudflare.com/workers/platform/pricing/','https://developers.cloudflare.com/d1/platform/pricing/','https://developers.cloudflare.com/durable-objects/platform/pricing/'],
   provider_notification_cost_not_bound:true},
  gates:{source_pipeline:'PASS',hosted_transport_20k:'HOLD_NATIVE_LOAD_RESOURCE_AND_BUDGET',
   default_cron_20k_slo:fanout?'HOLD_NATIVE_FANOUT_BINDING_AND_SLO':maxDetectionSeconds<=180?'PASS':'HOLD_CAPACITY_DEFAULT_CRON_BUDGET',
   commercial_delivery:'DISABLED_BY_USER'}};
 writeFileSync(output,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
 console.log(JSON.stringify({output,sha256:hash(readFileSync(output)),devices:count,delivered,ticks,scanner:result.scanner,gates:result.gates}));
}finally{worker?.close();sink?.close();rmSync(dir,{recursive:true,force:true});}
