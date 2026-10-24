import {recordOfflineRecoveryBatch} from './recovery-scan-batch.mjs';
import {boundedRecoveryMap,claimRecoveryDeviceLease,releaseRecoveryDeviceLease} from './recovery-scan-leases.mjs';
// H.A.R.A. Commander recovery inbox: source-only, default OFF.
// PERSISTED is a durable D1 receipt; PORTAL_ACKNOWLEDGED is a human action.
// Neither is proof of external push/email delivery. No bearer token is logged.
const STATES = new Set(["STALLED","RECOVERING","RECOVERED","DEGRADED"]);
const SCHEMA = "hara.commander.recovery-event.v1";
const MAX_EVENT_BODY = 2048;
const MAX_EVENT_AGE_MS = 7 * 86400000;
const STALE_AFTER_MS = 120000;
const RETENTION_MS = 90 * 86400000;
const FIELDS = new Set(["schema","incident_id","generation","sequence","state","at_utc","error_code"]);

function deny(code) { throw new Error(code); }
export function recoveryAlertsEnabled(env) {
  return env?.COMMANDER_RECOVERY_ALERTS_ENABLED === "true";
}
// Fail closed in PROD: a recovery watcher may process only explicitly listed,
// HARA-owned canary devices. Broader 20k acceptance is a separate #163 gate.
export function prodCanaryDeviceIds(env) {
  if (env?.ENVIRONMENT!=="PROD") return null;
  const raw=env.COMMANDER_RECOVERY_ALERTS_PROD_CANARY_DEVICE_IDS;
  if (typeof raw!=="string" || !raw || raw.length>2048) return [];
  const list=raw.split(",").map(x=>x.trim());
  if (!list.length || list.length>16
      || list.some(x=>!/^HARA-DEVICE-[0-9a-fA-F-]{36}$/.test(x))
      || new Set(list).size!==list.length) return [];
  return list;
}
export function recoveryDeviceEnabled(env,device) {
  if (!recoveryAlertsEnabled(env)) return false;
  const allowed=prodCanaryDeviceIds(env);
  return allowed===null || Boolean(device && allowed.includes(device.device_id));
}
function requireEnabled(env) {
  if (!recoveryAlertsEnabled(env)) deny("RECOVERY_ALERTS_DISABLED");
}
function validIdentity(device) {
  if (!device || typeof device.tenant_id !== "string" || !device.tenant_id
      || typeof device.device_id !== "string" || !device.device_id
      || device.state !== "ACTIVE" || device.revoked_at_utc) {
    deny("DEVICE_AUTH_INVALID");
  }
}
function safeUtc(value, nowMs) {
  if (typeof value !== "string"
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)) {
    deny("RECOVERY_EVENT_TIME_INVALID");
  }
  const epoch=Date.parse(value);
  if (!Number.isFinite(epoch) || epoch > nowMs+300000 || epoch < nowMs-MAX_EVENT_AGE_MS) {
    deny("RECOVERY_EVENT_TIME_INVALID");
  }
  return new Date(epoch).toISOString();
}
function cleanEvent(body, nowMs=Date.now()) {
  if (!body || typeof body !== "object" || Array.isArray(body)
      || Object.keys(body).some(k=>!FIELDS.has(k))
      || body.schema !== SCHEMA
      || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,119}$/.test(body.incident_id || "")
      || !Number.isSafeInteger(body.generation) || body.generation < 1 || body.generation > 1000000
      || !Number.isSafeInteger(body.sequence) || body.sequence < 1 || body.sequence > 2147483647
      || !STATES.has(body.state)) deny("RECOVERY_EVENT_INVALID");
  const code=body.error_code === undefined || body.error_code === null ? null : body.error_code;
  if (code !== null && (typeof code !== "string"
      || !/^[A-Z][A-Z0-9_]{0,63}$/.test(code))) deny("RECOVERY_EVENT_INVALID");
  return {incident_id:body.incident_id, generation:body.generation,sequence:body.sequence,
    state:body.state,at_utc:safeUtc(body.at_utc,nowMs),error_code:code};
}
// Map the exact source-only Codex 0.3.56 outbox proposal envelope.
// Transport sends may be bound after review, but PERSISTED is NOT delivery.
const CODEX_OUTBOX_SCHEMA="hara.commander.recovery-alert.proposal.v1";
const CODEX_FIELDS=new Set(["schema","event_id","client_incident_key",
  "transition_seq","worker","state","observed_at_utc","detector"]);
