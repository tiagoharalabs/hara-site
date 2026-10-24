// Execute only on Services using its existing Wrangler. Protected references
// stay local; output is synthetic metrics/receipts, never bearer credentials.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomBytes} from 'node:crypto';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
import {CAPS,withinBudget} from './recovery_queue_budget_r163.mjs';
const execute=promisify(execFile),hash=x=>createHash('sha256').update(x).digest('hex');
const NODE='/home/sartorius/.nvm/versions/node/v24.15.0/bin/node';
const WRANGLER='/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/node_modules/wrangler/bin/wrangler.js';
const DB='hara-commander-r163-canary-dev-20261024',DBID='e769835e-0748-4f41-b868-c7c76b627fe9';
const WORKER='hara-commander-r163-canary-20261024';
const QUEUE='hara-commander-r163-recovery-dev-20261024',DLQ='hara-commander-r163-recovery-dlq-dev-20261024';
const ORIGIN='https://'+WORKER+'.tiago-sartori.workers.dev';
const SINK='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev';
const output=process.argv[2],source=process.argv[3];
assert.equal(path.dirname(output),'/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_BETA_FECHADO_VM_R1_20261023');
assert.ok(path.basename(output).startsWith('r163-queue-dev-'));
assert.equal(source,'/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-beta-0356-review-20261023');
const configPath=path.join(output,'queue.config.jsonc'),statePath=path.join(output,'private-state.json');
const state=JSON.parse(fs.readFileSync(statePath,'utf8'));
assert.equal(fs.lstatSync(statePath).mode&0o077,0);assert.equal(fs.lstatSync(output).mode&0o077,0);
const cfg=JSON.parse(fs.readFileSync(configPath,'utf8'));
assert.equal(cfg.name,WORKER);assert.equal(cfg.vars.ENVIRONMENT,'DEV');assert.equal(cfg.vars.R163_QA_ISOLATED,'true');
assert.equal(cfg.d1_databases[0].database_id,DBID);assert.equal(cfg.routes,undefined);
assert.equal(cfg.queues.producers[0].binding,'RECOVERY_DELIVERY_QUEUE');assert.equal(cfg.queues.producers[0].queue,QUEUE);
const consumer=cfg.queues.consumers[0];assert.equal(consumer.queue,QUEUE);assert.equal(consumer.dead_letter_queue,DLQ);
assert.equal(consumer.max_retries,2);assert.equal(consumer.max_batch_size,1);assert.equal(consumer.max_batch_timeout,5);
const nativeEnv={...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_LOG:'log'};
let number=0,active=false,queueFault=false,previousDevices=0;
const evidence={schema:'hara.commander.r163.hosted-queue-campaign.v1',state:'RUNNING',source_commit:state.source_commit,
 worker:WORKER,d1:DBID,queue:QUEUE,dlq:DLQ,caps:CAPS,commercial:false,prod_modified:false,
 native_queue:true,hosted_20k:false,hosted_20k_gate:'HOLD_ADDITIONAL_BUDGET',stages:[],native_queries:[],receipts:[]};
