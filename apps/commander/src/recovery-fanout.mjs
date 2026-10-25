// Source only, default OFF. No Queue is created or inferred from this contract.
// Native admission must bind the Queue/DLQ, paid D1 budget and max_batch_size=1,
// then measure queue latency and 20k end-to-end SLOs. No HTTP dispatch route.
// Provider API/limits: https://developers.cloudflare.com/queues/configuration/javascript-apis/
// https://developers.cloudflare.com/queues/platform/limits/ and /d1/platform/limits/
import {recoveryAlertsEnabled,listOfflineRecoveryCandidates,detectOfflineRecoveryDevices} from './recovery-alerts.mjs';
import {recoveryPartition} from './recovery-scan-leases.mjs';
import {listRecoveryDeliveryCandidates,dispatchRecoveryDeliveries} from './recovery-delivery.mjs';

const SCHEMA='hara.commander.recovery-work.v1';
const enabled=env=>env?.COMMANDER_RECOVERY_FANOUT_ENABLED==='true'&&recoveryAlertsEnabled(env);
const queueFor=env=>env?.RECOVERY_DELIVERY_QUEUE||env?.COMMANDER_RECOVERY_WORK_QUEUE;
const bound=env=>typeof queueFor(env)?.sendBatch==='function';
const schemaKeys=(body,field)=>Object.keys(body).sort().join(',')===['schema','kind',field].sort().join(',');
function valid(body){
 if(!body||typeof body!=='object'||Array.isArray(body)||body.schema!==SCHEMA)return false;
 const scan=body.kind==='SCAN',field=scan?'device_ids':'event_ids',ids=body[field];
 return (scan||body.kind==='DELIVER')&&schemaKeys(body,field)&&Array.isArray(ids)&&ids.length>0&&
  ids.length<=(scan?96:10)&&new Set(ids).size===ids.length&&ids.every(id=>typeof id==='string'&&
   (scan?/^[A-Za-z0-9][A-Za-z0-9_-]{0,179}$/:/^HARA-REC-[0-9a-f]{48}$/).test(id));
}
export async function enqueueRecoveryWork(env,{nowMs=Date.now(),maxDevices=20000,maxEvents=20000}={}){
 const result={state:'DISABLED',scan_devices:0,delivery_events:0,jobs:0,batches:0};
 if(!enabled(env))return result;
 if(!bound(env))return {...result,state:'HOLD_RECOVERY_QUEUE_BINDING'};
 if(!Number.isSafeInteger(nowMs)||nowMs<0||[maxDevices,maxEvents].some(n=>!Number.isSafeInteger(n)||n<1||n>20000)){
  throw Error('RECOVERY_FANOUT_BUDGET_INVALID');
 }
 result.state='COMPLETE';let pending=[],pendingBytes=2;
 const flush=async()=>{
  if(!pending.length)return;
  await queueFor(env).sendBatch(pending);
  result.jobs+=pending.length;result.batches++;pending=[];pendingBytes=2;
 };
 const add=async body=>{
  const entry={body},bytes=new TextEncoder().encode(JSON.stringify(entry)).length+1;
  // 100 messages alone is insufficient: 96 long device IDs per job can exceed
  // the provider's 256KB aggregate limit. Use a conservative byte ceiling too.
  if(pending.length&&(pending.length>=100||pendingBytes+bytes>240000))await flush();
  pending.push(entry);pendingBytes+=bytes;
 };
 let after=null;const partitions=Array.from({length:16},()=>[]);
 while(result.scan_devices<maxDevices){
  const limit=Math.min(500,maxDevices-result.scan_devices);
  const rows=await listOfflineRecoveryCandidates(env,nowMs,{limit,after});
  for(const row of rows){
   const shard=recoveryPartition(row.device_id),scanIds=partitions[shard];
   scanIds.push(row.device_id);result.scan_devices++;
   if(scanIds.length===96){await add({schema:SCHEMA,kind:'SCAN',device_ids:scanIds});partitions[shard]=[];}
  }
  if(rows.length<limit)break;
  after=rows.at(-1);
 }
 for(const device_ids of partitions)if(device_ids.length)await add({schema:SCHEMA,kind:'SCAN',device_ids});
 after=null;let eventIds=[];
 while(result.delivery_events<maxEvents){
  const limit=Math.min(500,maxEvents-result.delivery_events);
  const page=await listRecoveryDeliveryCandidates(env,{nowMs,limit,after});
  if(page.state!=='COMPLETE'){result.delivery_state=page.state;break;}
  for(const row of page.rows){
   eventIds.push(row.event_id);result.delivery_events++;
   if(eventIds.length===10){await add({schema:SCHEMA,kind:'DELIVER',event_ids:eventIds});eventIds=[];}
  }
  if(page.rows.length<limit)break;
  after=page.rows.at(-1);
 }
 if(eventIds.length)await add({schema:SCHEMA,kind:'DELIVER',event_ids:eventIds});
 await flush();return result;
}
export async function consumeRecoveryWork(batch,env,{nowMs=Date.now(),fetchImpl=fetch,timeoutMs=5000}={}){
 const messages=Array.isArray(batch?.messages)?batch.messages:[];
 const delaySeconds=env?.COMMANDER_RECOVERY_QUEUE_RETRY_SECONDS==='15'?15:60;
 const retry=()=>{for(const message of messages)message.retry({delaySeconds});};
 if(!enabled(env)){retry();return {state:'DISABLED'};}
 if(!bound(env)){retry();return {state:'HOLD_RECOVERY_QUEUE_BINDING'};}
 // One 96-device job stays below the paid D1 per-invocation query budget even
 // with idempotency/race checks. Do not implicitly accept a larger native batch.
 if(messages.length!==1){retry();return {state:'HOLD_RECOVERY_QUEUE_BATCH_SIZE'};}
 const message=messages[0],body=message.body;
 if(!valid(body)){message.ack();return {state:'REJECTED_RECOVERY_WORK'};}
 try{
  const result=body.kind==='SCAN'?await detectOfflineRecoveryDevices(env,body.device_ids,nowMs):
   await dispatchRecoveryDeliveries(env,{eventIds:body.event_ids,nowMs,fetchImpl,timeoutMs,exclusiveDeviceLeases:true});
  if(result.state?.startsWith('HOLD_')||result.held||result.pending||result.exhausted){
   message.retry({delaySeconds});return {state:'RETRY',result};
  }
  message.ack();return {state:'ACKNOWLEDGED',result};
 }catch{
  message.retry({delaySeconds});return {state:'RETRY'};
 }
}