function normalizeIncomingEvent(body,nowMs) {
  if (body?.schema!==CODEX_OUTBOX_SCHEMA) return cleanEvent(body,nowMs);
  if (!body || typeof body!=="object" || Array.isArray(body)
      || Object.keys(body).length!==CODEX_FIELDS.size
      || Object.keys(body).some(k=>!CODEX_FIELDS.has(k))
      || !/^[0-9a-f]{32}$/.test(body.event_id||"")
      || !/^[0-9a-f]{32}$/.test(body.client_incident_key||"")
      || !Number.isSafeInteger(body.transition_seq)
      || body.transition_seq<1 || body.transition_seq>2147483647
      || !["heartbeat","executor"].includes(body.worker)
      || !["LINUX_PROCESS_GUARDIAN","WINDOWS_JOB_GUARDIAN"].includes(body.detector)
      || !STATES.has(body.state)) deny("RECOVERY_EVENT_INVALID");
  // Server scope comes exclusively from resolveDeviceCredential; the outbox
  // proposal itself deliberately carries no tenant or device claim.
  const core=cleanEvent({
    schema:SCHEMA,
    incident_id:"agent-"+body.client_incident_key,
    generation:1,sequence:body.transition_seq,state:body.state,
    at_utc:body.observed_at_utc
  },nowMs);
  return {...core,client_event_id:body.event_id,worker:body.worker,detector:body.detector};
}
async function sha(input) {
  const buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf),b=>b.toString(16).padStart(2,"0")).join("");
}
async function incidentForHeartbeat(device) {
  return "offline-"+(await sha(JSON.stringify([device.tenant_id,device.device_id,device.last_seen_at_utc]))).slice(0,40);
}
async function persist(env,device,event,origin="AGENT",anchor=null,nowMs=Date.now(),lease=null) {
  requireEnabled(env); validIdentity(device);
  if (!recoveryDeviceEnabled(env,device)) deny("RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  const now=new Date(nowMs).toISOString();
  const fingerprint=await sha(JSON.stringify([event.incident_id,event.generation,event.sequence,
    event.state,event.at_utc,event.error_code,origin,anchor,
    event.client_event_id||null,event.worker||null,event.detector||null]));
  const eventId="HARA-REC-"+(await sha(JSON.stringify([device.tenant_id,device.device_id,
    event.incident_id,event.generation,event.sequence]))).slice(0,48);
  // One conditional INSERT is the admission/ordering fence, even for concurrent claims.
  // It also rechecks the enrollment's live validity (and heartbeat anchor for server detection).
  const result=await env.PRODUCT_DB.prepare(
    "INSERT INTO commander_device_recovery_events "+
    "(event_id,tenant_id,device_id,incident_id,generation,sequence,event_state,origin,"+
    "client_event_id,worker,detector,error_code,event_at_utc,heartbeat_anchor_at_utc,payload_sha256,persisted_at_utc) "+
    "SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? FROM commander_devices d "+
    "WHERE d.device_id=? AND d.tenant_id=? AND d.state='ACTIVE' AND d.revoked_at_utc IS NULL "+
    "AND (?='AGENT' OR (d.approval_mode='PERSISTENT_TRUSTED' AND d.tunnel_mode='OUTBOUND_RELAY')) "+
    "AND (?!='SERVER' OR ?!='DEGRADED' OR d.last_seen_at_utc=?) "+
    // The very first transition must be 1. Subsequent transitions are
    // contiguous within the same incident generation, atomically with INSERT.
    "AND COALESCE((SELECT MAX(x.sequence) FROM commander_device_recovery_events x "+
    "WHERE x.tenant_id=d.tenant_id AND x.device_id=d.device_id "+
    "AND x.incident_id=? AND x.generation=?),0)=? "+
    "AND NOT EXISTS (SELECT 1 FROM commander_device_recovery_events r "+
    "WHERE r.tenant_id=d.tenant_id AND r.device_id=d.device_id AND r.incident_id=? "+
    "AND (r.generation>? OR (r.generation=? AND r.sequence>=?))) "+
    (lease?"AND EXISTS (SELECT 1 FROM recovery_device_leases l WHERE l.device_id=d.device_id AND l.tenant_id=d.tenant_id AND l.lease_token=? AND l.lease_until_ms>?) ":"")+
    "ON CONFLICT DO NOTHING"
  ).bind(eventId,device.tenant_id,device.device_id,event.incident_id,event.generation,
    event.sequence,event.state,origin,event.client_event_id||null,
    event.worker||null,event.detector||null,event.error_code,event.at_utc,anchor,fingerprint,now,
    device.device_id,device.tenant_id,origin,origin,event.state,anchor,
    event.incident_id,event.generation,event.sequence-1,
    event.incident_id,event.generation,event.generation,event.sequence,
    ...(lease?[lease.lease_token,nowMs]:[])).run();
  if (!result?.meta?.changes) {
    const current=await env.PRODUCT_DB.prepare(
      "SELECT state,revoked_at_utc FROM commander_devices WHERE device_id=? AND tenant_id=? LIMIT 1"
    ).bind(device.device_id,device.tenant_id).first();
    if (!current || current.state!=="ACTIVE" || current.revoked_at_utc) deny("DEVICE_AUTH_INVALID");
    const row=await env.PRODUCT_DB.prepare(
      "SELECT payload_sha256 FROM commander_device_recovery_events "+
      "WHERE event_id=? AND tenant_id=? AND device_id=? LIMIT 1"
    ).bind(eventId,device.tenant_id,device.device_id).first();
    if (!row && lease) {
      const held=await env.PRODUCT_DB.prepare("SELECT lease_token,lease_until_ms FROM recovery_device_leases WHERE device_id=? AND tenant_id=?")
        .bind(device.device_id,device.tenant_id).first();
      if(!held||held.lease_token!==lease.lease_token||held.lease_until_ms<=nowMs)deny("RECOVERY_DEVICE_LEASE_LOST");
    }
    if (!row) deny("RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER");
    if (row.payload_sha256!==fingerprint) deny("RECOVERY_EVENT_IDEMPOTENCY_CONFLICT");
  }
  return {schema:"hara.commander.recovery-ingest.v1",ack:"PERSISTED",
    event_id:eventId,client_event_id:event.client_event_id||null,
    duplicate:!Boolean(result?.meta?.changes),
    external_delivery_confirmed:false};
}
export async function readRecoveryEventBody(request,maxBytes=MAX_EVENT_BODY) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes<1 || maxBytes>MAX_EVENT_BODY) deny("RECOVERY_EVENT_INVALID");
  const declared=Number(request.headers.get("content-length") || 0);
  if (!Number.isFinite(declared) || declared>maxBytes) deny("RECOVERY_EVENT_BODY_TOO_LARGE");
  if (!request.body) deny("RECOVERY_EVENT_INVALID");
  const reader=request.body.getReader();
  let bytes=0;const chunks=[];
  try {
    while (true) {
      const next=await reader.read();
      if (next.done) break;
      bytes+=next.value.byteLength;
      if (bytes>maxBytes) deny("RECOVERY_EVENT_BODY_TOO_LARGE");
      chunks.push(next.value);
    }
  } finally {
    await reader.cancel().catch(()=>{});
  }
  const all=new Uint8Array(bytes);let cursor=0;
  for (const chunk of chunks) {all.set(chunk,cursor);cursor+=chunk.byteLength;}
  let obj;
  try {
    const raw=new TextDecoder("utf-8",{fatal:true}).decode(all);
    obj=JSON.parse(raw);
    // Flat, scalar-only envelope: any repeated key is ambiguous and must fail.
    const names=[...raw.matchAll(/"((?:[^"\\]|\\.)+)"\s*:/g)];
    if (names.length!==Object.keys(obj||{}).length) deny("RECOVERY_EVENT_INVALID");
  } catch (_error) { deny("RECOVERY_EVENT_INVALID"); }
  return obj;
}
export async function ingestRecoveryEvent(env,device,body,nowMs=Date.now()) {
  return persist(env,device,normalizeIncomingEvent(body,nowMs),"AGENT",null,nowMs);
}
function requirePortalAdmin(session) {
  if (!session) deny("AUTH_REQUIRED");
  if (!["OWNER","ADMIN"].includes(String(session.role||"").toUpperCase())) {
    deny("RECOVERY_ALERTS_ADMIN_REQUIRED");
  }
}
// A PROD rollout whitelists devices, not every customer's portal session.
 // Reject other tenants before reading the incident table so their portal
 // stops its polling after 403 and cannot expose/reconcile non-canary events.
