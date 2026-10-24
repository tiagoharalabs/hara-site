// #163: server delivery is separate from Agent ingestion and human portal ACK.
// No default destination, token, invented receipt, or implicit commercial opt-in.
// receipt_sha256 hashes UTF-8 canonical JSON of the authenticated GET receipt
// (top-level keys sorted), so an independent readback can reproduce the proof.
import {claimRecoveryDeviceLease,releaseRecoveryDeviceLease} from './recovery-scan-leases.mjs';
import {recoveryDeviceEnabled,prodCanaryDeviceIds} from './recovery-alerts.mjs';

const TARGET_FIELDS=['tenant_id','id','kind','origin','writePath','readPath','writeSecret','readSecret'];
const stable=value=>JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))));
async function sha(value){
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
 return Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
}
function targetsFor(env){
 const origins=JSON.parse(env.COMMANDER_RECOVERY_DELIVERY_ALLOWED_ORIGINS);
 const targets=JSON.parse(env.COMMANDER_RECOVERY_DELIVERY_TARGETS);
 if(!Array.isArray(origins)||!origins.length||origins.length>16||
    !Array.isArray(targets)||!targets.length||targets.length>16)throw Error('TARGET_CONFIG');
 const tenants=new Set(),ids=new Set();
 for(const t of targets){
  if(!t||Object.keys(t).sort().join(',')!==[...TARGET_FIELDS].sort().join(',')||
     typeof t.tenant_id!=='string'||!t.tenant_id||t.tenant_id.length>180||
     !/^[A-Za-z0-9_.:-]{1,64}$/.test(t.id)||tenants.has(t.tenant_id)||ids.has(t.id)||
     !['QA_RECIPIENT_V1','HTTPS_RECEIPT_V1'].includes(t.kind)||
     (t.kind==='QA_RECIPIENT_V1'&&env.ENVIRONMENT!=='DEV'))throw Error('TARGET_CONFIG');
  const url=new URL(t.origin);
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.port||
     url.pathname!=='/'||url.origin!==t.origin||!origins.includes(t.origin)||
     !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}$/.test(url.hostname)||
     /(?:^|\.)(?:localhost|local|internal|invalid)$/.test(url.hostname))throw Error('TARGET_CONFIG');
  for(const key of ['writePath','readPath']){
   if(typeof t[key]!=='string'||t[key].length>180||!/^\/[A-Za-z0-9_/-]+$/.test(t[key])||
      t[key].includes('//')||new URL(t[key],url).origin!==url.origin)throw Error('TARGET_CONFIG');
  }
  if(!t.readPath.endsWith('/'))throw Error('TARGET_CONFIG');
  for(const key of ['writeSecret','readSecret']){
   if(!/^[A-Z][A-Z0-9_]{2,79}$/.test(t[key])||typeof env[t[key]]!=='string'||
      env[t[key]].length<16||env[t[key]].length>512||/[\r\n]/.test(env[t[key]]))throw Error('TARGET_CONFIG');
  }
  tenants.add(t.tenant_id);ids.add(t.id);
 }
 return targets;
}
function envelope(row,target){
 if(target.kind==='QA_RECIPIENT_V1'){
  if(row.origin!=='AGENT'||!row.client_event_id||!row.incident_id.startsWith('agent-'))return null;
  return {schema:'hara.commander.recovery-alert.proposal.v1',event_id:row.client_event_id,
   client_incident_key:row.incident_id.slice(6),transition_seq:row.sequence,worker:row.worker,
   state:row.event_state,observed_at_utc:row.event_at_utc,detector:row.detector};
 }
 return {schema:'hara.commander.recovery-notification.v1',event_id:row.event_id,
  incident_id:row.incident_id,generation:row.generation,sequence:row.sequence,
  state:row.event_state,at_utc:row.event_at_utc,error_code:row.error_code,
  origin:row.origin,worker:row.worker,detector:row.detector};
}
async function readJson(response){
 if(!response.ok)throw Error('RECIPIENT_UNAVAILABLE');
 const declared=Number(response.headers.get('content-length')||0);
 if(!Number.isFinite(declared)||declared>4096||!response.body)throw Error('RECIPIENT_RECEIPT_INVALID');
 const reader=response.body.getReader(),parts=[];let length=0;
 try{while(true){const r=await reader.read();if(r.done)break;
  length+=r.value.byteLength;if(length>4096)throw Error('RECIPIENT_RECEIPT_INVALID');parts.push(r.value);
 }}finally{await reader.cancel().catch(()=>{});}
 const bytes=new Uint8Array(length);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
 const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes),obj=JSON.parse(raw);
 if(!obj||Array.isArray(obj)||typeof obj!=='object'||
    [...raw.matchAll(/"((?:[^"\\]|\\.)+)"\s*:/g)].length!==Object.keys(obj).length)throw Error('RECIPIENT_RECEIPT_INVALID');
 return obj;
}
function validateReceipt(receipt,target,event,hash,reference=null){
 const qa=target.kind==='QA_RECIPIENT_V1';
 const schema=qa?'hara.commander.review163.recipient-readback.v1':'hara.commander.recovery-recipient.v1';
 if(receipt?.schema!==schema||receipt.state!==(qa?'QA_RECIPIENT_PERSISTED':'RECIPIENT_PERSISTED')||
    receipt.event_id!==event.event_id||receipt.fingerprint!==hash||
    !/^[A-Za-z0-9_.:-]{1,160}$/.test(receipt.receipt_ref||'')||
    (reference!==null&&receipt.receipt_ref!==reference)||(!qa&&receipt.recipient_id!==target.id))throw Error('RECIPIENT_RECEIPT_INVALID');
 return receipt;
}
async function deliver(env,target,event,fetchImpl,signal,attempt){
 const hash=await sha(stable(event));
 const read=()=>fetchImpl(target.origin+target.readPath+encodeURIComponent(event.event_id),{
  method:'GET',headers:{authorization:'Bearer '+env[target.readSecret],accept:'application/json'},redirect:'error',signal});
 // An ambiguous prior POST is reconciled before re-posting the same key.
 // The admitted receiver must provide durable idempotent POST + scoped readback.
 if(attempt>1){
  const existing=await read();
  if(existing.status!==404)return validateReceipt(await readJson(existing),target,event,hash);
  await existing.body?.cancel();
 }
 const response=await fetchImpl(target.origin+target.writePath,{
  method:'POST',headers:{authorization:'Bearer '+env[target.writeSecret],'content-type':'application/json',
   accept:'application/json','idempotency-key':event.event_id},body:stable(event),redirect:'error',signal});
 const accepted=await readJson(response);
 const qa=target.kind==='QA_RECIPIENT_V1';
 if(accepted.schema!==(qa?'hara.commander.review163.recipient-accepted.v1':'hara.commander.recovery-recipient.v1')||
    accepted.state!==(qa?'QA_RECIPIENT_PERSISTED':'RECIPIENT_PERSISTED')||accepted.event_id!==event.event_id||
    !/^[A-Za-z0-9_.:-]{1,160}$/.test(accepted.receipt_ref||''))throw Error('RECIPIENT_RECEIPT_INVALID');
 if(!qa)validateReceipt(accepted,target,event,hash);
 return validateReceipt(await readJson(await read()),target,event,hash,accepted.receipt_ref);
}
// Metadata-only scheduling for an explicitly admitted Queue binding. Native
// claims and live enrollment fences remain in dispatchRecoveryDeliveries.
export async function listRecoveryDeliveryCandidates(env,{nowMs=Date.now(),limit=500,after=null}={}){
 if(env?.COMMANDER_RECOVERY_DELIVERY_ENABLED!=='true')return {state:'DISABLED',rows:[]};
 let targets;try{targets=targetsFor(env);}catch{return {state:'HOLD_RECOVERY_TARGET_CONFIG',rows:[]};}
 if(!Number.isSafeInteger(nowMs)||nowMs<0||!Number.isSafeInteger(limit)||limit<1||limit>500||
    (after&&(typeof after.event_id!=='string'||!/^HARA-REC-[0-9a-f]{48}$/.test(after.event_id)||
      !Number.isFinite(Date.parse(after.persisted_at_utc)))))throw Error('RECOVERY_DELIVERY_BUDGET_INVALID');
 const admitted=prodCanaryDeviceIds(env);
 if(admitted!==null&&!admitted.length)return {state:'COMPLETE',rows:[]};
 const scope=admitted===null?'':` AND r.device_id IN (${admitted.map(()=>'?').join(',')})`;
 const cursor=after?' AND (r.persisted_at_utc>? OR (r.persisted_at_utc=? AND r.event_id>?))':'';
 const rows=await env.PRODUCT_DB.prepare(`WITH targets(tenant_id,binding_id,kind) AS
   (VALUES ${targets.map(()=>'(?,?,?)').join(',')})
  SELECT r.event_id,r.persisted_at_utc FROM commander_device_recovery_events r
  JOIN targets t ON t.tenant_id=r.tenant_id
  JOIN commander_devices d ON d.device_id=r.device_id AND d.tenant_id=r.tenant_id
  LEFT JOIN recovery_delivery_outbox o ON o.event_id=r.event_id AND o.binding_id=t.binding_id AND o.tenant_id=r.tenant_id
  WHERE d.state='ACTIVE' AND d.revoked_at_utc IS NULL
   AND (t.kind<>'QA_RECIPIENT_V1' OR (r.origin='AGENT' AND r.client_event_id IS NOT NULL AND r.incident_id LIKE 'agent-%'))
   AND (o.event_id IS NULL OR (o.attempts<8 AND
    ((o.state IN ('PENDING','RETRY') AND o.next_attempt_ms<=?) OR (o.state='INFLIGHT' AND o.lease_until_ms<=?))))
   ${scope}${cursor} ORDER BY r.persisted_at_utc,r.event_id LIMIT ?`)
  .bind(...targets.flatMap(t=>[t.tenant_id,t.id,t.kind]),nowMs,nowMs,...(admitted||[]),
    ...(after?[after.persisted_at_utc,after.persisted_at_utc,after.event_id]:[]),limit).all();
 return {state:'COMPLETE',rows:rows.results||[]};
}
export async function dispatchRecoveryDeliveries(env,{fetchImpl=fetch,nowMs=Date.now(),maxEvents=10,timeoutMs=5000,eventIds,exclusiveDeviceLeases=false}={}){
 const summary={state:'DISABLED',staged:0,attempted:0,delivered:0,held:0,exhausted:0};
 if(env?.COMMANDER_RECOVERY_DELIVERY_ENABLED!=='true')return summary;
 let targets;
 try{targets=targetsFor(env);}catch{return {...summary,state:'HOLD_RECOVERY_TARGET_CONFIG'};}
 // An internal QA/job selection is a restriction, never a new authority. Keep
 // canonical predecessor fences even when a predecessor is outside this list.
 if(eventIds!==undefined&&(!Array.isArray(eventIds)||!eventIds.length||eventIds.length>10||
    eventIds.some(id=>typeof id!=='string'||!/^HARA-REC-[0-9a-f]{48}$/.test(id))||
    new Set(eventIds).size!==eventIds.length))throw Error('RECOVERY_DELIVERY_SCOPE_INVALID');
 const scope=eventIds||[],scopeClause=alias=>scope.length?` AND ${alias}event_id IN (${scope.map(()=>'?').join(',')})`:'';
 if(!Number.isSafeInteger(nowMs)||nowMs<0||!Number.isSafeInteger(maxEvents)||maxEvents<1||maxEvents>10||
    !Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>5000)throw Error('RECOVERY_DELIVERY_BUDGET_INVALID');
 summary.state='COMPLETE';const start=performance.now();
 const clock=()=>exclusiveDeviceLeases?nowMs+Math.floor(performance.now()-start):nowMs;
 for(const target of targets){
  if(summary.attempted>=maxEvents||performance.now()-start>=20000)break;
  // Stage only matching, live enrollments. No callback-supplied tenant or URL.
  const candidates=await env.PRODUCT_DB.prepare(`SELECT r.* FROM commander_device_recovery_events r
   JOIN commander_devices d ON d.device_id=r.device_id AND d.tenant_id=r.tenant_id
   WHERE r.tenant_id=? AND d.state='ACTIVE' AND d.revoked_at_utc IS NULL
    AND NOT EXISTS(SELECT 1 FROM recovery_delivery_outbox o WHERE o.event_id=r.event_id AND o.binding_id=?)${scopeClause('r.')}
   ORDER BY r.persisted_at_utc,r.device_id,r.incident_id,r.generation,r.sequence,r.event_id LIMIT ?`).bind(target.tenant_id,target.id,...scope,maxEvents).all();
  for(const row of candidates.results||[]){
   if(!recoveryDeviceEnabled(env,row)||!envelope(row,target)){summary.held++;continue;}
   const inserted=await env.PRODUCT_DB.prepare(`INSERT OR IGNORE INTO recovery_delivery_outbox
    (event_id,binding_id,tenant_id,state) VALUES(?,?,?,'PENDING')`).bind(row.event_id,target.id,target.tenant_id).run();
   summary.staged+=Number(inserted.meta?.changes||0);
  }
  await env.PRODUCT_DB.prepare(`UPDATE recovery_delivery_outbox SET state='EXHAUSTED',lease_until_ms=0
   WHERE binding_id=? AND tenant_id=? AND state='INFLIGHT' AND attempts>=8 AND lease_until_ms<=?${scopeClause('')}`).bind(target.id,target.tenant_id,nowMs,...scope).run();
  while(summary.attempted<maxEvents&&performance.now()-start<20000){
   const row=await env.PRODUCT_DB.prepare(`UPDATE recovery_delivery_outbox SET state='INFLIGHT',attempts=attempts+1,lease_until_ms=?
    WHERE event_id=(SELECT o.event_id FROM recovery_delivery_outbox o
     JOIN commander_device_recovery_events r ON r.event_id=o.event_id AND r.tenant_id=o.tenant_id
     JOIN commander_devices d ON d.device_id=r.device_id AND d.tenant_id=r.tenant_id
     WHERE o.binding_id=? AND o.tenant_id=? AND o.attempts<8 AND d.state='ACTIVE' AND d.revoked_at_utc IS NULL
      AND ((o.state IN ('PENDING','RETRY') AND o.next_attempt_ms<=?) OR (o.state='INFLIGHT' AND o.lease_until_ms<=?))${scopeClause('o.')}
      AND NOT EXISTS(SELECT 1 FROM commander_device_recovery_events pr
       LEFT JOIN recovery_delivery_outbox p ON p.event_id=pr.event_id AND p.binding_id=o.binding_id AND p.tenant_id=o.tenant_id
       WHERE pr.tenant_id=r.tenant_id AND pr.device_id=r.device_id AND pr.incident_id=r.incident_id
        AND pr.generation=r.generation AND pr.sequence<r.sequence AND COALESCE(p.state,'MISSING')<>'DELIVERED')
     ORDER BY r.persisted_at_utc,r.event_id LIMIT 1) AND binding_id=? AND tenant_id=? RETURNING *`)
    .bind(clock()+timeoutMs+10000,target.id,target.tenant_id,clock(),clock(),...scope,target.id,target.tenant_id).first();
   if(!row)break;
   summary.attempted++;
   const source=await env.PRODUCT_DB.prepare(`SELECT r.*,d.state AS device_state,d.revoked_at_utc FROM commander_device_recovery_events r
    JOIN commander_devices d ON d.device_id=r.device_id AND d.tenant_id=r.tenant_id WHERE r.event_id=? AND r.tenant_id=?`)
    .bind(row.event_id,target.tenant_id).first();
   let state='RETRY',receipt=null,deviceLease=null;const controller=new AbortController();let timer;
   try{
    if(!source||source.device_state!=='ACTIVE'||source.revoked_at_utc||!recoveryDeviceEnabled(env,source))throw Error('RECOVERY_DEVICE_NOT_ACTIVE');
    if(exclusiveDeviceLeases){
     deviceLease=await claimRecoveryDeviceLease(env,source,clock());
     if(!deviceLease)throw Error('RECOVERY_DEVICE_LEASE_HELD');
    }
    const body=envelope(source,target);if(!body)throw Error('RECOVERY_RECEIVER_UNSUPPORTED');
    receipt=await Promise.race([deliver(env,target,body,fetchImpl,controller.signal,row.attempts),
     new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error('RECIPIENT_TIMEOUT'));},timeoutMs);})]);
    state='DELIVERED';
   }catch{state=row.attempts>=8?'EXHAUSTED':'RETRY';summary.held++;}
   finally{clearTimeout(timer);controller.abort();}
   const next=nowMs+Math.min(3600000,5000*2**Math.min(16,row.attempts-1));
   const result=await env.PRODUCT_DB.prepare(`UPDATE recovery_delivery_outbox SET state=?,next_attempt_ms=?,lease_until_ms=0,receipt_ref=?,receipt_sha256=?
    WHERE event_id=? AND binding_id=? AND tenant_id=? AND state='INFLIGHT' AND attempts=?${deviceLease?
     ` AND EXISTS(SELECT 1 FROM recovery_device_leases l JOIN commander_devices d ON d.device_id=l.device_id AND d.tenant_id=l.tenant_id WHERE l.device_id=? AND l.tenant_id=? AND l.lease_token=? AND l.lease_until_ms>? AND d.state='ACTIVE' AND d.revoked_at_utc IS NULL)`:''}`)
    .bind(state,next,state==='DELIVERED'?receipt.receipt_ref:null,state==='DELIVERED'?await sha(stable(receipt)):null,
     row.event_id,target.id,target.tenant_id,row.attempts,
     ...(deviceLease?[deviceLease.device_id,deviceLease.tenant_id,deviceLease.lease_token,clock()]:[])).run();
   if(exclusiveDeviceLeases&&!result.meta?.changes)summary.held++;
   if(deviceLease)await releaseRecoveryDeviceLease(env,deviceLease);
   if(result.meta?.changes&&state==='DELIVERED')summary.delivered++;
   if(state==='EXHAUSTED')summary.exhausted++;
  }
 }
 if(summary.held)summary.state='PARTIAL';
 return summary;
}
