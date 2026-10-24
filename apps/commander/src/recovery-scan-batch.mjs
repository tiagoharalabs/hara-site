import {boundedRecoveryMap} from './recovery-scan-leases.mjs';
// SQL JSON values are built only from freshly selected enrollments and server
// digests. A Queue body never supplies tenant, heartbeat, lease or event content.
// Three bounded SQL transactions replace per-device durable commits. Every row
// still has an exclusive random token and an atomic live-enrollment write fence.
const EPOCH="CAST((julianday('now')-2440587.5)*86400000 AS INTEGER)";
export async function recordOfflineRecoveryBatch(env,rows,nowMs,prepare){
 const concurrency=Number(env.COMMANDER_RECOVERY_SCAN_CONCURRENCY||1);
 if(![1,2,4].includes(concurrency))throw Error('RECOVERY_SCAN_CONCURRENCY_INVALID');
 if(!rows.length)return {checked:0,persisted:0,held:0,exhausted:0,bounded:true,concurrency};
 if(rows.length>96)throw Error('RECOVERY_SCAN_BATCH_INVALID');
 const input=rows.map(d=>({device_id:d.device_id,tenant_id:d.tenant_id,token:crypto.randomUUID()}));
 const claimed=await env.PRODUCT_DB.prepare(`INSERT INTO recovery_device_leases(device_id,tenant_id,lease_token,lease_until_ms)
  SELECT d.device_id,d.tenant_id,json_extract(j.value,'$.token'),${EPOCH}+30000 FROM json_each(?) j
  CROSS JOIN commander_devices d ON d.device_id=json_extract(j.value,'$.device_id') AND d.tenant_id=json_extract(j.value,'$.tenant_id')
  WHERE d.state='ACTIVE' AND d.revoked_at_utc IS NULL
  ON CONFLICT(device_id) DO UPDATE SET tenant_id=excluded.tenant_id,lease_token=excluded.lease_token,lease_until_ms=excluded.lease_until_ms
  WHERE recovery_device_leases.lease_until_ms<=${EPOCH} RETURNING *`).bind(JSON.stringify(input)).all();
 const leases=claimed.results||[],byId=new Map(rows.map(d=>[d.device_id,d]));
 let persisted=0,held=rows.length-leases.length;
 try{
  const records=await boundedRecoveryMap(leases,concurrency,async lease=>({
   ...await prepare(byId.get(lease.device_id)),token:lease.lease_token
  }));
  if(records.length){
   const payload=JSON.stringify(records);
   const result=await env.PRODUCT_DB.prepare(`INSERT INTO commander_device_recovery_events
    (event_id,tenant_id,device_id,incident_id,generation,sequence,event_state,origin,error_code,event_at_utc,
     heartbeat_anchor_at_utc,payload_sha256,persisted_at_utc)
    SELECT json_extract(j.value,'$.event_id'),d.tenant_id,d.device_id,json_extract(j.value,'$.incident_id'),
     1,1,'DEGRADED','SERVER','HEARTBEAT_STALE',json_extract(j.value,'$.at_utc'),
     json_extract(j.value,'$.anchor'),json_extract(j.value,'$.fingerprint'),?
    FROM json_each(?) j CROSS JOIN commander_devices d ON d.device_id=json_extract(j.value,'$.device_id')
     AND d.tenant_id=json_extract(j.value,'$.tenant_id')
    CROSS JOIN recovery_device_leases l ON l.device_id=d.device_id AND l.tenant_id=d.tenant_id
     AND l.lease_token=json_extract(j.value,'$.token') AND l.lease_until_ms>${EPOCH}
    WHERE d.state='ACTIVE' AND d.revoked_at_utc IS NULL AND d.approval_mode='PERSISTENT_TRUSTED'
     AND d.tunnel_mode='OUTBOUND_RELAY' AND d.last_seen_at_utc=json_extract(j.value,'$.anchor')
     AND NOT EXISTS(SELECT 1 FROM commander_device_recovery_events r WHERE r.tenant_id=d.tenant_id
      AND r.device_id=d.device_id AND r.incident_id=json_extract(j.value,'$.incident_id'))
    ON CONFLICT DO NOTHING`).bind(new Date(nowMs).toISOString(),payload).run();
   persisted=Number(result.meta?.changes||0);
   // A changed heartbeat/revocation is an intentional skip. A still-eligible
   // enrollment lacking the exact durable event means lost lease or conflict;
   // it must retry rather than being silently acknowledged.
   const unresolved=await env.PRODUCT_DB.prepare(`SELECT d.device_id FROM json_each(?) j
    CROSS JOIN commander_devices d ON d.device_id=json_extract(j.value,'$.device_id') AND d.tenant_id=json_extract(j.value,'$.tenant_id')
    WHERE d.state='ACTIVE' AND d.revoked_at_utc IS NULL AND d.approval_mode='PERSISTENT_TRUSTED'
     AND d.tunnel_mode='OUTBOUND_RELAY' AND d.last_seen_at_utc=json_extract(j.value,'$.anchor')
     AND NOT EXISTS(SELECT 1 FROM commander_device_recovery_events r WHERE r.event_id=json_extract(j.value,'$.event_id')
      AND r.tenant_id=d.tenant_id AND r.device_id=d.device_id AND r.payload_sha256=json_extract(j.value,'$.fingerprint'))`)
    .bind(payload).all();
   held+=(unresolved.results||[]).length;
  }
 }finally{
  if(leases.length)await env.PRODUCT_DB.prepare(`DELETE FROM recovery_device_leases WHERE rowid IN(
   SELECT l.rowid FROM json_each(?) j CROSS JOIN recovery_device_leases l ON l.device_id=json_extract(j.value,'$.device_id')
    AND l.tenant_id=json_extract(j.value,'$.tenant_id') AND l.lease_token=json_extract(j.value,'$.lease_token'))`)
   .bind(JSON.stringify(leases)).run();
 }
 return {schema:'hara.commander.recovery-offline-scan.v1',checked:rows.length,persisted,held,exhausted:0,bounded:true,concurrency,batched:true};
}
