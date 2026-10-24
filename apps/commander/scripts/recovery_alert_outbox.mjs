/** Agent ingestion and recipient delivery have separate terminal receipts.
 * /api/portal/slo/ack is never a delivery receipt.
 * Store interface: async run(sql,args)->{changes}, first(sql,args)->row|null.
 * The owner must decide whether to extend the SLO subsystem or admit another
 * sink, then bind an idempotent sender and a verifier of actual delivery.
 */
export const HOLD_REMOTE_ALERT_OWNER_163='HOLD_REMOTE_ALERT_OWNER_163';
export const SOURCE_CONTRACT=Object.freeze({
 status:'SOURCE_IMPLEMENTED_INGEST_CONTRACT_R163',
 ingestRoute:'/api/device/recovery-events',ingestAck:'PERSISTED',
 owner:'https://github.com/tiagoharalabs/hara-site/issues/163',
 existingIncidentMigrations:['0026_slo_incidents.sql','0027_slo_incident_ack_escalation.sql'],
 externalTransportBound:false,humanIncidentAckIsDeliveryAck:false,
 hourlySloMonitorIsRecoveryDetector:false,serverIncidentIdentityInvented:false,
});
const FIELDS=['schema','event_id','client_incident_key','transition_seq','worker','state','observed_at_utc','detector'];
async function validate(event){
 if(!event || Object.keys(event).sort().join('\0')!==[...FIELDS].sort().join('\0'))throw Error('ALERT_METADATA_DENIED');
 if(event.schema!=='hara.commander.recovery-alert.proposal.v1' || !/^[0-9a-f]{32}$/.test(event.event_id) ||
    !/^[0-9a-f]{32}$/.test(event.client_incident_key) || !Number.isSafeInteger(event.transition_seq) ||
    event.transition_seq<1 || event.transition_seq>2147483647 || !['heartbeat','executor'].includes(event.worker) ||
    !['STALLED','RECOVERING','RECOVERED','DEGRADED'].includes(event.state) ||
    !['LINUX_PROCESS_GUARDIAN','WINDOWS_JOB_GUARDIAN'].includes(event.detector) ||
    !Number.isFinite(Date.parse(event.observed_at_utc)) || new Date(event.observed_at_utc).toISOString()!==event.observed_at_utc)throw Error('ALERT_METADATA_DENIED');
 const body=JSON.stringify(Object.fromEntries(Object.keys(event).sort().map(key=>[key,event[key]])));
 if(new TextEncoder().encode(body).byteLength>2048)throw Error('ALERT_METADATA_DENIED');
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body));
 return {body,fingerprint:Array.from(new Uint8Array(hash),x=>x.toString(16).padStart(2,'0')).join('')};
}
function deliveryMatches(row,receipt){
 return receipt?.kind==='DELIVERY_CONFIRMED' && receipt.eventId===row.event_id &&
   typeof receipt.receiptRef==='string' && receipt.receiptRef.length>0 && receipt.receiptRef.length<=512;
}
export class RecoveryAlertOutbox {
 constructor(store,policy={}){
  this.store=store;
  this.policy={timeoutMs:10000,leaseMs:15000,retryBaseMs:5000,retryCapMs:300000,maxAttempts:8,random:Math.random,...policy};
  const p=this.policy;
  if(![p.timeoutMs,p.leaseMs,p.retryBaseMs,p.retryCapMs,p.maxAttempts].every(x=>Number.isSafeInteger(x)&&x>0) ||
     p.leaseMs<=p.timeoutMs || p.retryCapMs<p.retryBaseMs || p.maxAttempts>32)throw Error('ALERT_RETRY_POLICY_INVALID');
 }
 async initialize(){
  // Initialization is explicit, on the injected private/test store only. There
  // is no D1 migration runner or import into the deployed Worker in this patch.
  await this.store.run(`CREATE TABLE IF NOT EXISTS commander_recovery_delivery_outbox (
   event_id TEXT PRIMARY KEY, client_incident_key TEXT NOT NULL, transition_seq INTEGER NOT NULL,
   fingerprint TEXT NOT NULL, body_json TEXT NOT NULL, state TEXT NOT NULL,
   attempts INTEGER NOT NULL DEFAULT 0, lease_until_ms INTEGER NOT NULL DEFAULT 0,
   next_attempt_ms INTEGER NOT NULL DEFAULT 0, receipt_ref TEXT,
   UNIQUE(client_incident_key,transition_seq))`);
 }
 async inspect(eventId){return this.store.first('SELECT * FROM commander_recovery_delivery_outbox WHERE event_id=?',[eventId]);}
 async enqueue(event){
  const {body,fingerprint}=await validate(event);
  const prior=await this.store.first('SELECT * FROM commander_recovery_delivery_outbox WHERE event_id=? OR (client_incident_key=? AND transition_seq=?)',
   [event.event_id,event.client_incident_key,event.transition_seq]);
  if(prior){if(prior.event_id!==event.event_id || prior.fingerprint!==fingerprint)throw Error('ALERT_IDEMPOTENCY_CONFLICT');return prior;}
  const maximum=await this.store.first('SELECT COALESCE(MAX(transition_seq),0) AS n FROM commander_recovery_delivery_outbox WHERE client_incident_key=?',[event.client_incident_key]);
  if(event.transition_seq!==Number(maximum.n)+1)throw Error('ALERT_SEQUENCE_GAP');
  await this.store.run(`INSERT OR IGNORE INTO commander_recovery_delivery_outbox
   (event_id,client_incident_key,transition_seq,fingerprint,body_json,state) VALUES(?,?,?,?,?,'PENDING_TRANSPORT')`,
   [event.event_id,event.client_incident_key,event.transition_seq,fingerprint,body]);
  const saved=await this.store.first('SELECT * FROM commander_recovery_delivery_outbox WHERE event_id=? OR (client_incident_key=? AND transition_seq=?)',
   [event.event_id,event.client_incident_key,event.transition_seq]);
  if(!saved || saved.event_id!==event.event_id || saved.fingerprint!==fingerprint)throw Error('ALERT_IDEMPOTENCY_CONFLICT');
  return saved;
 }
 async claim(nowMs,ingest=false){
  if(!Number.isSafeInteger(nowMs)||nowMs<0)throw Error('ALERT_CLOCK_INVALID');
  await this.store.run(`UPDATE commander_recovery_delivery_outbox SET state='EXHAUSTED',lease_until_ms=0
   WHERE state='INFLIGHT' AND lease_until_ms<=? AND attempts>=?`,[nowMs,this.policy.maxAttempts]);
  return this.store.first(`UPDATE commander_recovery_delivery_outbox SET state='INFLIGHT',attempts=attempts+1,lease_until_ms=?
   WHERE event_id=(SELECT current.event_id FROM commander_recovery_delivery_outbox current
    WHERE current.attempts<? AND ((current.state IN ('PENDING_TRANSPORT','RETRY') AND current.next_attempt_ms<=?)
        OR (current.state='INFLIGHT' AND current.lease_until_ms<=?))
      AND NOT EXISTS (SELECT 1 FROM commander_recovery_delivery_outbox previous
       WHERE previous.client_incident_key=current.client_incident_key
         AND previous.transition_seq<current.transition_seq AND ${ingest?"previous.state NOT IN ('PERSISTED','DELIVERED')":"previous.state<>'DELIVERED'"})
    ORDER BY current.next_attempt_ms,current.client_incident_key,current.transition_seq LIMIT 1)
   RETURNING *`,[nowMs+this.policy.leaseMs,this.policy.maxAttempts,nowMs,nowMs]);
 }
 async confirm(row,receipt){
  if(!deliveryMatches(row,receipt))return false;
  const result=await this.store.run(`UPDATE commander_recovery_delivery_outbox SET state='DELIVERED',receipt_ref=?,lease_until_ms=0
   WHERE event_id=? AND state='INFLIGHT' AND attempts=?`,[receipt.receiptRef,row.event_id,row.attempts]);
  return Number(result.changes)===1;
 }
 async dispatchIngest(options={}){return this._dispatch({...options,ingest:true});}
 async dispatch(options={}){return this._dispatch({...options,ingest:false});}
 async _dispatch({send,verifyReceipt,nowMs=Date.now(),ingest=false}={}){
  // Absence of either owner-supplied operation is a scoped HOLD, never a fake
  // acceptance boolean, guessed endpoint, human acknowledgement or local ACK.
  if(typeof send!=='function'||(!ingest&&typeof verifyReceipt!=='function'))return {state:HOLD_REMOTE_ALERT_OWNER_163};
  const row=await this.claim(nowMs,ingest);if(!row)return {state:'EMPTY'};
  const controller=new AbortController();let timer;
  try {
   const delivery=(async()=>{
    const event=JSON.parse(row.body_json);
    const response=await send(event,{idempotencyKey:row.event_id,attempt:row.attempts,signal:controller.signal});
    if(!ingest)return verifyReceipt(event,response);
    if(response?.schema!=='hara.commander.recovery-ingest.v1'||response.ack!=='PERSISTED'||
       response.client_event_id!==event.event_id||response.external_delivery_confirmed!==false||
       !/^HARA-REC-[0-9a-f]{48}$/.test(response.event_id||''))throw Error('ALERT_PERSISTENCE_NOT_CONFIRMED');
    return {kind:'PERSISTED',eventId:event.event_id,receiptRef:response.event_id};
   })();
   const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error('ALERT_DELIVERY_TIMEOUT'));},this.policy.timeoutMs);});
   const receipt=await Promise.race([delivery,timeout]);
   if(ingest){
    const result=await this.store.run(`UPDATE commander_recovery_delivery_outbox SET state='PERSISTED',receipt_ref=?,lease_until_ms=0
     WHERE event_id=? AND state='INFLIGHT' AND attempts=?`,[receipt.receiptRef,row.event_id,row.attempts]);
    return {state:Number(result.changes)===1?'PERSISTED':'STALE_ATTEMPT',eventId:row.event_id};
   }
   if(!deliveryMatches(row,receipt))throw Error('ALERT_DELIVERY_NOT_CONFIRMED');
   if(!await this.confirm(row,receipt))return {state:'STALE_ATTEMPT',eventId:row.event_id};
   return {state:'DELIVERED',eventId:row.event_id,receiptRef:receipt.receiptRef};
  } catch {
   const exhausted=row.attempts>=this.policy.maxAttempts;
   const jitter=Math.max(0,Math.min(1,Number(this.policy.random())));
   const backoff=Math.min(this.policy.retryCapMs,this.policy.retryBaseMs*2**Math.min(30,row.attempts-1));
   const state=exhausted?'EXHAUSTED':'RETRY';
   const result=await this.store.run(`UPDATE commander_recovery_delivery_outbox SET state=?,next_attempt_ms=?,lease_until_ms=0
    WHERE event_id=? AND state='INFLIGHT' AND attempts=?`,[state,nowMs+Math.ceil(backoff*(1+jitter*.2)),row.event_id,row.attempts]);
   return {state:Number(result.changes)===1?state:'STALE_ATTEMPT',eventId:row.event_id};
  } finally {clearTimeout(timer);}
 }
}
