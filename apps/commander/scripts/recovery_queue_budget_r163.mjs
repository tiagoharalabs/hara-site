// Dedicated #163 QA only. Durable reservations survive crashes and concurrent
// consumers. They cannot be refunded by a client or reset by a new campaign.
export const CAPS={queue:4000,reads:250000,writes:10000,active_ms:1800000,events:500};
export const BUDGET_SCHEMA=`CREATE TABLE IF NOT EXISTS r163_qa_budget(
 id INTEGER PRIMARY KEY CHECK(id=1),state TEXT NOT NULL,start_ms INTEGER NOT NULL,
 deadline_ms INTEGER NOT NULL,rows_read INTEGER NOT NULL,rows_written INTEGER NOT NULL,
 reserved_read INTEGER NOT NULL DEFAULT 0,reserved_write INTEGER NOT NULL DEFAULT 0,
 queue_ops_upper INTEGER NOT NULL DEFAULT 0,events_reserved INTEGER NOT NULL DEFAULT 0,
 invocations INTEGER NOT NULL DEFAULT 0,anomaly TEXT);
 CREATE TABLE IF NOT EXISTS r163_qa_jobs(
 message_id TEXT PRIMARY KEY,kind TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
 outcome TEXT NOT NULL,completed_ms INTEGER,detail TEXT);
 CREATE TABLE IF NOT EXISTS r163_qa_dlq(
 message_id TEXT PRIMARY KEY,queue_name TEXT NOT NULL,body_sha256 TEXT NOT NULL,observed_ms INTEGER NOT NULL);`;
export function withinBudget(row,now=Date.now()){
 return row&&row.state==='ACTIVE'&&now<row.deadline_ms&&
  row.rows_read+row.reserved_read<CAPS.reads&&row.rows_written+row.reserved_write<CAPS.writes&&
  row.queue_ops_upper<CAPS.queue&&row.events_reserved<=CAPS.events;
}
export async function budgeted(env,{reads,writes},fn){
 if(env.ENVIRONMENT!=='DEV'||env.R163_QA_ISOLATED!=='true')throw Error('HOLD_QA_ISOLATION');
 if(![reads,writes].every(n=>Number.isSafeInteger(n)&&n>=16))throw Error('HOLD_BUDGET_RESERVATION');
 const db=env.PRODUCT_DB,now=Date.now();
 // Bookkeeping uses a PK lookup; its own read/write bounds are included below.
 const reserved=await db.prepare(`UPDATE r163_qa_budget SET reserved_read=reserved_read+?,reserved_write=reserved_write+?
  WHERE id=1 AND state='ACTIVE' AND deadline_ms>? AND rows_read+reserved_read+?<=?
  AND rows_written+reserved_write+?<=? RETURNING *`)
  .bind(reads,writes,now,reads,CAPS.reads,writes,CAPS.writes).first();
 if(!reserved)throw Error('HOLD_CAMPAIGN_BUDGET_OR_DEADLINE');
 // Conservative PK bookkeeping allowance includes reservation, settlement and
 // metering/status overhead. Query metadata below is provider-measured.
 let read=8,write=8,anomaly=null,result;
 const record=r=>{
  if(!r?.meta||!Number.isSafeInteger(r.meta.rows_read)||!Number.isSafeInteger(r.meta.rows_written))
   throw Error('HOLD_MISSING_D1_METER');
  read+=r.meta.rows_read;write+=r.meta.rows_written;
  if(read>reads||write>writes)throw Error('HOLD_D1_RESERVATION_ANOMALY');
  return r;
 };
 const metered={prepare:sql=>({bind:(...args)=>{
  const statement=db.prepare(sql).bind(...args);
  const query=async method=>{
   if(anomaly)throw Error('HOLD_CAMPAIGN_STOPPED');
   try{return record(await statement[method]());}catch(error){anomaly=error.message;throw error;}
  };
  return {all:()=>query('all'),run:()=>query('run'),first:async()=>(await query('all')).results?.[0]??null};
 }})};
 const originalQueue=env.RECOVERY_DELIVERY_QUEUE;
 const queue=originalQueue?{sendBatch:async entries=>{
  // 12 operations per published job covers write/read/delete, both configured
  // retries, transfer to DLQ, and bounded authenticated DLQ read/ack. This is
  // an upper reservation, not a claim of provider-billed operations.
  const n=entries.length*12;
  const r=await metered.prepare(`UPDATE r163_qa_budget SET queue_ops_upper=queue_ops_upper+?
   WHERE id=1 AND state='ACTIVE' AND queue_ops_upper+?<=? RETURNING queue_ops_upper`).bind(n,n,CAPS.queue).first();
  if(!r)throw Error('HOLD_QUEUE_BUDGET');
  await originalQueue.sendBatch(entries);
 }}:undefined;
 try{result=await fn({...env,PRODUCT_DB:metered,RECOVERY_DELIVERY_QUEUE:queue});}
 catch(error){anomaly??=error.message;throw error;}
 finally{
  // An unhandled crash retains the entire reservation. An observed anomaly
  // permanently stops new work; no automatic budget renewal is possible.
  await db.prepare(`UPDATE r163_qa_budget SET reserved_read=reserved_read-?,reserved_write=reserved_write-?,
   rows_read=rows_read+?,rows_written=rows_written+?,invocations=invocations+1,
   state=CASE WHEN ? IS NULL THEN state ELSE 'STOPPED' END,anomaly=COALESCE(?,anomaly) WHERE id=1`)
   .bind(reads,writes,read,write,anomaly,anomaly).run();
 }
 return result;
}
export async function startRecoveryBudget(db,now=Date.now()){
 // Resume a paused attempt in the same window. Never renew a deadline, reset
 // counters/reservations, or reactivate an anomalous/expired campaign.
 const row=await db.prepare(`UPDATE r163_qa_budget SET state='ACTIVE',
  start_ms=CASE WHEN start_ms=0 THEN ? ELSE start_ms END,
  deadline_ms=CASE WHEN start_ms=0 THEN ? ELSE deadline_ms END
  WHERE id=1 AND state='PAUSED' AND (start_ms=0 OR deadline_ms>?)
   AND rows_read+reserved_read<? AND rows_written+reserved_write<? AND queue_ops_upper<? AND events_reserved<=?
  RETURNING *`).bind(now,now+CAPS.active_ms,now,CAPS.reads,CAPS.writes,CAPS.queue,CAPS.events).first();
 if(!row)throw Error('HOLD_CAMPAIGN_NOT_RESUMABLE');return row;
}