async function portalCanaryScope(env,session) {
  const admitted=prodCanaryDeviceIds(env);
  if (admitted===null) return null;
  if (!admitted.length) deny("RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  const placeholders=admitted.map(()=>"?").join(",");
  const device=await env.PRODUCT_DB.prepare(
    "SELECT 1 AS admitted FROM commander_devices "+
    "WHERE tenant_id=? AND state='ACTIVE' AND revoked_at_utc IS NULL "+
    "AND device_id IN ("+placeholders+") LIMIT 1"
  ).bind(session.tenant_id,...admitted).first();
  if (!device) deny("RECOVERY_ALERTS_DEVICE_NOT_ADMITTED");
  return admitted;
}
export async function listRecoveryEvents(env,session,limit=20) {
  requireEnabled(env);requirePortalAdmin(session);
  if (!Number.isSafeInteger(limit) || limit<1 || limit>50) deny("RECOVERY_EVENT_LIMIT_INVALID");
  const scoped=await portalCanaryScope(env,session);
  const where=scoped===null?"":" AND device_id IN ("+scoped.map(()=>"?").join(",")+")";
  const res=await env.PRODUCT_DB.prepare(
    "SELECT event_id,device_id,incident_id,generation,sequence,event_state,origin,"+
    "client_event_id,worker,detector,error_code,"+
    "event_at_utc,persisted_at_utc,portal_ack_at_utc "+
    "FROM commander_device_recovery_events WHERE tenant_id=?"+where+" "+
    "ORDER BY persisted_at_utc DESC,event_id DESC LIMIT ?"
  ).bind(session.tenant_id,...(scoped||[]),limit).all();
  return {schema:"hara.commander.recovery-inbox.v1",
    events:res.results||[],external_delivery_confirmed:false};
}
export async function acknowledgeRecoveryEvent(env,session,body,nowMs=Date.now()) {
  requireEnabled(env);requirePortalAdmin(session);
  const id=body && typeof body==="object" && !Array.isArray(body)
    && Object.keys(body).length===1 ? body.event_id : null;
  if (typeof id!=="string" || !/^HARA-REC-[0-9a-f]{48}$/.test(id)) {
    deny("RECOVERY_EVENT_INVALID");
  }
  const scoped=await portalCanaryScope(env,session);
  const where=scoped===null?"":" AND device_id IN ("+scoped.map(()=>"?").join(",")+")";
  const now=new Date(nowMs).toISOString();
  await env.PRODUCT_DB.prepare(
    "UPDATE commander_device_recovery_events SET "+
    "portal_ack_at_utc=COALESCE(portal_ack_at_utc,?),"+
    "portal_ack_subject_id=COALESCE(portal_ack_subject_id,?) "+
    "WHERE event_id=? AND tenant_id=?"+where
  ).bind(now,session.subject_id,id,session.tenant_id,...(scoped||[])).run();
  const row=await env.PRODUCT_DB.prepare(
    "SELECT portal_ack_at_utc FROM commander_device_recovery_events "+
    "WHERE event_id=? AND tenant_id=?"+where+" LIMIT 1"
  ).bind(id,session.tenant_id,...(scoped||[])).first();
  if (!row) deny("RECOVERY_EVENT_NOT_FOUND");
  return {schema:"hara.commander.recovery-portal-ack.v1",
    ack:"PORTAL_ACKNOWLEDGED",event_id:id,acknowledged_at_utc:row.portal_ack_at_utc,
    external_delivery_confirmed:false};
}
// Server detector requires a separately scheduled 1-minute cron and owner approval.
// Only durable-trust outbound sessions are eligible. Manual stop/revoked/offline
// devices are excluded. A large-fleet detection SLO still requires a hosted proof.
export async function listOfflineRecoveryCandidates(env,nowMs=Date.now(),{limit=200,after=null,deviceIds}={}) {
  requireEnabled(env);
  if (!Number.isSafeInteger(limit) || limit<1 || limit>500) deny("RECOVERY_EVENT_LIMIT_INVALID");
  if (!Number.isSafeInteger(nowMs) || nowMs<0) deny("RECOVERY_EVENT_TIME_INVALID");
  if (deviceIds!==undefined && (!Array.isArray(deviceIds) || !deviceIds.length || deviceIds.length>96
      || new Set(deviceIds).size!==deviceIds.length
      || deviceIds.some(id=>typeof id!=="string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,179}$/.test(id)))) {
    deny("RECOVERY_DEVICE_SCOPE_INVALID");
  }
  if (after && (typeof after.device_id!=="string" || !Number.isFinite(Date.parse(after.last_seen_at_utc)))) {
    deny("RECOVERY_SCAN_CURSOR_INVALID");
  }
  const cutoff=new Date(nowMs-STALE_AFTER_MS).toISOString();
  const admitted=prodCanaryDeviceIds(env);
  // Intersect scopes before preparing SQL: 96 IDs plus a separate 16-ID PROD
  // whitelist would exceed D1's 100 bound parameters. Neither scope expands it.
  const scoped=deviceIds===undefined?admitted:
    (admitted===null?deviceIds:deviceIds.filter(id=>admitted.includes(id)));
  if (scoped!==null && !scoped.length) return [];
  const source=scoped===null?"commander_devices d":
    "(SELECT column1 AS device_id FROM (VALUES "+scoped.map(()=>"(?)").join(",")+")) selected CROSS JOIN commander_devices d ON d.device_id=selected.device_id";
  const cursorClause=after?"AND (d.last_seen_at_utc>? OR (d.last_seen_at_utc=? AND d.device_id>?)) ":"";
  if (1+(scoped||[]).length+(after?3:0)+1>100) deny("RECOVERY_SCAN_CURSOR_INVALID");
  const rows=await env.PRODUCT_DB.prepare(
    "SELECT d.device_id,d.tenant_id,d.state,d.revoked_at_utc,d.approval_mode,d.tunnel_mode,"+
    "d.last_seen_at_utc FROM "+source+" "+
    "WHERE d.state='ACTIVE' AND d.revoked_at_utc IS NULL "+
    "AND d.approval_mode='PERSISTENT_TRUSTED' AND d.tunnel_mode='OUTBOUND_RELAY' "+
    "AND d.last_seen_at_utc < ? AND d.last_seen_at_utc > d.created_at_utc "+
    cursorClause+
    "AND NOT EXISTS (SELECT 1 FROM commander_device_recovery_events r "+
    "WHERE r.device_id=d.device_id AND r.origin='SERVER' AND r.event_state='DEGRADED' "+
    "AND r.heartbeat_anchor_at_utc=d.last_seen_at_utc) "+
    "ORDER BY d.last_seen_at_utc,d.device_id LIMIT ?"
  ).bind(...(scoped||[]),cutoff,...(after?[after.last_seen_at_utc,after.last_seen_at_utc,after.device_id]:[]),limit).all();
  return rows.results||[];
}
async function recordOfflineCandidates(env,rows,nowMs,{leased=false}={}) {
  if(leased&&env.COMMANDER_RECOVERY_SCAN_BATCHED==='true'){
    return recordOfflineRecoveryBatch(env,rows,nowMs,async device=>{
      const incident=await incidentForHeartbeat(device),anchor=device.last_seen_at_utc;
      const at=new Date(Date.parse(anchor)+STALE_AFTER_MS).toISOString();
      return {device_id:device.device_id,tenant_id:device.tenant_id,anchor,incident_id:incident,at_utc:at,
        event_id:"HARA-REC-"+(await sha(JSON.stringify([device.tenant_id,device.device_id,incident,1,1]))).slice(0,48),
        fingerprint:await sha(JSON.stringify([incident,1,1,"DEGRADED",at,"HEARTBEAT_STALE","SERVER",anchor,null,null,null]))};
    });
  }
  let recorded=0,held=0;
  const started=performance.now(),clock=()=>nowMs+Math.floor(performance.now()-started);
  const concurrency=leased?Number(env.COMMANDER_RECOVERY_SCAN_CONCURRENCY||1):1;
  await boundedRecoveryMap(rows,concurrency,async device=>{
    const lease=leased?await claimRecoveryDeviceLease(env,device,clock()):null;
    if(leased&&!lease){held++;return;}
    try{
      const incident=await incidentForHeartbeat(device);
      const event={incident_id:incident,generation:1,sequence:1,state:"DEGRADED",
        at_utc:new Date(Date.parse(device.last_seen_at_utc)+STALE_AFTER_MS).toISOString(),
        error_code:"HEARTBEAT_STALE"};
      try {
        const ack=await persist(env,device,event,"SERVER",device.last_seen_at_utc,clock(),lease);
        if (!ack.duplicate) recorded++;
      } catch (error) {
        if (error.message!=="RECOVERY_EVENT_STALE_OR_OUT_OF_ORDER"
            && error.message!=="DEVICE_AUTH_INVALID") throw error;
      }
    }finally{if(lease)await releaseRecoveryDeviceLease(env,lease);}
  });
  return {schema:"hara.commander.recovery-offline-scan.v1",checked:rows.length,
    persisted:recorded,held,exhausted:0,bounded:true,concurrency};
}
export async function detectOfflineRecoveryEvents(env,nowMs=Date.now(),limit=200) {
  const rows=await listOfflineRecoveryCandidates(env,nowMs,{limit});
  const result=await recordOfflineCandidates(env,rows,nowMs);
  if (prodCanaryDeviceIds(env)?.length===0) result.canary_unconfigured=true;
  return result;
}
// One native queue message, with admission rechecked at consumption time. No
// queue payload may choose an enrollment's tenant, anchor or authorization.
export async function detectOfflineRecoveryDevices(env,deviceIds,nowMs=Date.now()) {
  const rows=await listOfflineRecoveryCandidates(env,nowMs,{limit:96,deviceIds});
  return recordOfflineCandidates(env,rows,nowMs,{leased:true});
}
export async function observeHeartbeatRecovery(env,device,nowMs=Date.now()) {
  if (!recoveryDeviceEnabled(env,device)) return null;
  if (!device?.last_seen_at_utc || device.approval_mode!=="PERSISTENT_TRUSTED"
      || device.tunnel_mode!=="OUTBOUND_RELAY"
      || Date.parse(device.last_seen_at_utc)>=nowMs-STALE_AFTER_MS) return null;
  const incident=await incidentForHeartbeat(device);
  const row=await env.PRODUCT_DB.prepare(
    "SELECT event_id FROM commander_device_recovery_events "+
    "WHERE device_id=? AND tenant_id=? AND incident_id=? AND origin='SERVER' "+
    "AND event_state='DEGRADED' LIMIT 1"
  ).bind(device.device_id,device.tenant_id,incident).first();
  if (!row) return null;
  return persist(env,device,{incident_id:incident,generation:1,sequence:2,
    state:"RECOVERED",at_utc:new Date(nowMs).toISOString(),error_code:null},
    "SERVER",device.last_seen_at_utc,nowMs);
}
export async function cleanupRecoveryEvents(env,nowMs=Date.now()) {
  if (!recoveryAlertsEnabled(env)) return {deleted:0};
  const cutoff=new Date(nowMs-RETENTION_MS).toISOString();
  const result=await env.PRODUCT_DB.prepare(
    "DELETE FROM commander_device_recovery_events WHERE event_id IN "+
    "(SELECT event_id FROM commander_device_recovery_events "+
    "WHERE persisted_at_utc<? ORDER BY persisted_at_utc LIMIT 500)"
  ).bind(cutoff).run();
  return {deleted:result.meta?.changes||0};
}
