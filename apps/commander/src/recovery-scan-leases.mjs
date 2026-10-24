// One exclusive, expiring enrollment lease. A random attempt token is also the
// write fence: a crashed/late attempt cannot release or commit over its successor.
export function recoveryPartition(id){
 let hash=2166136261;for(const c of id)hash=Math.imul(hash^c.charCodeAt(0),16777619);
 return (hash>>>0)%16;
}
export async function boundedRecoveryMap(items,concurrency,fn){
 if(![1,2,4].includes(concurrency))throw Error('RECOVERY_SCAN_CONCURRENCY_INVALID');
 const results=new Array(items.length);let cursor=0,failure;
 await Promise.all(Array.from({length:Math.min(items.length,concurrency)},async()=>{
  while(!failure&&cursor<items.length){
   const index=cursor++;
   try{results[index]=await fn(items[index],index);}catch(error){failure??=error;}
  }
 }));
 if(failure)throw failure;return results;
}
export async function claimRecoveryDeviceLease(env,device,nowMs){
 const token=crypto.randomUUID();
 return await env.PRODUCT_DB.prepare(`INSERT INTO recovery_device_leases(device_id,tenant_id,lease_token,lease_until_ms)
  SELECT device_id,tenant_id,?,? FROM commander_devices
  WHERE device_id=? AND tenant_id=? AND state='ACTIVE' AND revoked_at_utc IS NULL
  ON CONFLICT(device_id) DO UPDATE SET tenant_id=excluded.tenant_id,lease_token=excluded.lease_token,lease_until_ms=excluded.lease_until_ms
  WHERE recovery_device_leases.lease_until_ms<=?
  RETURNING device_id,tenant_id,lease_token,lease_until_ms`)
  .bind(token,nowMs+30000,device.device_id,device.tenant_id,nowMs).first();
}
export async function releaseRecoveryDeviceLease(env,lease){
 const r=await env.PRODUCT_DB.prepare(`DELETE FROM recovery_device_leases
  WHERE device_id=? AND tenant_id=? AND lease_token=?`)
  .bind(lease.device_id,lease.tenant_id,lease.lease_token).run();
 return Boolean(r.meta?.changes);
}
