import {budgeted} from './recovery_queue_budget_r163.mjs';
const DLQ='hara-commander-r163-recovery-dlq-dev-20261024';
export async function acceptR163Dlq(batch,env){
 if(env.ENVIRONMENT!=='DEV'||env.R163_QA_ISOLATED!=='true'||batch.queue!==DLQ||batch.messages?.length!==1)throw Error('HOLD_QA_DLQ_IDENTITY');
 return budgeted(env,{reads:64,writes:64},async e=>{
  const m=batch.messages[0],raw=JSON.stringify(m.body);
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>32000)throw Error('HOLD_DLQ_PAYLOAD');
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw));
  const sha=Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('');
  await e.PRODUCT_DB.prepare('INSERT INTO r163_qa_dlq(message_id,queue_name,body_sha256,observed_ms) VALUES(?,?,?,?) ON CONFLICT DO NOTHING')
   .bind(m.id,DLQ,sha,Date.now()).run();
  const row=await e.PRODUCT_DB.prepare('SELECT body_sha256,queue_name FROM r163_qa_dlq WHERE message_id=?').bind(m.id).first();
  if(row?.body_sha256!==sha||row.queue_name!==DLQ)throw Error('HOLD_DLQ_RECEIPT_CONFLICT');
  m.ack();
 });
}