const checkpoint=()=>fs.writeFileSync(path.join(output,'campaign-evidence.json'),JSON.stringify(evidence,null,2)+'\n',{mode:0o600});
async function cli(args,input){
 const options={cwd:output,env:nativeEnv,timeout:60000,maxBuffer:8*1024*1024};
 // secret bulk is performed by the initial operator, never by this campaign.
 const r=await execute(NODE,[WRANGLER,...args],options);return r.stdout;
}
async function control(name,body){
 const r=await fetch(ORIGIN+'/__qa/'+name,{method:body===undefined?'GET':'POST',headers:{authorization:'Bearer '+state.control_token,'content-type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(15000)});
 const o=await r.json();assert.equal(r.status,200,'QA_CONTROL_'+name+'_'+JSON.stringify(o));return o;
}
async function check(){
 const s=await control('status');assert.ok(withinBudget(s.budget),'CAMPAIGN_BUDGET_STOP_'+JSON.stringify(s.budget));
 if(s.jobs.some(j=>!['ACKNOWLEDGED','STARTED','EXPECTED_FAULT_RETRY'].includes(j.outcome)))throw Error('ANOMALOUS_QUEUE_JOB');
 evidence.budget=s.budget;return s;
}
async function debit({reads=0,writes=0,events=0}){
 const r=await control('debit',{reads,writes,events});assert.ok(withinBudget(r.budget),'CAMPAIGN_BUDGET_STOP');evidence.budget=r.budget;
}
const literal=x=>x===null?'NULL':typeof x==='number'?String(x):"'"+String(x).replaceAll("'","''")+"'";
async function query(sql,{sink=false,maxWrites=0,maxReads=20000}={}){
 if(active){const s=await check();assert.ok(s.budget.rows_written+s.budget.reserved_write+maxWrites+16<CAPS.writes);
  assert.ok(s.budget.rows_read+s.budget.reserved_read+maxReads+16<CAPS.reads);}
 const file=path.join(output,'query-'+String(++number).padStart(4,'0')+'.json');
 const o=JSON.parse(await cli(['d1','execute',sink?'hara-commander-r163-notify-sink-dev-20261024':DB,'--remote','--config',sink?state.sink_config:configPath,'--json','--command',sql]));
 assert.ok(o.length&&o.every(r=>r.success===true));fs.writeFileSync(file,JSON.stringify(o,null,2)+'\n',{flag:'wx',mode:0o600});
 const reads=o.reduce((n,r)=>n+r.meta.rows_read,0),writes=o.reduce((n,r)=>n+r.meta.rows_written,0);
 assert.ok(Number.isSafeInteger(reads)&&Number.isSafeInteger(writes));assert.ok(reads<=maxReads&&writes<=maxWrites,'NATIVE_SQL_BOUND');
 evidence.native_queries.push({file:path.basename(file),sha256:hash(fs.readFileSync(file)),reads,writes,sink});
 if(active)await debit({reads,writes});return o.flatMap(r=>r.results||[]);
}
async function deviceRequest(device,route,body,expected){
 const r=await fetch(ORIGIN+route,{method:'POST',headers:{authorization:'Bearer '+device.token,'content-type':'application/json'},body:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(10000)});
 const value=await r.json();assert.equal(r.status,expected,'DEVICE_RESPONSE_'+JSON.stringify(value));return value;
}
async function map(items,fn){let cursor=0;await Promise.all(Array.from({length:4},async()=>{while(cursor<items.length)await fn(items[cursor++]);}));}
async function waitUntil(test,deadlineMs){
 while(Date.now()<deadlineMs){const r=await test();if(r)return r;await new Promise(r=>setTimeout(r,1500));}
 throw Error('MEASUREMENT_DEADLINE');
}
async function stage(concurrency,n){
 assert.ok([1,2,4].includes(concurrency));await check();
 cfg.queues.consumers[0].max_concurrency=concurrency;cfg.vars.COMMANDER_RECOVERY_SCAN_CONCURRENCY=String(concurrency);
 fs.writeFileSync(configPath,JSON.stringify(cfg,null,2)+'\n',{mode:0o600});
 const deployed=await cli(['deploy','--config',configPath]);
 fs.writeFileSync(path.join(output,'deploy-'+concurrency+'.txt'),deployed,{flag:'wx',mode:0o600});
 assert.ok(deployed.includes(WORKER)&&deployed.includes('Version ID:'));
 const step={concurrency,devices:n,synthetic_events_reserved:n*2+previousDevices,deployment_sha256:hash(deployed),started_at:new Date().toISOString()};
 evidence.stages.push(step);checkpoint();
 // Recovery of previous heartbeat anchors contributes previously active enrollments as real server
 // events. Reserve those as well, never silently exclude them from the ceiling.
 await debit({events:step.synthetic_events_reserved});
 const devices=state.devices.slice(0,n);
 await map(devices,d=>deviceRequest(d,'/api/device/heartbeat',{device_id:d.id,agent_version:'0.3.54',architecture:'x86_64',approval_mode:'PERSISTENT_TRUSTED'},200));
 const rows=await query('SELECT device_id,last_seen_at_utc FROM commander_devices WHERE tenant_id='+literal(state.tenant)+' AND device_id IN ('+devices.map(d=>literal(d.id)).join(',')+')',{maxReads:n*3});
 assert.equal(rows.length,n);step.heartbeat_anchors=rows;
 const events=devices.map((d,i)=>({device:d,event:{schema:'hara.commander.recovery-alert.proposal.v1',event_id:hash(state.campaign+'|event|'+concurrency+'|'+i).slice(0,32),
  client_incident_key:hash(state.campaign+'|incident|'+concurrency+'|'+i).slice(0,32),transition_seq:1,worker:'executor',state:'STALLED',
  observed_at_utc:new Date().toISOString(),detector:'LINUX_PROCESS_GUARDIAN'}}));
 await map(events,async x=>{const ack=await deviceRequest(x.device,'/api/device/recovery-events',x.event,202);assert.equal(ack.ack,'PERSISTED');x.server_id=ack.event_id;});
 const repeated=await deviceRequest(events[0].device,'/api/device/recovery-events',events[0].event,202);assert.equal(repeated.duplicate,true);
 await deviceRequest(events[0].device,'/api/device/recovery-events',{...events[0].event,state:'RECOVERED'},409);
 await deviceRequest(events[0].device,'/api/device/recovery-events',{...events[0].event,transition_seq:3},409);
 const deliveryStart=Date.now();step.delivery_enqueue=await control('produce',{});
 const ids=events.map(e=>literal(e.server_id)).join(',');let delivered;
 delivered=await waitUntil(async()=>{
  await check();const r=await query("SELECT o.*,r.client_event_id,r.portal_ack_at_utc FROM recovery_delivery_outbox o JOIN commander_device_recovery_events r ON r.event_id=o.event_id WHERE o.event_id IN ("+ids+")",{maxReads:n*5});
  assert.ok(r.every(row=>row.state!=='EXHAUSTED'),'DELIVERY_EXHAUSTED');return r.length===n&&r.every(row=>row.state==='DELIVERED')?r:null;
 },Date.now()+45000);
 step.delivery_wall_ms=Date.now()-deliveryStart;
 // Count conservative sink operation bounds, because its independent Worker
 // has no per-response D1 meter. Native verification SELECT metadata is exact.
 await debit({reads:n*8,writes:n*4});
 for(const x of events){
  const r=await fetch(SINK+'/receipt/'+x.event.event_id,{headers:{authorization:'Bearer '+state.sink_read},redirect:'error',signal:AbortSignal.timeout(10000)});
  assert.equal(r.status,200);const receipt=await r.json(),row=delivered.find(o=>o.event_id===x.server_id);
  assert.equal(receipt.event_id,x.event.event_id);assert.equal(receipt.receipt_ref,row.receipt_ref);
  const canonical=JSON.stringify(Object.fromEntries(Object.entries(receipt).sort(([a],[b])=>a.localeCompare(b))));
  assert.equal(hash(canonical),row.receipt_sha256);assert.equal(row.portal_ack_at_utc,null);
  evidence.receipts.push({server_id:x.server_id,client_id:x.event.event_id,receipt_sha256:row.receipt_sha256,receipt_ref:row.receipt_ref});
 }
 const sinkRows=await query('SELECT event_id,fingerprint,receipt_ref FROM qa_delivery_receipts WHERE event_id IN ('+events.map(e=>literal(e.event.event_id)).join(',')+')',{sink:true,maxReads:n*3});assert.equal(sinkRows.length,n);
 const replayJobCount=(await check()).jobs.length;await control('produce',{});
 await new Promise(r=>setTimeout(r,1500));assert.equal((await check()).jobs.length,replayJobCount,'CONFIRMED_NOTIFICATION_REQUEUED');
 const lastHeartbeat=Math.max(...rows.map(r=>Date.parse(r.last_seen_at_utc)));
 await waitUntil(async()=>{await check();return Date.now()>=lastHeartbeat+121000;},lastHeartbeat+125000);
 const scanStart=Date.now(),before=(await check()).jobs.filter(j=>j.kind==='SCAN').map(j=>j.message_id);
 step.scan_enqueue=await control('produce',{});
 let finalStatus;
 await waitUntil(async()=>{
  const s=await check(),newJobs=s.jobs.filter(j=>j.kind==='SCAN'&&!before.includes(j.message_id));
  if(newJobs.length===step.scan_enqueue.jobs&&newJobs.every(j=>j.outcome==='ACKNOWLEDGED')){finalStatus=s;return true;}return false;
 },lastHeartbeat+178000);
 const detections=await query("SELECT device_id,heartbeat_anchor_at_utc,persisted_at_utc,event_id FROM commander_device_recovery_events WHERE tenant_id="+literal(state.tenant)+" AND origin='SERVER' AND event_state='DEGRADED' AND heartbeat_anchor_at_utc IN ("+rows.map(r=>literal(r.last_seen_at_utc)).join(',')+")",{maxReads:n*5});
 assert.equal(detections.length,n);assert.equal(new Set(detections.map(d=>d.device_id)).size,n);
 const delays=detections.map(d=>(Date.parse(d.persisted_at_utc)-Date.parse(d.heartbeat_anchor_at_utc))/1000).sort((a,b)=>a-b);
 step.detection={devices:n,observed_from_real_heartbeat:true,intervals_scaled:false,enqueue_wall_ms:Date.now()-scanStart,
  max_persisted_delay_s:delays.at(-1),p95_s:delays[Math.floor((n-1)*.95)],p99_s:delays[Math.floor((n-1)*.99)],
  readback_upper_delay_s:(finalStatus.server_ms-Math.min(...rows.map(r=>Date.parse(r.last_seen_at_utc))))/1000,
  processing_upper_ms:finalStatus.server_ms-scanStart,rows:detections};
 assert.ok(step.detection.readback_upper_delay_s<=180,'SLO_180S');assert.ok(step.detection.processing_upper_ms<45000,'PROCESSING_45S');
 previousDevices=n;step.state='PASS_HOSTED_DEV';step.finished_at=new Date().toISOString();checkpoint();console.log(JSON.stringify({stage:concurrency,state:step.state,devices:n,detection:step.detection.max_persisted_delay_s,upper:step.detection.readback_upper_delay_s,budget:evidence.budget}));
}
try{
 await control('start',{});active=true;
 const unauthorized=await fetch(ORIGIN+'/__qa/produce',{method:'POST'});assert.equal(unauthorized.status,401);
 const unauthenticated=await fetch(ORIGIN+'/api/device/recovery-events',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});assert.equal(unauthenticated.status,401);
 for(const [c,n] of [[1,25],[2,50],[4,50]])await stage(c,n);
 await control('fault',{});queueFault=true;
 const fault=await waitUntil(async()=>{const s=await check();return s.jobs.find(j=>j.detail?.includes('R163-QA-DLQ-FAULT')&&j.attempts===3);},Date.now()+90000);
 evidence.dlq={state:'HOLD_NATIVE_DLQ_READBACK',fault_attempts:3,message_id:fault.message_id};
 evidence.budget=(await check()).budget;evidence.state='PASS_CAMPAIGN_PENDING_DLQ_READBACK';checkpoint();
 console.log(JSON.stringify({state:evidence.state,evidence_sha256:hash(fs.readFileSync(path.join(output,'campaign-evidence.json'))),output}));
}catch(error){
 evidence.state='FAIL_STOPPED';evidence.error={type:error.constructor.name,message:String(error.message).slice(0,600)};checkpoint();
 console.error(JSON.stringify({state:evidence.state,error:evidence.error,output}));process.exitCode=1;
}finally{
 try{await control('stop',{});}catch{}
}
