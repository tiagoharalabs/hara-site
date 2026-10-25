// Entry point ONLY for hara-commander-r163-canary-20261024. No public/product
// configuration imports this laboratory control plane or its synthetic faults.
import worker from '../src/worker.js';
import {DeviceChannel as CoreDeviceChannel} from '../src/device-channel.mjs';
import {wrapQaEntry,wrapQaDeviceChannel} from './recovery_resource_qa_r163.mjs';
import {enqueueRecoveryWork,consumeRecoveryWork} from '../src/recovery-fanout.mjs';
import {acceptR163Dlq} from './recovery_queue_dlq_r163.mjs';
import {budgeted,CAPS,startRecoveryBudget,pauseRecoveryBudget,readRecoveryQaStatus} from './recovery_queue_budget_r163.mjs';
const QUEUE='hara-commander-r163-recovery-dev-20261024';
const DLQ='hara-commander-r163-recovery-dlq-dev-20261024';
const json=(o,status=200)=>Response.json(o,{status,headers:{'cache-control':'no-store'}});
const isolated=env=>env.ENVIRONMENT==='DEV'&&env.R163_QA_ISOLATED==='true';
async function auth(request,env){
 const token=request.headers.get('authorization')||'';
 const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token.startsWith('Bearer ')?token.slice(7):''));
 return Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('')===env.R163_QA_CONTROL_SHA256;
}
const produce=(env,scan=true)=>budgeted(env,{reads:15000,writes:64},e=>enqueueRecoveryWork(e,{maxDevices:500,maxEvents:500,scan}));
const legacyQaWorker={
 async fetch(request,env,ctx){
  if(!isolated(env))return json({code:'HOLD_QA_ISOLATION'},503);
  const path=new URL(request.url).pathname;
  if(path.startsWith('/__qa/')){
   if(!await auth(request,env))return json({code:'AUTH_REQUIRED'},401);
   try{
    if(path==='/__qa/status'&&request.method==='GET'){
     return json(await readRecoveryQaStatus(env));
    }
    if(path==='/__qa/start'&&request.method==='POST'){
     const row=await startRecoveryBudget(env.PRODUCT_DB);return json({state:row.state,deadline_ms:row.deadline_ms});
    }
    if(path==='/__qa/stop'&&request.method==='POST'){
     await pauseRecoveryBudget(env.PRODUCT_DB);return json({state:'PAUSED'});
    }
    if(path==='/__qa/debit'&&request.method==='POST'){
     const b=await request.json();
     if(Object.keys(b).sort().join(',')!=='events,reads,writes'||Object.values(b).some(n=>!Number.isSafeInteger(n)||n<0))throw Error('INVALID_DEBIT');
     const row=await env.PRODUCT_DB.prepare(`UPDATE r163_qa_budget SET rows_read=rows_read+?,rows_written=rows_written+?,events_reserved=events_reserved+?,
      state=CASE WHEN rows_read+reserved_read+?>=? OR rows_written+reserved_write+?>=? OR events_reserved+?>? THEN 'STOPPED' ELSE state END
      WHERE id=1 RETURNING *`).bind(b.reads+4,b.writes+4,b.events,b.reads+4,CAPS.reads,b.writes+4,CAPS.writes,b.events,CAPS.events).first();
     return json({budget:row});
    }
    if(path==='/__qa/recipient-preflight'&&request.method==='POST')return json(await budgeted(env,{reads:32,writes:32},async e=>{
     const origin='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev';
     if(typeof e.R163_QA_RECIPIENT?.fetch!=='function')throw Error('HOLD_QA_RECIPIENT_BINDING');
     let public_status=null;try{const r=await fetch(origin+'/health');public_status=r.status;await r.body?.cancel();}catch{}
     const r=await e.R163_QA_RECIPIENT.fetch(origin+'/receipt/'+('0'.repeat(32)),{headers:{authorization:'Bearer '+e.R163_QA_READ}});
     const read_status=r.status;await r.body?.cancel();
     const w=await e.R163_QA_RECIPIENT.fetch(origin+'/notify',{method:'POST',headers:{authorization:'Bearer '+e.R163_QA_WRITE,'content-type':'application/json'},body:'{}'});
     const write_status=w.status;await w.body?.cancel();
     let error_redirect;try{const q=await e.R163_QA_RECIPIENT.fetch(origin+'/health',{redirect:'error'});error_redirect=q.status;await q.body?.cancel();}catch(err){error_redirect=err.constructor.name;}
     return {public_status,read_status,write_status,error_redirect,recipient:'hara-commander-r163-sink-20261024'};
    }));
    if(path==='/__qa/produce'&&request.method==='POST')return json(await produce(env));
    if(path==='/__qa/produce-delivery'&&request.method==='POST')return json(await produce(env,false));
    if(path==='/__qa/fault'&&request.method==='POST')return json(await budgeted(env,{reads:32,writes:32},async e=>{
     await e.RECOVERY_DELIVERY_QUEUE.sendBatch([{body:{schema:'hara.commander.recovery-work.v1',kind:'SCAN',device_ids:['R163-QA-DLQ-FAULT']}}]);
     return {queued:true};
    }));
   }catch(error){return json({code:String(error.message).slice(0,100)},503);}
   return json({code:'NOT_FOUND'},404);
  }
  // All authenticated test traffic is metered too; the real credential resolver
  // and product handlers remain the implementation under test.
  if(path==='/api/device/heartbeat'||path==='/api/device/recovery-events'){
   try{return await budgeted(env,{reads:256,writes:64},e=>worker.fetch(request,e,ctx));}
   catch(error){return json({code:String(error.message).slice(0,100)},503);}
  }
  if(path==='/api/health')return worker.fetch(request,env,ctx);
  return json({code:'QA_SURFACE_RESTRICTED'},404);
 },
 async scheduled(event,env,ctx){
  // Explicit harness ticks make campaign scope/count reproducible. The existing
  // minute schedule stays configured but no background work runs unbudgeted.
  if(isolated(env)&&env.R163_QA_AUTOMATIC_CRON==='true')ctx.waitUntil(produce(env));
 },
 async queue(batch,env){
  if(!isolated(env)||![QUEUE,DLQ].includes(batch.queue))throw Error('HOLD_QA_QUEUE_IDENTITY');
  if(batch.messages.length!==1)throw Error('HOLD_QA_BATCH_SIZE');
  if(batch.queue===DLQ){
   await acceptR163Dlq(batch,env);return;
  }
  const message=batch.messages[0],body=message.body;
  const fault=body?.kind==='SCAN'&&body.device_ids?.length===1&&body.device_ids[0]==='R163-QA-DLQ-FAULT';
  const n=(body?.device_ids||body?.event_ids||[]).length;
  await budgeted(env,{reads:500+n*80,writes:64+n*25},async e=>{
   const before=Date.now();
   // Durable attempt evidence is independent of provider retries and the main
   // outbox. The expected poison message retries twice, then reaches the DLQ.
   await e.PRODUCT_DB.prepare(`INSERT INTO r163_qa_jobs(message_id,kind,attempts,outcome,detail) VALUES(?,?,1,'STARTED',?)
    ON CONFLICT(message_id) DO UPDATE SET attempts=attempts+1,outcome='STARTED'`)
    .bind(message.id,body?.kind||'INVALID',JSON.stringify(body)).run();
   let result;
   if(fault){message.retry({delaySeconds:5});result={state:'EXPECTED_FAULT_RETRY'};}
   else result=await consumeRecoveryWork(batch,e,{fetchImpl:async(url,init)=>{
    if(new URL(url).origin!=='https://hara-commander-r163-sink-20261024.tiago-sartori.workers.dev'||typeof e.R163_QA_RECIPIENT?.fetch!=='function')throw Error('HOLD_QA_RECIPIENT_BINDING');
    return e.R163_QA_RECIPIENT.fetch(url,init);
   }});
   await e.PRODUCT_DB.prepare('UPDATE r163_qa_jobs SET outcome=?,completed_ms=? WHERE message_id=?')
    .bind(result.state,Date.now(),message.id).run();
   console.log(JSON.stringify({schema:'hara.commander.r163.queue-job.v1',id:message.id,kind:body?.kind,
    state:result.state,devices:n,elapsed_ms:Date.now()-before,concurrency:e.COMMANDER_RECOVERY_SCAN_CONCURRENCY}));
  });
 }
};

// Only this dedicated QA entry exports the cumulative metering boundary.
export class DeviceChannel extends wrapQaDeviceChannel(CoreDeviceChannel) {}
export default wrapQaEntry(legacyQaWorker,worker);
